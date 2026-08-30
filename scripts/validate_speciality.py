#!/usr/bin/env python3
"""build_speciality.py が生成した healthcare:speciality を検証する。

生成側と独立した基準で確かめる:
  * OSM のタグ値上限 255 文字を超えていないか
  * 値が OSM の語彙に存在するか（wiki 文書化値 / taginfo 実用値）
  * 値の書式（小文字英数と _ のみ、区切りは ; 、空要素や重複が無いか）

終了コード: 欠陥が 1 件でもあれば 1、なければ 0。
"""

import argparse
import collections
import csv
import os
import re
import sys

MAX_TAG_LENGTH = 255
VALUE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")

# wiki の Key:healthcare:speciality に記載された値
WIKI_VALUES = {
    "abdominal_surgery", "allergology", "anaesthetics", "angiology", "cardiology",
    "cardiothoracic_surgery", "child_psychiatry", "community", "dermatology",
    "dermatovenereology", "diagnostic_radiology", "emergency", "endocrinology",
    "gastroenterology", "general", "geriatrics", "gynaecology", "haematology",
    "hepatology", "infectious_diseases", "intensive", "internal",
    "dental_oral_maxillo_facial_surgery", "neonatology", "nephrology", "neurology",
    "pediatric_neurology", "neuropsychiatry", "neurosurgery", "nuclear",
    "occupational", "oncology", "ophthalmology", "orthodontics", "orthopaedics",
    "otolaryngology", "paediatric_surgery", "paediatrics", "palliative", "pathology",
    "perinatology", "physiatry", "plastic_surgery", "podiatry", "proctology",
    "psychiatry", "pulmonology", "radiology", "radiotherapy", "rheumatology",
    "stomatology", "surgery", "transplant", "trauma", "tropical", "urology",
    "vascular_surgery", "venereology", "weight_loss", "rehabilitation", "abortion",
    "fertility", "obstetric_ultrasonography", "urgent", "vaccination", "implantology",
    "endodontics", "paediatric_dentistry", "denturist", "periodontics",
    "dental_radiology", "clinical_pathology", "biology", "biochemistry", "blood_check",
    "traditional_chinese_medicine", "acupuncture", "homeopathy", "naturopathy",
    "osteopathy", "chiropractic", "ayurveda", "herbalism", "hypnosis", "reflexology",
    "reiki", "shiatsu",
}

# wiki には無いが taginfo で相当数使われている値。採用時は出典を明示する。
IN_USE_VALUES = {
    "dentistry": 1518,
    "dialysis": 483,
}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("target", nargs="?",
                   default=os.path.join("output", "speciality.csv"))
    p.add_argument("--report-dir", default=None,
                   help="検証結果の出力先。既定は入力ファイルと同じディレクトリ")
    args = p.parse_args()
    if not os.path.exists(args.target):
        sys.exit(f"入力ファイルがありません: {args.target}\n"
                 "先に scripts/build_speciality.py を実行してください。")

    with open(args.target, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    too_long = []
    bad_format = []
    unknown_value = []
    duplicated = []
    empty = 0
    value_use = collections.Counter()

    for r in rows:
        value = r["healthcare:speciality"]
        if not value:
            empty += 1
            continue
        if len(value) > MAX_TAG_LENGTH:
            too_long.append((r, f"{len(value)}文字（上限{MAX_TAG_LENGTH}）"))
        parts = value.split(";")
        if any(not v for v in parts):
            bad_format.append((r, "空の値が含まれる"))
        seen = [v for v, n in collections.Counter(parts).items() if n > 1]
        if seen:
            duplicated.append((r, f"重複した値: {','.join(seen)}"))
        for v in parts:
            if not v:
                continue
            value_use[v] += 1
            if not VALUE_PATTERN.match(v):
                bad_format.append((r, f"書式が不正な値: {v}"))
            elif v not in WIKI_VALUES and v not in IN_USE_VALUES:
                unknown_value.append((r, f"OSMの語彙に無い値: {v}"))

    report = []
    for kind, items in (("too_long", too_long), ("bad_format", bad_format),
                        ("unknown_value", unknown_value), ("duplicated", duplicated)):
        for r, detail in items:
            report.append([kind, r["ID"], r["正式名称"],
                           r["healthcare:speciality"][:120], detail])
    # 検証結果は入力ファイル名から導く。業態ごとに実行しても上書きされないようにする。
    report_dir = args.report_dir or os.path.dirname(args.target) or "."
    os.makedirs(report_dir, exist_ok=True)
    out = os.path.join(report_dir,
                       os.path.basename(args.target).replace(".csv", "")
                       + "_validation.csv")
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["種別", "ID", "正式名称", "healthcare:speciality", "内容"])
        w.writerows(report)

    lengths = [len(r["healthcare:speciality"]) for r in rows if r["healthcare:speciality"]]
    print(f"検証対象   : {args.target}")
    print(f"  検証数           : {len(lengths):,}")
    print(f"  値なし           : {empty:,}")
    print(f"  最大文字数       : {max(lengths) if lengths else 0}")
    print(f"  255文字超        : {len(too_long):,}")
    print(f"  書式不正         : {len(bad_format):,}")
    print(f"  語彙に無い値     : {len(unknown_value):,}")
    print(f"  値の重複         : {len(duplicated):,}")
    print(f"  異なり値数       : {len(value_use)}")

    in_use = [v for v in value_use if v in IN_USE_VALUES]
    if in_use:
        print("\n  wiki未文書だが実用値として採用:")
        for v in sorted(in_use):
            print(f"    {v:<12} taginfo {IN_USE_VALUES[v]:,}件 / 本データ {value_use[v]:,}施設")
    for kind, items in (("too_long", too_long), ("bad_format", bad_format),
                        ("unknown_value", unknown_value)):
        for r, detail in items[:3]:
            print(f"\n  {kind.upper()} {r['正式名称'][:26]}\n    {detail}")

    print(f"\n詳細: {out}")
    fatal = len(too_long) + len(bad_format) + len(unknown_value) + len(duplicated)
    sys.exit(1 if fatal else 0)


if __name__ == "__main__":
    main()
