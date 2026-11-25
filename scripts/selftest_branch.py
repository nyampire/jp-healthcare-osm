#!/usr/bin/env python3
"""branch_split.py の逆テスト。

分ける形と分けない形を固定する。分けない形は、文字列だけでは店名の
終わりを決められない形と、支店名が場所を示さない形である。
読み仮名とローマ字と英語名は、店名の部分を決められたときだけ返す。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from branch_split import (borrow_reading, split_english,  # noqa: E402
                          split_latn_by_reading, split_name, split_reading)


def main():
    cases = []

    def eq(name, got, want):
        cases.append((name, got == want, got))

    # 1. name を分ける形
    eq("空白の位置で分ける", split_name("アイン薬局 塚ノ原店"), ("アイン薬局", "塚ノ原店"))
    eq("空白が無ければ最後の薬局の直後で分ける",
       split_name("つつじ薬局潮見店"), ("つつじ薬局", "潮見店"))
    eq("調剤薬局で終わる店名も分ける",
       split_name("かもめ調剤薬局東浜店"), ("かもめ調剤薬局", "東浜店"))
    eq("店名が薬局で終わらなくても空白があれば分ける",
       split_name("薬局マツモトキヨシ 松戸新田店"), ("薬局マツモトキヨシ", "松戸新田店"))
    eq("中黒の区切りを除いて分ける",
       split_name("なの花薬局・開成店"), ("なの花薬局", "開成店"))

    # 2. name を分けない形
    eq("店で終わらなければ分けない", split_name("アイン薬局"), None)
    eq("空白の後ろにも薬局があれば分けない", split_name("辻薬店 辻薬局玄海町店"), None)
    eq("店名に会社名があれば分けない",
       split_name("あおい調剤薬局株式会社 石原店"), None)
    eq("空白が無く調剤薬局で始まれば分けない",
       split_name("調剤薬局ツルハドラッグ花川北店"), None)
    eq("薬局を含まず空白も無ければ分けない",
       split_name("ヘルスファーマシィタカキ大林店"), None)
    eq("本店は分けない", split_name("すみれ薬局本店"), None)
    eq("空白の後ろが本店でも分けない", split_name("川口薬局 本店"), None)
    eq("何号店は分けない", split_name("ビック薬局3号店"), None)
    eq("支店名が店だけなら分けない", split_name("つがる薬局店"), None)
    eq("空白が2つ以上なら分けない", split_name("保険調剤 いちご薬局 星置店"), None)
    eq("店名が薬局だけになるなら分けない",
       split_name("薬局 マツモトキヨシ塩田店"), None)
    eq("空白が無く保険調剤薬局で始まれば分けない",
       split_name("保険調剤薬局タイキファーマシー高田店"), None)
    eq("ピリオドの区切りを除いて分ける",
       split_name("爽やか薬局.大宮店"), ("爽やか薬局", "大宮店"))

    # 3. 読み仮名とローマ字
    eq("読みをやっきょくの直後で切る",
       split_reading("れいんぼーやっきょくかみいそてん", "レインボー薬局", "やっきょく"),
       "れいんぼーやっきょく")
    eq("読みの空白が余分でもやっきょくで切る",
       split_reading("たんぽぽ やっきょく おおつてん", "たんぽぽ薬局", "やっきょく"),
       "たんぽぽ やっきょく")
    eq("店名が薬局で終わらなければ空白で切る",
       split_reading("やっきょくまつもときよし まつどしんでんてん",
                     "薬局マツモトキヨシ", "やっきょく"),
       "やっきょくまつもときよし")
    eq("やっきょくの誤記で空白も無ければ返さない",
       split_reading("ゆにすまいるやきょくやちよてん", "ユニスマイル薬局", "やっきょく"), "")
    eq("店名が薬局で終わりやっきょくが無ければ空白で切らない",
       split_reading("あいんふぁーましーず はこだてひよしてん", "アイン薬局", "やっきょく"), "")
    eq("ローマ字の大文字小文字を区別しない",
       split_reading("Sugi Yakkyoku Nammoriten", "スギ薬局", "yakkyoku"), "Sugi Yakkyoku")
    eq("ローマ字の末尾のハイフンを除く",
       split_reading("Sankyu-yakkyoku-shimokoujyakuten", "サンキュー薬局", "yakkyoku"),
       "Sankyu-yakkyoku")
    eq("空の値は空のまま", split_reading("", "アイン薬局", "やっきょく"), "")

    # 4. 同じ店名の行から読みを借りる
    eq("同じ店名の読みで始まれば借りる",
       borrow_reading("やっきょくまつもときよしえすぱるふくしまてん", {"やっきょくまつもときよし"}),
       "やっきょくまつもときよし")
    eq("借りても元の読みの空白は残す",
       borrow_reading("やっきょく たろーふぁーましー よつくらてん", {"やっきょくたろーふぁーましー"}),
       "やっきょく たろーふぁーましー")
    eq("いくつも当てはまれば長いほうを借りる",
       borrow_reading("やっきょくともずにしてん", {"やっきょく", "やっきょくともず"}),
       "やっきょくともず")
    eq("どの読みでも始まらなければ借りない",
       borrow_reading("あいんふぁーましーず はこだてひよしてん", {"あいんやっきょく"}), "")
    eq("読み全体と同じなら借りない",
       borrow_reading("あいんやっきょく", {"あいんやっきょく"}), "")
    eq("手がかりが無ければ借りない", borrow_reading("あいんやっきょく", None), "")

    # 5. 読みを手がかりにローマ字を切る
    eq("yakkyoku の誤記があっても読みで切る",
       split_latn_by_reading("Norden Yakkoku Kitachitoseten", "のるでんやっきょく", "きたちとせてん"),
       "Norden Yakkoku")
    eq("つながった綴りも読みで切る",
       split_latn_by_reading("Soudanyakyokusintokorozawaten", "そうだんやっきょく", "しんところざわてん"),
       "Soudanyakyoku")
    eq("前半が読みと合わなければ切らない",
       split_latn_by_reading("Furawa Yaxtukyoku Tagojunishiyaizuten", "ふらわーやっきょく",
                             "たごじゅうにしやいづてん"), "")
    eq("支店名の読みが無ければ切らない",
       split_latn_by_reading("Ain Yakkoku Nadogayaten", "あいんやっきょく", ""), "")

    # 6. 英語名
    eq("Pharmacy の直後で切る",
       split_english("Ain Pharmacy Kibikamogawaten", "アイン薬局"), "Ain Pharmacy")
    eq("Drugstore の直後で切る",
       split_english("Rainbow Drugstore Kamiiso Branch", "レインボー薬局"), "Rainbow Drugstore")
    eq("Pharmacy が無ければ返さない",
       split_english("Chozaiyakkyoku Tsuruha Drug Wakkanai sakae ten", "調剤薬局ツルハドラッグ"), "")
    eq("切ると括弧が閉じなければ返さない",
       split_english("Sogo Yakkyoku(Sogo Drugstore) Matsumotocho", "そうごう薬局"), "")
    eq("店名が薬局で終わらなければ返さない",
       split_english("Matsumoto Kiyoshi Pharmacy Matsudo", "薬局マツモトキヨシ"), "")

    failed = 0
    print("=== branch_split.py 逆テスト ===\n")
    for name, ok, got in cases:
        if not ok:
            failed += 1
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
        if not ok:
            print(f"        実際: {got!r}")
    print(f"\n  {len(cases) - failed}/{len(cases)} 件")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
