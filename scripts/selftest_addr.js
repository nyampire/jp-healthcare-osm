#!/usr/bin/env node
/**
 * addr_columns.js の逆テスト。
 *
 * 固定した入力を foldColumns にかけ、狙った分類になることを確かめる。
 * ネットワークを使わない。nja-osm-tags のバッチ出力を模したフィクスチャを読む。
 */

const fs = require("fs");
const os = require("os");
const path = require("path");
const { execFileSync } = require("child_process");
const { foldColumns, recheckAddress, adoptRecheck } = require("./addr_columns.js");

const ROOT = path.dirname(__dirname);
const FIXTURE = path.join(ROOT, "tests", "known_bad_addr.csv");
const ENV = "NJA_API_BASE";

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

  checkRecheck();
  checkStartupGuard();
}

/**
 * build_addr.js が住所データの取得先を確かめてから動くことを検査する。
 *
 * 公開 API は配信しているデータが古く、20万件を通すと相手にも負荷がかかる。
 * 取得先を確かめずに走り出すと、気づかないまま公開 API を叩き切ってしまう。
 * 検査は入力を読む前に行われるので、ここでバッチは起動しない。
 */
function checkStartupGuard() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "osm-iryo-addr-guard-"));
  fs.writeFileSync(
    path.join(dir, "01-1_hospital_facility_info_20260101.csv"),
    "\ufeffID,正式名称,都道府県コード,所在地,所在地座標（緯度）,所在地座標（経度）\n",
  );

  const run = (env) => {
    try {
      execFileSync("node", [path.join(__dirname, "build_addr.js"),
        "--sector", "hospital", "--data-dir", dir],
        { encoding: "utf8", env, stdio: ["ignore", "pipe", "pipe"] });
      return { status: 0, stderr: "" };
    } catch (e) {
      return { status: e.status, stderr: String(e.stderr || "") };
    }
  };

  const base = { ...process.env };
  delete base[ENV];

  const cases = [
    ["取得先が未設定なら落ちる", base, "住所データの取得先が設定されていません"],
    ["公開 API を指していたら落ちる",
      { ...base, [ENV]: "https://japanese-addresses-v2.geoloniamaps.com/api/ja" },
      "公開 API は使いません"],
  ];

  let failed = 0;
  console.log("");
  for (const [name, env, needle] of cases) {
    const r = run(env);
    const ok = r.status === 2 && r.stderr.includes(needle);
    if (!ok) failed++;
    console.log(`  ${ok ? "PASS" : "FAIL"}  ${name}`);
    if (!ok) {
      console.log(`        終了コード ${r.status}（期待 2）`);
      console.log(`        stderr: ${r.stderr.trim().split("\n")[0] || "(空)"}`);
    }
  }
  fs.rmSync(dir, { recursive: true, force: true });
  if (failed) process.exit(1);
}

/**
 * 推定の照合し直しを検査する。
 *
 * NJA は入力に建物名が続くと住居表示の明細照合を外し、番地を推定として返す。
 * 番地だけの住所に組み直して通し直すと明細が取れることがあり、本番データでは
 * 30,931件中2,811件がそれだった。組み直す文字列と、採用の条件を確かめる。
 */
function checkRecheck() {
  console.log("");
  const cases = [];

  const base = {
    "addr:country": "JP", "addr:province": "北海道", "addr:county": "",
    "addr:city": "札幌市", "addr:suburb": "中央区", "addr:quarter": "",
    "addr:neighbourhood": "北11条西15丁目",
    "addr:block_number": "2", "addr:housenumber": "1",
    "_番地の根拠": "推定",
  };
  cases.push(["建物名を落として番地だけの住所を組む",
    recheckAddress(base) === "北海道札幌市中央区北11条西15丁目2番1号",
    recheckAddress(base)]);

  const noHouse = { ...base, "addr:housenumber": "" };
  cases.push(["住居番号が無ければ番までで組む",
    recheckAddress(noHouse) === "北海道札幌市中央区北11条西15丁目2番",
    recheckAddress(noHouse)]);

  const noBlock = { ...base, "addr:block_number": "", "addr:housenumber": "" };
  cases.push(["街区符号が無ければ組まない",
    recheckAddress(noBlock) === "", recheckAddress(noBlock)]);

  const verified = { "_番地の根拠": "照合済み", "addr:block_number": "2",
    "addr:housenumber": "1", "_lat": "43.07", "_lng": "141.33", "_座標精度": "8" };
  const got = adoptRecheck(base, verified);
  cases.push(["照合済みになれば採用する", got !== null && got["_番地の根拠"] === "照合済み", String(got && got["_番地の根拠"])]);
  cases.push(["採用時は座標も明細のものに差し替える",
    got !== null && got["_lat"] === "43.07" && got["_座標精度"] === "8",
    String(got && got["_lat"])]);

  cases.push(["推定のままなら採用しない",
    adoptRecheck(base, { ...verified, "_番地の根拠": "推定" }) === null, ""]);

  // 番地が変わるのは組み直しが別の場所を指した場合で、本番データでは0件だった。
  // 起きたときに黙って値が入れ替わらないよう、採用しない側に倒す。
  cases.push(["番地が食い違えば採用しない",
    adoptRecheck(base, { ...verified, "addr:housenumber": "9" }) === null, ""]);

  cases.push(["元が推定でなければ採用しない",
    adoptRecheck({ ...base, "_番地の根拠": "照合済み" }, verified) === null, ""]);

  let failed = 0;
  for (const [name, ok, actual] of cases) {
    if (!ok) failed++;
    console.log(`  ${ok ? "PASS" : "FAIL"}  ${name}`);
    if (!ok && actual) console.log(`        実際: ${actual}`);
  }
  if (failed) process.exit(1);
}

main();
