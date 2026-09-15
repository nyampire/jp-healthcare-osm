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
from build_osm import (coord_note, emergency_tag, join_notes,  # noqa: E402
                       needs_review, number_note, resolve_neighbourhood)


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
    # 座標を捨てた理由は、捨てた値そのものを含む唯一の文で、他の文から
    # 復元できない。積まれた順で先頭に来ることを固定する。
    hours = ("255文字を超えたため末尾の規則1件を落とした: "
             "Jun 04,Jun 11,Jun 18,Jun 25,Jul 02,Jul 09,Jul 16,Jul 23,Jul 30,Aug 06,Aug 12-Aug")
    worst = join_notes([reason, hours], [])
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
         needs_review({}, {}, {}, "町字が入力と別", False), "yes"),
        ("どれにも当たらない行は要確認にしない",
         needs_review({}, {}, {}, "", False), ""),
        ("名称が要確認なら要確認にする",
         needs_review({"要確認": "yes"}, {}, {}, "", False), "yes"),
        ("営業時間が要確認なら要確認にする",
         needs_review({}, {"要確認": "yes"}, {}, "", False), "yes"),
        ("住所が要確認なら要確認にする",
         needs_review({}, {}, {"要確認": "yes"}, "", False), "yes"),
        ("番地を出さなかった行は要確認にする",
         needs_review({}, {}, {}, "", True), "yes"),
    ]

    # 施設種別の推定は 要確認 の理由にしない。amenity=doctors に倒した判断は
    # 診療所の72,962行すべてに同じ形で当てはまり、行を選り分けないため。
    # 立てていた頃は診療所77,188行のうち75,309行で立ち、うち57,011行は
    # 備考に定型文しか無かった。周知は MapRoulette のチャレンジ説明に置く。
    cases += [
        ("施設種別が推定というだけでは要確認にしない",
         needs_review({}, {}, {}, "", False), ""),
    ]

    # 救急科。emergency=yes は healthcare:speciality とは別の列から決まる。
    # 255文字の上限に当たった施設では healthcare:speciality が general の
    # 1語に潰れるが、その潰れた後の値からは救急科の有無を復元できない。
    # <業態>_speciality.csv の emergency 列は潰す前に決まっているので、
    # 潰れた施設でもタグが残ることをここで固定する。
    cases += [
        ("general に潰れた病院でも emergency を出す",
         emergency_tag("hospital", {"healthcare:speciality": "general",
                                    "emergency": "yes"}), "yes"),
        ("救急科の無い病院には emergency を出さない",
         emergency_tag("hospital", {"healthcare:speciality": "general",
                                    "emergency": ""}), ""),
        ("診療所には emergency を出さない",
         emergency_tag("clinic", {"emergency": "yes"}), ""),
        ("医院には emergency を出さない",
         emergency_tag("doctors", {"emergency": "yes"}), ""),
        ("emergency の列が無くても止まらない",
         emergency_tag("hospital", {}), ""),
    ]

    # 推定の番地を出さなかった行の1文。build_addr.js が町字の明細に照らして
    # 決めた 番地の判定 列を読む。どの判定でも番地は出さないので、変わるのは
    # 作業者が現地で何を調べるかである。
    cases += [
        ("地番と分かった行は地番のためと書く",
         number_note({"番地の判定": "地番"}),
         "地番のため addr:block_number と addr:housenumber を出さない"),
        ("どちらの明細にも無い行は見つからないと書く",
         number_note({"番地の判定": "不一致"}),
         "番地が住居表示にも地番にも見つからないため出さない"),
        ("照合できない行は明細が無いと書く",
         number_note({"番地の判定": "判定不能"}),
         "照合する明細が無いため番地を出さない"),
        ("判定が空なら推定のためと書く",
         number_note({"番地の判定": ""}),
         "番地が推定のため addr:block_number と addr:housenumber を出さない"),
        ("番地の判定の列が無くても止まらない",
         number_note({}),
         "番地が推定のため addr:block_number と addr:housenumber を出さない"),
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
