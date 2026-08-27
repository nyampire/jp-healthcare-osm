/**
 * nja-osm-tags のバッチ出力1行と、元データの座標を、出力列に畳む。
 *
 * バッチには --lat-column / --lng-column を渡さない。
 * 渡すと nja-osm-tags 側の resolveCoord が先に合流を済ませ、由来が
 * _座標精度 と _lat の空欄の組み合わせに埋もれる。
 * 渡さなければ _lat / _lng / _座標精度 は常に NJA の点だけを表すので、
 * 合流規則をこの1箇所に置ける。
 */

/** 位置情報データのレベルと、その意味 */
const POINT_LEVEL_NOTE = {
  1: "都道府県庁所在地",
  2: "市区町村役場の所在地",
  3: "大字と丁目の代表点",
  8: "住居表示の位置",
};

/** addr:* のキー。OSM の階層順に並べる */
const ADDR_KEYS = [
  "addr:country", "addr:province", "addr:county", "addr:city",
  "addr:suburb", "addr:quarter", "addr:neighbourhood",
  "addr:block_number", "addr:housenumber",
];

/**
 * 数値として有効で 0 でないか。
 * nja-osm-tags の serialize.ts の usable と同じ判定にする。
 * ここがずれると、どちらの座標を採ったかが2つのリポジトリで食い違う。
 */
function usable(v) {
  if (v === undefined || v === null || String(v).trim() === "") return false;
  const n = parseFloat(v);
  return Number.isFinite(n) && n !== 0;
}

/**
 * 1行を出力列に畳む。
 *
 * 元データの緯度と経度が両方とも有効なら、それを採る。
 * 片方でも欠ければ NJA の点に回す。片方だけ採ると、欠けたほうが 0 のまま
 * 残って赤道上の座標になる。
 */
function foldColumns(nja, rawLat, rawLon, adoptLevel) {
  const out = {
    lat: "", lon: "",
    "座標の出典": "", "位置レベル": "", "位置レベルの意味": "",
    "補完しなかった理由": "",
    "番地の根拠": nja["_番地の根拠"] || "",
    "正規化住所": ADDR_KEYS.map((k) => nja[k] || "").join(""),
    "未解釈の文字列": nja["note"] || "",
    "fixme": nja["fixme"] || "",
    "要確認": "", "備考": "",
  };
  const notes = [];

  if (usable(rawLat) && usable(rawLon)) {
    out.lat = String(rawLat).trim();
    out.lon = String(rawLon).trim();
    out["座標の出典"] = "原データ";
    if (out["未解釈の文字列"]) notes.push(`住所の未解釈部分: ${out["未解釈の文字列"]}`);
    out["備考"] = notes.join(" / ");
    return out;
  }

  const level = nja["_座標精度"] === "" || nja["_座標精度"] === undefined
    ? null : parseInt(nja["_座標精度"], 10);
  if (level !== null) {
    out["位置レベル"] = String(level);
    out["位置レベルの意味"] = POINT_LEVEL_NOTE[level] || "";
  }

  if (nja["_備考"] === "地番方式のため対象外") {
    out["座標の出典"] = "なし";
    out["補完しなかった理由"] = "地番方式";
    out["要確認"] = "yes";
    notes.push("地番方式の住所のため座標を補完しない");
  } else if (!usable(nja["_lat"]) || !usable(nja["_lng"])) {
    out["座標の出典"] = "なし";
    out["補完しなかった理由"] = "解決できず";
    out["要確認"] = "yes";
    notes.push("住所から座標を解決できなかった");
  } else if (level !== null && level >= adoptLevel) {
    out.lat = nja["_lat"];
    out.lon = nja["_lng"];
    out["座標の出典"] = "ジオコーディング";
    notes.push(`住所から付与（位置レベル${level}、${out["位置レベルの意味"]}）`);
  } else {
    out["座標の出典"] = "なし";
    out["補完しなかった理由"] = "位置レベル不足";
    out["要確認"] = "yes";
    notes.push(`位置レベル${level === null ? "不明" : level}`
      + `${out["位置レベルの意味"] ? `（${out["位置レベルの意味"]}）` : ""}のため採用しない`);
  }

  if (out["未解釈の文字列"]) notes.push(`住所の未解釈部分: ${out["未解釈の文字列"]}`);
  out["備考"] = notes.join(" / ");
  return out;
}

module.exports = { foldColumns, ADDR_KEYS, POINT_LEVEL_NOTE };
