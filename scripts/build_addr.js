#!/usr/bin/env node
/**
 * 住所を addr:* に構造化し、座標が無い施設だけ座標を補完する。
 *
 * 入力:
 *   NN-*_..._YYYYMMDD.csv  施設票
 *
 * 出力 (output/):
 *   <業態>_geocoded.csv    全施設。元の値と付与した値を別列で持つ
 *
 * 処理方針:
 *   住所の解析は nja-osm-tags に任せる。子プロセスで呼ぶ。
 *   ESM + TypeScript なので、CommonJS のこのファイルから require できない。
 *
 *   元データに座標がある施設は上書きしない。合流の規則は addr_columns.js の
 *   foldColumns 1箇所にある。
 *
 *   地番方式の住所の座標は補完に使わない。nja-osm-tags がライセンス上の
 *   措置として返さないため、こちら側にも値が来ない。
 *   件数は 補完しなかった理由 列で数えられる。
 *
 * 使い方:
 *   node scripts/build_addr.js --sector hospital [--limit 100] [--adopt-level 8]
 */

const fs = require("fs");
const os = require("os");
const path = require("path");
const { execFileSync } = require("child_process");
const { foldColumns, ADDR_KEYS } = require("./addr_columns.js");

const SECTORS = {
  hospital: { label: "病院", pattern: /^01-1_hospital_facility_info_.*\.csv$/, name: "正式名称" },
  clinic: { label: "診療所", pattern: /^02-1_clinic_facility_info_.*\.csv$/, name: "正式名称" },
  dental: { label: "歯科診療所", pattern: /^03-1_dental_facility_info_.*\.csv$/, name: "正式名称" },
  maternity: { label: "助産所", pattern: /^04_maternity_home_.*\.csv$/, name: "正式名称" },
  pharmacy: { label: "薬局", pattern: /^05_pharmacy_.*\.csv$/, name: "名称" },
};

const DEFAULT_ADOPT_LEVEL = 8;
const BATCH = path.join(__dirname, "..", "vendor", "nja-osm-tags", "bin", "batch.ts");

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

function toCsv(rows) {
  return rows.map((r) => r.map((v) => {
    const s = v === null || v === undefined ? "" : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  }).join(",")).join("\n");
}

function findSource(dir, pattern) {
  const hits = fs.readdirSync(dir).filter((f) => pattern.test(f)).sort();
  if (!hits.length) {
    console.error(`入力ファイルが見つかりません: ${pattern}`);
    process.exit(2);
  }
  return path.join(dir, hits[hits.length - 1]);
}

/** nja-osm-tags のバッチを呼び、出力を行の配列で返す */
function runBatch(inputPath) {
  const stdout = execFileSync("node", [BATCH, "--address-column", "所在地", inputPath], {
    encoding: "utf8",
    // 20万行を通すので既定の 1MB では足りない
    maxBuffer: 1024 * 1024 * 1024,
    stdio: ["ignore", "pipe", "inherit"],
  });
  const rows = parseCsv(stdout);
  const header = rows.shift();
  return rows.filter((r) => r.length && r[0]).map((r) => {
    const rec = {};
    header.forEach((h, i) => (rec[h] = r[i] === undefined ? "" : r[i]));
    return rec;
  });
}

async function main() {
  const argv = process.argv.slice(2);
  const arg = (k, d) => {
    const i = argv.indexOf(k);
    return i >= 0 && argv[i + 1] ? argv[i + 1] : d;
  };
  const sector = arg("--sector", "hospital");
  if (!SECTORS[sector]) {
    console.error(`業態は次から選んでください: ${Object.keys(SECTORS).join(", ")}`);
    process.exit(2);
  }
  const dataDir = arg("--data-dir", ".");
  const outDir = arg("--out-dir", "output");
  const limit = parseInt(arg("--limit", "0"), 10);
  const adoptLevel = parseInt(arg("--adopt-level", String(DEFAULT_ADOPT_LEVEL)), 10);

  const conf = SECTORS[sector];
  const src = findSource(dataDir, conf.pattern);
  const rows = parseCsv(fs.readFileSync(src, "utf8"));
  const header = rows.shift();
  const ix = {};
  header.forEach((h, n) => (ix[h] = n));

  let src_rows = rows.filter((r) => r.length && r[0]);
  if (limit > 0) src_rows = src_rows.slice(0, limit);

  // バッチへの入力を一時ファイルに書く。所在地だけを渡し、座標は渡さない。
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "osm-iryo-addr-"));
  const tmpIn = path.join(tmpDir, `${sector}_in.csv`);
  const inRows = [["ID", "所在地"]];
  for (const r of src_rows) inRows.push([r[0], r[ix["所在地"]].trim()]);
  fs.writeFileSync(tmpIn, "﻿" + toCsv(inRows));

  console.log(`${conf.label}: ${src_rows.length.toLocaleString()} 件を nja-osm-tags に通します`);
  const njaRows = runBatch(tmpIn);
  fs.rmSync(tmpDir, { recursive: true, force: true });

  if (njaRows.length !== src_rows.length) {
    console.error(`入力 ${src_rows.length} 行に対し出力 ${njaRows.length} 行。中断します`);
    process.exit(1);
  }

  const outHeader = [
    "ID", "名称", "都道府県コード",
    "元_所在地", "元_緯度", "元_経度",
    "lat", "lon", "座標の出典", "位置レベル", "位置レベルの意味",
    "補完しなかった理由", "番地の根拠", "正規化住所", "未解釈の文字列", "fixme",
    ...ADDR_KEYS,
    "要確認", "備考",
  ];
  const out = [outHeader];
  const stat = {};
  const bump = (k) => (stat[k] = (stat[k] || 0) + 1);

  for (let i = 0; i < src_rows.length; i++) {
    const r = src_rows[i];
    const nja = njaRows[i];
    if (nja["ID"] !== r[0]) {
      console.error(`行の順序が食い違いました: ${r[0]} と ${nja["ID"]}`);
      process.exit(1);
    }
    const rawLat = r[ix["所在地座標（緯度）"]].trim();
    const rawLon = r[ix["所在地座標（経度）"]].trim();
    const f = foldColumns(nja, rawLat, rawLon, adoptLevel);

    bump(f["座標の出典"] === "原データ" ? "原データの座標を採用"
      : f["座標の出典"] === "ジオコーディング" ? "ジオコーディングで補完"
      : `不採用 ${f["補完しなかった理由"]}`);

    out.push([
      r[0], r[ix[conf.name]], r[ix["都道府県コード"]],
      r[ix["所在地"]].trim(), rawLat, rawLon,
      f.lat, f.lon, f["座標の出典"], f["位置レベル"], f["位置レベルの意味"],
      f["補完しなかった理由"], f["番地の根拠"], f["正規化住所"], f["未解釈の文字列"],
      f["fixme"],
      ...ADDR_KEYS.map((k) => nja[k] || ""),
      f["要確認"], f["備考"],
    ]);
  }

  fs.mkdirSync(outDir, { recursive: true });
  const file = path.join(outDir, `${sector}_geocoded.csv`);
  fs.writeFileSync(file, "﻿" + toCsv(out));

  console.log(`\n施設数       : ${(out.length - 1).toLocaleString()}`);
  for (const k of Object.keys(stat).sort()) {
    console.log(`  ${k.padEnd(24)} ${stat[k].toLocaleString().padStart(8)}`);
  }
  const filled = stat["原データの座標を採用"] || 0;
  const added = stat["ジオコーディングで補完"] || 0;
  console.log(`座標がある施設: ${(filled + added).toLocaleString()} / ${(out.length - 1).toLocaleString()}`
    + ` (${(((filled + added) / (out.length - 1)) * 100).toFixed(1)}%)`);
  console.log(`出力         : ${file}`);
}

main();
