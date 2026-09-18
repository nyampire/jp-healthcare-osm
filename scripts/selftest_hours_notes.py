#!/usr/bin/env python3
"""build_opening_hours.py の 備考 と 要確認 の逆テスト。

3つを固定する。

1. closure_comment が、中黒や空白の入った表記でも期間名を拾うこと。
   `年末・年始` は `年末年始` と同じ休診期間だが、素の部分一致では当たらない。

2. needs_review_hours が、情報がどこにも残らない行だけに印を立てること。
   休診日の記述をコメントに退避できた行と、休診日が無いという記述の行では
   作業者に頼むことが無い。

3. build_notes が、作業者に頼むことがある文と、処理の記録である文を
   分けて返すこと。OSM 側の 備考 には前者だけを写す。

4. 時刻不明の営業日を持つ施設で、unknown として出した場合と、出力を
   見送った場合とで、別の文を返すこと。どちらも作業者に頼むことがある。

5. resolve_conflicts が、平日に時刻が1つも無い施設を unknown で出さないこと。
   祝日だけ時刻を持つ施設を unknown で出すと、通常の週に一度も開かない
   式になる。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_opening_hours import (DECISION_UNKNOWN,  # noqa: E402
                                 DECISION_WITHHOLD, build_notes,
                                 closure_comment, needs_review_hours,
                                 resolve_conflicts)


def main():
    cases = []

    def eq(name, got, want):
        cases.append((name, got == want, got))

    # 1. 期間名の拾い方
    eq("年末年始を拾う", closure_comment("年末年始"), "年末年始は休診")
    eq("中黒が入っても拾う", closure_comment("年末・年始"), "年末年始は休診")
    eq("空白が入っても拾う", closure_comment("年末 年始"), "年末年始は休診")
    eq("休みが付いても拾う", closure_comment("年末年始休み"), "年末年始は休診")
    eq("複数の期間を並べる", closure_comment("GWお盆"), "GW・お盆は休診")
    eq("拾えない記述では空を返す", closure_comment("土曜日午後"), "")

    # 2. 要確認 を立てるか
    eq("除外があれば立てる", needs_review_hours(1, 0, "Mo 09:00-12:00", "", ""), "yes")
    eq("矛盾があれば立てる", needs_review_hours(0, 1, "Mo 09:00-12:00", "", ""), "yes")
    eq("opening_hours が空なら立てる", needs_review_hours(0, 0, "", "", ""), "yes")
    eq("変換できない記述が残れば立てる",
       needs_review_hours(0, 0, "Mo 09:00-12:00", "土曜日午後", ""), "yes")
    eq("コメントに退避できたなら立てない",
       needs_review_hours(0, 0, "Mo 09:00-12:00", "お盆", "お盆は休診"), "")
    eq("休診日が無いという記述なら立てない",
       needs_review_hours(0, 0, "Mo 09:00-12:00", "なし", ""), "")
    eq("年中無休も休診日が無いという記述",
       needs_review_hours(0, 0, "Mo 09:00-12:00", "年中無休", ""), "")
    eq("記述が空なら立てない", needs_review_hours(0, 0, "Mo 09:00-12:00", "", ""), "")
    eq("句点だけの記述なら立てない",
       needs_review_hours(0, 0, "Mo 09:00-12:00", "。", ""), "")

    # 3. 備考 と 要確認の理由 の切り分け
    excluded = [["1", "火", "01", "Tu", "耳鼻いんこう科", "00:45-17:15", "too_early"]]
    extra = {"nth": ["Sa[3] off"], "dates": 6, "comment": "お盆は休診",
             "unparsed": "お盆"}
    note, why = build_notes("1", excluded, 0, [], extra, {})

    eq("備考には処理の記録も入る", "その他の休診日から6日を反映" in note, True)
    eq("備考には定期週の休診も入る", "定期週の休診を反映: Sa[3] off" in note, True)
    eq("要確認の理由に処理の記録は入らない",
       "その他の休診日から6日を反映" in why, False)
    eq("要確認の理由に除外が入る",
       why, "opening_hours から1件を除いた（開始が 06:00 より前）: "
            "火 耳鼻いんこう科 00:45-17:15")

    note2, why2 = build_notes("1", [], 0, [], {"unparsed": "土曜日午後"}, {})
    eq("変換できない記述は要確認の理由に入る",
       why2, "休診日の記述「土曜日午後」を opening_hours に変換できていない")

    note3, why3 = build_notes("1", [], 4, [], {"dates": 2}, {})
    eq("日跨ぎと休診日の反映だけなら理由は空", why3, "")
    eq("それでも備考には残る", "日跨ぎとして採用 4件" in note3, True)

    # 4. 時刻不明の営業日
    con = [["1", "n", "01", "月", "1(診療)", "なし", "曜日フラグは営業日だが時刻が無い"]]
    note4, why4 = build_notes("1", [], 0, con, {"unknown": ["月"]},
                              {("1", "月"): DECISION_UNKNOWN})
    eq("unknown にした曜日を理由に書く",
       why4, "営業日の月曜に時刻の記載が無いため opening_hours に unknown と書いた")
    eq("unknown の曜日を矛盾の一覧に重ねない",
       "営業曜日と時刻が食い違う" in note4, False)

    note5, why5 = build_notes("1", [], 0, con, {"withheld": True},
                              {("1", "月"): DECISION_WITHHOLD})
    eq("全営業日が時刻不明なら出力しない旨を書く",
       why5, "opening_hours をタグ出力していない。営業日の月曜に時刻の記載が無い")
    eq("見送った曜日も矛盾の一覧に重ねない",
       "営業曜日と時刻が食い違う" in note5, False)

    # 5. unknown で出すか、出力を見送るか
    def fac_of(open_days, ph_open=False):
        return {"f": {"closed": {d: ("1" if d in open_days else "0")
                                 for d in "月火水木金土日"},
                      "ph": "0" if ph_open else "1"}}

    _, wh1, unk1 = resolve_conflicts({("f", "火"): [(540, 1080)]},
                                     fac_of("月火"))
    eq("平日に時刻があれば unknown で残す", (sorted(wh1), unk1),
       ([], {"f": ["月"]}))

    _, wh2, unk2 = resolve_conflicts({("f", "祝"): [(540, 1080)]},
                                     fac_of("月火", ph_open=True))
    eq("祝日だけなら出力を見送る", (sorted(wh2), unk2), (["f"], {}))

    _, wh3, unk3 = resolve_conflicts({}, fac_of("月火"))
    eq("時刻が1つも無ければ出力を見送る", (sorted(wh3), unk3), (["f"], {}))

    failed = 0
    print("=== build_opening_hours.py 備考と要確認 逆テスト ===\n")
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
