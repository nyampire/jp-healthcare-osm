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
const { loadPrefBox, outOfPref, inBox, MARGIN_DEGREES } = require("./pref_bbox.js");

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
  checkOutOfPref();
  checkPrefBoxTable();
}

/**
 * mapping/pref_bbox.csv そのものを検査する。
 *
 * 表が欠けたり縮んだりすると、正しい座標を県外と誤判定して動かす。
 * 生成し直したときに気づけるよう、行数と範囲を固定する。
 */
function checkPrefBoxTable() {
  console.log("");
  const box = loadPrefBox();
  const names = Object.keys(box);
  const codes = names.map((n) => box[n].code).sort();
  const want = Array.from({ length: 47 }, (_, i) => String(i + 1).padStart(2, "0"));

  const cases = [
    ["47都道府県が揃っている", names.length === 47, String(names.length)],
    ["コードが01から47まで重複なく並ぶ", codes.join(",") === want.join(","), codes.join(",")],
    ["矩形の上下と左右が逆転していない",
      names.every((n) => box[n].latMin < box[n].latMax && box[n].lonMin < box[n].lonMax), ""],
    ["矩形が日本の範囲に収まる",
      names.every((n) => box[n].latMin >= 20 && box[n].latMax <= 46
        && box[n].lonMin >= 122 && box[n].lonMax <= 154), ""],
    // 東京都の矩形は南鳥島と沖ノ鳥島を含むので、硫黄島の座標を含む。
    ["硫黄島の座標が東京都の矩形の中にある",
      inBox(box["東京都"], 24.79439, 141.306414), ""],
    // 誤りの例。熊本県の施設の座標が愛知県の矩形の中にある。
    ["熊本県の矩形は愛知県の座標を含まない",
      inBox(box["熊本県"], 35.085644, 137.190795) === false, ""],
    ["愛知県の矩形は愛知県の座標を含む",
      inBox(box["愛知県"], 35.085644, 137.190795), ""],
  ];

  let failed = 0;
  for (const [name, ok, actual] of cases) {
    if (!ok) failed++;
    console.log(`  ${ok ? "PASS" : "FAIL"}  ${name}`);
    if (!ok && actual) console.log(`        実際: ${actual}`);
  }
  console.log(`\n  ${cases.length - failed}/${cases.length} 件`);
  if (failed) process.exit(1);
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

/**
 * 県外を指す座標の判定を検査する。
 *
 * 距離では判定できない。海上自衛隊硫黄島航空基地医務室は正しい座標のまま
 * 住所点から270.6km離れる。県外かどうかで見ると、硫黄島の座標は東京都の
 * 矩形の中にあり、誤りの7件は別の県の矩形の中にある。
 */
function checkOutOfPref() {
  console.log("");
  const cases = [];

  // 実データから採った値を丸めたもの。東京都は南鳥島と沖ノ鳥島を含む。
  const box = {
    "熊本県": { code: "43", latMin: 32.1143, latMax: 33.1672, lonMin: 129.9929, lonMax: 131.2894 },
    "愛知県": { code: "23", latMin: 34.5776, latMax: 35.4245, lonMin: 136.6725, lonMax: 137.8395 },
    "東京都": { code: "13", latMin: 20.4256, latMax: 35.8580, lonMin: 136.0811, lonMax: 153.9806 },
  };

  cases.push(["自県の矩形の外かつ他県の矩形の中なら県名を返す",
    JSON.stringify(outOfPref(box, "熊本県", 35.085644, 137.190795)) === '["愛知県","東京都"]',
    JSON.stringify(outOfPref(box, "熊本県", 35.085644, 137.190795))]);

  cases.push(["自県の矩形の中なら null を返す",
    outOfPref(box, "熊本県", 32.95, 131.10) === null, ""]);

  // 硫黄島の実際の座標。東京都の矩形の中にあるので差し替えの対象にしない。
  cases.push(["硫黄島の座標は東京都の矩形の中にある",
    outOfPref(box, "東京都", 24.79439, 141.306414) === null, ""]);

  cases.push(["どの県の矩形にも入らなければ null を返す",
    outOfPref(box, "熊本県", 45.0, 141.0) === null, ""]);

  cases.push(["表に無い県名なら null を返す",
    outOfPref(box, "沖縄県", 35.085644, 137.190795) === null, ""]);

  cases.push(["県名が空なら null を返す",
    outOfPref(box, "", 35.085644, 137.190795) === null, ""]);

  // 矩形の縁の外側でも余裕の内側なら自県とみなす。埋立地や岬を吸収する。
  cases.push(["余裕の内側は自県の矩形の中とみなす",
    outOfPref(box, "熊本県", 33.1672 + 0.03, 130.5) === null, ""]);

  cases.push(["余裕の外側は自県の矩形の外とみなす",
    inBox(box["熊本県"], 33.1672 + 0.07, 130.5, MARGIN_DEGREES) === false, ""]);

  // 表の読み込み。区切りだけの単純な CSV で、BOM を落とすことを確かめる。
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "osm-iryo-bbox-"));
  const file = path.join(dir, "pref_bbox.csv");
  fs.writeFileSync(file,
    "﻿都道府県コード,都道府県,lat_min,lat_max,lon_min,lon_max\n"
    + "13,東京都,20.425600,35.858000,136.081100,153.980600\n"
    + "43,熊本県,32.114300,33.167200,129.992900,131.289400\n");
  const loaded = loadPrefBox(file);
  cases.push(["表を読むと県名で引ける", Object.keys(loaded).length === 2, String(Object.keys(loaded).length)]);
  cases.push(["BOM を落として県名を読む", loaded["東京都"] !== undefined, Object.keys(loaded).join(",")]);
  cases.push(["矩形の値を数値で持つ",
    loaded["熊本県"].latMin === 32.1143 && loaded["熊本県"].lonMax === 131.2894,
    String(loaded["熊本県"] && loaded["熊本県"].latMin)]);
  cases.push(["都道府県コードを文字列で持つ",
    loaded["熊本県"].code === "43", String(loaded["熊本県"] && loaded["熊本県"].code)]);
  fs.rmSync(dir, { recursive: true, force: true });

  // foldColumns を通したときの出力。差し替えた行が何を持つかを固定する。
  const nja = {
    "addr:country": "JP", "addr:province": "熊本県", "addr:county": "",
    "addr:city": "阿蘇市", "addr:suburb": "内牧", "addr:quarter": "",
    "addr:neighbourhood": "", "addr:block_number": "", "addr:housenumber": "",
    "_lat": "32.950000", "_lng": "131.100000", "_座標精度": "3",
    "_番地の根拠": "推定", "note": "", "fixme": "",
  };
  const fold = (rec, la, lo) => foldColumns(rec, la, lo, 8, 1000, box);

  const moved = fold(nja, "35.085644", "137.190795");
  // 緯度と経度の両方を見る。このリポジトリは「GeoJSON は経度が先。緯度を先に
  // 置くと日本の施設が海上へ飛ぶ」を警戒しているので、片方だけの検査だと
  // 経度が落ちる壊れ方や、緯度と経度が入れ替わる壊れ方をすり抜ける。
  cases.push(["県外の座標を住所点に差し替える",
    moved.lat === "32.950000" && moved.lon === "131.100000",
    `${moved.lat}, ${moved.lon}`]);
  cases.push(["差し替えた行の出典はジオコーディング",
    moved["座標の出典"] === "ジオコーディング", moved["座標の出典"]]);
  cases.push(["差し替えた行に要確認が立つ", moved["要確認"] === "yes", moved["要確認"]]);
  cases.push(["差し替えた行の位置レベルは住所点のもの",
    moved["位置レベル"] === "3", moved["位置レベル"]]);
  cases.push(["備考に元の県と落ちた先の県が入る",
    moved["備考"].includes("熊本県ではなく愛知県と東京都の範囲"), moved["備考"]]);
  cases.push(["備考に捨てた座標が入る",
    moved["備考"].includes("元データの座標 35.085644, 137.190795 が"), moved["備考"]]);

  const kept = fold(nja, "32.950000", "131.100000");
  cases.push(["自県の座標は差し替えない", kept["座標の出典"] === "原データ", kept["座標の出典"]]);

  // レベル2は市区町村の代表点。県境の稜線に建つ山岳診療所を市街地へ動かすので
  // 対象にしない。鹿島槍冷池山荘診療所（富山県の住所、座標は長野県側）が実例。
  const lv2 = fold({ ...nja, "_座標精度": "2" }, "35.085644", "137.190795");
  cases.push(["位置レベル2は差し替えない", lv2["座標の出典"] === "原データ", lv2["座標の出典"]]);

  const lv8 = fold({ ...nja, "_座標精度": "8", "_番地の根拠": "照合済み" },
    "35.085644", "137.190795");
  cases.push(["レベル8は1km規則が先に働き、同じ住所点を採る",
    lv8.lat === "32.950000" && lv8["備考"].includes("離れているため"), lv8["備考"]]);
  cases.push(["1km規則の備考にも捨てた座標が入る",
    lv8["備考"].includes("元データの座標 35.085644, 137.190795 が"), lv8["備考"]]);

  const noProv = fold({ ...nja, "addr:province": "" }, "35.085644", "137.190795");
  cases.push(["県名が空なら差し替えない",
    noProv["座標の出典"] === "原データ", noProv["座標の出典"]]);

  const noPoint = fold({ ...nja, "_lat": "", "_lng": "" }, "35.085644", "137.190795");
  cases.push(["住所点が無ければ差し替えない",
    noPoint["座標の出典"] === "原データ", noPoint["座標の出典"]]);

  // 座標の理由は build_osm.py が読む列。備考の先頭の1文と同じ内容を、
  // 他の文と混ざらない形で持つ。build_osm.py は備考を定型文に置き換えるので、
  // 捨てた座標を MapRoulette まで運ぶにはこの列が要る。
  const why = (rec) => (typeof rec["座標の理由"] === "string"
    ? rec["座標の理由"] : "(座標の理由の列が無い)");
  cases.push(["県外の規則が座標の理由に捨てた座標を書く",
    why(moved).includes("元データの座標 35.085644, 137.190795 が")
    && why(moved).includes("の範囲にあるため"), why(moved)]);
  cases.push(["座標の理由が備考の先頭の1文と一致する",
    why(moved) === moved["備考"].split(" / ")[0], why(moved)]);
  cases.push(["1km規則も座標の理由を書く",
    why(lv8).includes("元データの座標 35.085644, 137.190795 が")
    && why(lv8).includes("離れているため"), why(lv8)]);
  cases.push(["原データを採った行の座標の理由は空",
    why(kept) === "", why(kept)]);

  let failed = 0;
  for (const [name, ok, actual] of cases) {
    if (!ok) failed++;
    console.log(`  ${ok ? "PASS" : "FAIL"}  ${name}`);
    if (!ok && actual) console.log(`        実際: ${actual}`);
  }
  console.log(`\n  ${cases.length - failed}/${cases.length} 件`);
  if (failed) process.exit(1);
}

main();
