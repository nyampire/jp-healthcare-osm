/**
 * 住所から得た点だけを見て、座標を採るかどうかを決める。
 *
 * 元データが座標を持たない行と、元データの座標を穴埋めと判断して捨てた行の
 * どちらもここを通る。判断の分かれ目を2箇所に書くと必ず食い違うので、
 * foldColumns と fix_placeholder_coords.js の両方からこれを呼ぶ。
 *
 * 返す 説明 は 備考 に積む1文。fields はそのまま出力列に重ねられる。
 */
function resolveFromAddress({ lat, lng, level, note }, adoptLevel) {
  const fields = {
    lat: "", lon: "", "座標の出典": "", "補完しなかった理由": "", "要確認": "",
    "位置レベル": level === null || level === undefined ? "" : String(level),
    "位置レベルの意味": POINT_LEVEL_NOTE[level] || "",
  };

  if (note === "地番方式のため対象外") {
    fields["座標の出典"] = "なし";
    fields["補完しなかった理由"] = "地番方式";
    fields["要確認"] = "yes";
    return { fields, 説明: "地番方式の住所のため座標を補完しない" };
  }
  if (!usable(lat) || !usable(lng)) {
    fields["座標の出典"] = "なし";
    fields["補完しなかった理由"] = "解決できず";
    fields["要確認"] = "yes";
    return { fields, 説明: "住所から座標を解決できなかった" };
  }
  if (level !== null && level !== undefined && level >= adoptLevel) {
    fields.lat = String(lat);
    fields.lon = String(lng);
    fields["座標の出典"] = "ジオコーディング";
    return {
      fields,
      説明: `住所から付与（位置レベル${level}、${fields["位置レベルの意味"]}）`,
    };
  }
  fields["座標の出典"] = "なし";
  fields["補完しなかった理由"] = "位置レベル不足";
  fields["要確認"] = "yes";
  return {
    fields,
    説明: `位置レベル${level === null || level === undefined ? "不明" : level}`
      + `${fields["位置レベルの意味"] ? `（${fields["位置レベルの意味"]}）` : ""}のため採用しない`,
  };
}

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

/**
 * 元データの座標を住所側で置き換える距離の下限。
 *
 * 診療所32,626件の実測で、両者の距離は中央値15m、99パーセンタイル413mだった。
 * 1kmを超えるのは119件（0.36%）で、その全てが番地を明細と照合できた行だった。
 * 大きい方は熊本の診療所が約900km離れており、元データの座標の誤りと判断できる。
 * 敷地の広い病院でも1kmは超えないので、正しい座標を動かす危険が小さい。
 */
const MAX_DRIFT_METERS = 1000;

/** 2点間の距離をメートルで返す */
function distanceMeters(lat1, lon1, lat2, lon2) {
  const R = 6371000;
  const toRad = (d) => (d * Math.PI) / 180;
  const p1 = toRad(lat1);
  const p2 = toRad(lat2);
  const dp = toRad(lat2 - lat1);
  const dl = toRad(lon2 - lon1);
  const h = Math.sin(dp / 2) ** 2
    + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

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
function foldColumns(nja, rawLat, rawLon, adoptLevel, maxDrift = MAX_DRIFT_METERS) {
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

  const level = nja["_座標精度"] === "" || nja["_座標精度"] === undefined
    ? null : parseInt(nja["_座標精度"], 10);

  if (usable(rawLat) && usable(rawLon)) {
    // 元データの座標が住所から大きく離れている場合だけ、住所側を採る。
    // 同じ座標を別の市区町村の施設が共有している例が実在し、元データの座標が
    // 誤っていることがある。
    //
    // 条件を絞る理由は2つある。位置レベルが8未満だと比較相手が町字の代表点に
    // なり、正しい座標まで離れて見える。番地が推定だと、入力文字列を機械的に
    // 切った番地に引きずられて別の場所を指しうる。
    // 実測では1kmを超えた119件が全て照合済みだったので、絞っても取りこぼさない。
    const drift = level !== null && level >= adoptLevel
      && nja["_番地の根拠"] === "照合済み"
      && usable(nja["_lat"]) && usable(nja["_lng"])
      ? distanceMeters(parseFloat(rawLat), parseFloat(rawLon),
        parseFloat(nja["_lat"]), parseFloat(nja["_lng"]))
      : null;

    if (drift !== null && drift > maxDrift) {
      out.lat = nja["_lat"];
      out.lon = nja["_lng"];
      out["座標の出典"] = "ジオコーディング";
      out["位置レベル"] = String(level);
      out["位置レベルの意味"] = POINT_LEVEL_NOTE[level] || "";
      out["要確認"] = "yes";
      notes.push(`元データの座標がジオコーダ座標から${Math.round(drift).toLocaleString()}m離れているため、ジオコーダ座標を採用`);
      if (out["未解釈の文字列"]) notes.push(`住所の未解釈部分: ${out["未解釈の文字列"]}`);
      out["備考"] = notes.join(" / ");
      return out;
    }

    out.lat = String(rawLat).trim();
    out.lon = String(rawLon).trim();
    out["座標の出典"] = "原データ";
    if (out["未解釈の文字列"]) notes.push(`住所の未解釈部分: ${out["未解釈の文字列"]}`);
    out["備考"] = notes.join(" / ");
    return out;
  }

  const r = resolveFromAddress(
    { lat: nja["_lat"], lng: nja["_lng"], level, note: nja["_備考"] }, adoptLevel);
  Object.assign(out, r.fields);
  notes.push(r.説明);

  if (out["未解釈の文字列"]) notes.push(`住所の未解釈部分: ${out["未解釈の文字列"]}`);
  out["備考"] = notes.join(" / ");
  return out;
}

module.exports = {
  foldColumns, resolveFromAddress, distanceMeters, usable,
  ADDR_KEYS, POINT_LEVEL_NOTE, MAX_DRIFT_METERS,
};
