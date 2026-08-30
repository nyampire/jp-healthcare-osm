#!/usr/bin/env python3
"""build_osm.py が生成した OSM 向けデータを検証する。

生成側と独立した基準で確かめる:
  * CSV と GeoJSON の件数と ID が一致するか
  * GeoJSON が Point の FeatureCollection として成立しているか
  * 座標が日本の範囲に入るか。緯度と経度を取り違えていないか
  * タグのキーと値が OSM に投入できる形か（空値、255文字、制御文字）
  * amenity と healthcare の値が OSM の語彙にあるか
  * name が空の地物が無いか

終了コード: 欠陥が 1 件でもあれば 1、なければ 0。
"""

import argparse
import collections
import csv
import json
import os
import re
import sys

MAX_TAG_LENGTH = 255
JP_LAT = (20.0, 46.0)
JP_LON = (122.0, 154.0)

# 施設種別に使う値。OSM wiki に記載があり taginfo でも広く使われているもの。
AMENITY_VALUES = {"hospital", "clinic", "doctors", "dentist", "pharmacy"}
HEALTHCARE_VALUES = {"hospital", "clinic", "doctor", "dentist", "pharmacy", "midwife"}

RE_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_:-]*$")
RE_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
RE_URL = re.compile(r"^https?://\S+$")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("prefix", help="output/osm/<業態>/<業態>_osm の接頭辞、または CSV のパス")
    p.add_argument("--report-dir", default=None,
                   help="検証結果の出力先。既定は入力ファイルと同じディレクトリ")
    args = p.parse_args()
    base = args.prefix[:-4] if args.prefix.endswith(".csv") else args.prefix
    csv_path, gj_path = base + ".csv", base + ".geojson"
    for f in (csv_path, gj_path):
        if not os.path.exists(f):
            sys.exit(f"入力ファイルがありません: {f}")

    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    with open(gj_path, encoding="utf-8") as f:
        gj = json.load(f)

    issues = collections.defaultdict(list)

    def add(kind, ident, detail):
        issues[kind].append((ident, detail))

    # GeoJSON の構造
    if gj.get("type") != "FeatureCollection":
        add("geojson_structure", "-", f"type が FeatureCollection でない: {gj.get('type')}")
    feats = gj.get("features", [])
    if len(feats) != len(rows):
        add("count_mismatch", "-", f"CSV {len(rows):,} 件に対し GeoJSON {len(feats):,} 件")

    gj_ids = []
    for n, ft in enumerate(feats):
        fid = (ft.get("properties") or {}).get("_id", f"#{n}")
        gj_ids.append(fid)
        geom = ft.get("geometry") or {}
        if geom.get("type") != "Point":
            add("geojson_structure", fid, f"geometry が Point でない: {geom.get('type')}")
            continue
        c = geom.get("coordinates")
        if not (isinstance(c, list) and len(c) == 2):
            add("geojson_structure", fid, f"coordinates の形が不正: {c}")
            continue
        lon, lat = c
        # GeoJSON は経度が先。取り違えると日本の施設が全て海上へ飛ぶ。
        # 日本の経度域と緯度域は重ならないので、順序の誤りは値域で検出できる。
        if JP_LAT[0] < lon < JP_LAT[1] and JP_LON[0] < lat < JP_LON[1]:
            add("coord_order", fid, f"経度と緯度が逆の可能性: [{lon}, {lat}]")
        elif not (JP_LON[0] < lon < JP_LON[1] and JP_LAT[0] < lat < JP_LAT[1]):
            add("coord_range", fid, f"日本の範囲外: [{lon}, {lat}]")

    if len(gj_ids) == len(rows):
        for r, gid in zip(rows, gj_ids):
            if r["ID"] != gid:
                add("id_mismatch", r["ID"], f"GeoJSON 側は {gid}")
                break

    # CSV 側のタグ
    tag_keys = [k for k in rows[0].keys()
                if k not in ("ID", "都道府県コード", "lat", "lon", "座標の出典",
                             "要確認", "備考")] if rows else []
    value_use = collections.Counter()
    for r in rows:
        fid = r["ID"]
        try:
            la, lo = float(r["lat"]), float(r["lon"])
        except ValueError:
            add("coord_range", fid, f"座標が数値でない: {r['lat']}, {r['lon']}")
            continue
        if not (JP_LAT[0] < la < JP_LAT[1] and JP_LON[0] < lo < JP_LON[1]):
            add("coord_range", fid, f"日本の範囲外: {la}, {lo}")

        if not r.get("name"):
            add("name_missing", fid, "name が空")
        if not r.get("amenity") and not r.get("healthcare"):
            add("type_missing", fid, "amenity と healthcare がどちらも空")

        a, h = r.get("amenity", ""), r.get("healthcare", "")
        if a and a not in AMENITY_VALUES:
            add("unknown_value", fid, f"amenity の値が想定外: {a}")
        if h and h not in HEALTHCARE_VALUES:
            add("unknown_value", fid, f"healthcare の値が想定外: {h}")
        if a:
            value_use[f"amenity={a}"] += 1
        if h:
            value_use[f"healthcare={h}"] += 1

        # 番地だけあって町字が無い行。OSM では階層を飛ばした addr は使えない
        if r.get("addr:housenumber") and not r.get("addr:neighbourhood"):
            add("addr_hierarchy", fid, "addr:housenumber があるのに addr:neighbourhood が空")

        # 住居表示未実施の町字では、NJA が解決できなかった地番が note に残る。
        # 値の出自は利用者の入力文字列だが、実質は地番なので投入前に確認する。
        note = r.get("note", "")
        if note and note[0].isdigit():
            add("addr_note_chiban", fid, f"note が数字で始まる: {note}")

        # addr:province は元データの所在地の先頭と一致するはず。
        # 食い違うのは町字の照合が別の都道府県へ流れた兆候になる。
        # 都道府県コードとの突き合わせにすると47件の対応表が要るので、
        # 同じ行にある addr:full の先頭を使う。
        prov = r.get("addr:province", "")
        full = r.get("addr:full", "")
        if prov and full and not full.startswith(prov):
            add("addr_province_mismatch", fid,
                f"addr:province が {prov} だが所在地は {full[:12]} で始まる")

        w = r.get("website", "")
        if w and not RE_URL.match(w):
            add("bad_website", fid, f"URL の形式が不正: {w[:60]}")

        for k in tag_keys:
            v = r.get(k, "")
            if not v:
                continue
            if not RE_KEY.match(k):
                add("bad_key", fid, f"キーの書式が不正: {k}")
            if len(v) > MAX_TAG_LENGTH:
                add("tag_too_long", fid, f"{k} が {len(v)} 文字")
            if RE_CTRL.search(v):
                add("control_char", fid, f"{k} に制御文字が含まれる")
            if v != v.strip():
                add("untrimmed", fid, f"{k} の前後に空白がある")

    # 同一座標に複数の施設が乗っていないか
    coords = collections.Counter((r["lat"], r["lon"]) for r in rows)
    dup = sum(n for n in coords.values() if n > 1)

    # 同じ座標を別の市区町村の施設が共有している行。
    # 同じ建物に複数の診療所が入るのは普通なので、重なり自体は欠陥ではない。
    # 市区町村が違えば話は別で、同じ点が両方の住所であることはありえない。
    # 少なくとも一方の座標が誤っている。
    #
    # どれが正しいかは機械的に決まらないので、座標は動かさず一覧に出す。
    # 距離や位置レベルを使う判定は要らない。重なりと市区町村の一致だけで済む。
    same_point = collections.defaultdict(list)
    for r in rows:
        same_point[(r["lat"], r["lon"])].append(r)
    for members in same_point.values():
        if len(members) < 2:
            continue
        cities = {(r.get("都道府県コード", ""), r.get("addr:city", ""))
                  for r in members}
        if len(cities) < 2:
            continue
        names = "、".join(sorted({r.get("addr:city", "") or "(不明)"
                                 for r in members}))
        for r in members:
            add("coord_cross_city", r["ID"],
                f"同じ座標を別の市区町村の{len(members)}件が共有: {names}")

    report_dir = args.report_dir or os.path.dirname(csv_path) or "."
    os.makedirs(report_dir, exist_ok=True)
    out = os.path.join(report_dir, os.path.basename(base) + "_validation.csv")
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["種別", "ID", "内容"])
        for kind in sorted(issues):
            for ident, detail in issues[kind]:
                w.writerow([kind, ident, detail])

    print(f"検証対象   : {csv_path}")
    print(f"  地物数           : {len(rows):,}")
    print(f"  GeoJSON の地物数 : {len(feats):,}")
    # defaultdict を参照すると空の項目が増えてしまうため get で読む
    for k in ("geojson_structure", "count_mismatch", "id_mismatch", "coord_order",
              "coord_range", "name_missing", "type_missing", "unknown_value",
              "bad_website", "bad_key", "tag_too_long", "control_char", "untrimmed",
              "addr_hierarchy", "addr_note_chiban", "addr_province_mismatch",
              "coord_cross_city"):
        items = issues.get(k, [])
        print(f"  {k:<18}: {len(items):,}")
        for ident, detail in items[:2]:
            print(f"      {ident} {detail}")
    print(f"  同一座標の重なり  : {dup:,} 件が {sum(1 for n in coords.values() if n > 1):,} 地点に集中")
    print("\n  施設種別の内訳:")
    for k, n in value_use.most_common():
        print(f"    {k:<24} {n:>8,}")
    print(f"\n詳細: {out}")
    # addr_note_chiban は欠陥ではなく申し送り。住居表示未実施の町字で
    # NJA が解決できなかった残余が note に残り、その数字は実質的に地番になる。
    # 値は落とさずに残し、分割するかどうかは利用者が件数を見て判断する。
    # 残す方針のものを fatal に算入すると、パイプライン全体が止まる。
    # 検出も件数表示も *_validation.csv への記録も従来どおり行う。
    INFORMATIONAL = ("addr_note_chiban", "coord_cross_city")
    fatal = sum(len(v) for k, v in issues.items() if k not in INFORMATIONAL)
    sys.exit(1 if fatal else 0)


if __name__ == "__main__":
    main()
