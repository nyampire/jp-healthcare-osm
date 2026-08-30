#!/usr/bin/env python3
"""各タグの生成結果を施設単位に結合し、OSM へ投入できる形にまとめる。

入力 (output/):
  <業態>_geocoded.csv       座標と住所（元の値と付与した値）
  <業態>_names.csv          name 系のタグ
  <業態>_opening_hours.csv  opening_hours
  <業態>_speciality.csv     healthcare:speciality（3業態のみ）
  NN-*_..._YYYYMMDD.csv     施設票（website、病床数など未加工の列）
  mapping/facility_tags.csv 業態から amenity と healthcare への対応

出力 (output/):
  <業態>_osm.csv      施設単位の全タグ。表計算ソフトで確認する用
  <業態>_osm.geojson  同じ内容の点データ。JOSM で開いて地図上で確認する用

処理方針:
  座標が無い施設は出力しない。OSM のノードを作れないため。
  ただし件数は集計に出し、どの施設が落ちたかは <業態>_geocoded.csv で追える。

  タグの値が無い場合はその列を空にする。空文字のタグは OSM に入れない。

  ref 系のタグは付けない。医療情報ネットの ID を OSM のどのキーで持つかは
  imports メーリングリストでの合意が要るため、決まるまで保留する。
  ID 列は残すので、合意後に付け直せる。
"""

import argparse
import collections
import csv
import glob
import json
import os
import re
import sys

SECTORS = {
    "hospital": ("病院", "01-1_hospital_facility_info_*.csv", "正式名称"),
    "clinic": ("診療所", "02-1_clinic_facility_info_*.csv", "正式名称"),
    "dental": ("歯科診療所", "03-1_dental_facility_info_*.csv", "正式名称"),
    "maternity": ("助産所", "04_maternity_home_*.csv", "正式名称"),
    "pharmacy": ("薬局", "05_pharmacy_*.csv", "名称"),
}

# 元データの出典。PDL1.0 は加工した旨と加工者の明示を求めている。
SOURCE = "厚生労働省 医療情報ネットのオープンデータ (2026-06-01)"

# 日本の範囲。ここを外れる座標は出力しない。
JP_BOUNDS = (20.0, 46.0, 122.0, 154.0)

# OSM のタグ値の上限
MAX_TAG_LENGTH = 255

RE_URL = re.compile(r"^https?://\S+$")
# 検索エンジンの転送 URL。施設のサイトではないので website には入れない。
RE_REDIRECT = re.compile(r"^https?://(www\.)?(bing\.com/ck/|google\.[a-z.]+/url\?|"
                         r"search\.yahoo\.[a-z.]+/)", re.I)
# スキームを欠いた裸のドメイン。先頭がドメイン名の形をしているものだけを対象にする。
RE_BARE_DOMAIN = re.compile(r"^[\w-]+(\.[\w-]+)+(/\S*)?$")
# コロンが抜けた表記。`http//example.jp` のような打ち間違い。
RE_MISSING_COLON = re.compile(r"^(https?)//(\S+)$")


def resolve(base, pattern):
    hits = sorted(glob.glob(os.path.join(base, pattern)))
    if not hits:
        sys.exit(f"入力ファイルが見つかりません: {pattern}")
    return hits[-1]


def read_csv(path, key="ID"):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        return {r[key]: r for r in csv.DictReader(f)}


def load_facility_tags(path):
    """業態と条件から amenity, healthcare を引く表を返す。"""
    with open(path, encoding="utf-8-sig", newline="") as f:
        out = collections.defaultdict(dict)
        for r in csv.DictReader(f):
            out[r["業態"].strip()][r["条件"].strip()] = r
        return out


def fit_opening_hours(value):
    """opening_hours を 255 文字に収める。収まらない分は末尾の規則から落とす。

    休診日を個別に並べた施設では 396 文字になる例がある。
    先頭の曜日と時刻の規則が最も価値が高く、末尾の日付指定は個別の休診日なので、
    後ろから落として基本の営業時間を残す。
    """
    v = value.strip()
    if len(v) <= MAX_TAG_LENGTH:
        return v, ""
    rules = v.split("; ")
    dropped = []
    while rules and len("; ".join(rules)) > MAX_TAG_LENGTH:
        dropped.append(rules.pop())
    if not rules:
        return "", f"{MAX_TAG_LENGTH}文字を超え、残せる規則が無いため出力しない"
    return "; ".join(rules), (f"{MAX_TAG_LENGTH}文字を超えたため末尾の規則"
                              f"{len(dropped)}件を落とした: {'; '.join(reversed(dropped))[:80]}")


def clean_url(value):
    """website に入れられる形へ直す。直した内容は呼び出し側で備考に残す。

    元データにはスキームを欠いた裸のドメインと、コロンが抜けた表記が混じる。
    病院票では前者が473件、後者が34件あった。

    コロンの脱字は、書かれているスキームをそのまま活かして補う。
    裸のドメインはスキームが分からないので https を補う。現在のウェブでは https が
    既定で、http のみのサイトも https へ転送されるのが通例のため。
    どちらも元データに無い文字を足しているので、補った事実を記録する。
    """
    v = value.strip()
    if not v:
        return "", ""
    # 形式の照合より先に落とす。正しい形の URL でも長すぎればタグに入れられない。
    if RE_REDIRECT.match(v):
        return "", f"検索エンジンの転送 URL のため出力しない: {v[:60]}"
    if len(v) > MAX_TAG_LENGTH:
        return "", f"{MAX_TAG_LENGTH}文字を超えるため出力しない: {len(v)}文字"
    if RE_URL.match(v):
        return v, ""
    m = RE_MISSING_COLON.match(v)
    if m:
        return f"{m.group(1)}://{m.group(2)}", f"コロンの脱字を補った: {v[:60]}"
    if RE_BARE_DOMAIN.match(v):
        return f"https://{v}", f"スキームが無いため https を補った: {v[:60]}"
    return "", f"website に使えない形式のため出力しない: {v[:60]}"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir", default=".")
    p.add_argument("--out-dir", default="output")
    p.add_argument("--sector", default="hospital", choices=sorted(SECTORS))
    p.add_argument("--tags", default=os.path.join("mapping", "facility_tags.csv"))
    args = p.parse_args()

    label, pattern, name_col = SECTORS[args.sector]
    src = resolve(args.data_dir, pattern)
    ftags = load_facility_tags(args.tags)
    print(f"業態     : {label}")
    print(f"施設票   : {os.path.basename(src)}")

    build_dir = os.path.join(args.out_dir, "build")
    geo = read_csv(os.path.join(build_dir, f"{args.sector}_geocoded.csv"))
    names = read_csv(os.path.join(build_dir, f"{args.sector}_names.csv"))
    hours = read_csv(os.path.join(build_dir, f"{args.sector}_opening_hours.csv"))
    spec = read_csv(os.path.join(build_dir, f"{args.sector}_speciality.csv"))
    for label_, d in (("座標", geo), ("名称", names), ("時間", hours)):
        if not d:
            sys.exit(f"{label_}の生成結果がありません。先に build を実行してください。")
    print(f"結合元   : 座標 {len(geo):,} / 名称 {len(names):,} / 時間 {len(hours):,}"
          + (f" / 診療科 {len(spec):,}" if spec else ""))

    # 施設票から未加工のまま使う列を拾う
    with open(src, encoding="utf-8-sig", newline="") as f:
        r = csv.reader(f)
        idx = {h: n for n, h in enumerate(next(r))}
        raw = {}
        for row in r:
            raw[row[0]] = row
    has_web = next((c for c in ("案内用ホームページアドレス", "薬局のホームページアドレス")
                    if c in idx), None)
    has_beds = "合計病床数" in idx

    rows = []
    features = []
    stat = collections.Counter()

    for fid, g in geo.items():
        lat, lon = g["lat"].strip(), g["lon"].strip()
        if not lat or not lon:
            stat["座標が無く出力しない"] += 1
            continue
        la, lo = float(lat), float(lon)
        if not (JP_BOUNDS[0] < la < JP_BOUNDS[1] and JP_BOUNDS[2] < lo < JP_BOUNDS[3]):
            stat["座標が日本の範囲外で出力しない"] += 1
            continue

        nm = names.get(fid, {})
        hr = hours.get(fid, {})
        sp = spec.get(fid, {})
        row = raw.get(fid, [])
        notes = []

        # 施設種別。診療所だけ病床数で分ける
        cond = ""
        if args.sector == "clinic":
            beds = row[idx["合計病床数"]].strip() if row and has_beds else ""
            cond = "病床1以上" if beds.isdigit() and int(beds) > 0 else "病床0または空欄"
        ft = ftags[args.sector].get(cond) or ftags[args.sector].get("")
        if ft is None:
            sys.exit(f"施設種別の対応が見つかりません: {args.sector} / {cond}")
        if ft["確度"] == "broader":
            notes.append(f"施設種別を推定: {ft['備考']}")
            stat["施設種別が推定"] += 1

        website = ""
        if has_web and row:
            website, why = clean_url(row[idx[has_web]])
            if why:
                notes.append(why)
                stat["website を補った" if website else "website を落とした"] += 1

        beds_tag = ""
        if has_beds and row:
            b = row[idx["合計病床数"]].strip()
            if b.isdigit() and int(b) > 0:
                beds_tag = b

        if g["座標の出典"] == "ジオコーディング":
            notes.append(f"座標は住所から付与（位置レベル{g['位置レベル']}）")
            stat["座標が付与"] += 1
        else:
            stat["座標が元データ"] += 1

        oh, why = fit_opening_hours(hr.get("opening_hours", ""))
        if why:
            notes.append(why)
            stat["opening_hours を短縮" if oh else "opening_hours を落とした"] += 1

        # 推定の番地は出さない。台帳と突き合わせられた8,219件のうち番地が
        # 実在したのは33.9%で、街区符号が100を超える545件は0%だった。
        # 誤った番地は OSM 上で別の建物を指すため、無いほうがましと判断した。
        # 元の住所文字列は addr:full に全件残るので、情報は失われない。
        # 対象は 番地の根拠 列で数えられる。
        inferred = g.get("番地の根拠", "") == "推定"
        block_number = "" if inferred else g.get("addr:block_number", "")
        housenumber = "" if inferred else g.get("addr:housenumber", "")
        if inferred and (g.get("addr:block_number") or g.get("addr:housenumber")):
            notes.append("番地が推定のため addr:block_number と addr:housenumber を出さない")

        tags = {
            "amenity": ft["amenity"].strip(),
            "healthcare": ft["healthcare"].strip(),
            "name": nm.get("name", ""),
            "official_name": nm.get("official_name", ""),
            "short_name": nm.get("short_name", ""),
            "name:ja-Hira": nm.get("name:ja-Hira", ""),
            "name:ja-Latn": nm.get("name:ja-Latn", ""),
            "name:en": nm.get("name:en", ""),
            "opening_hours": oh,
            "healthcare:speciality": sp.get("healthcare:speciality", ""),
            "website": website,
            "addr:full": g["元_所在地"],
            "addr:country": g.get("addr:country", ""),
            "addr:province": g.get("addr:province", ""),
            "addr:county": g.get("addr:county", ""),
            "addr:city": g.get("addr:city", ""),
            "addr:suburb": g.get("addr:suburb", ""),
            "addr:quarter": g.get("addr:quarter", ""),
            "addr:neighbourhood": g.get("addr:neighbourhood", ""),
            "addr:block_number": block_number,
            "addr:housenumber": housenumber,
            "note": g.get("未解釈の文字列", ""),
            "fixme": g.get("fixme", ""),
            "beds": beds_tag,
            "source": SOURCE,
        }
        tags = {k: v for k, v in tags.items() if v}

        review = "yes" if (nm.get("要確認") or hr.get("要確認") or g.get("要確認")
                           or ft["確度"] == "broader") else ""
        rows.append((fid, g["都道府県コード"], la, lo, g["座標の出典"], tags, review,
                     " / ".join(notes)))
        features.append({
            "type": "Feature",
            # GeoJSON は経度が先。緯度を先に置くと日本の施設が海上へ飛ぶ
            "geometry": {"type": "Point", "coordinates": [lo, la]},
            "properties": {**tags, "_id": fid, "_座標の出典": g["座標の出典"]},
        })
        stat["出力"] += 1

    keys = ["amenity", "healthcare", "name", "official_name", "short_name",
            "name:ja-Hira", "name:ja-Latn", "name:en", "opening_hours",
            "healthcare:speciality", "website", "addr:full",
            "addr:country", "addr:province", "addr:county", "addr:city",
            "addr:suburb", "addr:quarter", "addr:neighbourhood",
            "addr:block_number", "addr:housenumber", "note", "fixme",
            "beds", "source"]
    os.makedirs(args.out_dir, exist_ok=True)
    csv_path = os.path.join(args.out_dir, f"{args.sector}_osm.csv")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ID", "都道府県コード", "lat", "lon", "座標の出典"] + keys
                   + ["要確認", "備考"])
        for fid, pref, la, lo, origin, tags, review, note in rows:
            w.writerow([fid, pref, la, lo, origin]
                       + [tags.get(k, "") for k in keys] + [review, note])

    gj_path = os.path.join(args.out_dir, f"{args.sector}_osm.geojson")
    with open(gj_path, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": features},
                  f, ensure_ascii=False)

    print()
    for k in sorted(stat):
        print(f"  {k:<24} {stat[k]:>8,}")
    filled = collections.Counter()
    for _, _, _, _, _, tags, _, _ in rows:
        for k in keys:
            if tags.get(k):
                filled[k] += 1
    print("\n  タグの充足率:")
    for k in keys:
        n = filled[k]
        if n:
            print(f"    {k:<24} {n:>8,} ({n / max(len(rows), 1) * 100:5.1f}%)")
    print(f"\n出力: {csv_path}")
    print(f"      {gj_path}")


if __name__ == "__main__":
    main()
