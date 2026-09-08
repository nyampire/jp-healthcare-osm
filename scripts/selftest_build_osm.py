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
from build_osm import (coord_note, join_notes, needs_review,  # noqa: E402
                       resolve_neighbourhood)


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

    # 備考の並び順。build_maproulette.py が _要確認 を200文字で切るので、
    # 並び順がそのまま「切られたときに何が残るか」を決める。
    # 施設種別の定型文は72,962行すべてに同じ85文字で付き、その行について
    # 何も語らない。これが先頭にあると、行ごとに違う文が押し出される。
    boiler = ("施設種別を推定: 暫定値。病床数が空欄の31399件を無床とみなしている。"
              "空欄は未記入であって無床の証拠ではない。一律clinicにする案もあり、"
              "コミュニティでの合意待ち")
    hours = ("255文字を超えたため末尾の規則1件を落とした: "
             "Jun 04,Jun 11,Jun 18,Jun 25,Jul 02,Jul 09,Jul 16,Jul 23,Jul 30,Aug 06,Aug 12-Aug")
    worst = join_notes([reason, hours], [boiler])
    cases += [
        ("定型文を最後に置く",
         join_notes(["行に固有"], ["定型"]), "行に固有 / 定型"),
        ("行に固有の文が無ければ定型文だけを返す",
         join_notes([], ["定型"]), "定型"),
        ("定型文が無ければ行に固有の文だけを返す",
         join_notes(["行に固有"], []), "行に固有"),
        ("最悪の組み合わせでも理由が先頭200文字に丸ごと残る",
         reason in worst[:200], True),
    ]

    # 誤った町字が出た行。addr:neighbourhood を出さず、修正候補を備考に回す。
    # 修正候補は行ごとに違うので join_notes の specific 側に入り、
    # MapRoulette の200文字で切られても先頭に残る。
    cases += [
        ("修正候補があれば addr:neighbourhood を出さない",
         resolve_neighbourhood({"addr:neighbourhood": "鶴見町",
                                "町字の修正候補": "鶴見中央"})[0], ""),
        ("修正候補があれば備考に候補を書く",
         resolve_neighbourhood({"addr:neighbourhood": "鶴見町",
                                "町字の修正候補": "鶴見中央"})[1],
         "町字が入力と別のものになったため addr:neighbourhood を出さない。"
         "修正候補: 鶴見中央"),
        ("修正候補が無ければ町字をそのまま出す",
         resolve_neighbourhood({"addr:neighbourhood": "生麦一丁目",
                                "町字の修正候補": ""}),
         ("生麦一丁目", "")),
        ("修正候補の列が無くても町字をそのまま出す",
         resolve_neighbourhood({"addr:neighbourhood": "生麦一丁目"}),
         ("生麦一丁目", "")),
        ("町字も修正候補も無ければ両方とも空",
         resolve_neighbourhood({}), ("", "")),
    ]

    # 要確認 の判定。build_maproulette.py は 要確認 が立った行にしか
    # 備考をタスクへ載せないので、町字を出さなかった行はここで立てないと
    # 修正候補が作業者に届かない。
    cases += [
        ("町字を出さなかった行は要確認にする",
         needs_review({}, {}, {}, "exact", "町字が入力と別"), "yes"),
        ("どれにも当たらない行は要確認にしない",
         needs_review({}, {}, {}, "exact", ""), ""),
        ("名称が要確認なら要確認にする",
         needs_review({"要確認": "yes"}, {}, {}, "exact", ""), "yes"),
        ("営業時間が要確認なら要確認にする",
         needs_review({}, {"要確認": "yes"}, {}, "exact", ""), "yes"),
        ("住所が要確認なら要確認にする",
         needs_review({}, {}, {"要確認": "yes"}, "exact", ""), "yes"),
        ("施設種別が推定なら要確認にする",
         needs_review({}, {}, {}, "broader", ""), "yes"),
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
