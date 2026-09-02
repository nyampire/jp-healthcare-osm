#!/usr/bin/env python3
"""build_osm.py の coord_note の逆テスト。

ジオコーディングで座標を付けた行の 備考 に何を書くかを決める関数。
元データの座標を捨てた行では、捨てた値と理由を作業者に見せる必要がある。
その値は geocoded.csv の 座標の理由 列に入っている。

固定しているのは3件。
  1. 座標の理由が入っていれば、その文をそのまま返す
  2. 座標の理由が空なら、位置レベルだけの定型文を返す
  3. 座標の理由の列そのものが無くても、定型文を返す

3 は古い geocoded.csv を読んだときの経路。列を足す前に作った出力が
残っていても、KeyError で止まらずに今までどおり動く必要がある。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_osm import coord_note  # noqa: E402


def main():
    reason = ("元データの座標 35.085644, 137.190795 が熊本県ではなく"
              "東京都と愛知県の範囲にあるため、ジオコーダ座標を採用")
    cases = [
        ("座標の理由があればその文を返す",
         coord_note({"位置レベル": "3", "座標の理由": reason}), reason),
        ("座標の理由が空なら位置レベルの定型文を返す",
         coord_note({"位置レベル": "8", "座標の理由": ""}),
         "座標は住所から付与（位置レベル8）"),
        ("座標の理由の列が無くても定型文を返す",
         coord_note({"位置レベル": "3"}),
         "座標は住所から付与（位置レベル3）"),
    ]

    failed = 0
    print("=== build_osm.py coord_note 逆テスト ===\n")
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
