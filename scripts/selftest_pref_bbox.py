#!/usr/bin/env python3
"""mapping/pref_bbox.csv の県名を、県名の唯一の表と突き合わせる逆テスト。

outOfPref は box[province] が引けないとき null を返す。安全側に倒しているので、
表の県名が nja の addr:province とずれても例外は出ない。規則が全行で
黙って働かなくなり、逆テストも通ってしまう。

県名の表は scripts/prefectures.py の PREF ひとつだけに持つ決まりなので、
生成物である mapping/pref_bbox.csv がそれと一致することを検査する。

固定しているのは3件。
  1. コードと県名の対応が PREF と1件残らず一致する
  2. 県名に重複が無い（重複すると後の行が前の行の矩形を上書きする）
  3. 県名の前後に空白や引用符が混ざっていない
"""

import csv
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from prefectures import PREF  # noqa: E402


def main():
    path = os.path.join(ROOT, "mapping", "pref_bbox.csv")
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    got = {r["都道府県コード"]: r["都道府県"] for r in rows}
    names = [r["都道府県"] for r in rows]

    cases = [
        ("コードと県名の対応が prefectures.py の PREF と一致する", got, PREF),
        ("県名に重複が無い", len(set(names)), len(names)),
        ("県名に空白や引用符が混ざっていない",
         [n for n in names if n != n.strip() or '"' in n], []),
    ]

    failed = 0
    print("=== mapping/pref_bbox.csv の県名 逆テスト ===\n")
    for name, got_v, want in cases:
        ok = got_v == want
        if not ok:
            failed += 1
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
        if not ok:
            if isinstance(got_v, dict) and isinstance(want, dict):
                for k in sorted(set(got_v) | set(want)):
                    if got_v.get(k) != want.get(k):
                        print(f"        {k}: 表 \"{got_v.get(k)}\" / PREF \"{want.get(k)}\"")
            else:
                print(f"        実際: {got_v}")
                print(f"        期待: {want}")
    print(f"\n  {len(cases) - failed}/{len(cases)} 件")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
