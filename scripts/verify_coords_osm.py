#!/usr/bin/env python3
"""出力した座標を、既存 OpenStreetMap の同名オブジェクトと突き合わせて検算する。

入力:
  --pbf   日本全体の .osm.pbf (Geofabrik の japan-latest.osm.pbf など)
  output/osm/<業態>/<業態>_osm.geojson

出力 (既定 output/reports/):
  coord_osm_distance.csv          閾値を超えた施設の一覧

なぜ要るか:
  住所との突き合わせ (verify_coords_addr.py) は、住所側に座標が無い
  27,913件を検算できない。名称は住所とは独立した手がかりなので、
  そこを別の角度から埋められる。実測では両者の疑いが重なったのは
  1,224件中 130件だけで、片方では足りない。

同名の別施設をどう外すか:
  「野口歯科医院」は元データに28件あり、OSM にも9件ある。姓と診療科の
  組み合わせは全国で衝突する。距離だけを見ると、遠くの別施設を
  「ずれている」と誤って数える。
  そこで OSM 側でも元データ側でも名称が全国に1件だけの組み合わせに絞る。
  実測では、この条件を付けないと 2km 超が 35.2% 出るが、付けると 8.3% に落ちる。
  残る 2km 超も別施設なので、既定では 2km を超えたものを同一施設と見なさない。

この距離が意味するもの:
  OSM との食い違いであって、こちらの誤りの量ではない。どちらがずれて
  いるかは分からない。移転や OSM 側の古さでも離れる。疑いに留める。

前提:
  osmium (osmium-tool) が要る。2.3GB を1回舐めるので数分かかる。
  --extract に道を渡すと、抽出結果を再利用して2回目以降を速くできる。

終了コード:
  0 実行できた   2 入力または osmium が無い

使い方:
  python3 scripts/verify_coords_osm.py --pbf ~/data/japan-latest.osm.pbf
  python3 scripts/verify_coords_osm.py --pbf ... --extract output/reports/healthcare.osm.pbf
"""

import argparse
import collections
import csv
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata

SECTORS = ["hospital", "clinic", "dental", "maternity", "pharmacy"]

# 元データの名称に残る法人格。名称の異同を見るときは邪魔になる。
# build_names.py は name から法人格を落とすが、OSM 側は付いたままの
# ことがあるので、突き合わせる直前に両側から落とす。
ENTITY_PREFIXES = [
    "医療法人社団", "医療法人財団", "社会医療法人", "特定医療法人", "医療法人",
    "公益財団法人", "公益社団法人", "一般財団法人", "一般社団法人",
    "社会福祉法人", "独立行政法人", "地方独立行政法人",
    "国家公務員共済組合連合会", "公立学校共済組合", "学校法人",
    "株式会社", "有限会社", "合同会社",
]

RE_PUNCT = re.compile(r"[\s　・･,，.．\-ー－‐−—()（）\[\]「」『』/／|｜]")

# 抽出するタグ。amenity は日本で clinic と hospital の使い分けに揺れが
# あるため、healthcare の有無も併せて拾う。
OSM_FILTERS = [
    "nwr/amenity=hospital,clinic,doctors,dentist,pharmacy",
    "nwr/healthcare",
]

R_EARTH = 6371000.0

# 同一施設と見なす上限。これを超えたら同名の別施設として数えない。
DEFAULT_MAX_DISTANCE = 2000.0
# 疑いとして書き出す下限。
DEFAULT_MIN_DISTANCE = 50.0

# 名称が短すぎると衝突ばかりになる。「内科」「薬局」だけの行を弾く。
MIN_NAME_LENGTH = 3


def normalize_name(s):
    """法人格と記号と空白を落として、比較できる形にする。

    全角と半角の揺れは NFKC で吸収する。元データは全角、OSM は半角の
    ことが多く、揃えないと同じ施設が別名に見える。
    """
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    for p in ENTITY_PREFIXES:
        s = s.replace(p, "")
    return RE_PUNCT.sub("", s).strip().lower()


def distance_meters(lat1, lon1, lat2, lon2):
    to_rad = math.radians
    p1, p2 = to_rad(lat1), to_rad(lat2)
    dp, dl = to_rad(lat2 - lat1), to_rad(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R_EARTH * math.asin(math.sqrt(h))


def decode_object_id(raw):
    """osmium の --add-unique-id=type_id が付ける id を OSM の型と番号に戻す。

    面は a を付けて返り、way なら番号が2倍、relation なら2倍して1を足した
    値になっている。復元しないと osm.org の URL が外れる。
    """
    if not raw or not raw[1:].isdigit():
        return raw
    kind, num = raw[0], int(raw[1:])
    if kind == "n":
        return f"node/{num}"
    if kind == "w":
        return f"way/{num}"
    if kind == "r":
        return f"relation/{num}"
    if kind == "a":
        return f"way/{num // 2}" if num % 2 == 0 else f"relation/{num // 2}"
    return raw


def centroid(geometry):
    """点はそのまま、線と面は頂点の平均を返す。

    面の重心としては粗いが、ここで欲しいのは施設がどのあたりにあるかで、
    数mの違いは後段の閾値に埋もれる。
    """
    coords = geometry["coordinates"]
    if geometry["type"] == "Point":
        return coords[0], coords[1]

    def flatten(x):
        if isinstance(x[0], (int, float)):
            yield x
        else:
            for y in x:
                yield from flatten(y)

    pts = list(flatten(coords))
    return (sum(p[0] for p in pts) / len(pts),
            sum(p[1] for p in pts) / len(pts))


def run_osmium(pbf, extract_path, workdir):
    """pbf から医療系オブジェクトを抜き、GeoJSON Text Sequence にして返す。

    extract_path が既にあれば抽出をやり直さない。2.3GB を舐めるのに
    数分かかるので、閾値を変えて試すたびに待たされないようにする。
    """
    if shutil.which("osmium") is None:
        sys.exit("osmium が見つかりません。osmium-tool を入れてください "
                 "(macOS なら brew install osmium-tool)")
    if not os.path.exists(pbf):
        sys.exit(f"pbf がありません: {pbf}")

    if extract_path and os.path.exists(extract_path):
        filtered = extract_path
    else:
        filtered = extract_path or os.path.join(workdir, "healthcare.osm.pbf")
        os.makedirs(os.path.dirname(os.path.abspath(filtered)), exist_ok=True)
        subprocess.run(["osmium", "tags-filter", pbf, *OSM_FILTERS,
                        "-o", filtered, "--overwrite"], check=True)

    seq = os.path.join(workdir, "healthcare.geojsonseq")
    subprocess.run(["osmium", "export", filtered, "-f", "geojsonseq",
                    "-o", seq, "--overwrite", "--add-unique-id=type_id"],
                   check=True)
    return seq


def load_osm(seq_path):
    """抽出した OSM オブジェクトを読み、名称ごとの索引を返す"""
    index = collections.defaultdict(list)
    total = named = 0
    with open(seq_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip().lstrip("\x1e")
            if not line:
                continue
            feat = json.loads(line)
            total += 1
            props = feat.get("properties", {})
            # name が無く name:ja だけの物件がある。落とすと照合できる数が減る。
            name = props.get("name") or props.get("name:ja") or ""
            key = normalize_name(name)
            if len(key) < MIN_NAME_LENGTH:
                continue
            named += 1
            lon, lat = centroid(feat["geometry"])
            index[key].append({
                "id": decode_object_id(feat.get("id", "")),
                "name": name, "lat": lat, "lon": lon,
            })
    return index, total, named


def load_ours(sectors, out_dir):
    rows = []
    for sector in sectors:
        path = os.path.join(out_dir, "osm", sector, f"{sector}_osm.geojson")
        if not os.path.exists(path):
            sys.exit(f"入力ファイルがありません: {path}")
        with open(path, encoding="utf-8") as f:
            for feat in json.load(f)["features"]:
                p = feat["properties"]
                lon, lat = feat["geometry"]["coordinates"]
                rows.append({
                    "業態": sector, "_id": p.get("_id", ""),
                    "名称": p.get("name", ""),
                    "正規化名": normalize_name(p.get("name", "")),
                    "都道府県": p.get("addr:province", ""),
                    "市区町村": p.get("addr:city", ""),
                    "座標の出典": p.get("_座標の出典", ""),
                    "lat": lat, "lon": lon,
                })
    return rows


def match(rows, index, max_distance):
    """双方で名称が一意な組み合わせだけを、距離つきで返す。

    返すのは (照合できた行, 遠すぎて同一施設と見なさなかった件数)。
    """
    ours = collections.Counter(r["正規化名"] for r in rows if r["正規化名"])
    matched, dropped = [], 0
    for r in rows:
        key = r["正規化名"]
        if len(key) < MIN_NAME_LENGTH or ours[key] != 1:
            continue
        cand = index.get(key, [])
        if len(cand) != 1:
            continue
        o = cand[0]
        d = distance_meters(r["lat"], r["lon"], o["lat"], o["lon"])
        if d > max_distance:
            dropped += 1
            continue
        hit = dict(r)
        hit["距離m"] = d
        hit["OSM_ID"] = o["id"]
        hit["OSM名称"] = o["name"]
        matched.append(hit)
    return matched, dropped


def percentiles(values, points=(50, 75, 90, 95, 99)):
    v = sorted(values)
    if not v:
        return {}
    out = {p: v[min(int(len(v) * p / 100), len(v) - 1)] for p in points}
    out["max"] = v[-1]
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--pbf", required=True, help="日本全体の .osm.pbf")
    p.add_argument("--extract", default=None,
                   help="抽出結果の置き場。あれば再利用し、無ければ作る")
    p.add_argument("--sector", choices=SECTORS, action="append")
    p.add_argument("--out-dir", default="output")
    p.add_argument("--report-dir", default=None)
    p.add_argument("--max-distance", type=float, default=DEFAULT_MAX_DISTANCE,
                   help="これを超えたら同名の別施設と見なす")
    p.add_argument("--min-distance", type=float, default=DEFAULT_MIN_DISTANCE,
                   help="これを超えたものを疑いとして書き出す")
    args = p.parse_args()

    rows = load_ours(args.sector or SECTORS, args.out_dir)
    with tempfile.TemporaryDirectory() as workdir:
        seq = run_osmium(args.pbf, args.extract, workdir)
        index, total, named = load_osm(seq)

    print(f"OSM から抽出したオブジェクト: {total:,}件 "
          f"（名称が使えたもの {named:,}件 / 正規化後のキー {len(index):,}）")
    matched, dropped = match(rows, index, args.max_distance)
    if not matched:
        print("照合できた施設がありません")
        return

    print(f"照合できた施設: {len(matched):,} / {len(rows):,} "
          f"= {len(matched) / len(rows) * 100:.1f}%"
          f"（同名だが {args.max_distance:,.0f}m 超で外した {dropped:,}件を除く）")
    pc = percentiles([r["距離m"] for r in matched])
    for k in (50, 75, 90, 95, 99):
        print(f"  {k:3d}パーセンタイル {pc[k]:>9,.1f} m")
    print(f"  最大            {pc['max']:>9,.1f} m")

    over = sorted([r for r in matched if r["距離m"] > args.min_distance],
                  key=lambda r: -r["距離m"])
    print("")
    print("業態別 " + f"{args.min_distance:,.0f}m 超の割合")
    by = collections.defaultdict(lambda: [0, 0])
    for r in matched:
        by[r["業態"]][1] += 1
        if r["距離m"] > args.min_distance:
            by[r["業態"]][0] += 1
    for s in SECTORS:
        n, t = by[s]
        if t:
            print(f"  {s:10s} {n:6,d} / {t:6,d}  ({n / t * 100:5.2f}%)")

    report_dir = args.report_dir or os.path.join(args.out_dir, "reports")
    os.makedirs(report_dir, exist_ok=True)
    path = os.path.join(report_dir, "coord_osm_distance.csv")
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["距離m", "業態", "_id", "名称", "都道府県", "市区町村",
                    "座標の出典", "lat", "lon", "OSM_ID", "OSM名称", "OSM_URL"])
        for r in over:
            w.writerow([f"{r['距離m']:.1f}", r["業態"], r["_id"], r["名称"],
                        r["都道府県"], r["市区町村"], r["座標の出典"],
                        r["lat"], r["lon"], r["OSM_ID"], r["OSM名称"],
                        f"https://www.openstreetmap.org/{r['OSM_ID']}"])
    print("")
    print(f"{args.min_distance:,.0f}m を超えた {len(over):,}件 → {path}")


if __name__ == "__main__":
    main()
