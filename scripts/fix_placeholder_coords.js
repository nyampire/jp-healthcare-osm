#!/usr/bin/env node
/**
 * 元データの座標のうち、実在の位置ではなく穴埋めのものを捨てる。
 *
 * 入力・出力 (output/):
 *   <業態>_geocoded.csv    その場で書き換える
 *
 * 元データは座標を持たない施設に、都道府県庁の代表点や丸めた値を入れている。
 * 本番データでは13地点が県庁の代表点で、山形県の 38.0,140.0 のように
 * 県庁とは無関係な丸め値もある。どちらも施設の位置ではない。
 *
 * 見分けは県庁からの距離ではできない。県庁の中や隣にも医療機関があり、
 * 代表点から300m以内の515件のうち404件は実在の施設だった。
 * 効くのは次の2つで、本番データではこの判定で取り違えが0件だった。
 *
 *   1. 同じ座標を2つ以上の市区町村の施設が共有している
 *      1つの点が両方の住所であることはありえない。
 *      ただし自分の住所から得た点がその座標の近くにあるなら、
 *      同じ建物に入る施設の重なりなので残す。
 *   2. 緯度と経度がともに0.1度の格子に乗っている
 *      0.1度は約11kmで、施設の位置の精度ではない。
 *
 * 判定1は業態をまたがないと成立しない。同じ県庁の代表点に病院と薬局が
 * 1件ずつ乗っている場合、業態ごとに見ると市区町村が1つに見えてしまう。
 * そのため build_addr.js の中ではなく、全業態が揃ってから走らせる。
 *
 * 使い方:
 *   node scripts/fix_placeholder_coords.js [--out-dir output] [--adopt-level 8]
 */

const fs = require("fs");
const path = require("path");
const { resolveFromAddress, distanceMeters, usable } = require("./addr_columns.js");

const SECTORS = ["hospital", "clinic", "dental", "maternity", "pharmacy"];
const DEFAULT_ADOPT_LEVEL = 8;

/**
 * 同じ建物とみなす距離。
 *
 * 元データの座標と、その施設の住所から得た点が、これより近ければ実在とみなす。
 * 本番データでは、市区町村をまたいで共有された111件のうち、自分の住所の点が
 * 300m以内にあるものは0件だった。単一の市区町村で共有する404件では350件が
 * 300m以内で、こちらは同じ建物に入る施設の重なりだった。
 */
const SAME_PLACE_METERS = 300;

/** 0.1度の格子に乗っているか。丸めた穴埋めの値を見分ける */
function onCoarseGrid(lat, lon) {
  const on = (v) => Math.abs(v * 10 - Math.round(v * 10)) < 1e-9;
  return on(lat) && on(lon);
}

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

function toCsv(rows) {
  return rows.map((r) => r.map((v) => {
    const s = v === undefined || v === null ? "" : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  }).join(",")).join("\n") + "\n";
}

/** 元データの座標をキーにする。表記の揺れを数値に寄せる */
function coordKey(lat, lon) {
  return `${parseFloat(lat)},${parseFloat(lon)}`;
}

function main() {
  const argv = process.argv.slice(2);
  const arg = (k, d) => {
    const i = argv.indexOf(k);
    return i >= 0 && argv[i + 1] ? argv[i + 1] : d;
  };
  const outDir = arg("--out-dir", "output");
  const adoptLevel = parseInt(arg("--adopt-level", String(DEFAULT_ADOPT_LEVEL)), 10);

  // 全業態を読む。判定1は業態をまたいで数えないと成立しない
  const files = [];
  for (const sector of SECTORS) {
    const file = path.join(outDir, `${sector}_geocoded.csv`);
    if (!fs.existsSync(file)) continue;
    const rows = parseCsv(fs.readFileSync(file, "utf8"));
    const header = rows.shift();
    const recs = rows.filter((r) => r.length && r[0]).map((r) => {
      const rec = {};
      header.forEach((h, i) => (rec[h] = r[i] === undefined ? "" : r[i]));
      return rec;
    });
    files.push({ sector, file, header, recs });
  }
  if (!files.length) {
    console.error(`${outDir} に <業態>_geocoded.csv がありません`);
    process.exit(2);
  }
  const missing = SECTORS.filter(
    (s) => !files.some((f) => f.sector === s));
  if (missing.length) {
    console.log(`揃っていない業態があります: ${missing.join(", ")}`);
    console.log("  座標の共有は揃っている業態の中でしか数えられません");
  }

  // 元データの座標ごとに、乗っている施設の市区町村を集める
  const cities = new Map();
  for (const { recs } of files) {
    for (const rec of recs) {
      const lat = rec["元_緯度"], lon = rec["元_経度"];
      if (!usable(lat) || !usable(lon)) continue;
      const key = coordKey(lat, lon);
      if (!cities.has(key)) cities.set(key, new Set());
      const city = (rec["addr:city"] || "").trim();
      // 市区町村が空の行は数に入れない。空同士が別の市区町村に見えてしまう
      if (city) cities.get(key).add(`${rec["都道府県コード"]}/${city}`);
    }
  }

  const stat = { 市区町村またぎ: 0, 丸め値: 0, 同じ建物として残した: 0 };
  const byOutcome = {};
  const changed = [];

  for (const f of files) {
    for (const rec of f.recs) {
      if (rec["座標の出典"] !== "原データ") continue;
      const lat = rec["元_緯度"], lon = rec["元_経度"];
      if (!usable(lat) || !usable(lon)) continue;
      const a = parseFloat(lat), b = parseFloat(lon);

      const shared = (cities.get(coordKey(lat, lon)) || new Set()).size >= 2;
      const coarse = onCoarseGrid(a, b);
      if (!shared && !coarse) continue;

      // 自分の住所から得た点がその座標の近くにあるなら、実在の重なりとみなす
      if (usable(rec["住所_lat"]) && usable(rec["住所_lon"])) {
        const d = distanceMeters(a, b,
          parseFloat(rec["住所_lat"]), parseFloat(rec["住所_lon"]));
        if (d <= SAME_PLACE_METERS) { stat.同じ建物として残した++; continue; }
      }

      const why = shared
        ? "元データの座標を別の市区町村の施設と共有しているため使わない"
        : "元データの座標が0.1度の格子に乗る丸め値のため使わない";
      if (shared) stat.市区町村またぎ++; else stat.丸め値++;

      const level = rec["住所_位置レベル"] === ""
        ? null : parseInt(rec["住所_位置レベル"], 10);
      const r = resolveFromAddress({
        lat: rec["住所_lat"], lng: rec["住所_lon"], level,
        note: rec["住所_備考"],
      }, adoptLevel);
      Object.assign(rec, r.fields);
      rec["要確認"] = "yes";

      const notes = [why, r.説明];
      if (rec["未解釈の文字列"]) notes.push(`住所の未解釈部分: ${rec["未解釈の文字列"]}`);
      rec["備考"] = notes.join(" / ");

      const k = rec["座標の出典"] === "ジオコーディング"
        ? "住所から付け直した" : `座標なし ${rec["補完しなかった理由"]}`;
      byOutcome[k] = (byOutcome[k] || 0) + 1;
      changed.push(`${f.sector} ${rec["ID"]} ${rec["元_所在地"]}`);
    }
  }

  for (const f of files) {
    const out = [f.header, ...f.recs.map((rec) => f.header.map((h) => rec[h]))];
    fs.writeFileSync(f.file, "﻿" + toCsv(out));
  }

  const total = stat.市区町村またぎ + stat.丸め値;
  console.log(`\n穴埋めとみなした座標: ${total.toLocaleString()} 件`);
  console.log(`  市区町村またぎ       ${String(stat.市区町村またぎ).padStart(8)}`);
  console.log(`  0.1度の格子          ${String(stat.丸め値).padStart(8)}`);
  console.log(`  同じ建物として残した ${String(stat.同じ建物として残した).padStart(8)}`);
  if (total) {
    console.log("\n書き換えた後の内訳:");
    for (const k of Object.keys(byOutcome).sort()) {
      console.log(`  ${k.padEnd(24)} ${String(byOutcome[k]).padStart(8)}`);
    }
  }
  console.log(`\n書き換えたファイル: ${files.map((f) => path.basename(f.file)).join(", ")}`);
}

main();
