#!/usr/bin/env node
/**
 * 都道府県の外接矩形の表を読み、座標が住所の県の外にあるかを判定する。
 *
 * 元データの座標が住所とは別の県の中に落ちている行を見つけるために使う。
 * 住所点からの距離では判定できない。小笠原村の住所点は父島にあるため、
 * 硫黄島の医務室は正しい座標のまま270.6km離れる。距離で切ると硫黄島を壊し、
 * 壊さない高さまで閾値を上げると誤りを取り逃がす。
 *
 * 表は mapping/pref_bbox.csv に持つ。生成は scripts/build_pref_bbox.js。
 */

const fs = require("fs");
const path = require("path");

const TABLE = path.join(path.dirname(__dirname), "mapping", "pref_bbox.csv");

// 自県の矩形に持たせる余裕（度）。緯度でおよそ5km。
// 埋立地や岬のように、大字の代表点の外側に施設が建つ場合を吸収する。
const MARGIN_DEGREES = 0.05;

let cache = null;

function parseTable(text) {
  const box = {};
  const lines = text.replace(/^﻿/, "").split(/\r?\n/);
  const ix = {};
  lines.shift().split(",").forEach((h, i) => (ix[h] = i));
  for (const line of lines) {
    if (!line.trim()) continue;
    const f = line.split(",");
    box[f[ix["都道府県"]]] = {
      code: f[ix["都道府県コード"]],
      latMin: parseFloat(f[ix["lat_min"]]),
      latMax: parseFloat(f[ix["lat_max"]]),
      lonMin: parseFloat(f[ix["lon_min"]]),
      lonMax: parseFloat(f[ix["lon_max"]]),
    };
  }
  return box;
}

/**
 * 表を読む。既定のファイルのときだけ結果を保持し、読み直さない。
 * ファイルが無ければ例外を投げる。判断に使う表が欠けたまま黙って
 * 規則が働かなくなるより、その場で止まるほうがよい。
 */
function loadPrefBox(file = TABLE) {
  if (file === TABLE && cache) return cache;
  const box = parseTable(fs.readFileSync(file, "utf8"));
  if (file === TABLE) cache = box;
  return box;
}

function inBox(b, lat, lon, margin = 0) {
  return lat >= b.latMin - margin && lat <= b.latMax + margin
    && lon >= b.lonMin - margin && lon <= b.lonMax + margin;
}

/**
 * 座標が自県の矩形の外にあり、かつ他県の矩形の中にあるなら、その県名を返す。
 * 当てはまらなければ null を返す。
 *
 * 他県の矩形の中にあることまで求める理由は、矩形の縁からはみ出す正当な座標を
 * 拾わないため。硫黄島の座標はどの県の矩形にも入らないので null になる。
 */
function outOfPref(box, province, lat, lon, margin = MARGIN_DEGREES) {
  const own = box[province];
  if (!own) return null;
  if (inBox(own, lat, lon, margin)) return null;
  const others = [];
  for (const name of Object.keys(box)) {
    if (name === province) continue;
    if (inBox(box[name], lat, lon)) others.push(name);
  }
  return others.length ? others : null;
}

module.exports = { loadPrefBox, outOfPref, inBox, MARGIN_DEGREES, TABLE };
