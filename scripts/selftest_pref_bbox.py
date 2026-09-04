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

あわせて、生成側が47県に満たない住所データで止まることも確かめる。
"""

import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from prefectures import PREF  # noqa: E402



def check_builder_stops_short(root):
    """47県に満たない住所データで build_pref_bbox.js が落ちること。

    住所データの取得先を間違えて指すと、都道府県のディレクトリが一部しか
    見つからない。生成側はそれを検出せず、少ない県だけの表を書き出して
    終了コード0を返す。その表を pref_bbox.js が読むと、載っていない県の
    施設は outOfPref が null を返し、県外の規則が黙って働かなくなる。

    2県ぶんの偽の住所データを作って走らせ、終了コードと、
    mapping/pref_bbox.csv が書き換わっていないことを見る。
    """
    table = os.path.join(root, "mapping", "pref_bbox.csv")
    with open(table, "rb") as f:
        before = f.read()

    tmp = tempfile.mkdtemp(prefix="osm-iryo-bbox-")
    try:
        for name, code in (("東京都", 131011), ("熊本県", 432011)):
            with open(os.path.join(tmp, name + ".json"), "w", encoding="utf-8") as f:
                json.dump({"data": [{"code": code}]}, f)
            os.mkdir(os.path.join(tmp, name))
            with open(os.path.join(tmp, name, "city.json"), "w", encoding="utf-8") as f:
                json.dump({"data": [{"point": [139.7, 35.6]},
                                    {"point": [139.8, 35.7]}]}, f)
        env = dict(os.environ, NJA_API_BASE=tmp)
        r = subprocess.run(
            [shutil.which("node") or "node",
             os.path.join(root, "scripts", "build_pref_bbox.js")],
            capture_output=True, text=True, env=env)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    with open(table, "rb") as f:
        after = f.read()
    # 検査より前に書き出していると本物の表が2県で潰れる。戻してから落とす。
    if after != before:
        with open(table, "wb") as f:
            f.write(before)

    return [
        ("47県に満たない住所データで生成側が落ちる", r.returncode, 1),
        ("落ちるときに県数を知らせる",
         "47" in r.stderr and "2" in r.stderr, True),
        ("落ちるとき mapping/pref_bbox.csv を書き換えない", after == before, True),
    ]


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
    cases += check_builder_stops_short(ROOT)

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
