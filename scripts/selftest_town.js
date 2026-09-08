#!/usr/bin/env node
/**
 * town_overmatch.js の逆テスト。
 *
 * NJA は `○○町` の `町` を落とした別名を町字パターンとして登録する。
 * 入力が指す町字を照合できなかったときにだけ別名が最後に拾い、
 * 入力とは別の大字が出る。その行を見分けられることを確かめる。
 *
 * 町字マスタは引数で渡す。ミラーを読まないのでネットワークもファイルも要らない。
 */

const { detectOvermatch, fold } = require("./town_overmatch.js");

/** 横浜市鶴見区の町字マスタの一部 */
const TSURUMI = [
  { oaza: "鶴見中央", name: "鶴見中央一丁目" },
  { oaza: "鶴見中央", name: "鶴見中央二丁目" },
  { oaza: "鶴見町", name: "鶴見町" },
  { oaza: "生麦", name: "生麦一丁目" },
];

/** 藤沢市の町字マスタの一部 */
const FUJISAWA = [
  { oaza: "辻堂元町", name: "辻堂元町一丁目" },
  { oaza: "辻堂", name: "辻堂" },
  { oaza: "鵠沼海岸", name: "鵠沼海岸一丁目" },
  { oaza: "鵠沼", name: "鵠沼" },
];

/** 結城市の町字マスタの一部。残余が町字ではない例 */
const YUKI = [
  { oaza: "大字結城", name: "大字結城" },
];

/** 大分市の町字マスタの一部。同じ大字の下に小字が並ぶ例 */
const OITA = [
  { oaza: "大字下郡", name: "大字下郡" },
  { oaza: "大字下郡", name: "大字下郡北" },
];

/** 豊橋市の町字マスタの一部。町字が quarter と neighbourhood に割れる例 */
const TOYOHASHI = [
  { oaza: "牟呂町", name: "牟呂町字内田" },
  { oaza: "牟呂内田町", name: "牟呂内田町" },
];

/** いわき市の町字マスタの一部。割れた町字で大字が一致する例 */
const IWAKI = [
  { oaza: "小名浜", name: "小名浜字愛宕" },
  { oaza: "小名浜", name: "小名浜字愛宕町" },
];

/** 岐阜市の町字マスタの一部。番地の数字が別の町字に化ける例 */
const GIFU = [
  { oaza: "橋本町", name: "橋本町二丁目" },
  { oaza: "二番町", name: "二番町" },
];

function rec(over) {
  return {
    "所在地": "", "addr:province": "", "addr:city": "", "addr:suburb": "",
    "addr:neighbourhood": "", "note": "", "addr:block_number": "",
    "_番地の根拠": "なし",
    ...over,
  };
}

function main() {
  const cases = [];
  const eq = (name, actual, expected) =>
    cases.push([name, actual === expected, `${JSON.stringify(actual)} (期待 ${JSON.stringify(expected)})`]);

  // 誤りとして見分けたい行
  eq("町を落とした別名が拾った行の修正候補を返す",
    detectOvermatch(rec({
      "所在地": "神奈川県横浜市鶴見区鶴見中央",
      "addr:province": "神奈川県", "addr:city": "横浜市", "addr:suburb": "鶴見区",
      "addr:neighbourhood": "鶴見町", "note": "中央",
    }), TSURUMI), "鶴見中央");

  eq("残余が2文字以上でも境界をまたいで照合する",
    detectOvermatch(rec({
      "所在地": "神奈川県藤沢市辻堂元町",
      "addr:province": "神奈川県", "addr:city": "藤沢市",
      "addr:neighbourhood": "辻堂", "note": "元町",
    }), FUJISAWA), "辻堂元町");

  eq("入力の丁目が漢数字でも算用数字のマスタと突き合わせる",
    detectOvermatch(rec({
      "所在地": "神奈川県藤沢市鵠沼海岸",
      "addr:province": "神奈川県", "addr:city": "藤沢市",
      "addr:neighbourhood": "鵠沼", "note": "海岸",
    }), FUJISAWA), "鵠沼海岸");

  // 誤りではない行
  eq("番地が取れている行は対象にしない",
    detectOvermatch(rec({
      "所在地": "神奈川県横浜市鶴見区鶴見中央1-2-3",
      "addr:province": "神奈川県", "addr:city": "横浜市", "addr:suburb": "鶴見区",
      "addr:neighbourhood": "鶴見町", "note": "中央",
      "addr:block_number": "2", "_番地の根拠": "照合済み",
    }), TSURUMI), "");

  eq("残余が空の行は対象にしない",
    detectOvermatch(rec({
      "所在地": "神奈川県横浜市鶴見区鶴見町",
      "addr:province": "神奈川県", "addr:city": "横浜市", "addr:suburb": "鶴見区",
      "addr:neighbourhood": "鶴見町", "note": "",
    }), TSURUMI), "");

  eq("残余が漢字で始まらない行は対象にしない",
    detectOvermatch(rec({
      "所在地": "神奈川県横浜市鶴見区鶴見町1234",
      "addr:province": "神奈川県", "addr:city": "横浜市", "addr:suburb": "鶴見区",
      "addr:neighbourhood": "鶴見町", "note": "1234",
    }), TSURUMI), "");

  eq("境界をまたぐ町字がマスタに無ければ対象にしない",
    detectOvermatch(rec({
      "所在地": "茨城県結城市結城西繁昌塚9629番1",
      "addr:province": "茨城県", "addr:city": "結城市",
      "addr:neighbourhood": "大字結城", "note": "西繁昌塚9629番1",
    }), YUKI), "");

  eq("大字が同じで小字が未解決なだけの行は対象にしない",
    detectOvermatch(rec({
      "所在地": "大分県大分市大字下郡北",
      "addr:province": "大分県", "addr:city": "大分市",
      "addr:neighbourhood": "大字下郡", "note": "北",
    }), OITA), "");

  eq("残余が入力の末尾に重ならない行は対象にしない",
    detectOvermatch(rec({
      "所在地": "神奈川県横浜市鶴見区鶴見町",
      "addr:province": "神奈川県", "addr:city": "横浜市", "addr:suburb": "鶴見区",
      "addr:neighbourhood": "鶴見町", "note": "中央",
    }), TSURUMI), "");

  // 町字が addr:quarter と addr:neighbourhood に割れる行。
  // バッチ出力の addr:neighbourhood だけを見ると町字を取り違える。
  eq("quarter と neighbourhood をつないだものを町字として扱う",
    detectOvermatch(rec({
      "所在地": "愛知県豊橋市牟呂内田町１９－１３",
      "addr:province": "愛知県", "addr:city": "豊橋市",
      "addr:quarter": "牟呂町", "addr:neighbourhood": "字内田", "note": "町19-13",
    }), TOYOHASHI), "牟呂内田町");

  eq("割れた町字でも大字が同じなら対象にしない",
    detectOvermatch(rec({
      "所在地": "福島県いわき市小名浜愛宕町１５－３",
      "addr:province": "福島県", "addr:city": "いわき市",
      "addr:quarter": "小名浜", "addr:neighbourhood": "字愛宕", "note": "町15-3",
    }), IWAKI), "");

  // 番地が取れた行では、残余が町字の直後から始まらない。
  // バッチ出力の _番地の根拠 と addr:block_number は、番地を採らなかった行では
  // どちらも空になるので、番地を取ったかどうかを表さない。
  // 境界の直前が数字かどうかで見分ける。
  eq("境界の直前が数字なら対象にしない",
    detectOvermatch(rec({
      "所在地": "岐阜県岐阜市橋本町２丁目５２番　岐阜シティタワー４３",
      "addr:province": "岐阜県", "addr:city": "岐阜市",
      "addr:neighbourhood": "橋本町二丁目", "note": "番 岐阜シティタワ-43",
    }), GIFU), "");

  // 表記の畳み込み
  eq("大字と字を落として突き合わせる", fold("大字大槻町字天正坦"), "大槻町天正坦");
  eq("ヶをケに畳む", fold("茅ヶ崎"), "茅ケ崎");

  let failed = 0;
  for (const [name, ok, actual] of cases) {
    if (!ok) failed++;
    console.log(`  ${ok ? "PASS" : "FAIL"}  ${name}`);
    if (!ok) console.log(`        実際: ${actual}`);
  }
  console.log(`\n  ${cases.length - failed}/${cases.length} 件`);
  if (failed) process.exit(1);
}

console.log("=== 町字の過剰照合 逆テスト ===\n");
main();
