"""薬局の name から支店名を分け、branch に移す（Issue #12）。

`アイン薬局 塚ノ原店` を `name=アイン薬局` と `branch=塚ノ原店` にする。
OSM wiki の Key:branch は、name にはブランドやチェーンの名前を、branch には
どの支店かを示す名前を書くとしている。branch の値は元データの支店名のまま
「店」まで含める。「店」を外した名前は元データにも看板にも無いためである。

分けるのは、name が「店」で終わる次の2つの形だけである。

1. 空白が1つあり、空白の後ろが支店名になっている形（`レインボー薬局 上磯店`）
2. 空白が無く、最後の「薬局」の直後から支店名になっている形（`つつじ薬局潮見店`）

次の形は分けない。どれも、どこまでを店名にするかを文字列から決められない。

- 空白の後ろにも「薬局」がある形（`辻薬店 辻薬局玄海町店`）。先頭の語は
  会社名や屋号で、運営者をどう扱うかは Issue #11 で決める。
- 店名に会社名が入っている形（`あおい調剤薬局株式会社 石原店`）。理由は同じ。
- 名前が「薬局」「調剤薬局」「保険薬局」で始まり空白が無い形
  （`調剤薬局ツルハドラッグ花川北店`）。最後の「薬局」が店名の先頭にある。
- 支店名が `本店` や `3号店` になる形。場所を示さず、名前の一部として読まれる。
- 支店名が「店」の1文字だけになる形（`つがる薬局店`）。

読み仮名とローマ字と英語名も、店名の部分だけにする。分けられない値は
出さない。支店名を含んだままの読みを短くした name に付けると、name と
読みが食い違うためである。元の名前は official_name に残る。
"""

import difflib
import re

# 支店名として分けない値。場所を示さず、名前の一部として読まれる。
KEEP_BRANCH = re.compile(r"本店|[0-9０-９一二三四五六七八九十]+号店|店")

# 店名にあれば分けない語。運営者の扱いは Issue #11 で決める。
COMPANY = re.compile(r"株式会社|有限会社|合同会社|合資会社|合名会社")

# 名前の先頭にあるとき、最後の「薬局」が店名の先頭を指す語
LEADING_PHARMACY = re.compile(r"(?:調剤|保険)*薬局")

# 店名と支店名の間に入る区切り
SEPARATOR = "・･-－‐.．、， 　"

# 英語名で「薬局」にあたる語
EN_PHARMACY = re.compile(r"pharmacy|drug ?store", re.I)


def split_name(name):
    """name を (店名, 支店名) に分ける。分けない形なら None を返す。"""
    if not name.endswith("店"):
        return None
    parts = name.split()
    if len(parts) == 2:
        head, branch = parts
        if "薬局" in branch:
            return None
    elif len(parts) == 1:
        if "薬局" not in name or LEADING_PHARMACY.match(name):
            return None
        i = name.rfind("薬局") + len("薬局")
        head, branch = name[:i], name[i:]
    else:
        return None
    head = head.rstrip(SEPARATOR)
    branch = branch.lstrip(SEPARATOR)
    if not head or not branch or KEEP_BRANCH.fullmatch(branch):
        return None
    if COMPANY.search(head):
        return None
    # `薬局 マツモトキヨシ塩田店` を分けると name が `薬局` だけになる。
    if LEADING_PHARMACY.fullmatch(head):
        return None
    return head, branch


def _cut_after(value, word, count):
    """value の最後の word の直後で切った前半を返す。

    word の出現数が店名の「薬局」の数と違えば、どの word が店名の終わりか
    決められないので空を返す。
    """
    lower = value.lower()
    if count == 0 or lower.count(word) != count:
        return ""
    i = lower.rfind(word) + len(word)
    return value[:i].rstrip(SEPARATOR)


def split_reading(value, head, word):
    """読み仮名かローマ字を、店名の部分だけにする。分けられなければ空を返す。

    店名が「薬局」で終わるなら、最後の word（やっきょく、yakkyoku）の直後で
    切る。word が見つからなければ返さない。`こあやきょく` のような誤記や、
    `あいんふぁーましーず` のような別の読みを、空白の位置で切って
    残さないためである。

    店名が「薬局」で終わらなければ、値に空白がちょうど1つあるときだけ
    空白の位置で切る。
    """
    if not value:
        return ""
    if head.endswith("薬局"):
        return _cut_after(value, word, head.count("薬局"))
    parts = value.split()
    if len(parts) == 2:
        return parts[0].rstrip(SEPARATOR)
    return ""


def split_english(value, head):
    """英語名を店名の部分だけにする。分けられなければ空を返す。

    店名が「薬局」で終わり、Pharmacy や Drugstore の数が「薬局」の数と
    同じときだけ、最後のその語の直後で切る。
    """
    if not value or not head.endswith("薬局"):
        return ""
    found = list(EN_PHARMACY.finditer(value))
    if not found or len(found) != head.count("薬局"):
        return ""
    cut = value[:found[-1].end()].rstrip(SEPARATOR)
    # `Sogo Yakkyoku(Sogo Drugstore) Matsumotocho` を切ると括弧が閉じない。
    if cut.count("(") != cut.count(")"):
        return ""
    return cut


def _squash(value):
    return re.sub(r"\s", "", value)


def borrow_reading(value, known):
    """同じ店名のほかの行で切れた読みを借りて、value を店名の部分だけにする。

    known は、同じ店名で「やっきょく」の直後か空白の位置で切れた読みの集まり。
    value が、空白を除いてそのどれかで始まるときだけ、その長さで切る。
    いくつも当てはまるなら最も長いものを使う。value の中の空白は残す。
    切れなければ空を返す。
    """
    if not value or not known:
        return ""
    flat = _squash(value)
    hits = [k for k in known if k and flat.startswith(k) and len(flat) > len(k)]
    if not hits:
        return ""
    n = len(max(hits, key=len))
    # 空白を除いて n 文字目までを、元の空白を残したまま取り出す
    seen = 0
    for i, ch in enumerate(value):
        if not ch.isspace():
            seen += 1
        if seen == n:
            return value[:i + 1].rstrip(SEPARATOR)
    return ""


def split_latn_by_reading(latn, head_hira, tail_hira):
    """店名と支店名の読みを手がかりに、ローマ字の切れ目を探す。

    「yakkyoku」の綴りに誤りがあって目印で切れない行に使う。空白、ハイフン、
    文字と文字の間をすべて候補にし、前半が店名の読みに、後半が支店名の読みに
    最も近い位置で切る。切った前半と後半がそれぞれ読みと一致しなければ
    空を返す。`Norden Yakkoku Kitachitoseten` は `Norden Yakkoku` になる。
    """
    # build_names が branch_split を読み込むので、関数の中で読み込む
    from build_names import fold_romaji, romaji_agrees, to_romaji
    if not latn or not head_hira or not tail_hira:
        return ""
    a = fold_romaji(to_romaji(_squash(head_hira)))
    b = fold_romaji(to_romaji(_squash(tail_hira)))
    if not a or not b:
        return ""
    best, pos = 0.0, None
    for p in range(1, len(latn)):
        x, y = fold_romaji(latn[:p]), fold_romaji(latn[p:])
        if not x or not y:
            continue
        s = (difflib.SequenceMatcher(None, a, x).ratio() * len(a)
             + difflib.SequenceMatcher(None, b, y).ratio() * len(b)) / (len(a) + len(b))
        if s > best:
            best, pos = s, p
    if pos is None:
        return ""
    head, tail = latn[:pos].rstrip(SEPARATOR), latn[pos:].strip(SEPARATOR)
    if not (romaji_agrees(head, head_hira)[0] and romaji_agrees(tail, tail_hira)[0]):
        return ""
    return head
