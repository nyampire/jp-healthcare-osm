#!/usr/bin/env python3
"""医療情報ネット オープンデータから OSM 用 opening_hours を生成する。

対応業態: 病院 / 診療所 / 歯科診療所 / 助産所 / 薬局（全5業態）
  時刻の持ち方で2種類に分かれる。
    two_file … 病院・診療所・歯科診療所。時刻は -2 ファイルに「診療科 × 時間帯」の
               行として入る。3業態とも -2 の列は完全一致し、施設票も診療所・歯科は
               病院の列の部分集合（病床の列が無いだけ）。
    inline  … 助産所・薬局。時刻は施設票の同一行に列として並ぶ（助産所は就業時間帯
               1-3、薬局は開店時間帯1-4）。診療科の概念が無い。
  用語も業態で異なる（休診 / 休業 / 閉店）が、意味は同じなので SECTORS の
  プロファイルで列名だけを差し替えている。

入力 (--sector で選択):
  NN-1_..._facility_info_YYYYMMDD.csv    施設票（曜日フラグ・祝日フラグ・時刻）
  NN-2_..._speciality_hours_YYYYMMDD.csv 診療科・診療時間票（two_file のみ）

出力 (output/、業態名を接頭辞に付ける):
  <業態>_opening_hours.csv   施設単位の opening_hours と要確認フラグ
  <業態>_excluded.csv        opening_hours から除外した区間の全件リスト（人手検証用）
  <業態>_emergency.csv       救急科の診療時間（該当する業態のみ）
  <業態>_conflicts.csv       施設票の曜日/祝日フラグと時刻が矛盾するケース

処理方針:
  01-2 は 1施設につき「診療科 × 時間帯」の複数行を持つが、OSM の opening_hours は
  ノードに 1 つしか持てない。そこで曜日ごとに全診療科の区間を和集合して畳む。

  和集合は「一番早い開始〜一番遅い終了」を採るため、1 行の誤入力が施設全体の値を
  汚染する。これを防ぐため、外来として明らかに成立しない区間を除外してから畳む。
  判定は他の行と比較せず、下記の絶対的な基準のみで行う。理由が一意に定まり、
  除外リストから第三者が検証できるため。

  01-1 と 01-2 が食い違う場合は resolve_conflicts() で解消する。食い違いは性質の
  異なる2種類が混在しており、一律にどちらを優先することはできない。判断内容は
  全件 conflicts.csv の「採用した判断」列に残す。

設計上の注意:
  * フラグはどの業態も 0=閉 / 1=開。「休診」「定期閉店」のように列名と論理が逆に
    見えるものが混じるので、必ず定義書の「フォーマット」列に従う。
  * 薬局には「営業日」と「定期閉店毎週」の2系列があるが、時刻の有無と完全に一致
    するのは「営業日」の方なのでそちらを曜日フラグとして採る。
  * 救急科は24時間・深夜運用が正常なため外来の opening_hours からは分離する。
    誤りではなく性質の異なるデータなので、捨てずに emergency.csv へ退避する。
  * 情報が足りない施設は opening_hours を出力しない。OSM では値を書かないコストは
    低い一方、誤った休診情報を書くと利用者が来院できなくなる。
"""

import argparse
import collections
import csv
import glob
import os
import re
import sys
import unicodedata

# 業態ごとの差分。用語（休診/休業/閉店）と時刻の持ち方だけが違い、
# マージ・除外・例外合成のロジックは全業態で共通に使える。
#   mode "two_file" … 時刻が別ファイル（診療科×時間帯の行）にある
#   mode "inline"   … 時刻が施設票の同一行に列として並ぶ
# フラグの論理はどの業態も 0=閉 / 1=開 で、列名（休診・定期閉店）とは逆になる
# ものが混じる。定義書の「フォーマット」列が唯一の根拠。
SECTORS = {
    "hospital": {
        "label": "病院", "mode": "two_file",
        "facility": "01-1_hospital_facility_info_*.csv",
        "hours": "01-2_hospital_speciality_hours_*.csv",
        "name_col": "正式名称",
        "weekly": "毎週決まった曜日に休診（{d}）",
        "nth": "決まった週に休診（定期週）第{n}週（{d}）",
        "ph": "祝日に休診",
        "other": "その他の休診日（gw、お盆等）",
    },
    "clinic": {
        "label": "診療所", "mode": "two_file",
        "facility": "02-1_clinic_facility_info_*.csv",
        "hours": "02-2_clinic_speciality_hours_*.csv",
        "name_col": "正式名称",
        "weekly": "毎週決まった曜日に休診（{d}）",
        "nth": "決まった週に休診（定期週）第{n}週（{d}）",
        "ph": "祝日に休診",
        "other": "その他の休診日（gw、お盆等）",
    },
    "dental": {
        "label": "歯科診療所", "mode": "two_file",
        "facility": "03-1_dental_facility_info_*.csv",
        "hours": "03-2_dental_speciality_hours_*.csv",
        "name_col": "正式名称",
        "weekly": "毎週決まった曜日に休診（{d}）",
        "nth": "決まった週に休診（定期週）第{n}週（{d}）",
        "ph": "祝日に休診",
        "other": "その他の休診日（gw、お盆等）",
    },
    "maternity": {
        "label": "助産所", "mode": "inline",
        "facility": "04_maternity_home_*.csv",
        "hours": None,
        "name_col": "正式名称",
        "weekly": "毎週決まった曜日に休業（{d}）",
        "nth": "決まった週に休業（定期週）第{n}週（{d}）",
        "ph": "祝日に休業",
        "other": "その他の休業日（gw、お盆等）",
        "time": "{d}_就業時間帯{s}_{se}時間",
        "slots": 3,
    },
    "pharmacy": {
        "label": "薬局", "mode": "inline",
        "facility": "05_pharmacy_*.csv",
        "hours": None,
        "name_col": "名称",
        # 営業日は時刻の有無と完全に一致しており、曜日フラグとして最も信頼できる。
        # 併存する「定期閉店毎週」は同義の別系列なので照合にのみ使う。
        "weekly": "営業日（{d}）",
        "weekly_alt": "定期閉店毎週（{d}）",
        # 定期閉店の週番号だけ全角数字で書かれている
        "nth": "定期閉店第{n}週（{d}）",
        "nth_fullwidth": True,
        "ph": "営業日（祝）",
        "other": "その他の閉店日（gw、お盆等）",
        "time": "{d}_開店時間帯{s}_{se}時間",
        "slots": 4,
    },
}

DAYS = "月火水木金土日"
DAYS_PH = DAYS + "祝"
OSM_DAY = {"月": "Mo", "火": "Tu", "水": "We", "木": "Th",
           "金": "Fr", "土": "Sa", "日": "Su", "祝": "PH"}

# 救急科。外来の診療時間とは運用が異なるため opening_hours の集計から除外する
EMERGENCY_CODES = {"09010"}

# 外来診療として成立する時間帯の範囲。これを外れる区間は入力誤りとみなす
OUTPATIENT_EARLIEST = 6 * 60    # 06:00
OUTPATIENT_LATEST = 23 * 60     # 23:00

# 終了が開始より前の区間は日跨ぎ（当直帯）として採用する。ただし継続時間がこれを
# 超えるものは夜勤ではなく打ち間違いとみなす。実データでは 15〜16時間に 188 件が
# 集中する一方、20時間超の 11 件はいずれも終了が開始の直前にある誤入力だった。
NIGHT_MAX_DURATION = 18 * 60    # 18時間

MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
DAYS_IN_MONTH = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

# 「その他の休診日」の自由記述から日付を拾う。区切り文字・桁揃え・スラッシュ表記・
# 範囲表現に揺れがあるため正規化してから当てる。
_MD = r"(?:(\d{1,2})\s*月\s*(\d{1,2})\s*日|(\d{1,2})\s*/\s*(\d{1,2}))"
RE_DATE_RANGE = re.compile(_MD + r"\s*[〜~\-−]\s*" + _MD)
RE_DATE = re.compile(_MD)
# 休診日の範囲として認める最大日数。これを超える範囲は終点の誤入力とみなし採用しない。
# 元データには `8/14-5/16`（8/16の誤り）、`お盆休み 12/13～8/16`（8/13の誤り）のように
# 終点を打ち間違えた範囲があり、そのまま年をまたいで展開すると1年の大半が休診になる。
# 実データでは休診日数の99%が20日以内で、長期休業でも1か月に収まる。
# 個別日付の羅列は何日あっても正当なので、判定は1本の範囲の長さに対してのみ行う。
MAX_CLOSURE_RANGE_DAYS = 31
# 日付を抽出したあとに残る説明語。これだけが残った場合は変換漏れではないため
# 警告しない。GW・お盆・午後のように日付を特定できない語はここに入れない。
RE_LABEL_NOISE = re.compile(
    r"年末年始|年末|年始|休診日?|休業|休み|振替|および|及び|から|まで|"
    r"[()（）・:：]|改行|等|など|予定|の|は|を|に|と")

# 日付を特定できない休診期間。opening_hours のコメントとして残す対象。
# 「午後」のような断片は単独では意味をなさないため含めない。
CLOSURE_KEYWORDS = [
    ("ゴールデンウィーク", "GW"),
    ("GW", "GW"),
    ("お盆", "お盆"),
    ("盆", "お盆"),
    ("年末年始", "年末年始"),
    ("創立記念日", "創立記念日"),
    ("夏季", "夏季"),
    ("夏期", "夏季"),
]

EXCLUSION_NOTE = {
    "null_placeholder": "開始と終了が同一。実質NULL",
    "sentinel_24h": "00:00-23:59。24時間対応の意図か要確認",
    "overnight_implausible": f"終了が開始より前で、日跨ぎとしても "
                             f"{NIGHT_MAX_DURATION // 60}時間を超える。打ち間違いの疑い",
    "too_early": f"開始が {OUTPATIENT_EARLIEST // 60:02d}:00 より前",
    "too_late": f"終了が {OUTPATIENT_LATEST // 60:02d}:00 より後",
}


def to_min(t):
    return int(t[:2]) * 60 + int(t[3:])


def to_hhmm(m):
    if m % 1440 == 0 and m > 0:
        return "24:00"
    h, mi = divmod(m % 1440, 60)
    return f"{h:02d}:{mi:02d}"


def classify(a, b):
    """区間を除外すべきか判定する。除外不要なら None を返す。

    終了が開始より前の区間は日跨ぎとして採用するため、時刻の範囲チェックは
    適用しない（当直帯は 06:00-23:00 に収まらないのが正常なため）。
    """
    if a == b:
        return "null_placeholder"
    if a == "00:00" and b == "23:59":
        return "sentinel_24h"
    s, e = to_min(a), to_min(b)
    if e < s:
        if e + 1440 - s >= NIGHT_MAX_DURATION:
            return "overnight_implausible"
        return None
    if s < OUTPATIENT_EARLIEST:
        return "too_early"
    if e > OUTPATIENT_LATEST:
        return "too_late"
    return None


def _md(groups, offset):
    """正規表現のグループから (月, 日) を取り出す。「M月D日」と「M/D」の両形式に対応。

    暦として成立しない値は None を返し、呼び出し側で未変換として残す。
    """
    if groups[offset]:
        m, d = int(groups[offset]), int(groups[offset + 1])
    else:
        m, d = int(groups[offset + 2]), int(groups[offset + 3])
    if not 1 <= m <= 12 or not 1 <= d <= DAYS_IN_MONTH[m - 1]:
        return None
    return m, d


def _expand(start, end):
    """(月, 日) の範囲を1日ずつ展開する。年をまたぐ範囲も扱う。"""
    out = []
    cur = start
    for _ in range(400):
        out.append(cur)
        if cur == end:
            break
        if cur[1] >= DAYS_IN_MONTH[cur[0] - 1]:
            cur = (cur[0] % 12 + 1, 1)
        else:
            cur = (cur[0], cur[1] + 1)
    return out


def parse_closed_dates(text):
    """自由記述から休診日の集合と、解釈できなかった残り文字列を返す。"""
    s = unicodedata.normalize("NFKC", text)
    for ch in "，、\n\r":
        s = s.replace(ch, ",")
    # 「2024年」「2024/」のような年表記は月日の誤検出を招くため先に落とす
    s = re.sub(r"(19|20)\d{2}\s*[年/]", " ", s)
    dates = set()
    rejected = []

    def take_range(m):
        a, b = _md(m.groups(), 0), _md(m.groups(), 4)
        if a is None or b is None:
            return m.group(0)
        span = _expand(a, b)
        if len(span) > MAX_CLOSURE_RANGE_DAYS:
            # 終点の誤入力とみなす。範囲が壊れている以上どちらの端点も信用できないので、
            # 個別日付として拾い直さないよう数字を含まない印に置き換え、原文は残す。
            rejected.append(m.group(0))
            return " 範囲不正 "
        dates.update(span)
        return " "

    def take_one(m):
        v = _md(m.groups(), 0)
        if v is None:
            return m.group(0)
        dates.add(v)
        return " "

    s = RE_DATE_RANGE.sub(take_range, s)
    s = RE_DATE.sub(take_one, s)
    rest = re.sub(r"[,\s　:：]+", "", s)
    if dates:
        rest = RE_LABEL_NOISE.sub("", rest)
    rest = rest.replace("範囲不正", "")
    for raw in rejected:
        rest += f"[{MAX_CLOSURE_RANGE_DAYS}日超の範囲:{raw}]"
    return dates, rest


def format_date_rule(dates):
    """休診日の集合を opening_hours の日付セレクタに畳む。連続日は範囲にまとめる。"""
    if not dates:
        return ""
    ordinals = []
    base = 0
    starts = {}
    for m in range(1, 13):
        starts[m] = base
        base += DAYS_IN_MONTH[m - 1]
    total = base
    for m, d in dates:
        ordinals.append(starts[m] + d - 1)
    ordinals = sorted(set(ordinals))

    runs = []
    for o in ordinals:
        if runs and o == runs[-1][1] + 1:
            runs[-1][1] = o
        else:
            runs.append([o, o])
    # 年末から年始へ連続する場合は 1 本の範囲にまとめる
    if len(runs) > 1 and runs[0][0] == 0 and runs[-1][1] == total - 1:
        runs[0][0] = runs[-1][0] - total
        runs.pop()

    def label(o):
        o %= total
        for m in range(12, 0, -1):
            if o >= starts[m]:
                return f"{MONTH_ABBR[m - 1]} {o - starts[m] + 1:02d}"
        return ""

    return ",".join(label(a) if a == b else f"{label(a)}-{label(b)}" for a, b in runs)


FULLWIDTH_DIGITS = {1: "１", 2: "２", 3: "３", 4: "４", 5: "５"}


def nth_col(profile, n, d):
    """定期休の列名を組み立てる。薬局だけ週番号が全角数字で書かれている。"""
    num = FULLWIDTH_DIGITS[n] if profile.get("nth_fullwidth") else n
    return profile["nth"].format(n=num, d=d)


def nth_week_rules(row, idx, has_day, profile):
    """定期週の休診指定を Sa[1,3] off 形式にする。

    第1〜5週すべてが休診の指定は「毎週その曜日は休診」と同義で、01-2 側の
    診療時間の有無に既に反映されているため出力しない。01-2 に診療時間が無い
    曜日への指定も無意味なので落とす。
    """
    rules = []
    for d in DAYS:
        weeks = [n for n in range(1, 6)
                 if row[idx[nth_col(profile, n, d)]].strip() == "0"]
        if not weeks or len(weeks) == 5 or not has_day(d):
            continue
        rules.append(f"{OSM_DAY[d]}[{','.join(map(str, weeks))}] off")
    return rules


def closure_comment(unparsed):
    """変換できなかった記述から、期間名だけを拾ってコメント文字列にする。

    opening_hours のコメントは機械判定されない表示用の情報なので、
    日付を特定できない GW・お盆等はここに退避する。
    """
    found = []
    for needle, label in CLOSURE_KEYWORDS:
        if needle in unparsed and label not in found:
            found.append(label)
    if not found:
        return ""
    return "・".join(found) + "は休診"


def load_facilities(path, profile):
    with open(path, encoding="utf-8-sig", newline="") as f:
        r = csv.reader(f)
        idx = {h: n for n, h in enumerate(next(r))}
        out = {}
        for row in r:
            dates, rest = parse_closed_dates(row[idx[profile["other"]]].strip())
            out[row[0]] = {
                "name": row[idx[profile["name_col"]]],
                "pref": row[idx["都道府県コード"]],
                "closed": {d: row[idx[profile["weekly"].format(d=d)]].strip()
                           for d in DAYS},
                "ph": row[idx[profile["ph"]]].strip(),
                "closed_dates": dates,
                "unparsed": rest,
                "row": row,
                "idx": idx,
            }
        return out


def load_intervals_inline(path, profile):
    """時刻が施設票の同一行に並ぶ業態（助産所・薬局）から区間を読む。

    診療科の概念が無いので救急科の分離は行わない。時間帯の枠数だけが業態で異なる。
    """
    intervals = collections.defaultdict(list)
    excluded = []
    overnight = collections.Counter()
    with open(path, encoding="utf-8-sig", newline="") as f:
        r = csv.reader(f)
        idx = {h: n for n, h in enumerate(next(r))}
        for row in r:
            fid = row[0]
            for d in DAYS_PH:
                for slot in range(1, profile["slots"] + 1):
                    a = row[idx[profile["time"].format(d=d, s=slot, se="開始")]].strip()
                    b = row[idx[profile["time"].format(d=d, s=slot, se="終了")]].strip()
                    if not (a and b):
                        continue
                    reason = classify(a, b)
                    if reason:
                        excluded.append([fid, d, str(slot), "", "",
                                         f"{a}-{b}", reason])
                        continue
                    s_, e_ = to_min(a), to_min(b)
                    if e_ < s_:
                        e_ += 1440
                        overnight[fid] += 1
                    intervals[(fid, d)].append((s_, e_))
    return intervals, [], excluded, overnight


def load_intervals(path):
    """(施設ID, 曜日) -> [(開始分, 終了分)] と、除外分・救急科分を返す。"""
    intervals = collections.defaultdict(list)
    emergency = []
    excluded = []
    overnight = collections.Counter()
    with open(path, encoding="utf-8-sig", newline="") as f:
        r = csv.reader(f)
        idx = {h: n for n, h in enumerate(next(r))}
        for row in r:
            fid, code = row[0], row[idx["診療科目コード"]]
            name, slot = row[idx["診療科目名"]], row[idx["診療時間帯"]]
            for d in DAYS_PH:
                a = row[idx[f"{d}_診療開始時間"]].strip()
                b = row[idx[f"{d}_診療終了時間"]].strip()
                if not (a and b):
                    continue
                # NULL 相当の行は救急科であっても退避せず落とす
                if a == b:
                    excluded.append([fid, d, slot, code, name, f"{a}-{b}",
                                     "null_placeholder"])
                    continue
                if code in EMERGENCY_CODES:
                    emergency.append([fid, d, slot, code, name, f"{a}-{b}"])
                    continue
                reason = classify(a, b)
                if reason:
                    excluded.append([fid, d, slot, code, name, f"{a}-{b}", reason])
                    continue
                s, e = to_min(a), to_min(b)
                if e < s:
                    e += 1440
                    overnight[fid] += 1
                intervals[(fid, d)].append((s, e))
    return intervals, emergency, excluded, overnight


def format_span(s, e):
    """区間を opening_hours の時刻表記にする。

    日跨ぎのマージ結果が24時間以上になると開始と終了が同じ表記になり、
    ゼロ長とも24時間とも読める曖昧な値（08:30-08:30）が出てしまうため、
    その場合は 00:00-24:00 に正規化する。
    """
    if e - s >= 1440:
        return "00:00-24:00"
    return f"{to_hhmm(s)}-{to_hhmm(e)}"


def merge(ivs):
    out = []
    for s, e in sorted(ivs):
        if out and s <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


def build_opening_hours(intervals, fac, profile, withheld=frozenset()):
    """01-2 の診療時間を基本ルールとし、01-1 の例外ルールを後ろに重ねる。

    opening_hours は後ろのルールが前を上書きするため、
    「基本時間 → 定期週の休診 → 祝日 → 特定日の休診」の順に並べる。
    """
    results = {}
    applied = {}
    for fid, meta in fac.items():
        if fid in withheld:
            results[fid] = ""
            applied[fid] = {"withheld": True}
            continue
        parts = []
        for d in DAYS_PH:
            ivs = intervals.get((fid, d))
            if not ivs:
                continue
            spans = merge(ivs)
            if any(e - s >= 1440 for s, e in spans):
                spans = [(0, 1440)]
            parts.append((OSM_DAY[d],
                          ",".join(format_span(s, e) for s, e in spans)))
        if not parts:
            results[fid] = ""
            applied[fid] = {}
            continue
        grp = collections.OrderedDict()
        for d, t in parts:
            grp.setdefault(t, []).append(d)
        rules = [f"{','.join(ds)} {t}" for t, ds in grp.items()]

        nth = nth_week_rules(meta["row"], meta["idx"],
                             lambda d: bool(intervals.get((fid, d))), profile)
        rules += nth

        ph = not intervals.get((fid, "祝")) and meta["ph"] == "0"
        if ph:
            rules.append("PH off")

        date_rule = format_date_rule(meta["closed_dates"])
        if date_rule:
            rules.append(f"{date_rule} off")

        oh = "; ".join(rules)
        # 日付にできない休診期間は fallback ルールのコメントとして残す。
        # 通常ルールとして書くと全時間帯を上書きして平日まで休診になるため、
        # 必ず || の後ろに置く。
        comment = closure_comment(meta["unparsed"])
        if comment:
            oh += f' || off "{comment}"'

        results[fid] = oh
        applied[fid] = {"nth": nth, "ph": ph,
                        "dates": len(meta["closed_dates"]),
                        "unparsed": meta["unparsed"],
                        "comment": comment}
    return results, applied


def resolve_conflicts(intervals, fac):
    """01-1 と 01-2 の矛盾を解消する。intervals を書き換え、判断内容を返す。

    矛盾は性質の異なる2種類が混在しており、一律には決められない。

    A) 01-1 が休診と言う曜日に 01-2 が時刻を持つ:
       その時刻が「01-1 が診療日と明示している曜日」の時刻と同一なら、記入者が
       全曜日に同じ値を入れた一律入力とみなし 01-1 を採る。土曜に平日と同じ
       09:00-17:00 が入っている類がこれで、実データの85%を占める。
       半日など独自の時刻を持つ場合は実在の診療とみなし 01-2 を採る。
       比較対象を「診療日」に限るのは、平日自身が休診指定されている場合に
       自分と比較して常に一致してしまうのを避けるため。

    B) 01-1 が診療日と言う曜日に 01-2 が時刻を持たない:
       これは矛盾ではなく 01-2 の記入漏れで、休診を意味しない。
       opening_hours には「開いているが時刻不明」を表す構文が無いため、
       その曜日を書かなければ休診と誤解される。誤情報を出さないよう、
       施設単位で opening_hours の出力自体を見送る。
    """
    decisions = {}
    withheld = set()
    for fid, meta in fac.items():
        # 01-1 が診療日と明示している曜日の時刻集合を、比較の基準にする
        baseline = set()
        for d in DAYS:
            if meta["closed"][d] == "1":
                baseline |= set(intervals.get((fid, d), []))

        for d in DAYS_PH:
            closed = (meta["ph"] == "0") if d == "祝" else (meta["closed"][d] == "0")
            if not closed:
                continue
            ivs = intervals.get((fid, d))
            if not ivs:
                continue
            if baseline and set(ivs) <= baseline:
                del intervals[(fid, d)]
                decisions[(fid, d)] = "曜日フラグを採用（営業日と同一時刻のため一律入力とみなす）"
            else:
                decisions[(fid, d)] = "時刻を採用（営業日と異なる独自の時刻）"

        missing = [d for d in DAYS
                   if meta["closed"][d] == "1" and not intervals.get((fid, d))]
        if missing:
            withheld.add(fid)
            for d in missing:
                decisions[(fid, d)] = "opening_hours を出力しない（時刻不明の営業日がある）"
    return decisions, withheld


def find_conflicts(intervals, fac):
    conflicts = []
    for fid, meta in fac.items():
        for d in DAYS:
            flag, has = meta["closed"][d], bool(intervals.get((fid, d)))
            if flag == "0" and has:
                conflicts.append([fid, meta["name"], meta["pref"], d, "0(休診)", "あり",
                                  "曜日フラグは休みだが時刻が入っている"])
            elif flag == "1" and not has:
                conflicts.append([fid, meta["name"], meta["pref"], d, "1(診療)", "なし",
                                  "曜日フラグは営業日だが時刻が無い"])
        if meta["ph"] == "0" and bool(intervals.get((fid, "祝"))):
            conflicts.append([fid, meta["name"], meta["pref"], "祝", "0(休診)", "あり",
                              "祝日フラグは休みだが祝日の時刻が入っている"])
    return conflicts


def build_notes(fid, excluded_rows, overnight_n, conflict_rows, extra, decisions):
    """施設1行だけを見て何が起きたか分かるよう、処理内容を日本語で組み立てる。

    詳細は excluded.csv / conflicts.csv に全件あるが、突き合わせずに済むよう
    件数と代表例をここに残す。
    """
    notes = []
    if overnight_n:
        notes.append(f"日跨ぎとして採用 {overnight_n}件")
    by_reason = collections.defaultdict(list)
    for r in excluded_rows:
        by_reason[r[6]].append(r)
    for reason, rows in sorted(by_reason.items()):
        detail = "、".join(f"{r[1]} {r[4]} {r[5]}" for r in rows[:2])
        if len(rows) > 2:
            detail += f" 他{len(rows) - 2}件"
        notes.append(f"除外 {len(rows)}件[{EXCLUSION_NOTE[reason]}]: {detail}")
    if extra.get("withheld"):
        days = "".join(r[3] for r in conflict_rows
                       if "出力しない" in decisions.get((fid, r[3]), ""))
        notes.append(
            f"opening_hours を出力しない: 曜日フラグが営業日とする{days}曜の時刻が無く、"
            "書くと休診と誤解されるため")
    if conflict_rows:
        by_decision = collections.Counter(
            decisions.get((fid, r[3]), "判断なし") for r in conflict_rows)
        detail = "、".join(
            f"{k}×{n}" if n > 1 else k
            for k, n in by_decision.items() if "出力しない" not in k)
        if detail:
            notes.append(f"曜日フラグと矛盾 {len(conflict_rows)}件 → {detail}")
    if extra.get("nth"):
        notes.append("定期週の休診を反映: " + "、".join(extra["nth"]))
    if extra.get("dates"):
        notes.append(f"その他の休診日から{extra['dates']}日を反映")
    if extra.get("comment"):
        notes.append(f"日付不明の休診期間をコメントに退避: {extra['comment']}")
    if extra.get("unparsed"):
        notes.append(f"未変換の休診日記述: {extra['unparsed'][:40]}")
    return " / ".join(notes)


def resolve(base_dir, pattern):
    hits = sorted(glob.glob(os.path.join(base_dir, pattern)))
    if not hits:
        sys.exit(f"入力ファイルが見つかりません: {pattern}")
    return hits[-1]


def write_csv(path, header, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir", default=".")
    p.add_argument("--out-dir", default="output")
    p.add_argument("--sector", default="hospital", choices=sorted(SECTORS))
    args = p.parse_args()

    profile = SECTORS[args.sector]
    label = profile["label"]
    f1 = resolve(args.data_dir, profile["facility"])
    f2 = resolve(args.data_dir, profile["hours"]) if profile["hours"] else None
    print(f"業態       : {label}")
    print(f"施設票     : {os.path.basename(f1)}")
    if f2:
        print(f"診療時間票 : {os.path.basename(f2)}")
    else:
        print("時刻       : 施設票の同一行（インライン）")

    fac = load_facilities(f1, profile)
    if profile["mode"] == "inline":
        intervals, emergency, excluded, overnight = load_intervals_inline(f1, profile)
    else:
        intervals, emergency, excluded, overnight = load_intervals(f2)
    # 矛盾の検出は解消前の状態で行い、そのあと intervals を書き換える
    conflicts = find_conflicts(intervals, fac)
    decisions, withheld = resolve_conflicts(intervals, fac)
    oh, applied = build_opening_hours(intervals, fac, profile, withheld)

    os.makedirs(args.out_dir, exist_ok=True)
    exc_by_fac = collections.Counter(r[0] for r in excluded)
    con_by_fac = collections.Counter(r[0] for r in conflicts)
    exc_rows = collections.defaultdict(list)
    for r in excluded:
        exc_rows[r[0]].append(r)
    con_rows = collections.defaultdict(list)
    for r in conflicts:
        con_rows[r[0]].append(r)

    def meta(fid, key):
        return fac.get(fid, {}).get(key, "")

    build_dir = os.path.join(args.out_dir, "build")
    os.makedirs(build_dir, exist_ok=True)
    write_csv(
        os.path.join(build_dir, f"{args.sector}_opening_hours.csv"),
        ["ID", "正式名称", "都道府県コード", "opening_hours",
         "除外区間数", "日跨ぎ採用数", "矛盾曜日数", "要確認", "備考"],
        [[fid, m["name"], m["pref"], oh[fid], exc_by_fac[fid], overnight[fid],
          con_by_fac[fid],
          "yes" if (exc_by_fac[fid] or con_by_fac[fid] or not oh[fid]) else "",
          build_notes(fid, exc_rows[fid], overnight[fid], con_rows[fid],
                      applied.get(fid, {}), decisions)
          or ("01-2に有効な診療時間がない" if not oh[fid] else "")]
         for fid, m in fac.items()])

    write_csv(
        os.path.join(args.out_dir, f"{args.sector}_excluded.csv"),
        ["分類", "ID", "正式名称", "都道府県コード", "曜日", "時間帯",
         "診療科目コード", "診療科目名", "除外した値", "除外理由"],
        [[r[6], r[0], meta(r[0], "name"), meta(r[0], "pref"),
          r[1], r[2], r[3], r[4], r[5], EXCLUSION_NOTE[r[6]]]
         for r in sorted(excluded, key=lambda x: (x[6], x[0]))])

    if emergency:
        write_csv(
            os.path.join(args.out_dir, f"{args.sector}_emergency.csv"),
            ["ID", "正式名称", "都道府県コード", "曜日", "時間帯",
             "診療科目コード", "診療科目名", "診療時間"],
            [[r[0], meta(r[0], "name"), meta(r[0], "pref"),
              r[1], r[2], r[3], r[4], r[5]] for r in emergency])

    write_csv(
        os.path.join(args.out_dir, f"{args.sector}_conflicts.csv"),
        ["ID", "正式名称", "都道府県コード", "曜日", "曜日フラグ", "時刻",
         "内容", "採用した判断"],
        [r + [decisions.get((r[0], r[3]), "")] for r in conflicts])

    generated = sum(1 for v in oh.values() if v)
    review = sum(1 for fid in fac
                 if exc_by_fac[fid] or con_by_fac[fid] or not oh[fid])
    print(f"\n施設数                 : {len(fac):,}")
    print(f"opening_hours 生成成功 : {generated:,} ({generated / len(fac) * 100:.1f}%)")
    if emergency:
        print(f"救急科として分離       : {len(emergency):,} 区間 "
              f"({len(set(r[0] for r in emergency)):,} 施設)")
    dec = collections.Counter(decisions.values())
    print(f"曜日フラグと時刻の矛盾 : {len(conflicts):,} 件 "
          f"({len(con_by_fac):,} 施設)")
    for k, n in dec.most_common():
        print(f"    {n:5,}  {k}")
    print(f"  → opening_hours 保留 : {len(withheld):,} 施設")
    print(f"要確認フラグ付き施設   : {review:,} ({review / len(fac) * 100:.1f}%)")
    print(f"日跨ぎとして採用       : {sum(overnight.values()):,} 区間 "
          f"({len(overnight):,} 施設)")
    print(f"定期週の休みを反映     : "
          f"{sum(1 for v in applied.values() if v.get('nth')):,} 施設")
    print(f"その他の休み日を反映   : "
          f"{sum(1 for v in applied.values() if v.get('dates')):,} 施設")
    print(f"休み日記述の未変換残り : "
          f"{sum(1 for v in applied.values() if v.get('unparsed')):,} 施設")
    print(f"うちコメントに退避     : "
          f"{sum(1 for v in applied.values() if v.get('comment')):,} 施設")
    print("\n除外した区間の内訳:")
    for cat, n in collections.Counter(r[6] for r in excluded).most_common():
        print(f"  {n:6,}  {cat:<18} {EXCLUSION_NOTE[cat]}")


if __name__ == "__main__":
    main()
