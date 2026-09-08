/**
 * 入力が指しているのとは別の町字が出た行を見分ける。
 *
 * NJA は `○○町` の `町` を落とした別名を町字パターンとして登録する。
 * パターンは文字数の降順で試されるので、入力が指す町字を照合できたときは
 * そちらが勝つ。照合できなかったときにだけ別名が最後に拾い、
 * 「町字を特定できず」ではなく「誤った町字」になる。
 *
 *   神奈川県横浜市鶴見区鶴見中央   → 鶴見町  残余 中央
 *   神奈川県藤沢市辻堂元町         → 辻堂    残余 元町
 *
 * 判定は町字マスタに照会して決める。文字列の見た目では決められない。
 * `大字結城` ← `結城西繁昌塚9629番1` は、結城市に `結城西繁昌塚` という町字が
 * 無いので正しい（残余は登録されていない小字）。
 * `大字沼` ← `沼本町` は、小倉南区に `沼本町一丁目`〜`四丁目` があるので誤り。
 *
 * 手順は3つ。
 *
 *   1. 残余は番地解析まで済んだ後の文字列なので、番地が取れていない行だけを
 *      対象にする。そうでない行では「残余は町字の直後から始まる」が成り立たない。
 *   2. 残余を生の入力の末尾に重ねて境界の位置を出す。数字や区切りの正規化は
 *      文字数を変えないので、残余の先頭が漢字なら位置がそのまま出る。
 *      重ならなかった行は誤りと判定しない。
 *   3. 境界をまたいで実在の町字名の頭と一致するかを見る。一致した町字の大字が
 *      出力された町字の大字と違えば誤り、同じなら「小字まで解決できなかった」
 *      だけなので誤りではない。
 *
 * 判定の中身は vendor/nja-osm-tags/scripts/measure-town-boundary.ts と同じ。
 * あちらは元データを直接読んで件数を測る調査用で、こちらは build_addr.js が
 * バッチ出力の1行ごとに呼ぶ。マスタは引数で受けるので、この関数は
 * ファイルもネットワークも触らない。
 */

const fs = require("fs");
const path = require("path");
const { machiAzaName } = require("@geolonia/japanese-addresses-v2");
const { findKanjiNumbers, kanji2number } = require("@geolonia/japanese-numeral");

/** 残余の先頭がこれなら語の続きが残っている */
const KANJI = /[々〇一-鿿]/;
/** 語を構成する文字。境界をまたぐ範囲をここまで伸ばす */
const WORD = /[々〇一-鿿ぁ-んァ-ヶー]/;
/** 半角と全角の算用数字。境界の直前に番地があるかを見るのに使う */
const DIGIT = /[0-9０-９]/;

/**
 * 表記差を畳んで突き合わせに使う。
 *
 * 判定にしか使わないので、地名の漢数字を壊しても構わない。
 * `大字` `字` は入力にもマスタにも付いたり付かなかったりする。
 * 郡山市の `大槻町天正坦` に対して入力は `大槻町字天正坦` と書く。
 */
function fold(text) {
  let out = String(text).replace(/[０-９]/g, (c) =>
    String.fromCharCode(c.charCodeAt(0) - 0xfee0));
  out = out.replace(/[-－﹣−‐⁃‑‒–—﹘―⎯⏤ーｰ─━]/g, "-");
  out = out.replace(/ヶ/g, "ケ").replace(/ヵ/g, "カ");
  for (const run of findKanjiNumbers(out)) {
    try {
      out = out.replace(run, String(kanji2number(run)));
    } catch {
      // 数値に直せないランは触らない
    }
  }
  return out.replace(/大?字/g, "");
}

/**
 * 町字マスタの1市区町村分を読む。
 *
 * base は NJA_API_BASE が指すローカルミラー。city は政令指定都市なら
 * `横浜市鶴見区` のように区まで含む。ファイルが無ければ空配列を返す。
 * 呼び出し側で市区町村ごとに使い回せるよう、キャッシュはここに持たない。
 */
function loadMaster(base, pref, city) {
  const p = path.join(base, pref, `${city}.json`);
  if (!fs.existsSync(p)) return [];
  const seen = new Set();
  const out = [];
  for (const t of JSON.parse(fs.readFileSync(p, "utf8")).data) {
    const name = machiAzaName(t);
    if (!name || seen.has(name)) continue;
    seen.add(name);
    out.push({ oaza: t.oaza_cho ?? "", name });
  }
  return out;
}

/**
 * 誤った町字が出た行なら修正候補の大字を返す。そうでなければ空文字を返す。
 *
 * nja は nja-osm-tags のバッチ出力1行。entries はその行の市区町村の町字マスタ。
 */
function detectOvermatch(nja, entries) {
  // NJA が返す町字は、この repo の列では addr:quarter と addr:neighbourhood に
  // 割れる。`牟呂町字内田` は quarter=牟呂町 neighbourhood=字内田 になる。
  // neighbourhood だけを見ると町字を取り違え、大字の比較が的を外す。
  const town = ["addr:quarter", "addr:neighbourhood"]
    .map((k) => (nja[k] || "").trim()).join("");
  if (!town) return "";

  const residue = [...(nja["note"] || "")];
  if (residue.length === 0) return "";
  if (!KANJI.test(residue[0])) return "";

  // 番地が取れていると残余が町字の直後から始まらないので対象外
  if ((nja["_番地の根拠"] || "") !== "なし") return "";

  const raw = [...(nja["所在地"] || "").trim()];
  const at = raw.length - residue.length;
  if (at <= 0 || raw[at] !== residue[0]) return "";

  // 番地が取れた行では、残余が町字の直後ではなく番地の後ろから始まる。
  // バッチ出力の _番地の根拠 と addr:block_number は、番地を採らなかった行では
  // 番地が取れていても空になるので、そこからは見分けられない。
  // 境界の直前が数字なら、町字と残余の間に番地が挟まっている。
  // `岐阜市橋本町２丁目５２番　岐阜シティタワー４３` の残余は `番...` から始まり、
  // 直前の `５２` が番地として取られている。この行を数えると、
  // 番地の `2番` が町字の `二番町` の頭と一致してしまう。
  if (DIGIT.test(raw[at - 1])) return "";

  // 境界の前後を語の切れ目まで伸ばした文字列
  let run = 0;
  while (run < residue.length && WORD.test(residue[run])) run++;
  const foldedRun = fold(residue.slice(0, run).join(""));
  // 残余が `字` だけなど、境界の先に語が残らない場合は判定できない
  if (foldedRun.length === 0) return "";

  const across = fold(raw.slice(0, at).join("")) + foldedRun;
  const minLength = [...foldedRun].length + 1;

  // 境界をまたいで実在の町字名の頭と一致するものを、長い順に探す
  let best;
  let bestLength = 0;
  for (const entry of entries) {
    const folded = fold(entry.name);
    for (let k = folded.length; k >= minLength; k--) {
      if (k <= bestLength) break;
      if (across.endsWith(folded.slice(0, k))) {
        best = entry;
        bestLength = k;
        break;
      }
    }
  }
  if (!best) return "";

  // 出力された町字そのものの大字を、マスタから引き直す。
  // 比較は畳んだ空間で行う。同じ場所が `島之内` と `大字島之内` の
  // 両方でマスタに入っていることがあり、文字列一致では別物に見える。
  const foldedTown = fold(town);
  const own = entries.find((e) => fold(e.name) === foldedTown);
  if (own && fold(own.oaza) === fold(best.oaza)) return "";

  return best.oaza || best.name;
}

module.exports = { fold, loadMaster, detectOvermatch, KANJI, WORD, DIGIT };
