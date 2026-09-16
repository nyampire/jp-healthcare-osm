#!/usr/bin/env python3
"""build_names.py の needs_review の逆テスト。

作業者の確認が要る施設かどうかを決める関数。MapRoulette は 要確認 が
立った行しかタスクにしないので、ここで立てるかどうかがそのまま
作業者に届くかどうかになる。

固定しているのは、出力に欠けが無い行で 要確認 を立てない点である。
運営主体を除去した行は、除去した文字列が official_name に残り operator も
出していない。元データの英語表記を採用しなかった行は、name と official_name
がどちらも出ている。どちらも作業者が現地で確かめる対象が無い。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_names import needs_review  # noqa: E402


def main():
    cases = [
        ("name が空なら立てる", needs_review(""), "yes"),
        ("空白だけの name も空として扱う", needs_review("  "), "yes"),
        ("name があれば立てない", needs_review("札幌厚生病院"), ""),
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
