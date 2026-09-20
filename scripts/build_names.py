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
        vals = [r["パターン"].strip() for r in csv.DictReader(f) if r["パターン"].strip()]
    return sorted(vals, key=len, reverse=True)


def load_facility_words(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        vals = [r["施設種別語"].strip() for r in csv.DictReader(f)
                if r["施設種別語"].strip()]
    return sorted(vals, key=len, reverse=True)


def load_operator_words(path):
    """先頭に来たら運営主体とみなす語。略称に残っていても落とす。

    `国民健康保険` や `市立` は保険者や設置者を表す語で、施設が略称でも
    名乗っていることがある。略称を根拠に残すと、施設名ではない語が name に
    入るため、略称の照合より先に判定する。
    """
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [r["語"].strip() for r in csv.DictReader(f) if r["語"].strip()]


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
        # みなすと、地名の `会津` が `津` だけになる。空白区切りは段2が扱う。
        if " " in head or "\u3000" in head:
            break
        if any(head.endswith(s) and len(head) > len(s) for s in suffixes):
            return head
    return ""


def is_facility(token, facility_words):
    return any(token.endswith(w) for w in facility_words)


def strip_entity(name, prefixes, suffixes, facility_words, short_name="",
                 speciality_words=frozenset(), operator_words=()):
    """先頭から運営主体と識別できるトークンだけを取り除く。

    戻り値は (施設名, 取り除いた文字列のリスト, 推定で落とした文字列のリスト)。
    識別できない場合は元のまま返す。

    3つ目は、法人格でも法人名の接尾辞でもなく、施設種別語の位置から運営主体と
    推定して落としたものである。この推定は外れることがあり、外れた行では
    `楠井　歯科` が `歯科` になる。正しいかどうかは元データだけでは決まらないので、
    呼び出し側で作業者に確かめてもらう印に使う。
    """
    removed = []
    guessed = []
    had_prefix = False
    rest = name

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

    # 2) 空白区切りのトークン列を先頭から見て、運営主体と識別できる分だけ落とす。
    #    施設名そのものに空白が含まれる例が多いので、識別できなければそこで止める。
    while " " in rest:
        head, tail = rest.split(" ", 1)
        tail = tail.strip()
        if not tail:
            break
        # 2a) 法人格そのもの、または法人名の接尾辞で終わるトークン
        if head in prefixes or any(head.endswith(s) for s in suffixes):
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
                removed.append(head)
                guessed.append(head)
                rest = tail
                continue
            # 元データの略称が「この語 + 残り」なら、施設が自ら名乗っている
            # 名前の一部であって運営主体ではない。落とさずにここで止める。
            if short_name and _squash(short_name) == _squash(head) + _squash(tail):
                break
            removed.append(head)
            guessed.append(head)
            rest = tail
            continue
        break

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
    #    段2の接尾辞の判定は空白区切りのトークンしか見ないので、ここで当てる。
    #    `恩賜財団済生会支部北海道済生会小樽病院` のように法人名が重なる例が
    #    あるので、落とせなくなるまで繰り返す。
    #    法人格を落とした行だけを対象にする。法人格が無い行にも当てると、
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
        # 一部であって運営主体ではない。段2b と同じ判定である。
        if _squash(short_name) == _squash(head) + _squash(tail):
            break
        # 施設種別語や診療科だけが残ると、どの施設を指すか分からなくなる。
        # `日本相撲協会診療所` が `診療所` に、`六会眼科` が `眼科` になる。
        if tail in facility_words or tail in speciality_words:
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
    施設名そのものが name から欠ける。official_name と short_name に元の形が
    残るので、作業者はその2つと見比べて直せる。
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
    p.add_argument("--speciality",
                   default=os.path.join("mapping", "speciality_mapping.csv"))
    args = p.parse_args()

    label, pattern, col_name, col_short, col_kana, col_en = SECTORS[args.sector]
    src = resolve(args.data_dir, pattern)
    prefixes = load_prefixes(args.prefixes)
    suffixes = load_suffixes(args.suffixes)
    facility_words = load_facility_words(args.facility_words)
    operator_words = load_operator_words(args.operator_words)
    speciality_words = load_speciality_words(args.speciality)
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
                short, speciality_words, operator_words)
            for x in removed:
                removed_use[x] += 1

            notes = []
            if normalized != original:
                notes.append("全角英数・空白を正規化")
                stats["文字正規化"] += 1
            if removed:
                notes.append("運営主体を除去: " + "／".join(removed))
                stats["主体除去"] += 1

            # フリガナは運営主体を含む読みなので、name を削った施設では対応しない
            hira = ""
            if kana:
                if removed:
                    notes.append("フリガナが運営主体を含み name と対応しないため name:ja-Hira は出力しない")
                    stats["読み不一致"] += 1
                else:
                    hira = to_hiragana(normalize_chars(kana))
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

            why = ""
            if guessed:
                why = ("名称の先頭の「" + "」「".join(guessed)
                       + "」を運営主体とみなして name から除いた。"
                       "official_name と short_name で確かめてください")
            if why:
                notes.append(why)
            review = needs_review(name, why)
            rows.append([fid, original, short, kana, en,
                         name, original, short, hira, name_en, name_latn,
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
                    "name", "official_name", "short_name", "name:ja-Hira",
                    "name:en", "name:ja-Latn", "要確認", "備考",
                    "要確認の理由"])
        w.writerows(rows)

    print()
    print(f"施設数              : {stats['施設']:,}")
    print(f"文字を正規化        : {stats['文字正規化']:,}")
    print(f"運営主体を除去      : {stats['主体除去']:,}")
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
