#!/usr/bin/env python3
"""OSM 向けデータを MapRoulette のタスクファイルに変換する。

入力 (output/):
  <業態>_osm.csv  結合済みのタグ

出力 (output/maproulette/):
  <業態>/<都道府県コード>_<都道府県名>.geojson  チャレンジ1つ分のタスク
  index.csv                                   チャレンジの一覧と件数

形式:
  line-by-line GeoJSON を使う。各行が RFC 7464 のレコードセパレータ（0x1E）で
  始まり、1タスクが1つの FeatureCollection として1行に収まる。
  https://learn.maproulette.org/en-US/documentation/line-by-line-geojson/

  1行ずつ読めるので巨大なファイルを扱え、MapRoulette 側が自動で判別する。

分割:
  都道府県ごとに分ける。全国199,347件を1つのチャレンジにすると、作業者が
  終わりの見えない列に向き合うことになる。地元の地理を知る人が自分の県から
  着手できる単位にする。

タスクの内容:
  重複の判定は作業者が行う。同名の施設は座標か住所で分かれるため、
  こちらで機械的に判定せず、提案するタグを properties に載せて委ねる。
  座標が住所から付与したものかどうかも載せるので、現地確認の要否を判断できる。
"""

import argparse
import collections
import csv
import json
import os
import sys

RS = "\x1e"

SECTORS = {
    "hospital": "病院", "clinic": "診療所", "dental": "歯科診療所",
    "maternity": "助産所", "pharmacy": "薬局",
}

PREF = {
    "01": "北海道", "02": "青森県", "03": "岩手県", "04": "宮城県", "05": "秋田県",
    "06": "山形県", "07": "福島県", "08": "茨城県", "09": "栃木県", "10": "群馬県",
    "11": "埼玉県", "12": "千葉県", "13": "東京都", "14": "神奈川県", "15": "新潟県",
    "16": "富山県", "17": "石川県", "18": "福井県", "19": "山梨県", "20": "長野県",
    "21": "岐阜県", "22": "静岡県", "23": "愛知県", "24": "三重県", "25": "滋賀県",
    "26": "京都府", "27": "大阪府", "28": "兵庫県", "29": "奈良県", "30": "和歌山県",
    "31": "鳥取県", "32": "島根県", "33": "岡山県", "34": "広島県", "35": "山口県",
    "36": "徳島県", "37": "香川県", "38": "愛媛県", "39": "高知県", "40": "福岡県",
    "41": "佐賀県", "42": "長崎県", "43": "熊本県", "44": "大分県", "45": "宮崎県",
    "46": "鹿児島県", "47": "沖縄県",
}

# タスクに載せるタグ。この順で properties に入る。
TAG_KEYS = ["amenity", "healthcare", "name", "official_name", "short_name",
            "name:ja-Hira", "name:ja-Latn", "name:en", "opening_hours",
            "healthcare:speciality", "website", "addr:full", "beds", "source"]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out-dir", default="output")
    p.add_argument("--sector", default="all",
                   choices=sorted(SECTORS) + ["all"])
    p.add_argument("--split", default="pref", choices=["pref", "none"],
                   help="pref は都道府県ごと、none は業態ごとに1ファイル")
    args = p.parse_args()

    sectors = sorted(SECTORS) if args.sector == "all" else [args.sector]
    mr_dir = os.path.join(args.out_dir, "maproulette")
    os.makedirs(mr_dir, exist_ok=True)
    index = []

    for sector in sectors:
        src = os.path.join(args.out_dir, f"{sector}_osm.csv")
        if not os.path.exists(src):
            sys.exit(f"入力がありません: {src}\n先に build_osm.py を実行してください。")
        with open(src, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))

        groups = collections.defaultdict(list)
        for r in rows:
            key = r["都道府県コード"] if args.split == "pref" else "all"
            groups[key].append(r)

        out_sub = os.path.join(mr_dir, sector)
        os.makedirs(out_sub, exist_ok=True)
        for key in sorted(groups):
            name = f"{key}_{PREF.get(key, key)}" if args.split == "pref" else sector
            path = os.path.join(out_sub, f"{name}.geojson")
            with open(path, "w", encoding="utf-8") as f:
                for r in groups[key]:
                    tags = {k: r[k] for k in TAG_KEYS if r.get(k)}
                    props = dict(tags)
                    props["_座標の出典"] = r["座標の出典"]
                    if r["座標の出典"] == "ジオコーディング":
                        props["_注意"] = "座標は住所から推定したもの。現地または航空写真で確認が必要"
                    if r.get("要確認"):
                        props["_要確認"] = r["備考"][:200]
                    task = {
                        "type": "FeatureCollection",
                        "features": [{
                            "type": "Feature",
                            # GeoJSON は経度が先
                            "geometry": {"type": "Point",
                                         "coordinates": [float(r["lon"]), float(r["lat"])]},
                            "properties": props,
                        }],
                    }
                    f.write(RS + json.dumps(task, ensure_ascii=False) + "\n")
            geocoded = sum(1 for r in groups[key] if r["座標の出典"] == "ジオコーディング")
            index.append([sector, SECTORS[sector], key, PREF.get(key, key),
                          len(groups[key]), geocoded,
                          os.path.relpath(path, args.out_dir),
                          os.path.getsize(path)])

    with open(os.path.join(mr_dir, "index.csv"), "w",
              encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["業態コード", "業態", "都道府県コード", "都道府県",
                    "タスク数", "うち座標が推定", "ファイル", "バイト数"])
        w.writerows(index)

    total = sum(r[4] for r in index)
    geo = sum(r[5] for r in index)
    print(f"チャレンジ数 : {len(index):,}")
    print(f"タスク総数   : {total:,}（うち座標が推定 {geo:,}）")
    by_sector = collections.Counter()
    for r in index:
        by_sector[r[1]] += r[4]
    for k, n in by_sector.most_common():
        print(f"  {k:<12} {n:>8,}")
    big = sorted(index, key=lambda r: -r[4])[:3]
    print("\n  タスクが多いチャレンジ:")
    for r in big:
        print(f"    {r[1]} {r[3]:<8} {r[4]:>7,} 件  {r[7] / 1024 / 1024:.1f}MB")
    print(f"\n出力: {mr_dir}")


if __name__ == "__main__":
    main()
