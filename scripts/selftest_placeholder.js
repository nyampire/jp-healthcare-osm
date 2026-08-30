#!/usr/bin/env node
/**
 * fix_placeholder_coords.js の逆テスト。
 *
 * 元データが座標を持たない施設に、都道府県庁の代表点や丸めた値を
 * 埋めている例が実在する。それを見分けて捨てられることを確かめる。
 * 見分けには業態をまたいだ突き合わせが要るので、2つのファイルに分けた
 * フィクスチャを使う。ネットワークは使わない。
 */

const fs = require("fs");
const os = require("os");
const path = require("path");
const { execFileSync } = require("child_process");

const ROOT = path.dirname(__dirname);
const FIXTURES = [
  ["hospital", path.join(ROOT, "tests", "known_bad_placeholder.csv")],
  ["clinic", path.join(ROOT, "tests", "known_bad_placeholder_2.csv")],
];

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

function readRecords(file) {
  const rows = parseCsv(fs.readFileSync(file, "utf8"));
  const header = rows.shift();
  return rows.filter((r) => r.length && r[0]).map((r) => {
    const rec = {};
    header.forEach((h, i) => (rec[h] = r[i] === undefined ? "" : r[i]));
    return rec;
  });
}

function main() {
  console.log("=== fix_placeholder_coords.js 逆テスト ===\n");
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "osm-iryo-placeholder-"));
  const buildDir = path.join(dir, "build");
  fs.mkdirSync(buildDir, { recursive: true });
  for (const [sector, src] of FIXTURES) {
    fs.copyFileSync(src, path.join(buildDir, `${sector}_geocoded.csv`));
  }

  execFileSync("node", [path.join(__dirname, "fix_placeholder_coords.js"),
    "--out-dir", dir], { encoding: "utf8", stdio: ["ignore", "pipe", "inherit"] });

  const fail = [];
  let n = 0;
  for (const [sector] of FIXTURES) {
    for (const rec of readRecords(path.join(buildDir, `${sector}_geocoded.csv`))) {
      n++;
      const checks = [
        ["座標の出典", rec["座標の出典"], rec["期待_座標の出典"]],
        ["lat", rec["lat"], rec["期待_lat"]],
        ["補完しなかった理由", rec["補完しなかった理由"], rec["期待_補完しなかった理由"]],
      ];
      let ok = true;
      for (const [key, actual, expected] of checks) {
        if (actual !== expected) {
          ok = false;
          fail.push(`${rec.ID} ${key}: 期待 "${expected}" / 実際 "${actual}"`);
        }
      }
      console.log(`  ${ok ? "PASS" : "FAIL"}  ${rec.ID} ${rec["元_所在地"]}`);
    }
  }
  fs.rmSync(dir, { recursive: true, force: true });

  console.log(`\n  ${n - new Set(fail.map((f) => f.split(" ")[0])).size}/${n} 件`);
  if (fail.length) {
    console.error("\n不一致");
    for (const f of fail) console.error(`  ${f}`);
    process.exit(1);
  }
}

main();
