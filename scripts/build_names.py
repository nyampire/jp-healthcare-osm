#!/usr/bin/env python3
"""医療情報ネット オープンデータから OSM 用の名称タグを生成する。

対応業態: 全5業態

入力 (--sector で選択):
  NN-*_..._YYYYMMDD.csv          施設票
  mapping/name_entity_prefixes.csv  運営主体の先頭パターン
  mapping/name_entity_suffixes.csv  法人名トークンの接尾辞

出力 (output/build/):
  <業態>_names.csv  元の列を保持したまま、OSM 用の名称列を追加したもの

処理方針:
  元データの列は一切書き換えず、正規化後の値は別列として持つ。判断を覆したく
  なったときに元に戻せることと、第三者が対比して検証できることを優先する。

  全角スペースは「運営主体｜施設名」の区切りとは限らない。実データには
  `母乳育児相談室　さいとう` `オアシス　ファーマシー` `ふじい薬局　明野調剤`
  のように施設名そのものに含まれる例が多数あり、助産所では74%がこの型だった。
  そのため「最後のトークンを施設名とする」規則は採らず、運営主体だと明示的に
  識別できるトークンだけを先頭から取り除く。識別できなければ何も削らない。

  対応表は CSV に外出ししている。どの語を運営主体とみなすかは判断を含むので、
  レビューして直せる形である必要があるため。

タグの割り当て:
  name            運営主体を除いた施設名
  official_name   元の正式名称（法人格を含む完全な名称）
  short_name      略称（元データにある業態のみ）
  name:ja-Hira    フリガナをひらがなに変換したもの
  name:en         英語表記のうち英語だと判別できたもの
  name:ja-Latn    英語表記のうち音写で、かつ読みと一致すると確認できたもの

  name:ja-Hira は OSM で 395,616 件使われており、`name:ja_kana`(43件) ではなく
  こちらが慣行。元データはカタカナなのでひらがなへ変換する。

  フリガナは法人格を含む読みになっている（例: カブシキガイシャアミヤヤッキョク）。
  name から運営主体を取り除いた施設では読みが name と一致しなくなるため、
  その場合は name:ja-Hira を出力せず備考に理由を残す。

  英語表記の列は英訳と音写が混在する（`Sapporo Medical University Hospital` と
  `airisutyouzaiyakkyoku` が同じ列にある）。英語だと判別できたものを name:en に、
  音写を name:ja-Latn に振り分ける。

  音写はそのままでは信用できない。先頭が欠けたもの（`医療福祉センター札幌あゆみの園`
  に対し `sapporoayuminosono`）や途中で切れたもの（`旭川脳神経外科循環器内科病院` に
  対し `Asahikawa Noge`）が混じるためで、そのまま入れると「この名前のローマ字表記で
  ある」という主張が偽になる。そこでフリガナから独立にヘボン式ローマ字を導出して
  突き合わせ、一致したものだけ採用する。実データでは 91.9% が一致した。
  出力には元の音写を使う。語間に空白があり、読みから生成した続き綴りより読みやすい。
"""

import argparse
import collections
import csv
import difflib
import glob
import os
import re
import sys

SECTORS = {
    "hospital": ("病院", "01-1_hospital_facility_info_*.csv",
                 "正式名称", "略称", "正式名称（フリガナ）", "英語表記（ローマ字表記）"),
    "clinic": ("診療所", "02-1_clinic_facility_info_*.csv",
               "正式名称", "略称", "正式名称（フリガナ）", "英語表記（ローマ字表記）"),
    "dental": ("歯科診療所", "03-1_dental_facility_info_*.csv",
               "正式名称", "略称", "正式名称（フリガナ）", "英語表記（ローマ字表記）"),
    "maternity": ("助産所", "04_maternity_home_*.csv",
                  "正式名称", "略称", "正式名称（フリガナ）", "英語表記（ローマ字表記）"),
    "pharmacy": ("薬局", "05_pharmacy_*.csv",
                 "名称", None, "フリガナ", "ローマ字"),
}

# 英語だと判別する語。これを含まない値は音写とみなして name:en には入れない。
ENGLISH_MARKERS = [
    "hospital", "clinic", "pharmacy", "dental", "dentist", "medical", "center",
    "centre", "university", "institute", "college", "association", "foundation",
    "corporation", "surgery", "care", "health", "maternity", "midwife",
    "drug", "dispensary", "eye", "children", "general", "memorial",
]

FULLWIDTH_ASCII = {chr(c): chr(c - 0xFEE0) for c in range(0xFF01, 0xFF5F)}

# ひらがな→ヘボン式ローマ字。macron は使わない（OSM の name:ja-Latn の慣行）。
# これは元データの音写を検証するために独立に導出するためのもので、出力そのものには
# 使わない。元の音写は語間に空白があり読みやすいので、検証を通ったらそちらを採る。
ROMAJI = {
    "きゃ": "kya", "きゅ": "kyu", "きょ": "kyo", "しゃ": "sha", "しゅ": "shu",
    "しょ": "sho", "ちゃ": "cha", "ちゅ": "chu", "ちょ": "cho", "にゃ": "nya",
    "にゅ": "nyu", "にょ": "nyo", "ひゃ": "hya", "ひゅ": "hyu", "ひょ": "hyo",
    "みゃ": "mya", "みゅ": "myu", "みょ": "myo", "りゃ": "rya", "りゅ": "ryu",
    "りょ": "ryo", "ぎゃ": "gya", "ぎゅ": "gyu", "ぎょ": "gyo", "じゃ": "ja",
    "じゅ": "ju", "じょ": "jo", "ぢゃ": "ja", "ぢゅ": "ju", "ぢょ": "jo",
    "びゃ": "bya", "びゅ": "byu", "びょ": "byo", "ぴゃ": "pya", "ぴゅ": "pyu",
    "ぴょ": "pyo", "ふぁ": "fa", "ふぃ": "fi", "ふぇ": "fe", "ふぉ": "fo",
    "ゔぁ": "va", "ゔぃ": "vi", "ゔぇ": "ve", "ゔぉ": "vo", "てぃ": "ti",
    "でぃ": "di", "とぅ": "tu", "どぅ": "du", "うぃ": "wi", "うぇ": "we",
    "うぉ": "wo", "しぇ": "she", "ちぇ": "che", "じぇ": "je", "つぁ": "tsa",
    "つぃ": "tsi", "つぇ": "tse", "つぉ": "tso",
    "あ": "a", "い": "i", "う": "u", "え": "e", "お": "o",
    "か": "ka", "き": "ki", "く": "ku", "け": "ke", "こ": "ko",
    "さ": "sa", "し": "shi", "す": "su", "せ": "se", "そ": "so",
    "た": "ta", "ち": "chi", "つ": "tsu", "て": "te", "と": "to",
    "な": "na", "に": "ni", "ぬ": "nu", "ね": "ne", "の": "no",
    "は": "ha", "ひ": "hi", "ふ": "fu", "へ": "he", "ほ": "ho",
    "ま": "ma", "み": "mi", "む": "mu", "め": "me", "も": "mo",
    "や": "ya", "ゆ": "yu", "よ": "yo", "ら": "ra", "り": "ri", "る": "ru",
    "れ": "re", "ろ": "ro", "わ": "wa", "ゐ": "i", "ゑ": "e", "を": "o",
    "ん": "n", "が": "ga", "ぎ": "gi", "ぐ": "gu", "げ": "ge", "ご": "go",
    "ざ": "za", "じ": "ji", "ず": "zu", "ぜ": "ze", "ぞ": "zo",
    "だ": "da", "ぢ": "ji", "づ": "zu", "で": "de", "ど": "do",
    "ば": "ba", "び": "bi", "ぶ": "bu", "べ": "be", "ぼ": "bo",
    "ぱ": "pa", "ぴ": "pi", "ぷ": "pu", "ぺ": "pe", "ぽ": "po",
    "ゔ": "vu", "ぁ": "a", "ぃ": "i", "ぅ": "u", "ぇ": "e", "ぉ": "o",
    "ゃ": "ya", "ゅ": "yu", "ょ": "yo", "ゎ": "wa",
}
VOWELS = "aiueo"
# 元の音写が読みと一致しているとみなす類似度。実データでは 0.9 以上に 91.9% が入り、
# それ未満は Kokuho（国民健康保険）のような略記や、途中で切れた記述だった。
ROMAJI_MATCH_RATIO = 0.9
KATA_TO_HIRA = {chr(c): chr(c - 0x60) for c in range(0x30A1, 0x30F7)}


def load_prefixes(path):
    """先頭パターンを長い順に返す。

    長い順に当てないと `特定医療法人社団…` が `特定医療法人` で止まり、
    `社団` が施設名側に残ってしまう。
    """
    with open(path, encoding="utf-8-sig", newline="") as f:
        vals = [r["パターン"].strip() for r in csv.DictReader(f)
                if r["パターン"].strip()
                and (r.get("種別") or "").strip() != "括弧略記"]
    return sorted(vals, key=len, reverse=True)


def load_bracket_words(path):
    """括弧に入って現れる法人格の略記。`(医)` `(有)` `(株)` など。

    展開された `医療法人` とは別に持つ。1文字の略記を先頭パターンの一覧に
    混ぜると、`医` で始まる施設名の1文字目を落としてしまう。
    """
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [r["パターン"].strip() for r in csv.DictReader(f)
                if r["パターン"].strip()
                and (r.get("種別") or "").strip() == "括弧略記"]


def load_bracket_notes(path):
    """括弧に入って現れる注記。`(出張専門)` `(崎の字は山へんに立・可)` など。

    診療のやり方や字体の説明であって施設の名前ではないので name から除く。
    分院名や地名の括弧書き（`(新宿)`）は一覧に無いので残る。
    """
    with open(path, encoding="utf-8-sig", newline="") as f:
        return {r["パターン"].strip() for r in csv.DictReader(f)
                if r["パターン"].strip()}


def load_bracket_alt(path):
    """括弧に入って現れる別名と旧称。`(ユナイテッドクリニック)` など。

    施設の名前なので、注記とは違って捨てずに alt_name と old_name へ移す。
    どの括弧書きが別名でどれが分院名かは元データのカラムでは区別できないので、
    一覧に書いた文字列とだけ照合する。
    """
    with open(path, encoding="utf-8-sig", newline="") as f:
        out = {}
        for r in csv.DictReader(f):
            pattern = r["パターン"].strip()
            if pattern:
                out[pattern] = (r["種別"].strip(), r["値"].strip())
        return out


def load_facility_words(path):
    """施設種別語。空白区切りのトークンを運営主体かどうか判定する側でも使う。"""
    with open(path, encoding="utf-8-sig", newline="") as f:
        vals = [r["施設種別語"].strip() for r in csv.DictReader(f)
                if r["施設種別語"].strip()
                and (r.get("種別") or "施設種別").strip() != "末尾の診療科"]
    return sorted(vals, key=len, reverse=True)


def load_tail_speciality_words(path):
    """名称の末尾に来る診療科名。施設名らしいかの判定だけに使う。

    `こやま耳鼻咽喉科` の `耳鼻咽喉科` は施設の種類ではないので、トークンを
    分ける処理には読ませない。読ませると `耳鼻咽喉科　鈴木医院` の先頭が
    施設名の一部として保護され、標榜している診療科が name に残る。
    診療科名の一覧（speciality_mapping.csv）は `耳鼻いんこう科` の表記なので、
    `耳鼻咽喉科` とは一致しない。
    """
    with open(path, encoding="utf-8-sig", newline="") as f:
        return {r["施設種別語"].strip() for r in csv.DictReader(f)
                if r["施設種別語"].strip()
                and (r.get("種別") or "").strip() == "末尾の診療科"}


def load_operator_words(path, where="先頭"):
    """運営主体や保険者を表す語のうち、除く位置 が where のものを返す。

    `先頭` は空白で区切られた先頭の語と一致したときだけ落とす。`市立` は
    施設が略称でも名乗っていることがあるが、施設名ではないので、略称の
    照合より先に判定して落とす。

    `全体` は名称のどこにあっても落とす。`遠別町国民健康保険診療所` のように
    自治体名と施設名の間に挟まる語が対象で、先頭だけを見ると当たらない。

    除く位置 の列が無い古い一覧でも、すべて 先頭 として読む。
    """
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [r["語"].strip() for r in csv.DictReader(f)
                if r["語"].strip()
                and (r.get("除く位置") or "先頭").strip() == where]


def load_speciality_words(path):
    """診療科そのものの語。先頭に来たら施設名ではない。"""
    with open(path, encoding="utf-8-sig", newline="") as f:
        return {r["診療科目名(最頻)"].strip() for r in csv.DictReader(f)
                if r["診療科目名(最頻)"].strip()}


def load_suffixes(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [r["接尾辞"].strip() for r in csv.DictReader(f) if r["接尾辞"].strip()]


def normalize_chars(s):
    """全角英数を半角に、全角スペースを半角スペースに直す。日本語の文字は触らない。"""
    out = "".join(FULLWIDTH_ASCII.get(c, c) for c in s)
    out = out.replace("　", " ")
    return " ".join(out.split())


def to_romaji(hira):
    """ひらがなをヘボン式ローマ字にする。長音記号は落とし、促音は次の子音を重ねる。"""
    out = []
    i = 0
    while i < len(hira):
        c = hira[i]
        if c == "ー":
            i += 1
            continue
        if c == "っ":
            nxt = ROMAJI.get(hira[i + 1:i + 3]) or ROMAJI.get(hira[i + 1:i + 2], "")
            if nxt and nxt[0] not in VOWELS:
                out.append(nxt[0])
            i += 1
            continue
        two = hira[i:i + 2]
        if two in ROMAJI:
            out.append(ROMAJI[two])
            i += 2
            continue
        if c in ROMAJI:
            r = ROMAJI[c]
            if r == "n" and i + 1 < len(hira):
                nx = ROMAJI.get(hira[i + 1:i + 3]) or ROMAJI.get(hira[i + 1], "")
                if nx and (nx[0] in VOWELS or nx[0] == "y"):
                    r = "n'"
            out.append(r)
            i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def fold_romaji(s):
    """比較用に綴りの揺れを吸収する。長音（ou/oo/uu）・訓令式・連続文字を畳む。"""
    s = re.sub(r"[^a-z]", "", s.lower())
    s = s.replace("ou", "o").replace("oo", "o").replace("uu", "u").replace("ei", "e")
    s = re.sub(r"(.)\1+", r"\1", s)
    s = s.replace("sy", "sh").replace("ty", "ch").replace("jy", "j").replace("zy", "j")
    s = s.replace("si", "shi").replace("ti", "chi").replace("tu", "tsu")
    return s.replace("hu", "fu")


def romaji_agrees(source, hira):
    """元の音写が読みと一致するか、独立に生成したローマ字と突き合わせて判定する。"""
    a, b = fold_romaji(to_romaji(hira)), fold_romaji(source)
    if not a or not b:
        return False, 0.0
    if a == b:
        return True, 1.0
    ratio = difflib.SequenceMatcher(None, a, b).ratio()
    return ratio >= ROMAJI_MATCH_RATIO, ratio


def titlecase_latn(s):
    return " ".join(w[:1].upper() + w[1:].lower() if w[:1].isalpha() else w
                    for w in s.split())


def to_hiragana(s):
    """カタカナをひらがなに変換する。長音符・記号はそのまま残す。"""
    return "".join(KATA_TO_HIRA.get(c, c) for c in s)


def _squash(value):
    """空白を除いて突き合わせる。元データは全角と半角の空白が混在する。"""
    return (value or "").replace("\u3000", "").replace(" ", "").strip()


# 法人名の接尾辞の直後にこの文字が来るときは、そこで語が切れていない。
# `岸和田市医師会館` の `会館`、`DIC株式会社小牧工場診療所` の `会社`、
# `肝属郡医師会立病院` の `会立`、`小松会営薬局` の `会営`、
# `ヤマグチ薬局六会店` の `会店` が該当する。
SUFFIX_CONTINUES = "館社立営店"

# 法人名を取り去った後に先頭へ残る空白と記号。`(社団)児玉医院` の閉じ括弧など。
LEADING_NOISE = re.compile(r"^[\s\u3000)\]）】」』＞>》・,、.。／/－-]+")


def entity_head(rest, suffixes, limit=10):
    """先頭から法人名の接尾辞で終わる最短の語を返す。無ければ空文字。

    最長の語を返すと `社会医療法人孝仁会札幌孝仁会記念病院` が `記念病院` に
    なる。法人名と同じ語が施設名にも入る形が多く、後ろ側まで落ちてしまう。

    接尾辞そのものより長い語だけを返す。`会田医院` の1文字目のように、
    施設名の先頭がたまたま接尾辞と同じ文字で始まる場合に切らないためである。
    """
    for i in range(1, min(len(rest), limit) + 1):
        nxt = rest[i:i + 1]
        if not nxt or nxt in SUFFIX_CONTINUES:
            continue
        head = rest[:i]
        # 空白をまたぐ語は返さない。`コスモ調剤薬局 会津店` の `会` を切れ目と
        # みなすと、地名の `会津` が `津` だけになる。空白で区切られた名称は
        # 2) が先に処理している。
        if " " in head or "\u3000" in head:
            break
        if any(head.endswith(s) and len(head) > len(s) for s in suffixes):
            return head
    return ""


# 語を落とした跡に残る連続した空白。`下北医療センター 国民健康保険 大畑診療所`
# から保険者の名を落とすと、空白が2つ並ぶ。
DOUBLE_SPACE = re.compile(r"[ \u3000]{2,}")

# 語をつなぐときに空白を残す境界。両側が欧字か数字のとき。
ASCII_HEAD = re.compile(r"[A-Za-z0-9]")
ASCII_TAIL = re.compile(r"[A-Za-z0-9]$")

# 名称に現れる括弧書き。`(医)成心会なりた内科クリニック` のように先頭にも、
# `岡本整形外科クリニック(医療法人)` のように末尾にも来る。
BRACKET = re.compile(r"[(（]([^)）]*)[)）]")


def is_facility(token, facility_words):
    return any(token.endswith(w) for w in facility_words)


def is_only_facility(value, facility_words):
    """施設の種類を表す語だけでできているかを返す。

    `薬局` や `歯科クリニック` のように施設種別語を取り去ると何も残らない
    文字列は、どの施設を指すか決められない。運営主体を落とした結果が
    この形になる行で、落とすのをやめる判定に使う。`荘歯科医院` のように
    実在の名称もこの形になるので、落とす前後の比較にだけ使い、
    名称そのものの良し悪しの判定には使わない。
    """
    rest = _squash(value)
    if not rest:
        return False
    changed = True
    while changed:
        changed = False
        for word in sorted(facility_words, key=len, reverse=True):
            if word in rest:
                rest = rest.replace(word, "")
                changed = True
    return not rest


def _join_tokens(value):
    """空白で区切られた語をつないで1つの名称に戻す。

    元データは語の区切りに空白を使うが、`キング　薬局` の空白は表記上の
    区切りであって名前の一部ではない。詰めて1語にする。ただし
    `OKP with Life` のように欧字が並ぶ箇所は、詰めると語の切れ目が
    読めなくなるので空白を残す。
    """
    out = ""
    for token in value.split(" "):
        if not token:
            continue
        if out and ASCII_HEAD.match(token) and ASCII_TAIL.search(out):
            out += " "
        out += token
    return out


def looks_like_facility(value, facility_words, speciality_words):
    """施設名らしく終わっているかを返す。

    施設種別語（`クリニック` `病院` など）か診療科名（`整形外科` など）で
    終わっていれば、施設を指す名前とみなす。`明雪会` のような法人名は
    どちらでも終わらない。
    """
    v = _squash(value)
    if not v:
        return False
    return (any(v.endswith(w) for w in facility_words)
            or any(v.endswith(w) for w in speciality_words))


def has_facility_word(value, facility_words, speciality_words):
    """施設種別語か診療科名を1つでも含むかを返す。

    末尾だけを見ると `宇梶歯科医院本院` や `レーベンデンタルクリニック稲城` を
    施設名でないと判定する。分院名や地名で終わる施設名が多いので、名前の
    どこかに施設種別語か診療科名があれば施設名とみなす。
    """
    v = _squash(value)
    if not v:
        return False
    return (any(w in v for w in facility_words)
            or any(w in v for w in speciality_words))


def use_short_name(name, short_name, facility_words, speciality_words):
    """正式名称に法人名しか入っていない施設かどうかを返す。

    元データの 正式名称 が `医療法人明雪会` のように法人名だけで終わり、
    施設名は 略称 の `環状通東整形外科` にしかない行がある。この形では
    法人格を落としても name が施設を指さないので、略称 を name に使う。

    name が施設種別語も診療科名も含まなければ、施設名が入っていないと判断する。
    `竹内外科胃腸科` のように診療科名を含む名前は、正式名称に施設名があるので
    使わない。

    name が 略称 に含まれるかどうかは見ない。`医療法人光` の 略称 は
    `安光歯科医院` で、`光` は途中に現れるだけの別の名前である。
    `医療法人　さんさん` の 略称 `さんさん歯科医院` のように、法人名に施設種別語を
    足した形も 略称 のほうが施設を指す。
    """
    if has_facility_word(name, facility_words, speciality_words):
        return False
    return looks_like_facility(short_name, facility_words, speciality_words)


def strip_bracket_notes(name, notes):
    """括弧に入った注記を name から除く。

    戻り値は (施設名, 除いた括弧書きのリスト)。除く対象が無ければ元のまま返す。
    元の文字列は official_name に残るので、ここで除いても情報は失われない。
    括弧を外すと名称が空になる行（`(出張専門)` だけの行）は元のまま返す。
    """
    dropped = []

    def _drop(m):
        if m.group(1).strip() in notes:
            dropped.append(m.group(0))
            return ""
        return m.group(0)

    cut = BRACKET.sub(_drop, name)
    if not dropped:
        return name, []
    cut = DOUBLE_SPACE.sub(" ", cut).strip()
    if not cut:
        return name, []
    return cut, dropped


def strip_bracket_alt(name, alt):
    """括弧に入った別名と旧称を name から除き、値を返す。

    戻り値は (施設名, alt_name, old_name, 除いた括弧書きのリスト)。
    `ギガクリニック札幌院(ユナイテッドクリニック)` は name が
    `ギガクリニック札幌院`、alt_name が `ユナイテッドクリニック` になる。
    括弧を外すと名称が空になる行は元のまま返す。
    """
    dropped = []
    found = []

    def _drop(m):
        hit = alt.get(m.group(1).strip())
        if hit:
            dropped.append(m.group(0))
            found.append(hit)
            return ""
        return m.group(0)

    cut = BRACKET.sub(_drop, name)
    if not dropped:
        return name, "", "", []
    cut = DOUBLE_SPACE.sub(" ", cut).strip()
    if not cut:
        return name, "", "", []
    alt_name = "／".join(v for kind, v in found if kind == "別名")
    old_name = "／".join(v for kind, v in found if kind == "旧称")
    return cut, alt_name, old_name, dropped


def strip_hira_notes(hira):
    """読みから括弧書きを除く。

    name から注記を除いた行で呼ぶ。元データのフリガナは
    `アサノハジョサンイン（シュッチョウセンモン）` のように注記の読みまで
    含んでおり、そのままでは name と対応しない。
    """
    cut = DOUBLE_SPACE.sub(" ", BRACKET.sub("", hira)).strip()
    return cut or hira


def _drop_stray_bracket(rest):
    """対応する相手が無い括弧が先頭に残ったときだけ取り去る。

    元データの 正式名称 には `医療法人社団）いのまた循環器科内科` のように
    閉じ括弧だけの行がある。法人格を落とすと `）いのまた…` が残る。
    名称の途中にある閉じない括弧（`キムデンタルクリニック(D.KIMS D`）は
    施設名の一部が切れた形なので触らない。
    """
    if rest[:1] in (")", "）"):
        return rest[1:].strip() or rest
    if rest[:1] in ("(", "（") and not any(c in rest for c in ")）"):
        return rest[1:].strip() or rest
    return rest


def strip_entity(name, prefixes, suffixes, facility_words, short_name="",
                 speciality_words=frozenset(), operator_words=(),
                 anywhere_words=(), bracket_words=()):
    """先頭から運営主体と識別できるトークンだけを取り除く。

    戻り値は (施設名, 取り除いた文字列のリスト, 推定で落とした文字列のリスト)。
    識別できない場合は元のまま返す。

    3つ目は、法人格でも法人名の接尾辞でもなく、施設種別語の位置から運営主体と
    推定して落としたものである。この推定が誤っている行では、施設名の一部を
    name から除いてしまう。正しいかどうかは元データだけでは決まらないので、
    呼び出し側で作業者に確かめてもらう印に使う。

    推定して落とした結果が施設種別語だけになった行では、落とした分を戻す。
    `キング　薬局` が `薬局` になると、どの薬局を指すか決められないためである。
    戻した行では3つ目が空になり、要確認 も立たない。
    """
    removed = []
    guessed = []
    had_prefix = False
    rest = name
    # 推定で語を落とす前の文字列。落とした結果が施設種別語だけになったとき、
    # ここへ戻す。
    before_guess = None
    # 法人名を落とすのをやめた行。名称に残る空白を詰めて返す。
    join_at_end = False

    # 0) 括弧に入った法人格。中身が一覧の略記そのものか、法人格で始まる
    #    （`(医療法人真生会)`）なら括弧ごと落とす。分院名や営業形態の括弧書き
    #    （`(那覇院)` `(出張専門)`）には触れない。
    def _drop_bracket(m):
        inner = m.group(1).strip()
        if inner in bracket_words or any(inner.startswith(p) for p in prefixes):
            removed.append(m.group(0))
            return ""
        return m.group(0)

    # 0b) `医）工藤整形外科` のように閉じ括弧だけで始まる行。開きが無いので
    #     対を探す _drop_bracket には一致しない。
    for word in sorted(bracket_words, key=len, reverse=True):
        for close in (")", "）"):
            head = word + close
            if rest.startswith(head) and len(rest) > len(head):
                removed.append(head)
                rest = rest[len(head):].strip()
                had_prefix = True
                break
        else:
            continue
        break

    cut = BRACKET.sub(_drop_bracket, rest)
    if cut != rest:
        cut = DOUBLE_SPACE.sub(" ", cut).strip()
        if cut:
            rest = cut
            had_prefix = True
        else:
            del removed[:]

    # 1) 空白を挟まずに法人格が前置されている場合（例: 医療法人社団明和会中村病院）
    changed = True
    while changed:
        changed = False
        for p in prefixes:
            if rest.startswith(p) and len(rest) > len(p):
                removed.append(p)
                rest = rest[len(p):].strip()
                changed = True
                had_prefix = True
                break

    rest = _drop_stray_bracket(rest)

    # 2) 空白区切りのトークン列を先頭から見て、運営主体と識別できる分だけ落とす。
    #    施設名そのものに空白が含まれる例が多いので、識別できなければそこで止める。
    while " " in rest:
        head, tail = rest.split(" ", 1)
        tail = tail.strip()
        if not tail:
            break
        # 2a) 法人格そのもの、または法人名の接尾辞で終わるトークン
        if head in prefixes or any(head.endswith(s) for s in suffixes):
            # 落とすと施設の種類を表す語だけが残る行では落とさない。
            # `晋栄福祉会　診療所` が `診療所` になり、どの診療所を指すか
            # 決められなくなる。ただし元データの略称が残りだけを名乗って
            # いるなら、それが施設の名前である（`仁寿会　荘病院` の略称は
            # `荘病院`）。
            if (is_only_facility(tail, facility_words)
                    and _squash(short_name) != _squash(tail)):
                join_at_end = True
                break
            removed.append(head)
            rest = tail
            continue
        # 2b) 先頭が施設種別語で終わらず、末尾側が終わるなら先頭は運営主体とみなす。
        #     `ふじい薬局 明野調剤` は先頭が施設種別語で終わるので保護され、
        #     `オアシス ファーマシー` は末尾が施設種別語でないので保護される。
        if (not is_facility(head, facility_words)
                and is_facility(tail.split(" ")[-1], facility_words)):
            # 診療科そのものと運営主体の語は、略称に残っていても落とす。
            if head in speciality_words or any(w in head for w in operator_words):
                if before_guess is None:
                    before_guess = rest
                removed.append(head)
                guessed.append(head)
                rest = tail
                continue
            # 元データの略称が「この語 + 残り」なら、施設が自ら名乗っている
            # 名前の一部であって運営主体ではない。落とさずにここで止める。
            if short_name and _squash(short_name) == _squash(head) + _squash(tail):
                break
            if before_guess is None:
                before_guess = rest
            removed.append(head)
            guessed.append(head)
            rest = tail
            continue
        break

    # 2') 推定で落とした結果、施設の種類を表す語だけが残ることがある。
    #     `キング　薬局` が `薬局` に、`しまだ　みみ・はな・のど　クリニック` が
    #     `クリニック` になり、どの施設を指すか決められない。推定で落とした分を
    #     まとめて戻す。段2a で落とした法人格は運営主体そのものなので戻さない。
    if before_guess is not None and is_only_facility(rest, facility_words):
        for token in guessed:
            removed.remove(token)
        guessed.clear()
        rest = _join_tokens(before_guess)

    # 3) トークンを落とした結果、先頭に再び法人格が現れることがある
    #    （例: `医療法人社団温光会 医療法人内藤病院`）。もう一度当てる。
    changed = True
    while changed:
        changed = False
        for pfx in prefixes:
            if rest.startswith(pfx) and len(rest) > len(pfx):
                removed.append(pfx)
                rest = rest[len(pfx):].strip()
                changed = True
                had_prefix = True
                break

    # 4) 法人格を落とした結果 `社団` `財団` だけが残った場合に続けて落とす
    for token in ("社団", "財団"):
        if rest.startswith(token) and len(rest) > len(token):
            removed.append(token)
            rest = rest[len(token):].strip()

    # 5) 空白を挟まずに法人名が前置されている場合（例: 特定医療法人仁泉会朝倉病院）。
    #    2) は空白で区切られた語しか見ないので、空白の無い名称では
    #    法人名の接尾辞が一度も照合されない。ここで照合する。
    #    `恩賜財団済生会支部北海道済生会小樽病院` のように法人名が重なる例が
    #    あるので、落とせなくなるまで繰り返す。
    #    法人格を落とした行だけを対象にする。法人格が無い行でも動かすと、
    #    `コスモ調剤薬局 会津店` や `ヤマグチ薬局六会店` の地名が削れる。
    before = rest
    while had_prefix:
        head = entity_head(rest, suffixes)
        if not head:
            break
        tail = LEADING_NOISE.sub("", rest[len(head):])
        if not tail:
            break
        # 元データの略称が「この語 + 残り」なら、施設が自ら名乗っている名前の
        # 一部であって運営主体ではない。2b) と同じ判定である。
        if _squash(short_name) == _squash(head) + _squash(tail):
            break
        # 施設種別語や診療科だけが残ると、どの施設を指すか分からなくなる。
        # `日本相撲協会診療所` が `診療所` に、`六会眼科` が `眼科` になる。
        # `歯科診療所` のように施設種別語が連なる形も同じ扱いにする。
        if is_only_facility(tail, facility_words) or tail in speciality_words:
            break
        # 何に附属するかが消える。`岩手県予防医学協会附属診療所` が
        # `附属診療所` になる。
        if tail.startswith(("附属", "付属")):
            break
        removed.append(head)
        rest = tail
    # 続けて落とした語は元の文字列で隣り合っている。`北海道社会` `事業協会` と
    # 分けて記録すると実在しない語が並ぶので、落とした範囲を1つにまとめる。
    if rest != before:
        guessed.append(before[:len(before) - len(rest)])

    # 法人名を落とした跡にも片方だけの括弧が残る。
    # `医療法人社団潮友会（巡回診療…` の `潮友会` は段5で落ちるので、
    # 段1の直後だけでは取り去れない。
    rest = _drop_stray_bracket(rest)

    # 6) 名称のどこにあっても落とす語。`国民健康保険` は保険者の名で、
    #    `遠別町国民健康保険診療所` のように自治体名と施設名の間に挟まる。
    #    どの語を落とすかは決まっていて推定ではないので、法人格と同じく
    #    要確認 は立てず、備考 の記録だけに残す。
    for word in anywhere_words:
        if word not in rest:
            continue
        # 元データの略称がこの語を含むなら、施設が自ら名乗っている名前の
        # 一部なので落とさない。
        if word in _squash(short_name):
            continue
        cut = DOUBLE_SPACE.sub(" ", rest.replace(word, "")).strip()
        # 施設種別語や診療科だけが残ると、どの施設を指すか分からなくなる。
        if not cut or cut in facility_words or cut in speciality_words:
            continue
        removed.append(word)
        rest = cut

    if join_at_end:
        rest = _join_tokens(rest)
    return rest, removed, guessed


# 英語表記に紛れる中黒。ASCII に収めるため空白へ寄せる。
# 長音記号は落とす。ローマ字を生成する側でも同じ扱いにしており、突き合わせの
# 両辺で表記を揃えておく必要があるため。
EN_PUNCT = {"･": " ", "・": " ", "　": " ", "／": "/", "－": "-",
            "”": '"', "’": "'", "ー": "", "ｰ": ""}


def clean_english(value):
    out = "".join(EN_PUNCT.get(c, c) for c in value)
    out = "".join(FULLWIDTH_ASCII.get(c, c) for c in out)
    return " ".join(out.split())


def looks_english(value):
    low = value.lower()
    return any(m in low for m in ENGLISH_MARKERS)


def resolve(base, pattern):
    hits = sorted(glob.glob(os.path.join(base, pattern)))
    if not hits:
        sys.exit(f"入力ファイルが見つかりません: {pattern}")
    return hits[-1]



def needs_review(name, why=""):
    """作業者の確認が要る施設かどうかを決める。

    立てるのは name が空の施設だけである。出力する名前そのものが無いので、
    元データを見ないとタグを埋められない。

    理由にしないものが2つある。どちらも、出力そのものには欠けが無い。

    運営主体を除去したことは理由にしない。除去した文字列は official_name に
    そのまま残り、operator も出していないため、作業者が現地で確かめる対象が
    無い。5業態で47,626行が該当していた。

    元データの英語表記を採用しなかったことも理由にしない。name と
    official_name はどちらも出ており、name:en と name:ja-Latn を足すかどうかは
    欠陥の修正ではなく任意の追加になる。5業態で20,151行が該当していた。
    採らなかった判断そのものは 備考 に残す。

    何をしたかの記録は要るが、作業を頼む印とは別物なので、備考 と 要確認 で
    扱いを分ける。mapping/facility_tags.csv の 確度=broader を build_osm.py の
    needs_review から外したのと同じ考え方である。

    先頭トークンを運営主体と推定して落とした行は理由にする。落とした語は
    行ごとに違い、推定が正しいかは元データだけでは決まらない。外れた行では
    施設名そのものが name から欠ける。official_name に元の形が残り、元データの
    略称 は理由の文の中に書くので、作業者はその2つと見比べて直せる。
    """
    if not name.strip():
        return "yes"
    if why.strip():
        return "yes"
    return ""


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir", default=".")
    p.add_argument("--out-dir", default="output")
    p.add_argument("--sector", default="hospital", choices=sorted(SECTORS))
    p.add_argument("--prefixes", default=os.path.join("mapping", "name_entity_prefixes.csv"))
    p.add_argument("--suffixes", default=os.path.join("mapping", "name_entity_suffixes.csv"))
    p.add_argument("--facility-words",
                   default=os.path.join("mapping", "name_facility_words.csv"))
    p.add_argument("--operator-words",
                   default=os.path.join("mapping", "name_operator_words.csv"))
    p.add_argument("--bracket-notes",
                   default=os.path.join("mapping", "name_bracket_notes.csv"))
    p.add_argument("--bracket-alt",
                   default=os.path.join("mapping", "name_bracket_alt.csv"))
    p.add_argument("--speciality",
                   default=os.path.join("mapping", "speciality_mapping.csv"))
    args = p.parse_args()

    label, pattern, col_name, col_short, col_kana, col_en = SECTORS[args.sector]
    src = resolve(args.data_dir, pattern)
    prefixes = load_prefixes(args.prefixes)
    suffixes = load_suffixes(args.suffixes)
    facility_words = load_facility_words(args.facility_words)
    operator_words = load_operator_words(args.operator_words)
    anywhere_words = load_operator_words(args.operator_words, "全体")
    bracket_words = load_bracket_words(args.prefixes)
    bracket_notes = load_bracket_notes(args.bracket_notes)
    bracket_alt = load_bracket_alt(args.bracket_alt)
    speciality_words = load_speciality_words(args.speciality)
    # 施設名らしいかの判定だけに足す語。トークンの分割には混ぜない。
    name_words = speciality_words | load_tail_speciality_words(args.facility_words)
    print(f"業態     : {label}")
    print(f"施設票   : {os.path.basename(src)}")

    rows = []
    stats = collections.Counter()
    removed_use = collections.Counter()

    with open(src, encoding="utf-8-sig", newline="") as f:
        r = csv.reader(f)
        idx = {h: n for n, h in enumerate(next(r))}
        for row in r:
            fid = row[0]
            original = row[idx[col_name]].strip()
            short = row[idx[col_short]].strip() if col_short else ""
            kana = row[idx[col_kana]].strip() if col_kana else ""
            en = row[idx[col_en]].strip() if col_en else ""

            normalized = normalize_chars(original)
            name, removed, guessed = strip_entity(
                normalized, prefixes, suffixes, facility_words,
                short, speciality_words, operator_words, anywhere_words,
                bracket_words)
            # 正式名称に法人名しか入っていない施設は、略称 を name に使う。
            # 法人格を落とした行だけを対象にする。法人格が無い名称は届出の
            # 表記ゆれであって、法人名だけになっている形とは別である。
            used_short = (any(x in prefixes for x in removed)
                          and use_short_name(name, short, facility_words,
                                             name_words))
            if used_short:
                alt = strip_entity(
                    normalize_chars(short), prefixes, suffixes, facility_words,
                    "", speciality_words, operator_words, anywhere_words,
                    bracket_words)[0]
                if looks_like_facility(alt, facility_words, name_words):
                    name = alt
                else:
                    used_short = False

            # 診療形態と字体の説明は施設の名前ではないので name から除く。
            # 運営主体の除去とは別の判断なので、備考 にも別の文で残す。
            name, dropped_notes = strip_bracket_notes(name, bracket_notes)

            # 括弧に入った別名と旧称は施設の名前なので、捨てずに
            # alt_name と old_name へ移す。
            name, alt_name, old_name, dropped_alt = strip_bracket_alt(
                name, bracket_alt)

            for x in removed:
                removed_use[x] += 1

            notes = []
            if normalized != original:
                notes.append("全角英数・空白を正規化")
                stats["文字正規化"] += 1
            if removed:
                notes.append("運営主体を除去: " + "／".join(removed))
                stats["主体除去"] += 1
            if dropped_notes:
                notes.append("括弧の注記を除去: " + "／".join(dropped_notes))
                stats["注記除去"] += 1
            if dropped_alt:
                notes.append("括弧の別名と旧称を移動: " + "／".join(dropped_alt))
                stats["別名移動"] += 1

            # フリガナは運営主体を含む読みなので、name を削った施設では対応しない
            hira = ""
            if kana:
                if removed or used_short:
                    notes.append("フリガナが運営主体を含み name と対応しないため name:ja-Hira は出力しない")
                    stats["読み不一致"] += 1
                else:
                    hira = to_hiragana(normalize_chars(kana))
                    # フリガナは注記の読みまで含む。name から注記を除いた行では
                    # 読みも合わせないと、name:ja-Hira が name と対応しない。
                    if dropped_notes or dropped_alt:
                        hira = strip_hira_notes(hira)
                    stats["読みあり"] += 1

            name_en = ""
            name_latn = ""
            if en:
                cleaned = clean_english(en)
                if not looks_english(cleaned):
                    # 音写とみられる値は name:ja-Latn の候補にする。ただし読みと
                    # 一致するか確認できたものだけを採る。元データには先頭が欠けた
                    # もの（旭川脳神経外科循環器内科病院 → Asahikawa Noge）が混じる。
                    if not hira:
                        notes.append(
                            f"音写だが読みが name と対応せず検証できないため出力しない: {en}")
                        stats["読み未対応で検証不能"] += 1
                    else:
                        ok, ratio = romaji_agrees(cleaned, hira)
                        if ok:
                            name_latn = titlecase_latn(cleaned)
                            stats["name:ja-Latn 出力"] += 1
                        else:
                            notes.append(
                                f"音写が読みと一致しないため出力しない"
                                f"（類似度{ratio:.2f}）: {en} / 読みからの生成="
                                f"{to_romaji(hira)}")
                            stats["読みと不一致"] += 1
                elif not cleaned.isascii():
                    notes.append(f"英語表記に ASCII 外の文字が残るため出力しない: {en}")
                    stats["非ASCIIのため除外"] += 1
                else:
                    name_en = cleaned
                    stats["英語表記あり"] += 1

            # 略称 は OSM のタグに出さないので、参照する文の中に値を書く。
            ref = f"元データの略称「{short}」と official_name" if short \
                else "official_name"
            why = ""
            if guessed:
                why = ("名称の先頭の「" + "」「".join(guessed)
                       + "」を運営主体とみなして name から除いた。"
                       f"{ref} で確かめてください")
            if used_short:
                why = ("正式名称が法人名で終わり施設名を含まないため、"
                       f"name に元データの略称「{short}」を使った。"
                       "official_name で確かめてください")
            if why:
                notes.append(why)
            review = needs_review(name, why)
            rows.append([fid, original, short, kana, en,
                         name, original, short, alt_name, old_name,
                         hira, name_en, name_latn,
                         review, " / ".join(notes), why])
            stats["施設"] += 1
            if review:
                stats["要確認"] += 1

    build_dir = os.path.join(args.out_dir, "build")
    os.makedirs(build_dir, exist_ok=True)
    out = os.path.join(build_dir, f"{args.sector}_names.csv")
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ID",
                    f"元_{col_name}", "元_略称", "元_フリガナ", "元_英語表記",
                    "name", "official_name", "short_name",
                    "alt_name", "old_name", "name:ja-Hira",
                    "name:en", "name:ja-Latn", "要確認", "備考",
                    "要確認の理由"])
        w.writerows(rows)

    print()
    print(f"施設数              : {stats['施設']:,}")
    print(f"文字を正規化        : {stats['文字正規化']:,}")
    print(f"運営主体を除去      : {stats['主体除去']:,}")
    print(f"括弧の注記を除去    : {stats['注記除去']:,}")
    print(f"別名と旧称を移動    : {stats['別名移動']:,}")
    print(f"name:ja-Hira 出力   : {stats['読みあり']:,}")
    print(f"  読み不一致で保留  : {stats['読み不一致']:,}")
    print(f"name:en 出力        : {stats['英語表記あり']:,}")
    print(f"  非ASCIIのため保留 : {stats['非ASCIIのため除外']:,}")
    print(f"name:ja-Latn 出力   : {stats['name:ja-Latn 出力']:,}")
    print(f"  読みと不一致で保留: {stats['読みと不一致']:,}")
    print(f"  読み未対応で検証不能: {stats['読み未対応で検証不能']:,}")
    # 列を足したときに位置がずれないよう、要確認は行を組み立てる際に数えておく
    print(f"要確認              : {stats['要確認']:,}")
    if removed_use:
        print("\n除去した運営主体 上位10:")
        for k, v in removed_use.most_common(10):
            print(f"  {v:7,}  {k}")
    print(f"\n出力: {out}")


if __name__ == "__main__":
    main()
