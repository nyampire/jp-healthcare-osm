#!/usr/bin/env python3
"""出力した座標を、住所から求めた点と突き合わせて検算する。

入力 (output/):
  osm/<業態>/<業態>_osm.geojson   出力した座標
  build/<業態>_geocoded.csv       住所_lat / 住所_lon / 住所_位置レベル

出力 (既定 output/reports/):
  coord_addr_distance.csv         閾値を超えた施設の一覧

なぜ要るか:
  build_addr.js の foldColumns は、元データの座標が住所の点から 1km 以上
  離れていれば住所側に差し替える (addr_columns.js の MAX_DRIFT_METERS)。
  ただし適用条件が「位置レベル8かつ番地が照合済み」で、実測では原データ座標
  189,401件のうち 80,831件 (42.7%) にしか効いていない。残る 108,570件は
  どれだけ離れていても素通りする。この検算はその素通りした分を数える。

位置レベルごとに閾値を変える理由:
  レベル8は住居表示の位置なので建物単位で比べられる。
  レベル3は大字と丁目の代表点、レベル2は市区町村役場の所在地で、
  離れていること自体は誤りではない。同じ閾値では意味を持たない。

離島と山間部について:
  レベル2で役場から数十km離れる施設は実在する (小笠原村硫黄島、対馬市、
  白山市白峰など)。距離だけでは誤りと区別できないので、この検算は
  「疑い」を出すに留め、判定は人に渡す。

終了コード:
  0 実行できた   2 入力が無い
  --fail-over を渡した場合のみ、レベル8でその距離を超える施設があれば 1。

使い方:
  python3 scripts/verify_coords_addr.py
  python3 scripts/verify_coords_addr.py --sector pharmacy --report-dir /tmp
"""

import argparse
import collections
import csv
import json
import math
import os
import sys

SECTORS = ["hospital", "clinic", "dental", "maternity", "pharmacy"]

# 位置レベルの意味。build_addr.js の POINT_LEVEL_NOTE と揃える。
LEVEL_NOTE = {
    "1": "都道府県庁所在地",
    "2": "市区町村役場の所在地",
    "3": "大字と丁目の代表点",
    "8": "住居表示の位置",
}

# 疑いとして書き出す下限。レベルごとに意味が違うので別の値にする。
# レベル8の100mは実測の95パーセンタイル(77.9m)の外側、
# レベル3の2kmは同じく95パーセンタイル(1,503m)の外側に置いた。
DEFAULT_THRESHOLDS = {"8": 100.0, "3": 2000.0, "2": 10000.0}

R_EARTH = 6371000.0


def distance_meters(lat1, lon1, lat2, lon2):
    """2点間の距離をメートルで返す。

    addr_columns.js の distanceMeters と同じ式にする。
    ここがずれると、差し替えの判定と検算の判定が食い違う。
    """
    to_rad = math.radians
    p1, p2 = to_rad(lat1), to_rad(lat2)
    dp, dl = to_rad(lat2 - lat1), to_rad(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R_EARTH * math.asin(math.sqrt(h))


def usable(v):
    """数値として有効で 0 でないか。addr_columns.js の usable と同じ判定。"""
    if v is None or str(v).strip() == "":
        return False
    try:
        n = float(v)
    except ValueError:
        return False
    return math.isfinite(n) and n != 0


def load_sector(sector, out_dir):
    """1業態ぶんを読んで、出力座標と住所点を突き合わせた行を返す。

    突合の鍵は施設 ID。geocoded 側に無い ID があれば、どちらかが
    古いまま残っているということなので落とす。黙って捨てない。
    """
    geo_path = os.path.join(out_dir, "build", f"{sector}_geocoded.csv")
    osm_path = os.path.join(out_dir, "osm", sector, f"{sector}_osm.geojson")
    for path in (geo_path, osm_path):
        if not os.path.exists(path):
            sys.exit(f"入力ファイルがありません: {path}")

    with open(geo_path, encoding="utf-8-sig", newline="") as f:
        geo = {r["ID"]: r for r in csv.DictReader(f)}
    with open(osm_path, encoding="utf-8") as f:
        features = json.load(f)["features"]

    rows = []
    for feat in features:
        p = feat["properties"]
        fid = p.get("_id", "")
        g = geo.get(fid)
        if g is None:
            sys.exit(f"{sector}: 出力にある ID が geocoded にありません: {fid}")
        lon, lat = feat["geometry"]["coordinates"]
        row = {
            "業態": sector,
            "_id": fid,
            "名称": p.get("name", ""),
            "都道府県": p.get("addr:province", ""),
            "市区町村": p.get("addr:city", ""),
            "住所": p.get("addr:full", ""),
            "座標の出典": p.get("_座標の出典", ""),
            "位置レベル": g.get("住所_位置レベル", ""),
            "番地の根拠": g.get("番地の根拠", ""),
            "lat": lat,
            "lon": lon,
            "距離m": None,
        }
        if usable(g.get("住所_lat")) and usable(g.get("住所_lon")):
            row["距離m"] = distance_meters(
                lat, lon, float(g["住所_lat"]), float(g["住所_lon"]))
        rows.append(row)
    return rows


def percentiles(values, points=(50, 75, 90, 95, 99)):
    """昇順に並べた値から百分位を返す。空なら空の辞書。"""
    v = sorted(values)
    if not v:
        return {}
    out = {p: v[min(int(len(v) * p / 100), len(v) - 1)] for p in points}
    out["max"] = v[-1]
    return out


def checked_by_drift_rule(row, adopt_level=8):
    """foldColumns の 1km 規則が、この行に効いたかどうか。

    条件は addr_columns.js の drift の算出条件と同じ。
    片方だけ直すと、検算が実態とずれたまま気づけなくなる。
    """
    level = row["位置レベル"]
    if not level.isdigit() or int(level) < adopt_level:
        return False
    if row["番地の根拠"] != "照合済み":
        return False
    return row["距離m"] is not None


def pick_suspects(rows, thresholds):
    """閾値を超えた行を、距離の大きい順に返す。

    元データの座標だけを見る。ジオコーディングの行は出力座標そのものが
    住所点なので距離が必ず 0 になり、数えても意味が無い。
    """
    out = []
    for r in rows:
        if r["座標の出典"] != "原データ" or r["距離m"] is None:
            continue
        limit = thresholds.get(r["位置レベル"])
        if limit is not None and r["距離m"] > limit:
            out.append(r)
    return sorted(out, key=lambda r: -r["距離m"])


def report(rows, out):
    """全国の集計を標準出力に書く"""
    src = [r for r in rows if r["座標の出典"] == "原データ"]
    out(f"原データ座標 {len(src):,}件")
    checked = [r for r in src if checked_by_drift_rule(r)]
    out(f"  1km規則の検査を受けた   {len(checked):8,d}"
        f"  ({len(checked) / len(src) * 100:5.1f}%)")
    out(f"  受けていない            {len(src) - len(checked):8,d}"
        f"  ({(len(src) - len(checked)) / len(src) * 100:5.1f}%)")

    reasons = collections.Counter()
    for r in src:
        if checked_by_drift_rule(r):
            continue
        if r["距離m"] is None:
            reasons["住所側の座標が無い"] += 1
        elif r["位置レベル"] != "8":
            reasons[f"位置レベルが8未満（{r['位置レベル'] or '空'}）"] += 1
        else:
            reasons[f"番地が「{r['番地の根拠'] or '空'}」"] += 1
    for k, v in reasons.most_common():
        out(f"    {k:28s} {v:8,d}")

    for level in ("8", "3", "2", "1"):
        v = [r["距離m"] for r in src
             if r["位置レベル"] == level and r["距離m"] is not None]
        if not v:
            continue
        pc = percentiles(v)
        out("")
        out(f"位置レベル{level}（{LEVEL_NOTE.get(level, '')}） {len(v):,}件"
            " 住所点までの距離")
        for p in (50, 75, 90, 95, 99):
            out(f"  {p:3d}パーセンタイル {pc[p]:>12,.1f} m")
        out(f"  最大            {pc['max']:>12,.1f} m")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--sector", choices=SECTORS, action="append",
                   help="業態を絞る。繰り返し指定できる。既定は全業態")
    p.add_argument("--out-dir", default="output")
    p.add_argument("--report-dir", default=None,
                   help="検算結果の出力先。既定は <out-dir>/reports")
    p.add_argument("--fail-over", type=float, default=None,
                   help="位置レベル8でこの距離(m)を超える施設があれば終了コード1")
    args = p.parse_args()

    sectors = args.sector or SECTORS
    rows = []
    for s in sectors:
        rows += load_sector(s, args.out_dir)
    if not rows:
        sys.exit("行がありません")

    report(rows, print)

    report_dir = args.report_dir or os.path.join(args.out_dir, "reports")
    os.makedirs(report_dir, exist_ok=True)
    path = os.path.join(report_dir, "coord_addr_distance.csv")
    suspects = pick_suspects(rows, DEFAULT_THRESHOLDS)
    cols = ["距離m", "位置レベル", "レベルの意味", "業態", "_id", "名称",
            "都道府県", "市区町村", "住所", "lat", "lon", "地図"]
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in suspects:
            w.writerow([f"{r['距離m']:.1f}", r["位置レベル"],
                        LEVEL_NOTE.get(r["位置レベル"], ""), r["業態"], r["_id"],
                        r["名称"], r["都道府県"], r["市区町村"], r["住所"],
                        r["lat"], r["lon"],
                        "https://www.openstreetmap.org/"
                        f"?mlat={r['lat']}&mlon={r['lon']}"
                        f"#map=18/{r['lat']}/{r['lon']}"])
    print("")
    print(f"閾値 {DEFAULT_THRESHOLDS} を超えた {len(suspects):,}件 → {path}")

    if args.fail_over is not None:
        over = [r for r in rows
                if r["座標の出典"] == "原データ" and r["位置レベル"] == "8"
                and r["距離m"] is not None and r["距離m"] > args.fail_over]
        if over:
            print(f"位置レベル8で {args.fail_over}m を超えた: {len(over):,}件",
                  file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
