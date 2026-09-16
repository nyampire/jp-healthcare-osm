#!/usr/bin/env python3
"""build_names.py の needs_review の逆テスト。

作業者の確認が要る施設かどうかを決める関数。MapRoulette は 要確認 が
立った行しかタスクにしないので、ここで立てるかどうかがそのまま
作業者に届くかどうかになる。

固定しているのは、運営主体を除去したことを理由にしない点である。
除去した文字列は official_name に残り、operator も出していないため、
作業者が現地で確かめる対象が無い。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_names import needs_review  # noqa: E402


def main():
    cases = [
        ("運営主体を除去しただけでは立てない",
         needs_review("札幌厚生病院", "", "", ""), ""),
        ("name が空なら立てる",
         needs_review("", "", "", ""), "yes"),
        ("英語表記があるのにどちらも出せなければ立てる",
         needs_review("札幌厚生病院", "Sapporo Kosei Byoin", "", ""), "yes"),
        ("英語表記から name:en を出せたら立てない",
         needs_review("札幌厚生病院", "Sapporo Kosei Hospital",
                      "Sapporo Kosei Hospital", ""), ""),
        ("英語表記から name:ja-Latn を出せたら立てない",
         needs_review("札幌厚生病院", "Sapporo Kosei Byoin",
                      "", "Sapporo Kosei Byoin"), ""),
        ("英語表記が無ければ立てない",
         needs_review("札幌厚生病院", "", "", ""), ""),
        ("name が空なら英語表記を出せていても立てる",
         needs_review("", "Sapporo", "Sapporo", ""), "yes"),
    ]

    failed = 0
    print("=== build_names.py needs_review 逆テスト ===\n")
    for name, got, want in cases:
        ok = got == want
        if not ok:
            failed += 1
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
        if not ok:
            print(f"        実際: {got!r}")
            print(f"        期待: {want!r}")
    print(f"\n  {len(cases) - failed}/{len(cases)} 件")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
