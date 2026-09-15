#!/usr/bin/env node
/**
 * number_source.js の逆テスト。
 *
 * 番地が 推定 になった行について、町字マスタの明細を読んで
 * 「地番」「不一致」「判定不能」のどれかに振り分ける関数を確かめる。
 *
 * どの判定でも番地は出さない。変わるのは 備考 の1文と、作業者が
 * 現地で何を調べればよいかである。地番と分かった行は住居表示を調べる
 * 作業になり、どちらの明細にも無い行は元データの住所そのものを疑う。
 *
 * 明細は引数で渡す。ミラーを読まないのでファイルもネットワークも要らない。
 */

const { detailNumbers, judgeNumber } = require("./number_source.js");

/** 高知市大膳町。街区符号は7番までで、地番には37がある */
const DAIZEN = {
  住居表示: detailNumbers("住居表示,大膳町\nblk_num,rsdt_num,rsdt_num2,lng,lat\n"
    + "1,1,,133.5,33.5\n1,2,,133.5,33.5\n7,1,,133.5,33.5\n"),
  地番: detailNumbers("地番,大膳町\nprc_num1,prc_num2,prc_num3,lng,lat\n"
    + "37,,,,\n38,1,,,\n"),
};

/** 高知市横浜東町。街区符号に10が無く、地番にも10が無い */
const YOKOHAMA = {
  住居表示: detailNumbers("住居表示,横浜東町\nblk_num,rsdt_num,rsdt_num2,lng,lat\n"
    + "9,1,,133.5,33.5\n11,1,,133.5,33.5\n"),
  地番: detailNumbers("地番,横浜東町\nprc_num1,prc_num2,prc_num3,lng,lat\n"
    + "12,,,,\n"),
};

/** 住居表示の明細を持たない町字。地番の明細だけがある */
const NO_RSDT = {
  住居表示: null,
  地番: detailNumbers("地番,某町\nprc_num1,prc_num2,prc_num3,lng,lat\n"
    + "37,,,,\n"),
};

/** どちらの明細も持たない町字 */
const NO_DETAIL = { 住居表示: null, 地番: null };

function main() {
  const cases = [];
  const eq = (name, got, want) => cases.push([name, got === want, got]);

  // 住居表示の明細に番地が無く、地番の明細にある行
  eq("地番の明細に一致すれば 地番",
    judgeNumber("37", "", DAIZEN), "地番");
  eq("枝番まで一致すれば 地番",
    judgeNumber("38", "1", DAIZEN), "地番");

  // 住居表示の明細があり、どちらにも無い行
  eq("どちらの明細にも無ければ 不一致",
    judgeNumber("10", "1", YOKOHAMA), "不一致");

  // 住居表示の明細が無い行。地番に一致すれば地番と書く
  eq("住居表示の明細が無くても地番に一致すれば 地番",
    judgeNumber("37", "", NO_RSDT), "地番");
  eq("住居表示の明細が無く地番にも無ければ 判定不能",
    judgeNumber("40", "", NO_RSDT), "判定不能");
  eq("どちらの明細も無ければ 判定不能",
    judgeNumber("40", "", NO_DETAIL), "判定不能");

  // 町字そのものを引けなかった行
  eq("町字を引けなければ 判定不能",
    judgeNumber("40", "", null), "判定不能");

  // 番地が無ければ落ちるものが無いので判定しない
  eq("番地が無ければ判定しない", judgeNumber("", "", DAIZEN), "");

  // 住居表示の明細に番地が丸ごとある行は判定を保留する。
  // 本番データでは0件だが、出たときに「どちらの明細にも無い」と
  // 書くと事実と違う文が出る。
  eq("住居表示の明細に一致すれば判定を保留する",
    judgeNumber("1", "2", DAIZEN), "");

  // 街区符号だけの一致では住居表示に当たったことにしない。
  // 本番データの1,487行がこれで、住居番号は台帳に無い。
  eq("街区符号だけの一致は住居表示に当たったことにしない",
    judgeNumber("1", "9", DAIZEN), "不一致");

  // 明細の読み取り
  const d = detailNumbers("地番,大膳町\nprc_num1,prc_num2,prc_num3,lng,lat\n"
    + "37,,,,\n38,1,,,\n39,1,2,,\n\n");
  eq("先頭2行を読み飛ばす", d.has("prc_num1"), false);
  eq("枝番の無い地番を読む", d.has("37"), true);
  eq("枝番をハイフンでつなぐ", d.has("38-1"), true);
  eq("3要素目までつなぐ", d.has("39-1-2"), true);
  eq("空行を落とす", d.size, 3);

  let failed = 0;
  for (const [name, ok, actual] of cases) {
    if (!ok) failed++;
    console.log(`  ${ok ? "PASS" : "FAIL"}  ${name}`);
    if (!ok) console.log(`        実際: ${actual}`);
  }
  console.log(`\n  ${cases.length - failed}/${cases.length} 件`);
  if (failed) process.exit(1);
}

console.log("=== 番地の判定 逆テスト ===\n");
main();
