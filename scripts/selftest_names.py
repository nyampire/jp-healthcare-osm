#!/usr/bin/env python3
"""build_names.py の needs_review と strip_entity の逆テスト。

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
from build_names import needs_review, strip_entity  # noqa: E402

PFX = ["医療法人社団", "医療法人"]
SUF = ["会", "機構"]
FW = ["病院", "医院", "診療所", "クリニック", "歯科"]
SPEC = {"内科", "外科", "消化器内科", "歯科"}
OPW = ["国民健康保険", "市立"]


def strip(name, short=""):
    return strip_entity(name, PFX, SUF, FW, short, SPEC, OPW)


def main():
    cases = [
        ("name が空なら立てる", needs_review(""), "yes"),
        ("空白だけの name も空として扱う", needs_review("  "), "yes"),
        ("name があれば立てない", needs_review("札幌厚生病院"), ""),
        ("推定で落とした語があれば立てる",
         needs_review("歯科", "先頭の「楠井」を運営主体とみなした"), "yes"),
    ]

    # strip_entity。先頭トークンを運営主体と推定してよいかを、元データの
    # 略称で確かめる。略称が「落とす語 + 残り」なら施設名の一部である。
    def eq(label, got, want):
        cases.append((label, got, want))

    eq("略称が施設名の一部と示すなら落とさない",
       strip("楠井 歯科", "楠井歯科"), ("楠井 歯科", [], []))
    eq("略称に法人格が残るなら落とす",
       strip("医療法人ことはる 東栄内科クリニック", "医療法人ことはる 東栄内科クリニック"),
       ("東栄内科クリニック", ["医療法人", "ことはる"], ["ことはる"]))
    eq("略称が無ければ従来どおり落とす",
       strip("楠井 歯科", ""), ("歯科", ["楠井"], ["楠井"]))
    eq("診療科そのものは略称に残っていても落とす",
       strip("消化器内科 中畑クリニック", "消化器内科中畑クリニック"),
       ("中畑クリニック", ["消化器内科"], ["消化器内科"]))
    eq("運営主体の語は略称に残っていても落とす",
       strip("国民健康保険 風間浦診療所", "国民健康保険風間浦診療所"),
       ("風間浦診療所", ["国民健康保険"], ["国民健康保険"]))
    eq("法人格の除去は推定に数えない",
       strip("医療法人社団祐川整形外科医院", "医療法人社団祐川整形外科医院"),
       ("祐川整形外科医院", ["医療法人社団"], []))

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
