#!/usr/bin/env python3
"""診療科目コードと healthcare:speciality の対応を一覧文書にする。

入力:
  mapping/speciality_mapping.csv          対応表
  mapping/speciality_rollup.csv           長さ超過時の畳み先
  NN-2_..._speciality_hours_YYYYMMDD.csv  施設数の集計に使う

出力:
  docs/speciality-mapping.md

対応表を手で書き写すと、表を編集したときに文書がずれる。
そのため対応表から生成する。対応表を直したら再実行する。
"""

import collections
import csv
import glob
import os
import sys

SECTORS = [("hospital", "病院", "01-2_hospital_speciality_hours_*.csv"),
           ("clinic", "診療所", "02-2_clinic_speciality_hours_*.csv"),
           ("dental", "歯科診療所", "03-2_dental_speciality_hours_*.csv")]

# コードの上2桁が診療科の系統を表す
FAMILIES = [("01", "内科系"), ("02", "外科系"), ("03", "小児科系"),
            ("04", "産婦人科系"), ("05", "眼科と耳鼻いんこう科系"),
            ("06", "皮膚科と泌尿器科系"), ("07", "精神科系"),
            ("08", "歯科系"), ("09", "その他")]

CONFIDENCE_NOTE = {
    "exact": "OSM 側に対応する値がある",
    "broader": "対応する値が無く、上位概念に丸めた",
    "none": "対応付けできず出力しない",
}


def resolve(pattern):
    hits = sorted(glob.glob(pattern))
    if not hits:
        sys.exit(f"入力ファイルが見つかりません: {pattern}")
    return hits[-1]


def count_facilities():
    """(業態, コード) -> 施設数 と、コード -> 業態別内訳 を返す。"""
    counts = collections.defaultdict(set)
    for key, _, pattern in SECTORS:
        path = resolve(pattern)
        with open(path, encoding="utf-8-sig", newline="") as f:
            r = csv.reader(f)
            idx = {h: n for n, h in enumerate(next(r))}
            col = idx["診療科目コード"]
            for row in r:
                counts[(key, row[col])].add(row[0])
    return {k: len(v) for k, v in counts.items()}


def load_mapping(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def main():
    rows = load_mapping(os.path.join("mapping", "speciality_mapping.csv"))
    rollup = load_mapping(os.path.join("mapping", "speciality_rollup.csv"))
    counts = count_facilities()

    # 既定の行と業態別の上書きを分ける
    default = {r["診療科目コード"]: r for r in rows if not r["業態"].strip()}
    override = collections.defaultdict(dict)
    for r in rows:
        if r["業態"].strip():
            override[r["業態"].strip()][r["診療科目コード"]] = r

    # 値から見た逆引き。どの診療科がその値に集まるかを示す
    reverse = collections.defaultdict(list)
    for code, r in sorted(default.items()):
        for v in r["healthcare:speciality"].split(";"):
            if v:
                reverse[v].append((code, r["診療科目名(最頻)"], r["対応の確度"]))

    out = []
    w = out.append
    w("# 診療科目コードと healthcare:speciality の対応")
    w("")
    w("`mapping/speciality_mapping.csv` の内容を読みやすくしたものです。")
    w("この文書は対応表から生成しています。")
    w("対応表を直したら `python3 scripts/build_speciality_doc.py` で作り直してください。")
    w("")
    w("変換処理の考え方は [processing.md](processing.md) を参照してください。")
    w("")
    w("## 対応の確度")
    w("")
    w("各行には対応の確からしさを付けています。")
    w("")
    for k in ("exact", "broader", "none"):
        n = sum(1 for r in default.values() if r["対応の確度"] == k)
        if n:
            w(f"- `{k}` は、{CONFIDENCE_NOTE[k]}ものです（{n}件）。")
    w("")
    w("`broader` は情報が粗くなります。")
    w("なぜ丸めたかを備考に書いているので、値を見直すときの手がかりにしてください。")
    w("")

    w("## 値から見た一覧")
    w("")
    w("ひとつの OSM 値に複数の診療科が集まる場合があります。")
    w("どこで情報が粗くなっているかは、この向きで見ると分かります。")
    w("")
    w("左の列は、その OSM 値が本来指す診療科です（確度 `exact`）。")
    w("右の列は、対応する値が無いため、やむを得ずその値へ寄せた診療科です（確度 `broader`）。")
    w("右の列に入った診療科は、OSM 側では左の列の診療科と区別が付きません。")
    w("")
    w("たとえば `gastroenterology` の行はこう読みます。")
    w("消化器内科と胃腸内科は、この値が本来指す診療科です。")
    w("内視鏡内科には対応する値が無いため、この値へ寄せました。")
    w("その結果、内視鏡内科だけを持つ施設と消化器内科を持つ施設は、")
    w("タグの上では同じ `gastroenterology` になります。")
    w("")
    w("右の列が空の行は、寄せた診療科が無く、情報が粗くなっていません。")
    w("")
    w("| healthcare:speciality | 本来指す診療科 | 寄せた診療科 |")
    w("|---|---|---|")
    for v in sorted(reverse, key=lambda x: (-len(reverse[x]), x)):
        items = reverse[v]
        exact = "、".join(n for _, n, c in items if c != "broader")
        wide = "、".join(n for _, n, c in items if c == "broader")
        w(f"| `{v}` | {exact} | {wide} |")
    w("")

    w("## コードから見た一覧")
    w("")
    w("施設数は、その診療科を持つ施設の数です。")
    w("同じ施設が複数の診療科を持つため、合計は施設総数と一致しません。")
    w("")
    for prefix, name in FAMILIES:
        codes = sorted(c for c in default if c.startswith(prefix))
        if not codes:
            continue
        w(f"### {prefix} {name}")
        w("")
        w("| コード | 診療科目名 | healthcare:speciality | 確度 | 病院 | 診療所 | 歯科 | 備考 |")
        w("|---|---|---|---|---:|---:|---:|---|")
        for c in codes:
            r = default[c]
            n = [counts.get((k, c), 0) for k, _, _ in SECTORS]
            cells = [f"{x:,}" if x else "" for x in n]
            note = r["備考"].replace("|", r"\|")
            w(f"| `{c}` | {r['診療科目名(最頻)']} | `{r['healthcare:speciality']}` | "
              f"{r['対応の確度']} | {cells[0]} | {cells[1]} | {cells[2]} | {note} |")
        w("")

    if override:
        w("## 業態別の上書き")
        w("")
        w("同じコードが業態によって別の意味で使われることがあります。")
        w("その場合は業態を指定した行を置き、その業態でのみ優先します。")
        w("")
        w("| 業態 | コード | 診療科目名 | healthcare:speciality | 確度 | 備考 |")
        w("|---|---|---|---|---|---|")
        label = {k: n for k, n, _ in SECTORS}
        for sector in sorted(override):
            for c in sorted(override[sector]):
                r = override[sector][c]
                note = r["備考"].replace("|", r"\|")
                w(f"| {label.get(sector, sector)} | `{c}` | {r['診療科目名(最頻)']} | "
                  f"`{r['healthcare:speciality']}` | {r['対応の確度']} | {note} |")
        w("")

    w("## タグ値が 255 文字を超えたときの畳み先")
    w("")
    w("診療科をすべて並べると OSM のタグ値の上限を超える施設があります。")
    w("超えた施設だけ、細分値を上位科へ畳みます。")
    w("主要な診療科は畳まずに残します。")
    w("")
    w("| 値 | 畳み先 | 備考 |")
    w("|---|---|---|")
    for r in rollup:
        w(f"| `{r['値']}` | `{r['畳み先']}` | {r['備考']} |")
    w("")

    w("## 対応値が無い診療科")
    w("")
    w("OSM の語彙に対応する値が無く、上位概念へ丸めた診療科のうち、")
    w("影響する施設数が多いものを挙げます。")
    w("imports メーリングリストでの論点になります。")
    w("")
    w("| 診療科目名 | 現在の値 | 施設数 | 論点 |")
    w("|---|---|---:|---|")
    review = []
    for c, r in default.items():
        if r["対応の確度"] != "broader" or "要検討" not in r["備考"]:
            continue
        total = sum(counts.get((k, c), 0) for k, _, _ in SECTORS)
        review.append((total, r["診療科目名(最頻)"], r["healthcare:speciality"], r["備考"]))
    for total, nm, v, note in sorted(review, reverse=True):
        w(f"| {nm} | `{v}` | {total:,} | {note} |")
    w("")

    path = os.path.join("docs", "speciality-mapping.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print(f"生成: {path}")
    print(f"  コード数     : {len(default)}")
    print(f"  業態別の上書き: {sum(len(v) for v in override.values())}")
    print(f"  異なり値     : {len(reverse)}")
    print(f"  要検討       : {len(review)}")


if __name__ == "__main__":
    main()
