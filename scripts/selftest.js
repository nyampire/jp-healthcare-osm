#!/usr/bin/env node
/**
 * validate_opening_hours.js 自身の逆テスト。
 *
 * 既知の不正な opening_hours を検証器にかけ、狙った分類で検出されることと、
 * 終了コードが期待どおりになることを確かめる。どの分類を不合格に算入するかは
 * パイプラインが止まるかどうかを直接決めるので、分類と並べて固定する。
 * 何も検出しない検証器は無意味なので、本番データが全件パスすることと同じくらい、
 * 壊れた値をきちんと落とせることを確認する必要がある。
 *
 * 実際にこの逆テストで、コメントだけのルールが unknown 状態の 1 区間として
 * 返り、区間数を数えるだけの実装では破損を見逃すことが判明した。
 *
 * 使い方: node scripts/selftest.js
 */

const { execFileSync } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

const ROOT = path.join(__dirname, "..");
const FIXTURE = path.join(ROOT, "tests", "known_bad.csv");

// 正式名称 -> 期待する検出分類（null は「検出されないのが正しい」）
const EXPECTED = {
  "正常な値": null,
  "コメントを通常ルールに誤配置": "never_open",
  "ゼロ長区間": "zero_span",
  "構文エラー": "error",
  "第1土曜のみ開院": null,
  "正しいコメント配置": null,
  // 日跨ぎが翌日にはみ出すと翌日自身のルールと衝突し、参照実装が警告を出す。
  // データが実際にそうなっている以上これは欠陥ではないが、既知の挙動として固定する。
  "日跨ぎの当直帯": "warning",
  // 255文字は OSM のタグ値の上限で、中間ファイルの欠陥ではない。
  // 検出はするが不合格には算入しない。終了コードの検査で固定する
  "255文字超の休診日列挙": "too_long",
};

function parseCsv(text) {
  const rows = [];
  let row = [], field = "", quoted = false, i = 0;
  if (text.charCodeAt(0) === 0xfeff) i = 1;
  while (i < text.length) {
    const c = text[i];
    if (quoted) {
      if (c === '"') {
        if (text[i + 1] === '"') { field += '"'; i += 2; continue; }
        quoted = false; i++; continue;
      }
      field += c; i++; continue;
    }
    if (c === '"') { quoted = true; i++; }
    else if (c === ",") { row.push(field); field = ""; i++; }
    else if (c === "\r") { i++; }
    else if (c === "\n") { row.push(field); rows.push(row); row = []; field = ""; i++; }
    else { field += c; i++; }
  }
  if (field !== "" || row.length) { row.push(field); rows.push(row); }
  return rows;
}

/** 検証器を走らせ、終了コードを返す */
function runValidator(target) {
  try {
    execFileSync("node",
      [path.join(__dirname, "validate_opening_hours.js"), target],
      { stdio: "ignore" });
    return 0;
  } catch (e) {
    return e.status;
  }
}

function main() {
  // 検証器は入力と同じディレクトリに validation.csv を書くため、
  // リポジトリの output/ を汚さないよう一時ディレクトリで動かす。
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "osm-iryo-selftest-"));
  const target = path.join(tmp, "known_bad.csv");
  fs.copyFileSync(FIXTURE, target);

  // 不正値を含む以上、終了コードが 1 になるのが正しい
  const status = runValidator(target);

  // 検証器は入力ファイル名から結果ファイル名を導く
  const reportPath = path.join(tmp, "known_bad_validation.csv");
  if (!fs.existsSync(reportPath)) {
    console.error("検証結果が出力されませんでした。検証器が動作していません。");
    process.exit(1);
  }
  const rows = parseCsv(fs.readFileSync(reportPath, "utf8"));
  const header = rows.shift();
  const col = {};
  header.forEach((h, n) => (col[h] = n));

  const detected = {};
  for (const r of rows) {
    if (!r[col["正式名称"]]) continue;
    // 同じ値が複数分類に該当しうるので最初の1つを代表にする
    if (!detected[r[col["正式名称"]]]) {
      detected[r[col["正式名称"]]] = r[col["種別"]];
    }
  }

  let failed = 0;
  console.log("=== validate_opening_hours.js 逆テスト ===\n");
  for (const [name, expect] of Object.entries(EXPECTED)) {
    const got = detected[name] || null;
    const ok = got === expect;
    if (!ok) failed++;
    const shown = got || "検出なし";
    const want = expect || "検出なし";
    console.log(`  ${ok ? "PASS" : "FAIL"}  ${name}`);
    if (!ok) console.log(`        期待: ${want} / 実際: ${shown}`);
  }
  // 分類に続けて終了コードを固定する。
  let ok = status === 1;
  if (!ok) failed++;
  console.log(`  ${ok ? "PASS" : "FAIL"}  不正データで終了コード 1 を返す`);
  if (!ok) console.log(`        期待: 1 / 実際: ${status}`);

  // 255文字超だけを含むファイルは通さなければならない。
  // 255文字は OSM のタグ値の上限であって中間ファイルの制約ではなく、
  // 収める処理は build_osm.py の fit_opening_hours が行う。
  // ここで落とすと、下流で解決済みの事象でパイプライン全体が止まる。
  const lines = fs.readFileSync(FIXTURE, "utf8").split("\n");
  const longLine = lines.find((l) => l.startsWith("T08,"));
  const onlyLong = path.join(tmp, "only_too_long.csv");
  fs.writeFileSync(onlyLong, `${lines[0]}\n${longLine}\n`);
  const longStatus = runValidator(onlyLong);
  ok = longStatus === 0;
  if (!ok) failed++;
  console.log(`  ${ok ? "PASS" : "FAIL"}  255文字超だけなら終了コード 0 を返す`);
  if (!ok) console.log(`        期待: 0 / 実際: ${longStatus}`);

  const total = Object.keys(EXPECTED).length + 2;
  console.log(`\n  ${total - failed}/${total} 件`);

  fs.rmSync(tmp, { recursive: true, force: true });
  process.exit(failed ? 1 : 0);
}

main();
