#!/usr/bin/env python3
"""build_names.py が生成した名称タグを検証する。

生成側と独立した基準で確かめる:
  * 元の列が保持されているか（正規化で失われていないか）
  * name が空でないか、OSM のタグ値上限 255 文字を超えていないか
  * name に法人格が残っていないか（除去漏れ）
  * name:ja-Hira にカタカナが残っていないか（変換漏れ）
  * name:en / name:ja-Latn が ASCII 以外を含んでいないか
  * name:ja-Latn が読みの検証を経ずに出ていないか、name:en と重複していないか

終了コード: 欠陥が 1 件でもあれば 1、なければ 0。
"""

import argparse
import collections
import csv
import os
import re
import sys

MAX_TAG_LENGTH = 255
# name:ja-Hira にカタカナが残っていれば変換漏れ。元のフリガナにはラテン文字が
# 混じる例（…ういめんずJRたわー…）があり、それは元データどおりなので許容する。
RE_KATAKANA = re.compile(r"[ァ-ヴ]")
RE_ASCII_OK = re.compile(r"^[\x20-\x7E]*$")


def load_prefixes(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [r["パターン"].strip() for r in csv.DictReader(f)
                if r["パターン"].strip() and r["種別"].strip() == "法人格"]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("target")
    p.add_argument("--prefixes",
                   default=os.path.join("mapping", "name_entity_prefixes.csv"))
    args = p.parse_args()
    if not os.path.exists(args.target):
        sys.exit(f"入力ファイルがありません: {args.target}")

    prefixes = load_prefixes(args.prefixes)
    with open(args.target, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        sys.exit("行がありません")

    orig_col = next(c for c in rows[0] if c.startswith("元_") and c != "元_略称")
    issues = collections.defaultdict(list)

    for r in rows:
        name = r["name"]
        if not name:
            issues["name_empty"].append((r, "name が空"))
        elif len(name) > MAX_TAG_LENGTH:
            issues["name_too_long"].append((r, f"{len(name)}文字"))
        for pfx in prefixes:
            if name.startswith(pfx):
                issues["entity_left"].append((r, f"法人格が残っている: {pfx}"))
                break
        if not r["official_name"]:
            issues["official_missing"].append((r, "official_name が空"))
        elif r["official_name"] != r[orig_col]:
            issues["official_altered"].append((r, "official_name が元の値と違う"))
        hira = r["name:ja-Hira"]
        if hira and RE_KATAKANA.search(hira):
            bad = "".join(sorted(set(RE_KATAKANA.findall(hira))))
            issues["hira_katakana_left"].append(
                (r, f"カタカナが残っている {bad[:12]!r}: {hira[:40]}"))
        en = r["name:en"]
        if en and not RE_ASCII_OK.match(en):
            issues["en_not_ascii"].append((r, f"ASCII 以外を含む: {en[:40]}"))
        latn = r.get("name:ja-Latn", "")
        if latn:
            if not RE_ASCII_OK.match(latn):
                issues["latn_not_ascii"].append((r, f"ASCII 以外を含む: {latn[:40]}"))
            elif not r["name:ja-Hira"]:
                # 読みと突き合わせて検証したものだけを出すため、読みが無いのに
                # ローマ字だけあるのは生成側の不整合
                issues["latn_without_hira"].append((r, f"読みが無いのに出力: {latn[:40]}"))
            if en:
                issues["latn_and_en"].append(
                    (r, f"英語とローマ字の両方が出ている: en={en[:24]} latn={latn[:24]}"))

    report = [[k, r["ID"], r[orig_col], r["name"], d]
              for k, items in issues.items() for r, d in items]
    out = os.path.join(os.path.dirname(args.target) or ".",
                       os.path.basename(args.target).replace(".csv", "")
                       + "_validation.csv")
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["種別", "ID", "元の名称", "name", "内容"])
        w.writerows(report)

    print(f"検証対象   : {args.target}")
    print(f"  検証数           : {len(rows):,}")
    print(f"  name あり        : {sum(1 for r in rows if r['name']):,}")
    print(f"  name:ja-Hira あり: {sum(1 for r in rows if r['name:ja-Hira']):,}")
    print(f"  name:en あり     : {sum(1 for r in rows if r['name:en']):,}")
    print(f"  name:ja-Latn あり: {sum(1 for r in rows if r.get('name:ja-Latn')):,}")
    for k in ("name_empty", "name_too_long", "entity_left", "official_missing",
              "official_altered", "hira_katakana_left", "en_not_ascii",
              "latn_not_ascii", "latn_without_hira", "latn_and_en"):
        print(f"  {k:<18}: {len(issues[k]):,}")
        for r, d in issues[k][:2]:
            print(f"      {r[orig_col][:30]!r} → {r['name'][:30]!r} / {d}")
    print(f"\n詳細: {out}")
    sys.exit(1 if report else 0)


if __name__ == "__main__":
    main()
