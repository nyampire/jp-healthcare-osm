#!/usr/bin/env node
/**
 * 都道府県の外接矩形の表を nja の住所データから生成する。
 *
 * 入力: $NJA_API_BASE/<都道府県>/<市区町村>.json の point（[経度, 緯度]）
 * 出力: mapping/pref_bbox.csv
 *
 * 施設の住所点からではなく nja から組む。施設の住所点だけを使うと、nja が
 * 住所を解けない地域で矩形が縮み、その地域の正しい座標を県外と誤判定する。
 * 北海道松前町や青森県深浦町がその例。
 *
 * 都道府県の境界は変わらないので npm run all には入れない。
 * 住所データを更新したときだけ実行する。
 */

const fs = require("fs");
const path = require("path");

const OUT = path.join(path.dirname(__dirname), "mapping", "pref_bbox.csv");

function main() {
  const base = process.env.NJA_API_BASE;
  if (!base) {
    console.error("住所データの取得先が設定されていません。NJA_API_BASE を設定してください。");
    process.exit(2);
  }
  if (/^https?:/i.test(base)) {
    console.error("公開 API は使いません。ローカルのバッチ出力を指してください。");
    process.exit(2);
  }

  const prefs = fs.readdirSync(base, { withFileTypes: true })
    .filter((d) => d.isDirectory()).map((d) => d.name);
  const rows = [];
  let files = 0;
  let points = 0;

  for (const pref of prefs) {
    // 都道府県コードは市区町村コードの先頭2桁。表を別に持たずに済む。
    const meta = JSON.parse(fs.readFileSync(path.join(base, `${pref}.json`), "utf8"));
    const code = String(meta.data[0].code).padStart(6, "0").slice(0, 2);

    let latMin = 90, latMax = -90, lonMin = 180, lonMax = -180;
    for (const f of fs.readdirSync(path.join(base, pref))) {
      if (!f.endsWith(".json")) continue;
      files++;
      const city = JSON.parse(fs.readFileSync(path.join(base, pref, f), "utf8"));
      for (const e of city.data || []) {
        const p = e.point;
        if (!Array.isArray(p) || p.length < 2) continue;
        const lon = p[0], lat = p[1];
        if (!Number.isFinite(lat) || !Number.isFinite(lon)) continue;
        points++;
        if (lat < latMin) latMin = lat;
        if (lat > latMax) latMax = lat;
        if (lon < lonMin) lonMin = lon;
        if (lon > lonMax) lonMax = lon;
      }
    }
    if (latMin > latMax) {
      console.error(`点が1つも読めませんでした: ${pref}`);
      process.exit(1);
    }
    rows.push([code, pref, latMin.toFixed(6), latMax.toFixed(6),
      lonMin.toFixed(6), lonMax.toFixed(6)]);
  }

  rows.sort((a, b) => a[0].localeCompare(b[0]));

  // 47県に満たないまま書き出さない。取得先を間違えて指すと都道府県の
  // ディレクトリが一部しか見つからず、少ない県だけの表ができる。その表では
  // 載っていない県の施設で outOfPref が null を返し、県外の規則が黙って
  // 働かなくなる。書き出しより前に落として、既存の表を残す。
  if (rows.length !== 47) {
    console.error(`都道府県が47件ではなく${rows.length}件でした。`
      + `NJA_API_BASE が指す先を確かめてください: ${base}`);
    process.exit(1);
  }

  fs.writeFileSync(OUT,
    "﻿都道府県コード,都道府県,lat_min,lat_max,lon_min,lon_max\n"
    + rows.map((r) => r.join(",")).join("\n") + "\n");

  console.log(`都道府県 ${rows.length} / 市区町村ファイル ${files.toLocaleString()} / 点 ${points.toLocaleString()}`);
  console.log(`出力: ${OUT}`);
}

main();
