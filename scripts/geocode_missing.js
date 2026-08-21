#!/usr/bin/env node
/**
 * 座標が 0.0,0.0 の施設について、住所からジオコーディングで座標を補完する。
 *
 * 入力:
 *   NN-*_..._YYYYMMDD.csv  施設票
 *
 * 出力 (output/):
 *   <業態>_geocoded.csv          全施設。元の値と付与した値を別列で持つ
 *   .geocode_cache.json          住所ごとの結果。再実行と再開に使う
 *
 * 処理方針:
 *   元データの住所と座標は書き換えず、ジオコーディングで得た値は別列に置く。
 *   どの座標が元データ由来で、どれが付与したものかを列で区別できるようにする。
 *   OSM へ投入したあとに出典を問われたとき、行を見れば答えられる必要がある。
 *
 *   採用するのは位置レベル 8 だけを既定とする。
 *   レベル 3 は大字と丁目の代表点で建物から数百メートルずれ、
 *   レベル 2 は市区町村役場の位置で施設と無関係になる（実測で 3.6km の例がある）。
 *   採用しなかった結果も列に残すので、あとから採否を変えられる。
 *
 *   ジオコーダの座標は EPSG:4326。元データも実測で現行測地系と確認済みなので、
 *   変換せずに同じ列へ入れられる。詳細は docs/geocoding-investigation.md を参照。
 *
 * 使い方:
 *   node scripts/geocode_missing.js --sector hospital [--limit 100] [--adopt-level 8]
 */

const fs = require("fs");
const path = require("path");
const { normalize } = require("@geolonia/normalize-japanese-addresses");

const SECTORS = {
  hospital: { label: "病院", pattern: /^01-1_hospital_facility_info_.*\.csv$/, name: "正式名称" },
  clinic: { label: "診療所", pattern: /^02-1_clinic_facility_info_.*\.csv$/, name: "正式名称" },
  dental: { label: "歯科診療所", pattern: /^03-1_dental_facility_info_.*\.csv$/, name: "正式名称" },
  maternity: { label: "助産所", pattern: /^04_maternity_home_.*\.csv$/, name: "正式名称" },
  pharmacy: { label: "薬局", pattern: /^05_pharmacy_.*\.csv$/, name: "名称" },
};

// 既定で採用する位置情報データのレベル。8 は住居表示または地番の位置。
const DEFAULT_ADOPT_LEVEL = 8;
// 同時に投げる本数。公開エンドポイントなので控えめにする。
const CONCURRENCY = 4;
// キャッシュを書き出す間隔。途中で止めても再開できるようにする。
const CACHE_FLUSH_EVERY = 200;

const POINT_LEVEL_NOTE = {
  1: "都道府県庁所在地",
  2: "市区町村役場の所在地",
  3: "大字と丁目の代表点",
  8: "住居表示または地番の位置",
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

function loadCache(file) {
  try { return JSON.parse(fs.readFileSync(file, "utf8")); } catch (e) { return {}; }
}

/** 住所を1件ジオコーディングする。結果はキャッシュに載せる。 */
async function geocodeOne(address, cache) {
  if (Object.prototype.hasOwnProperty.call(cache, address)) return cache[address];
  let out;
  try {
    const g = await normalize(address);
    out = {
      pref: g.pref || "", city: g.city || "", town: g.town || "", addr: g.addr || "",
      level: g.level, other: g.other || "",
      lat: g.point ? g.point.lat : null,
      lng: g.point ? g.point.lng : null,
      pointLevel: g.point ? g.point.level : null,
    };
  } catch (e) {
    out = { error: String(e).slice(0, 120) };
  }
  cache[address] = out;
  return out;
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
  console.log(`業態         : ${conf.label}`);
  console.log(`施設票       : ${path.basename(src)}`);
  console.log(`採用する位置レベル: ${adoptLevel} 以上`);

  const rows = parseCsv(fs.readFileSync(src, "utf8"));
  const header = rows.shift();
  const ix = {};
  header.forEach((h, n) => (ix[h] = n));
  for (const need of ["所在地", "所在地座標（緯度）", "所在地座標（経度）", conf.name]) {
    if (ix[need] === undefined) {
      console.error(`必要な列が見つかりません: ${need}`);
      process.exit(2);
    }
  }

  fs.mkdirSync(outDir, { recursive: true });
  const cacheFile = path.join(outDir, ".geocode_cache.json");
  const cache = loadCache(cacheFile);
  const cacheSizeAtStart = Object.keys(cache).length;
  if (cacheSizeAtStart) console.log(`キャッシュ   : ${cacheSizeAtStart.toLocaleString()} 件を読み込み`);

  // 座標が無い行だけを対象にする
  const targets = [];
  for (const r of rows) {
    if (!r.length || !r[0]) continue;
    const lat = r[ix["所在地座標（緯度）"]].trim();
    const missing = !lat || parseFloat(lat) === 0;
    if (missing && r[ix["所在地"]].trim()) targets.push(r);
  }
  const todo = limit > 0 ? targets.slice(0, limit) : targets;
  console.log(`座標なし     : ${targets.length.toLocaleString()} 件`
    + (limit > 0 ? `（--limit により ${todo.length.toLocaleString()} 件のみ処理）` : ""));

  let done = 0, sinceFlush = 0;
  const queue = todo.slice();
  const started = Date.now();
  async function worker() {
    while (queue.length) {
      const r = queue.shift();
      await geocodeOne(r[ix["所在地"]].trim(), cache);
      done++; sinceFlush++;
      if (sinceFlush >= CACHE_FLUSH_EVERY) {
        fs.writeFileSync(cacheFile, JSON.stringify(cache));
        sinceFlush = 0;
        const sec = (Date.now() - started) / 1000;
        process.stdout.write(`\r  処理中 ${done.toLocaleString()}/${todo.length.toLocaleString()} `
          + `(${(done / sec).toFixed(1)}件/秒)`);
      }
    }
  }
  await Promise.all(Array.from({ length: CONCURRENCY }, worker));
  fs.writeFileSync(cacheFile, JSON.stringify(cache));
  if (done) process.stdout.write("\r" + " ".repeat(60) + "\r");

  // 出力を組み立てる。全施設を出し、元の値と付与した値を別列で持つ。
  const out = [[
    "ID", "名称", "都道府県コード",
    "元_所在地", "元_緯度", "元_経度",
    "lat", "lon", "座標の出典", "位置レベル", "位置レベルの意味",
    "正規化住所", "住所レベル", "未解釈の文字列",
    "要確認", "備考",
  ]];
  const stat = {};
  const bump = (k) => (stat[k] = (stat[k] || 0) + 1);

  for (const r of rows) {
    if (!r.length || !r[0]) continue;
    const address = r[ix["所在地"]].trim();
    const rawLat = r[ix["所在地座標（緯度）"]].trim();
    const rawLon = r[ix["所在地座標（経度）"]].trim();
    const missing = !rawLat || parseFloat(rawLat) === 0;

    let lat = "", lon = "", origin = "", pl = "", plNote = "";
    let normAddr = "", addrLevel = "", other = "", review = "", notes = [];

    if (!missing) {
      lat = rawLat; lon = rawLon; origin = "原データ";
      bump("原データの座標を採用");
    } else {
      const g = cache[address];
      if (!g) {
        origin = "なし"; review = "yes";
        notes.push("座標が無く、ジオコーディングも未実施");
        bump("未処理");
      } else if (g.error) {
        origin = "なし"; review = "yes";
        notes.push(`ジオコーディングに失敗: ${g.error}`);
        bump("失敗");
      } else {
        pl = g.pointLevel === null ? "" : String(g.pointLevel);
        plNote = POINT_LEVEL_NOTE[g.pointLevel] || "";
        addrLevel = g.level === undefined ? "" : String(g.level);
        other = g.other;
        normAddr = [g.pref, g.city, g.town, g.addr].filter(Boolean).join("");
        if (g.pointLevel !== null && g.pointLevel >= adoptLevel) {
          lat = String(g.lat); lon = String(g.lng);
          origin = "ジオコーディング";
          notes.push(`住所から付与（位置レベル${g.pointLevel}、${plNote}）`);
          bump("ジオコーディングで補完");
        } else {
          origin = "なし"; review = "yes";
          notes.push(`位置レベル${g.pointLevel === null ? "不明" : g.pointLevel}`
            + `${plNote ? `（${plNote}）` : ""}のため採用しない`);
          bump(`不採用 レベル${g.pointLevel === null ? "不明" : g.pointLevel}`);
        }
        if (other) notes.push(`住所の未解釈部分: ${other}`);
      }
    }
    out.push([
      r[0], r[ix[conf.name]], r[ix["都道府県コード"]],
      address, rawLat, rawLon,
      lat, lon, origin, pl, plNote,
      normAddr, addrLevel, other,
      review, notes.join(" / "),
    ]);
  }

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
