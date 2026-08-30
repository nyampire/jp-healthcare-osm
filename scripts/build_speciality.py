#!/usr/bin/env python3
"""医療情報ネット オープンデータから OSM 用 healthcare:speciality を生成する。

対応業態: 病院 / 診療所 / 歯科診療所（診療科・診療時間票を持つ3業態）

入力 (--sector で選択):
  NN-2_..._speciality_hours_YYYYMMDD.csv 診療科・診療時間票
  mapping/speciality_mapping.csv         診療科目コード → OSM 値の対応表

出力 (output/):
  <業態>_speciality.csv  施設単位の healthcare:speciality と、丸めた診療科の内訳

  同じコードが業態によって別の意味で使われることがあるため、対応表は業態別の
  上書きを持てる。例えば 08991 は病院では口腔腫瘍外科だが、歯科診療所では
  インプラント・審美歯科・訪問歯科が大半を占める。「業態」列が空の行が既定で、
  業態名の入った行がその業態でのみ優先される。

処理方針:
  対応表はスクリプトに埋め込まず CSV に外出ししている。126コードの対応付けは
  医学的な判断を含み、第三者がレビューして直せる形である必要があるため。
  対応表を書き換えれば再実行するだけで出力が変わる。

  診療科目名は 126 コードに対し 523 種と揺れが大きいので、対応付けは必ず
  コードを鍵にする。名称は人が対応表を読むときの手がかりとしてのみ使う。

  「対応の確度」列の意味:
    exact   … OSM 側に対応する値がある
    broader … 対応する値が無く、上位概念に丸めた。情報が粗くなる
    none    … 対応付けできず出力しない

  末尾が 991/992 のコードは「その他（内科系）」等の総括枠で、1コードに最大151種の
  自由記述がぶら下がる。上位概念に丸める以外に扱いようがないため broader とし、
  丸めた事実を施設ごとの備考に残す。
"""

import argparse
import collections
import csv
import glob
import os
import sys

SECTORS = {
    "hospital": ("病院", "01-1_hospital_facility_info_*.csv",
                 "01-2_hospital_speciality_hours_*.csv"),
    "clinic": ("診療所", "02-1_clinic_facility_info_*.csv",
               "02-2_clinic_speciality_hours_*.csv"),
    "dental": ("歯科診療所", "03-1_dental_facility_info_*.csv",
               "03-2_dental_speciality_hours_*.csv"),
}

MAPPING_DEFAULT = os.path.join("mapping", "speciality_mapping.csv")
ROLLUP_DEFAULT = os.path.join("mapping", "speciality_rollup.csv")

# OSM のタグ値の上限
MAX_TAG_LENGTH = 255
# 畳んでも収まらない施設に与える値
CATCH_ALL_VALUE = "general"


def load_mapping(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        out = {}
        for row in csv.DictReader(f):
            key = (row.get("業態", "").strip(), row["診療科目コード"].strip())
            out[key] = {
                "name": row["診療科目名(最頻)"],
                "value": row["healthcare:speciality"].strip(),
                "confidence": row["対応の確度"].strip(),
                "source": row["出典"].strip(),
                "note": row["備考"].strip(),
            }
        return out


def load_rollup(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        return {row["値"].strip(): row["畳み先"].strip()
                for row in csv.DictReader(f) if row["畳み先"].strip()}


def apply_rollup(values, rollup):
    out = []
    for v in values:
        t = rollup.get(v, v)
        if t not in out:
            out.append(t)
    return out


def fit_to_limit(values, rollup):
    """255文字に収まる値と、適用した段階を返す。"""
    joined = ";".join(values)
    if len(joined) <= MAX_TAG_LENGTH:
        return joined, ""
    rolled = apply_rollup(values, rollup)
    joined = ";".join(rolled)
    if len(joined) <= MAX_TAG_LENGTH:
        return joined, "rollup"
    return CATCH_ALL_VALUE, "catch_all"


def load_departments(path):
    """施設ID -> {診療科目コード: 最頻の診療科目名} を返す。"""
    fac = collections.defaultdict(dict)
    with open(path, encoding="utf-8-sig", newline="") as f:
        r = csv.reader(f)
        idx = {h: n for n, h in enumerate(next(r))}
        for row in r:
            fac[row[0]][row[idx["診療科目コード"]]] = row[idx["診療科目名"]]
    return fac


def load_names(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        r = csv.reader(f)
        idx = {h: n for n, h in enumerate(next(r))}
        return {row[0]: (row[idx["正式名称"]], row[idx["都道府県コード"]]) for row in r}


def resolve(path, pattern):
    hits = sorted(glob.glob(os.path.join(path, pattern)))
    if not hits:
        sys.exit(f"入力ファイルが見つかりません: {pattern}")
    return hits[-1]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir", default=".")
    p.add_argument("--out-dir", default="output")
    p.add_argument("--mapping", default=MAPPING_DEFAULT)
    p.add_argument("--rollup", default=ROLLUP_DEFAULT)
    p.add_argument("--sector", default="hospital", choices=sorted(SECTORS))
    args = p.parse_args()

    sector = args.sector
    label, pat1, pat2 = SECTORS[sector]
    f1 = resolve(args.data_dir, pat1)
    f2 = resolve(args.data_dir, pat2)
    print(f"業態       : {label}")
    print(f"診療時間票 : {os.path.basename(f2)}")
    print(f"対応表     : {args.mapping}")

    mapping = load_mapping(args.mapping)
    rollup = load_rollup(args.rollup)
    names = load_names(f1)
    fac = load_departments(f2)

    unknown_codes = collections.Counter()
    rows = []
    stats = collections.Counter()
    value_use = collections.Counter()

    for fid, depts in fac.items():
        values = []
        broader = []
        unmapped = []
        for code, dept_name in sorted(depts.items()):
            m = mapping.get((sector, code)) or mapping.get(("", code))
            if m is None:
                unknown_codes[code] += 1
                unmapped.append(f"{code} {dept_name}")
                continue
            if not m["value"] or m["confidence"] == "none":
                unmapped.append(f"{code} {dept_name}")
                continue
            # 1コードが複数値に対応する場合があるので分解して重複を除く
            for v in m["value"].split(";"):
                if v and v not in values:
                    values.append(v)
            if m["confidence"] == "broader":
                broader.append(f"{dept_name}→{m['value']}")

        value, shortening = fit_to_limit(values, rollup)
        emitted = [v for v in value.split(";") if v]
        for v in emitted:
            value_use[v] += 1
        if shortening:
            stats[f"短縮:{shortening}"] += 1
        notes = []
        if shortening == "rollup":
            notes.append(f"255文字超のため細分値を上位科に畳んだ（{len(values)}値→{len(emitted)}値）")
        elif shortening == "catch_all":
            notes.append(
                f"畳んでも255文字を超えるため {CATCH_ALL_VALUE} 単独にした。"
                f"畳む前の{len(values)}値: " + ";".join(values))
        if broader:
            head = "、".join(broader[:3])
            if len(broader) > 3:
                head += f" 他{len(broader) - 3}件"
            notes.append(f"上位概念に丸めた診療科 {len(broader)}件: {head}")
        if unmapped:
            notes.append(f"対応値なしで出力しなかった診療科 {len(unmapped)}件: "
                         + "、".join(unmapped[:3]))
        name, pref = names.get(fid, ("", ""))
        rows.append([fid, name, pref, value, len(depts), len(emitted),
                     len(broader), len(unmapped), shortening, " / ".join(notes)])
        stats["施設"] += 1
        if value:
            stats["値あり"] += 1
        if broader:
            stats["丸めあり"] += 1
        if unmapped:
            stats["未対応あり"] += 1

    build_dir = os.path.join(args.out_dir, "build")
    os.makedirs(build_dir, exist_ok=True)
    with open(os.path.join(build_dir, f"{sector}_speciality.csv"), "w",
              encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ID", "正式名称", "都道府県コード", "healthcare:speciality",
                    "診療科数", "値の数", "丸めた数", "未対応数", "短縮", "備考"])
        w.writerows(sorted(rows))

    conf = collections.Counter(m["confidence"] for k, m in mapping.items()
                               if k[0] in ("", sector))
    print()
    applicable = [k for k in mapping if k[0] in ("", sector)]
    print(f"対応表のコード数       : {len(applicable)}"
          f"（うち{label}専用 {sum(1 for k in applicable if k[0])}件）")
    for k in ("exact", "broader", "none"):
        if conf[k]:
            print(f"    {conf[k]:4d}  {k}")
    print(f"施設数                 : {stats['施設']:,}")
    print(f"値を生成できた施設     : {stats['値あり']:,}")
    print(f"丸めを含む施設         : {stats['丸めあり']:,}")
    print(f"未対応を含む施設       : {stats['未対応あり']:,}")
    print(f"255文字超のため畳んだ  : {stats['短縮:rollup']:,}")
    print(f"畳んでも収まらず {CATCH_ALL_VALUE} : {stats['短縮:catch_all']:,}")
    if unknown_codes:
        print(f"対応表に無いコード     : {len(unknown_codes)} 種 "
              f"{list(unknown_codes)[:5]}")
    print()
    print("生成された値の使用施設数 上位12:")
    for v, n in value_use.most_common(12):
        print(f"  {n:6,}  {v}")


if __name__ == "__main__":
    main()
