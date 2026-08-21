#!/usr/bin/env node
/**
 * build_opening_hours.py が生成した opening_hours を、OSM の参照実装
 * opening_hours.js で検証する。
 *
 * 生成側（Python）と検証側（参照実装）を独立させることで、自前の正規表現では
 * 気づけない構文・意味の誤りを拾う。実際にこの検証で以下を検出した:
 *   - 24時間営業が `08:30-08:30` となり、ゼロ長とも24時間とも読める曖昧な出力
 *   - コメントを通常ルールとして書くと平日まで休診判定になる問題
 *
 * 使い方:
 *   node scripts/validate_opening_hours.js [output/opening_hours.csv]
 *
 * 終了コード: 生成側の欠陥（パースエラー・5週間で一度も開かない・ゼロ長区間）が
 *             1 件でもあれば 1、なければ 0。参照実装の警告は 0 のまま扱う。
 */

const fs = require("fs");
const path = require("path");
const opening_hours = require("opening_hours");

// PH（祝日）の解決に国が要るため日本を指定する。座標は国内であれば判定に影響しない。
const NOMINATIM = { lat: 35.68, lon: 139.77, address: { country_code: "jp" } };

// 検証に使う連続13週間。この期間に一度も開かない値は、コメントや例外ルールを通常
// ルールとして書いてしまい全時間帯を上書きした疑いが濃い。
// 窓を広く取るのは Sa[1] のように月内の特定週しか開かない施設を誤検知しないため。
// 1週間では「第1土曜のみ開院」が偽陽性になり、5週間でも足りなかった。
// 「第2月曜のみ開院」の施設は、5週間の窓に入る唯一の第2月曜が成人の日（1月第2月曜）と
// 重なり PH off で閉まるため偽陽性になる。日本には第2・第3月曜の祝日が複数あるので、
// 月内の同じ週が3回以上巡る長さを取る。
// 全件を長い窓で走査すると数万件では時間がかかりすぎるため2段階にする。
// まず5週間で高速に判定し、そこで「一度も開かない」と出た数件だけ13週間で確認する。
const PROBE_FROM = new Date(2026, 0, 5, 0, 0);       // 2026-01-05 (月)
const PROBE_TO = new Date(2026, 1, 9, 0, 0);         // 2026-02-09 (月) 5週間
const PROBE_TO_LONG = new Date(2026, 3, 6, 0, 0);    // 2026-04-06 (月) 13週間

// 開始と終了が同じ時刻の区間。ゼロ長とも24時間とも読めるため出力してはいけない。
const RE_ZERO_SPAN = /(\d{2}:\d{2})-\1/;

/** RFC4180 準拠の CSV パーサ。引用符内のカンマ・改行・二重引用符を扱う。 */
function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = "";
  let quoted = false;
  let i = 0;
  if (text.charCodeAt(0) === 0xfeff) i = 1; // BOM
  while (i < text.length) {
    const c = text[i];
    if (quoted) {
      if (c === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i += 2;
          continue;
        }
        quoted = false;
        i++;
        continue;
      }
      field += c;
      i++;
      continue;
    }
    if (c === '"') {
      quoted = true;
      i++;
    } else if (c === ",") {
      row.push(field);
      field = "";
      i++;
    } else if (c === "\r") {
      i++;
    } else if (c === "\n") {
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
      i++;
    } else {
      field += c;
      i++;
    }
  }
  if (field !== "" || row.length) {
    row.push(field);
    rows.push(row);
  }
  return rows;
}

function main() {
  const target = process.argv[2] ||
    path.join(__dirname, "..", "output", "opening_hours.csv");
  if (!fs.existsSync(target)) {
    console.error(`入力ファイルがありません: ${target}`);
    console.error("先に scripts/build_opening_hours.py を実行してください。");
    process.exit(2);
  }

  const rows = parseCsv(fs.readFileSync(target, "utf8"));
  const header = rows.shift();
  const col = {};
  header.forEach((h, n) => (col[h] = n));
  for (const need of ["ID", "正式名称", "opening_hours"]) {
    if (col[need] === undefined) {
      console.error(`必要な列が見つかりません: ${need}`);
      process.exit(2);
    }
  }

  let checked = 0;
  let empty = 0;
  const errors = [];
  const warnings = [];
  const neverOpen = [];
  const zeroSpan = [];
  const tooLong = [];

  for (const r of rows) {
    if (!r.length || !r[col.ID]) continue;
    const id = r[col.ID];
    const name = r[col["正式名称"]];
    const value = r[col.opening_hours];
    if (!value) {
      empty++;
      continue;
    }
    checked++;
    let oh;
    try {
      oh = new opening_hours(value, NOMINATIM, { mode: 0 });
    } catch (e) {
      errors.push({ id, name, value, detail: String(e) });
      continue;
    }
    const w = oh.getWarnings() || [];
    if (w.length) {
      warnings.push({ id, name, value, detail: w[0].replace(/\s+/g, " ") });
    }
    // 5週間で一度も開かないなら、時間ルールが例外ルールに潰されている。
    let intervals = [];
    try {
      intervals = oh.getOpenIntervals(PROBE_FROM, PROBE_TO);
    } catch (e) {
      intervals = [];
    }
    // getOpenIntervals は [from, to, unknown, comment] を返す。コメントだけの
    // ルールは期間全体を unknown=true の1区間で埋めてしまい、区間数を数えるだけ
    // では破損を見逃す。確実に開いている区間だけを数える。
    let open = intervals.filter((x) => !x[2]);
    if (!open.length) {
      // 短い窓で開かないものだけ長い窓で再確認する。件数が少ないので費用は無視できる。
      let long = [];
      try {
        long = oh.getOpenIntervals(PROBE_FROM, PROBE_TO_LONG).filter((x) => !x[2]);
      } catch (e) {
        long = [];
      }
      if (!long.length) {
        neverOpen.push({
          id, name, value,
          detail: intervals.length
            ? "連続13週間で確実に開く時間が無い（状態が unknown のみ）"
            : "連続13週間で一度も開かない",
        });
      }
    }
      // OSM のタグ値は 255 文字が上限。構文が正しくても投入できない。
    if (value.length > 255) {
      tooLong.push({ id, name, value, detail: `${value.length}文字（上限255）` });
    }
  const zero = value.match(RE_ZERO_SPAN);
    if (zero) {
      zeroSpan.push({
        id, name, value,
        detail: `開始と終了が同一の区間 ${zero[0]}（ゼロ長とも24時間とも読める）`,
      });
    }
  }

  // 検証結果は入力ファイル名から導く。業態ごとに実行しても上書きされないようにする。
  const outDir = path.dirname(target);
  const reportName = path.basename(target).replace(/\.csv$/, "") + "_validation.csv";
  const report = [["種別", "ID", "正式名称", "opening_hours", "内容"]];
  const push = (kind, list) =>
    list.forEach((x) => report.push([kind, x.id, x.name, x.value, x.detail]));
  push("error", errors);
  push("never_open", neverOpen);
  push("zero_span", zeroSpan);
  push("too_long", tooLong);
  push("warning", warnings);
  const csv = report
    .map((r) =>
      r.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(","))
    .join("\n");
  fs.writeFileSync(path.join(outDir, reportName), "﻿" + csv);

  console.log(`検証対象ファイル : ${path.relative(process.cwd(), target)}`);
  console.log(`opening_hours.js : ${require("opening_hours/package.json").version}`);
  console.log("");
  console.log(`  検証数           : ${checked.toLocaleString()}`);
  console.log(`  空欄（対象外）   : ${empty.toLocaleString()}`);
  console.log(`  パースエラー     : ${errors.length.toLocaleString()}`);
  console.log(`  警告             : ${warnings.length.toLocaleString()}`);
  console.log(`  5週間で一度も開かない: ${neverOpen.length.toLocaleString()}`);
  console.log(`  ゼロ長区間       : ${zeroSpan.length.toLocaleString()}`);
  console.log(`  255文字超        : ${tooLong.length.toLocaleString()}`);

  for (const e of errors.slice(0, 5)) {
    console.log(`\n  ERROR ${e.name}\n    ${e.value}\n    ${e.detail}`);
  }
  if (warnings.length) {
    const grouped = {};
    for (const w of warnings) {
      const key = w.detail.replace(/^.*<---\s*/, "").slice(0, 70);
      grouped[key] = (grouped[key] || 0) + 1;
    }
    console.log("\n  警告の内訳:");
    Object.entries(grouped)
      .sort((a, b) => b[1] - a[1])
      .forEach(([k, v]) => console.log(`    ${String(v).padStart(5)} 件  ${k}`));
  }
  console.log(`\n詳細: ${path.relative(process.cwd(), path.join(outDir, reportName))}`);

  for (const x of neverOpen.slice(0, 5)) {
    console.log(`\n  NEVER OPEN ${x.name}\n    ${x.value}`);
  }
  for (const x of zeroSpan.slice(0, 5)) {
    console.log(`\n  ZERO SPAN ${x.name}\n    ${x.value}`);
  }

  // ゼロ長区間と「一度も開かない」は生成側の欠陥なのでエラー扱いにする
  const fatal = errors.length + neverOpen.length + zeroSpan.length + tooLong.length;
  process.exit(fatal ? 1 : 0);
}

main();
