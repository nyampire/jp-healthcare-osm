/**
 * 番地が 推定 になった行を、町字マスタの明細で引き直す。
 *
 * NJA は住居表示の明細に当たらなかった番地を 推定 として返す。入力の残余を
 * ハイフンで区切り、最初の数字を街区符号、次を住居番号として読んだだけの
 * 状態で、実在は確かめていない。build_osm.py はこの行の番地を出さない。
 *
 * 推定 には性質の違うものが混ざっている。高知市大膳町の街区符号は7番までで、
 * 入力の `大膳町37` は街区符号ではありえないが、地番の明細には37がある。
 * 地番と分かるなら、備考にそう書ける。
 *
 * 値を出せるようにはならない。vendor/nja-osm-tags/src/numbers.ts の
 * ライセンス要件により、地番方式の番地は出さないと決まっている。
 * 地番と確定することは、出してはいけない値だと確定することである。
 * 変わるのは 備考 の1文と、作業者が現地で何を調べるかである。
 *
 * 判定そのもの（detailNumbers と judgeNumber）はファイルもネットワークも
 * 触らないので、明細を手で書いた逆テストで固定できる。ミラーを読むのは
 * loadTowns と loadDetail で、読み直しを減らすキャッシュは build_addr.js の
 * makeNumberJudge が持つ。
 */

const fs = require("fs");
const path = require("path");

/**
 * 明細の1町字分を、番地の集合として読む。
 *
 * 1行目が `地番,<町字名>` か `住居表示,<町字名>`、2行目が列名なので読み飛ばす。
 * 3列目までが番地の要素で、地番は prc_num1〜3、住居表示は blk_num、
 * rsdt_num、rsdt_num2 に入る。どちらも同じ位置なので1つの関数で読める。
 *
 * 要素はハイフンでつなぐ。geocoded.csv の addr:block_number と
 * addr:housenumber も同じ形でつながっているため、そのまま突き合わせられる。
 */
function detailNumbers(text) {
  const out = new Set();
  const lines = String(text).split("\n");
  for (let i = 2; i < lines.length; i++) {
    const c = lines[i].split(",");
    if (!c[0]) continue;
    out.add([c[0], c[1], c[2]].filter(Boolean).join("-"));
  }
  return out;
}

/**
 * 推定 になった1行の番地を、町字の明細に照らして判定する。
 *
 * detail は { 住居表示: Set|null, 地番: Set|null }。町字そのものを
 * 引けなかった行では null を渡す。
 *
 * 返す値は4つ。
 *
 *   地番      地番の明細に番地がある。住居表示の明細の有無は問わない
 *   不一致    住居表示の明細はあるが、どちらの明細にも番地が無い
 *   判定不能  住居表示の明細が無く、地番の明細にも番地が無い
 *   空文字    判定しない。番地が落ちていない行と、住居表示の明細に
 *             番地が丸ごとある行
 *
 * 突き合わせは街区符号と住居番号の組で行う。街区符号だけで見ると、
 * 本番データの1,487行が住居表示に当たったように見えるが、その全てで
 * 住居番号は台帳に無い。NJA も組で照合するので、街区符号だけの一致を
 * 「住居表示にある」と読むと、NJA が当てられなかった理由を見失う。
 *
 * 住居表示の明細が無い町字で地番に一致した行を 地番 に入れるのは、
 * 判定を分ける材料が他に無いためである。町字の rsdt フラグは真なのに
 * ミラーに明細が無い状態で、街区符号だった可能性は排除できない。
 * 本番データでは16,387行がここに入り、うち住居表示の明細を持つ町字の行は
 * 2,245行だった。
 */
function judgeNumber(blockNumber, housenumber, detail) {
  const blk = String(blockNumber || "").trim();
  if (!blk) return "";
  const full = [blk, String(housenumber || "").trim()].filter(Boolean).join("-");

  if (!detail) return "判定不能";
  const rsdt = detail["住居表示"];
  const chiban = detail["地番"];

  if (rsdt && rsdt.has(full)) return "";
  if (chiban && chiban.has(full)) return "地番";
  if (!rsdt) return "判定不能";
  return "不一致";
}

/** 町字名。machiAzaName と同じ組み立てにする */
function townName(t) {
  return `${t.oaza_cho || ""}${t.chome || ""}${t.koaza || ""}`;
}

/**
 * 町字マスタの1市区町村分を、町字名で引ける形で読む。
 *
 * town_overmatch.js の loadMaster は大字名だけを残すので使えない。
 * こちらは csv_ranges が要る。ファイルが無ければ null を返す。
 */
function loadTowns(base, pref, city) {
  const p = path.join(base, pref, `${city}.json`);
  if (!fs.existsSync(p)) return null;
  const out = new Map();
  for (const t of JSON.parse(fs.readFileSync(p, "utf8")).data) {
    const n = townName(t);
    if (n && !out.has(n)) out.set(n, t);
  }
  return out;
}

/**
 * 明細ファイルの一部だけを読む。
 *
 * 1市区町村分の明細は数十MBになるので、町字の csv_ranges が指す範囲だけを
 * 読む。ファイルの先頭には町字名と範囲の索引が置かれており、csv_ranges の
 * start はその後ろを指す。索引は読まない。
 */
function loadDetail(base, pref, city, kind, range) {
  const p = path.join(base, pref, `${city}-${kind}.txt`);
  if (!fs.existsSync(p)) return null;
  const fd = fs.openSync(p, "r");
  try {
    const buf = Buffer.alloc(range.length);
    fs.readSync(fd, buf, 0, range.length, range.start);
    return detailNumbers(buf.toString("utf8"));
  } finally {
    fs.closeSync(fd);
  }
}

module.exports = {
  detailNumbers, judgeNumber, townName, loadTowns, loadDetail,
};
