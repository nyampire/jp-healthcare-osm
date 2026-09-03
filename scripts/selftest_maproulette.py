#!/usr/bin/env python3
"""build_maproulette.py の clip_notes の逆テスト。

MapRoulette のタスクに載せる _要確認 を200文字に収める関数。
文の途中で切ると、座標の数値が「元データの座標 33.5」のように途中で
終わり、作業者には妥当な座標に見える。情報が消えるより悪い切れ方なので、
" / " の境界で切る必要がある。

固定しているのは5件。
  1. 上限以下の文字列はそのまま返す
  2. 上限を超えたら " / " の境界で切り、文の途中で終わらせない
  3. 先頭の1文だけで上限を超えるときは文字数で切る（これしか手が無い）
  4. 実データの最長（247文字）で、捨てた座標の理由が丸ごと残る
  5. 空文字列を渡しても落ちない
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_maproulette import clip_notes  # noqa: E402


def main():
    reason = ("元データの座標 37.531447, 140.432731 がジオコーダ座標から"
              "1,023,692m離れているため、ジオコーダ座標を採用")
    boiler = ("施設種別を推定: 暫定値。病床数が空欄の31399件を無床とみなしている。"
              "空欄は未記入であって無床の証拠ではない。一律clinicにする案もあり、"
              "コミュニティでの合意待ち")
    hours = ("255文字を超えたため末尾の規則1件を落とした: "
             "Jun 04,Jun 11,Jun 18,Jun 25,Jul 02,Jul 09,Jul 16,Jul 23,Jul 30,"
             "Aug 06,Aug 12-Aug")
    # 実際の並び順。行に固有の文が先、定型文が最後（build_osm.py の join_notes）
    worst = " / ".join([reason, hours, boiler])

    cases = [
        ("上限以下はそのまま返す",
         clip_notes("あいうえお", 200), "あいうえお"),
        ("上限を超えたら境界で切る",
         clip_notes("あいう / かきく / さしす", 12), "あいう / かきく"),
        ("先頭の1文だけで上限を超えるなら文字数で切る",
         clip_notes("あいうえおかきくけこ / さしす", 5), "あいうえお"),
        ("実データの最長でも理由が丸ごと残る",
         reason in clip_notes(worst, 200), True),
        ("切った結果が文の途中で終わらない",
         clip_notes(worst, 200) == " / ".join([reason, hours]), True),
        ("空文字列でも落ちない", clip_notes("", 200), ""),
    ]

    failed = 0
    print("=== build_maproulette.py clip_notes 逆テスト ===\n")
    for name, got, want in cases:
        ok = got == want
        if not ok:
            failed += 1
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
        if not ok:
            print(f"        実際: {got}")
            print(f"        期待: {want}")
    print(f"\n  {len(cases) - failed}/{len(cases)} 件")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
