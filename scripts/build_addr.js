#!/usr/bin/env node
/**
 * 住所を addr:* に構造化し、座標が無い施設だけ座標を補完する。
 *
 * 入力:
 *   NN-*_..._YYYYMMDD.csv  施設票
 *
 * 出力 (output/build/):
 *   <業態>_geocoded.csv    全施設。元の値と付与した値を別列で持つ
 *
 *   住所から得た点は 住所_lat / 住所_lon / 住所_位置レベル に必ず残す。
 *   元データの座標を採った行でも残すのは、その座標が都道府県庁の代表点の
 *   ような穴埋めだった場合に、fix_placeholder_coords.js が付け直すため。
 *
 * 処理方針:
 *   住所の解析は nja-osm-tags に任せる。子プロセスで呼ぶ。
 *   ESM + TypeScript なので、CommonJS のこのファイルから require できない。
 *
 *   元データに座標がある施設は上書きしない。合流の規則は addr_columns.js の
 *   foldColumns 1箇所にある。
 *
 *   番地が推定になった行は、番地だけの住所に組み直してもう一度通す。
 *   建物名で明細照合が外れていただけの行を照合済みに戻すため。
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
const { foldColumns, recheckAddress, adoptRecheck, ADDR_KEYS } = require("./addr_columns.js");
const { loadPrefBox } = require("./pref_bbox.js");

const SECTORS = {
  hospital: { label: "病院", pattern: /^01-1_hospital_facility_info_.*\.csv$/, name: "正式名称" },
  clinic: { label: "診療所", pattern: /^02-1_clinic_facility_info_.*\.csv$/, name: "正式名称" },
  dental: { label: "歯科診療所", pattern: /^03-1_dental_facility_info_.*\.csv$/, name: "正式名称" },
  maternity: { label: "助産所", pattern: /^04_maternity_home_.*\.csv$/, name: "正式名称" },
  pharmacy: { label: "薬局", pattern: /^05_pharmacy_.*\.csv$/, name: "名称" },
};

const DEFAULT_ADOPT_LEVEL = 8;
const API_BASE_ENV = "NJA_API_BASE";
const PUBLIC_API_HOST = "japanese-addresses-v2.geoloniamaps.com";
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

/**
 * 住所データの取得先を確かめる。
 *
 * nja-osm-tags は NJA_API_BASE が未設定なら公開 API を読む。
 * 20万件を通すと1件ごとに問い合わせが出るうえ、公開 API が配信している
 * データは手元に構築したものより古い。どちらも黙って起きてほしくないので、
 * 取得先が手元を指していることを確かめてから動く。
 *
 * 値が file:// や存在しないパスかどうかは nja-osm-tags の applyApiBase が
 * 起動時に確かめる。ここでは二重に検査しない。
 */
function requireLocalApiBase() {
  const raw = (process.env[API_BASE_ENV] || "").trim();
  if (!raw) {
    console.error(`住所データの取得先が設定されていません: ${API_BASE_ENV}`);
    console.error("japanese-addresses-v2 を手元に構築し、その out/api/ja を指してください");
    console.error(`  export ${API_BASE_ENV}=/path/to/japanese-addresses-v2/out/api/ja`);
    console.error("構築の手順は vendor/nja-osm-tags/docs/local-mirror.md にあります");
    process.exit(2);
  }
  if (raw.includes(PUBLIC_API_HOST)) {
    console.error(`公開 API は使いません: ${raw}`);
    console.error("配信されているデータが手元に構築したものより古く、");
    console.error("20万件の問い合わせは相手にも負荷をかけます");
    process.exit(2);
  }
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

/**
 * 推定になった行を、番地だけの住所に組み直して通し直す。
 *
 * NJA は番地の後ろに建物名や階が続くと明細照合を外し、番地を推定として返す。
 * 雑音を落とした住所で引き直すと明細が取れることがあり、その番地は台帳に
 * 実在することが確かめられる。本番データでは推定の9.1%がこれで照合済みに
 * なり、番地は1件も変わらなかった。
 *
 * 通すのは推定の行だけなので、全体の1往復には遠く及ばない。
 * njaRows をその場で書き換える。採否の規則は adoptRecheck にある。
 */
function recheckInferred(njaRows) {
  const targets = [];
  for (let i = 0; i < njaRows.length; i++) {
    if (njaRows[i]["_番地の根拠"] !== "推定") continue;
    const addr = recheckAddress(njaRows[i]);
    if (addr) targets.push([i, addr]);
  }
  if (!targets.length) return;

  console.log(`推定 ${targets.length.toLocaleString()} 件を番地だけの住所で照合し直します`);
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "osm-iryo-recheck-"));
  const file = path.join(dir, "recheck.csv");
  const rows = [["ID", "所在地"]];
  for (const [i, addr] of targets) rows.push([njaRows[i]["ID"], addr]);
  fs.writeFileSync(file, "\ufeff" + toCsv(rows));

  const out = runBatch(file);
  fs.rmSync(dir, { recursive: true, force: true });
  if (out.length !== targets.length) {
    console.error(`照合し直しの入力 ${targets.length} 行に対し出力 ${out.length} 行。中断します`);
    process.exit(1);
  }

  let adopted = 0, rejected = 0;
  for (let k = 0; k < targets.length; k++) {
    const i = targets[k][0];
    const take = adoptRecheck(njaRows[i], out[k]);
    if (take) { Object.assign(njaRows[i], take); adopted++; }
    else if (out[k]["_番地の根拠"] === "照合済み") rejected++;
  }
  console.log(`  照合済みに変わった: ${adopted.toLocaleString()} 件`);
  if (rejected) {
    console.log(`  番地が食い違うため採らなかった: ${rejected.toLocaleString()} 件`);
  }
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

  requireLocalApiBase();

  // 矩形の表をここで読む。foldColumns の既定引数から読ませると、最初の行を
  // 畳むときまで評価されない。表が無い環境では20万件のバッチを流し切った後で
  // 落ちることになり、数分を捨てる。取得先の検査と同じ場所で止める。
  try {
    loadPrefBox();
  } catch (e) {
    console.error(`都道府県の外接矩形の表を読めません: ${e.message}`);
    console.error("mapping/pref_bbox.csv が要ります。npm run build:pref-bbox で作り直せます");
    process.exit(2);
  }

  const conf = SECTORS[sector];
  const src = findSource(dataDir, conf.pattern);
  const rows = parseCsv(fs.readFileSync(src, "utf8"));
  const header = rows.shift();
  const ix = {};
  header.forEach((h, n) => (ix[h] = n));

  // 列が欠けたまま進むと r[undefined].trim() の TypeError になり、
  // どの列が無いのか分からない。読み終えた直後に検査して落とす。
  // 都道府県コードは .trim() を通らないので落ちないが、欠けると
  // 出力の列が黙って空になり build_osm.py まで伝わるので併せて見る。
  for (const need of ["所在地", "所在地座標（緯度）", "所在地座標（経度）",
                      "都道府県コード", conf.name]) {
    if (ix[need] === undefined) {
      console.error(`必要な列が見つかりません: ${need}`);
      process.exit(2);
    }
  }

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

  recheckInferred(njaRows);

  const outHeader = [
    "ID", "名称", "都道府県コード",
    "元_所在地", "元_緯度", "元_経度",
    "lat", "lon", "座標の出典", "位置レベル", "位置レベルの意味",
    "補完しなかった理由",
    // 住所から得た点は、元データの座標を採った行でも残す。
    // 穴埋めの座標を後段で捨てるとき、付け直す先がこれになる。
    "住所_lat", "住所_lon", "住所_位置レベル", "住所_備考",
    "番地の根拠", "正規化住所", "未解釈の文字列", "fixme",
    ...ADDR_KEYS,
    "要確認", "備考",
    // 元データの座標を捨てた行の理由。備考の先頭の1文と同じ内容を単独で持つ。
    // build_osm.py がジオコーディングの行の備考を作り直すときにこれを使う。
    // 列は末尾に足す。この CSV を読む側は全てヘッダ名で引いているが、
    // 末尾なら既存の列の位置が動かない。
    "座標の理由",
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
      f["補完しなかった理由"],
      nja["_lat"], nja["_lng"], nja["_座標精度"], nja["_備考"],
      f["番地の根拠"], f["正規化住所"], f["未解釈の文字列"],
      f["fixme"],
      ...ADDR_KEYS.map((k) => nja[k] || ""),
      f["要確認"], f["備考"], f["座標の理由"],
    ]);
  }

  const buildDir = path.join(outDir, "build");
  fs.mkdirSync(buildDir, { recursive: true });
  const file = path.join(buildDir, `${sector}_geocoded.csv`);
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
