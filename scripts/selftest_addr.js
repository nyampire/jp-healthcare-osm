#!/usr/bin/env node
/**
 * addr_columns.js の逆テスト。
 *
 * 固定した入力を foldColumns にかけ、狙った分類になることを確かめる。
 * ネットワークを使わない。nja-osm-tags のバッチ出力を模したフィクスチャを読む。
 */

const fs = require("fs");
const path = require("path");
const { foldColumns } = require("./addr_columns.js");

const ROOT = path.dirname(__dirname);
const FIXTURE = path.join(ROOT, "tests", "known_bad_addr.csv");

function parseCsv(text) {
  const rows = [];
  let row = [], field = "", quoted = false, i = 0;
  if (text.charCodeAt(0) === 0xfeff) i = 1;
  while (i < text.length) {
    const c = text[i];
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') { field += '"'; i += 2; continue; }
      if (c === '"') { quoted = false; i++; continue; }
      field += c; i++; continue;
    }
    if (c === '"') { quoted = true; i++; continue; }
    if (c === ",") { row.push(field); field = ""; i++; continue; }
    if (c === "\r") { i++; continue; }
    if (c === "\n") { row.push(field); rows.push(row); row = []; field = ""; i++; continue; }
    field += c; i++;
  }
  if (field || row.length) { row.push(field); rows.push(row); }
  return rows;
}

function main() {
  const rows = parseCsv(fs.readFileSync(FIXTURE, "utf8"));
  const header = rows.shift();
  const fail = [];
  let n = 0;

  for (const r of rows) {
    if (!r.length || !r[0]) continue;
    const rec = {};
    header.forEach((h, k) => (rec[h] = r[k] === undefined ? "" : r[k]));
    n++;

    const got = foldColumns(rec, rec["元_緯度"], rec["元_経度"], 8);
    const checks = [
      ["座標の出典", got["座標の出典"], rec["期待_座標の出典"]],
      ["補完しなかった理由", got["補完しなかった理由"], rec["期待_補完しなかった理由"]],
      ["lat", got.lat, rec["期待_lat"]],
    ];
    for (const [key, actual, expected] of checks) {
      if (actual !== expected) {
        fail.push(`${rec.case} ${key}: 期待 "${expected}" / 実際 "${actual}"`);
      }
    }
  }

  console.log(`検査した事例: ${n}`);
  if (fail.length) {
    console.error(`\n不一致 ${fail.length} 件`);
    for (const f of fail) console.error(`  ${f}`);
    process.exit(1);
  }
  console.log("すべて期待どおりに分類された");
}

main();
