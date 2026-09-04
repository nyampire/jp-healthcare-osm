#!/usr/bin/env python3
"""build_osm.py が生成した OSM 向けデータを検証する。

生成側と独立した基準で確かめる:
  * CSV と GeoJSON の件数と ID が一致するか
  * GeoJSON が Point の FeatureCollection として成立しているか
  * 座標が日本の範囲に入るか。緯度と経度を取り違えていないか
  * タグのキーと値が OSM に投入できる形か（空値、255文字、制御文字）
  * amenity と healthcare の値が OSM の語彙にあるか
  * name が空の地物が無いか
  * addr:province が都道府県コードと一致するか
  * 都道府県別ファイルがあれば、行数の合計と都道府県コードの集合が全国ファイルと
    一致するか（無ければ何もしない）
  * 隣に geocoded.csv があれば、座標の理由 が 備考 の先頭の1文と一致するか
    （無ければ何もしない）

終了コード: 欠陥が 1 件でもあれば 1、なければ 0。
"""

import argparse
import collections
import csv
import glob
import json
import os
import re
import sys

from prefectures import PREF

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

    # 残余の列が無ければ addr_note_chiban は何も見つけられない。
    # 検査が黙って無効になるほうが、検出0件よりたちが悪いので欠陥にする。
    if rows and "未解釈の文字列" not in rows[0]:
        add("missing_column", "-",
            "CSV に 未解釈の文字列 列が無く addr_note_chiban を検査できない")

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
    # タグでない列。ここに足し忘れると、日本語の列名が bad_key として
    # 検出され、非タグ列を増やすたびに検証が落ちる。
    NON_TAG_COLUMNS = ("ID", "都道府県コード", "lat", "lon", "座標の出典",
                       "要確認", "備考", "未解釈の文字列", "fixme の内容")
    tag_keys = [k for k in rows[0].keys()
                if k not in NON_TAG_COLUMNS] if rows else []
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

        # 住居表示未実施の町字では、NJA が解決できなかった地番が残余に残る。
        # 値の出自は利用者の入力文字列だが、実質は地番なので投入前に確認する。
        #
        # 残余は 2026-09-01 に OSM タグ（note）から CSV 末尾の非タグ列へ移した。
        # 参照先を追随させないと、この検査は何も見つけないまま通り続ける。
        # 列が消えたら黙って素通りしないよう、下で欠落を検出する。
        residue = r.get("未解釈の文字列", "")
        if residue and residue[0].isdigit():
            add("addr_note_chiban", fid, f"未解釈の文字列が数字で始まる: {residue}")

        # addr:province は都道府県コードから prefectures.PREF で引ける県名と
        # 一致するはず。食い違うのは町字の照合が別の都道府県へ流れた兆候になる。
        # 都道府県コードはこのブランチで出力ファイル名の根拠にもなっており、
        # PREF という単一の対応表が既にあるので、それをそのまま突き合わせに使う。
        code = r.get("都道府県コード", "")
        prov = r.get("addr:province", "")
        if prov and code in PREF and PREF[code] != prov:
            add("addr_province_mismatch", fid,
                f"addr:province が {prov} だが都道府県コードは {code}（{PREF[code]}）")

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

    # 都道府県別ファイルとの検算。県別分割はこのブランチの中心的な不変条件
    # なのに、確かめるコードが本番のパイプラインに無かった。検証対象と同じ
    # ディレクトリに <業態>別ファイルがあれば、行数の合計と都道府県コードの
    # 集合が全国ファイルと一致するか確かめる。無ければ何もしない
    # （selftest_osm.py は県別ファイルの無い一時ディレクトリで実行される）。
    #
    # ここで都道府県コードの集合まで見るのは、build_osm.py が最後に出す
    # 「都道府県別 : N 件のファイル対を書き出しました」の N を誰も検査して
    # おらず、ある県が丸ごと落ちても終了コード0になっていたため。
    sector = re.sub(r"_osm$", "", os.path.basename(base))
    pref_dir = os.path.dirname(csv_path) or "."
    pref_files = sorted(glob.glob(os.path.join(pref_dir, f"[0-9][0-9]_*_{sector}.csv")))
    if pref_files:
        total_split = 0
        codes_split = set()
        for pf in pref_files:
            with open(pf, encoding="utf-8-sig", newline="") as f:
                total_split += sum(1 for _ in csv.DictReader(f))
            codes_split.add(os.path.basename(pf)[:2])
        if total_split != len(rows):
            add("pref_split_row_mismatch", "-",
                f"都道府県別ファイルの合計 {total_split:,} 件に対し全国 {len(rows):,} 件")
        codes_national = {r["都道府県コード"] for r in rows if r.get("都道府県コード")}
        missing = codes_national - codes_split
        if missing:
            add("pref_split_missing", "-",
                f"都道府県別ファイルが無いコード: {','.join(sorted(missing))}")
        extra = codes_split - codes_national
        if extra:
            add("pref_split_extra", "-",
                f"全国ファイルに無い都道府県コードの都道府県別ファイル: "
                f"{','.join(sorted(extra))}")

    # 座標の理由 と 備考 の突き合わせ。build_addr.js は座標を差し替えた理由を
    # 座標の理由 と 備考 の両方へ書く。build_osm.py は備考を作り直すときに
    # 座標の理由 だけを運ぶので、2つが食い違うと OSM 側の備考だけが別のことを
    # 言い、MapRoulette の作業者は捨てられた座標を知らないまま判断することになる。
    #
    # 座標の理由 は OSM の CSV には出さない列なので、生成元の geocoded.csv を読む。
    # selftest_addr.js が同じ不変条件をフィクスチャ1件で見ているが、ここでは
    # 本番の全行で見る。県別ファイルと同じく、無ければ何もしない。
    geocoded = os.path.join(os.path.dirname(os.path.dirname(pref_dir)),
                            "build", sector + "_geocoded.csv")
    if os.path.exists(geocoded):
        with open(geocoded, encoding="utf-8-sig", newline="") as f:
            for g in csv.DictReader(f):
                why = (g.get("座標の理由") or "").strip()
                if not why:
                    continue
                head = (g.get("備考") or "").split(" / ")[0]
                if head != why:
                    add("coord_reason_mismatch", g.get("ID", "-"),
                        f"備考の先頭が 座標の理由 と違う: {head[:60]}")

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
              "missing_column", "addr_hierarchy", "addr_note_chiban",
              "addr_province_mismatch", "coord_reason_mismatch",
              "coord_cross_city", "pref_split_row_mismatch", "pref_split_missing",
              "pref_split_extra"):
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
