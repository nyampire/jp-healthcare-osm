#!/usr/bin/env python3
"""座標の検算スクリプトの逆テスト。

検算そのものが黙って甘くなる経路を潰す。
実データを読む部分ではなく、判定を決める純粋な関数を確かめる。
"""
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
# どちらも末尾が if __name__ == "__main__": main() なので import で走らない。
from verify_coords_addr import (  # noqa: E402
    DEFAULT_THRESHOLDS, checked_by_drift_rule, distance_meters, percentiles,
    pick_suspects, usable,
)
from verify_coords_osm import (  # noqa: E402
    centroid, decode_object_id, match, normalize_name,
)


def row(level="8", origin="原データ", dist=10.0, basis="照合済み"):
    return {"業態": "clinic", "_id": "T1", "名称": "テスト医院",
            "都道府県": "東京都", "市区町村": "千代田区", "住所": "",
            "座標の出典": origin, "位置レベル": level, "番地の根拠": basis,
            "lat": 35.0, "lon": 139.0, "距離m": dist}


def case_distance_matches_reference():
    """距離が既知の値と一致する。addr_columns.js と同じ式であること"""
    # 緯度1度はおよそ 111.19km。半径 6371km の大円で計算した値。
    d = distance_meters(35.0, 139.0, 36.0, 139.0)
    if not math.isclose(d, 111194.9, rel_tol=1e-4):
        return False, f"緯度1度が 111,194.9m でなく {d:.1f}m"
    if distance_meters(35.0, 139.0, 35.0, 139.0) != 0.0:
        return False, "同一点が 0 にならない"
    return True, ""


def case_usable_rejects_zero():
    """0 と空文字を座標として採らない。片方だけ採ると赤道上の点になる"""
    for bad in ("", "0", "0.0", None, "abc", "  "):
        if usable(bad):
            return False, f"{bad!r} を有効と判定した"
    for good in ("35.1", "-139.5", 1.0):
        if not usable(good):
            return False, f"{good!r} を無効と判定した"
    return True, ""


def case_drift_rule_conditions():
    """1km規則の適用条件が foldColumns と同じ3つであること"""
    if not checked_by_drift_rule(row()):
        return False, "レベル8・照合済み・距離ありが検査対象にならない"
    if checked_by_drift_rule(row(level="3")):
        return False, "レベル3を検査対象にしている"
    if checked_by_drift_rule(row(basis="推定")):
        return False, "番地が推定の行を検査対象にしている"
    if checked_by_drift_rule(row(dist=None)):
        return False, "住所側の座標が無い行を検査対象にしている"
    if checked_by_drift_rule(row(level="")):
        return False, "位置レベルが空の行を検査対象にしている"
    return True, ""


def case_suspects_use_level_thresholds():
    """位置レベルごとに別の閾値が効く。同じ距離でも判定が変わること"""
    rows = [row(level="8", dist=150.0), row(level="3", dist=150.0),
            row(level="2", dist=150.0)]
    got = pick_suspects(rows, DEFAULT_THRESHOLDS)
    if len(got) != 1 or got[0]["位置レベル"] != "8":
        return False, f"レベル8だけが残るはずが {[r['位置レベル'] for r in got]}"
    return True, ""


def case_suspects_skip_geocoded():
    """ジオコーディングの行を数えない。距離が必ず0で意味を持たないため"""
    rows = [row(origin="ジオコーディング", dist=99999.0)]
    if pick_suspects(rows, DEFAULT_THRESHOLDS):
        return False, "ジオコーディングの行を疑いに入れた"
    return True, ""


def case_suspects_have_no_level1_threshold():
    """レベル1に閾値を置かない。八丈島などが必ず数百km離れるため"""
    rows = [row(level="1", dist=286000.0)]
    if pick_suspects(rows, DEFAULT_THRESHOLDS):
        return False, "レベル1を疑いに入れた"
    return True, ""


def case_suspects_sorted_desc():
    """距離の大きい順に並ぶ"""
    rows = [row(dist=200.0), row(dist=900.0), row(dist=400.0)]
    got = [r["距離m"] for r in pick_suspects(rows, DEFAULT_THRESHOLDS)]
    if got != [900.0, 400.0, 200.0]:
        return False, f"並びが {got}"
    return True, ""


def case_percentiles_bounds():
    """百分位が範囲外を返さない。1件でも落ちないこと"""
    pc = percentiles(list(range(1, 101)))
    if pc["max"] != 100:
        return False, f"最大が 100 でなく {pc['max']}"
    if not 45 <= pc[50] <= 55:
        return False, f"中央値が {pc[50]}"
    if percentiles([]) != {}:
        return False, "空の入力で空の辞書を返さない"
    if percentiles([7.0])["max"] != 7.0:
        return False, "1件の入力で落ちる"
    return True, ""


def case_normalize_name():
    """法人格・全半角・記号の違いを吸収する"""
    pairs = [
        ("医療法人社団　のぞみ会　のぞみクリニック", "のぞみ会のぞみクリニック"),
        ("ＡＢＣ薬局", "abc薬局"),
        ("さくら・歯科 医院", "さくら歯科医院"),
        ("株式会社スギ薬局　本店", "スギ薬局本店"),
    ]
    for raw, want in pairs:
        got = normalize_name(raw)
        if got != want:
            return False, f"{raw!r} が {want!r} でなく {got!r}"
    if normalize_name("") != "":
        return False, "空文字で落ちる"
    return True, ""


def case_normalize_does_not_merge_different():
    """別の施設名を同じキーに潰さない"""
    if normalize_name("田中医院") == normalize_name("田中歯科医院"):
        return False, "田中医院と田中歯科医院が同じキーになった"
    return True, ""


def case_decode_object_id():
    """osmium の面 id を way / relation に戻す"""
    cases = [("n123", "node/123"), ("w456", "way/456"),
             ("r789", "relation/789"),
             ("a1000", "way/500"), ("a1001", "relation/500")]
    for raw, want in cases:
        got = decode_object_id(raw)
        if got != want:
            return False, f"{raw} が {want} でなく {got}"
    return True, ""


def case_centroid():
    """点はそのまま、面は頂点の平均を返す"""
    lon, lat = centroid({"type": "Point", "coordinates": [139.5, 35.5]})
    if (lon, lat) != (139.5, 35.5):
        return False, f"点が {lon},{lat}"
    lon, lat = centroid({"type": "Polygon", "coordinates": [
        [[139.0, 35.0], [139.0, 36.0], [140.0, 36.0], [140.0, 35.0]]]})
    if not (math.isclose(lon, 139.5) and math.isclose(lat, 35.5)):
        return False, f"面の重心が {lon},{lat}"
    return True, ""


def orow(name, lat=35.0, lon=139.0):
    return {"業態": "clinic", "_id": "T1", "名称": name,
            "正規化名": normalize_name(name), "都道府県": "", "市区町村": "",
            "座標の出典": "原データ", "lat": lat, "lon": lon}


def case_match_requires_unique_both_sides():
    """双方で名称が一意でなければ照合しない。同名の別施設を数えないため"""
    index = {normalize_name("あお医院"): [{"id": "node/1", "name": "あお医院",
                                        "lat": 35.0, "lon": 139.0}]}
    # 我々の側に同名が2件あれば照合しない
    got, _ = match([orow("あお医院"), orow("あお医院")], index, 2000.0)
    if got:
        return False, "我々の側で重複しているのに照合した"
    # OSM 側に同名が2件あれば照合しない
    idx2 = {normalize_name("あお医院"): [
        {"id": "node/1", "name": "あお医院", "lat": 35.0, "lon": 139.0},
        {"id": "node/2", "name": "あお医院", "lat": 35.1, "lon": 139.1}]}
    got, _ = match([orow("あお医院")], idx2, 2000.0)
    if got:
        return False, "OSM 側で重複しているのに照合した"
    # 双方で一意なら照合する
    got, _ = match([orow("あお医院")], index, 2000.0)
    if len(got) != 1:
        return False, "双方で一意なのに照合しない"
    return True, ""


def case_match_drops_far():
    """上限を超えた組み合わせを同一施設と見なさない"""
    index = {normalize_name("あお医院"): [{"id": "node/1", "name": "あお医院",
                                        "lat": 43.0, "lon": 141.0}]}
    got, dropped = match([orow("あお医院", 35.0, 139.0)], index, 2000.0)
    if got:
        return False, "800km 離れた組み合わせを照合した"
    if dropped != 1:
        return False, f"外した件数が 1 でなく {dropped}"
    return True, ""


def case_match_skips_short_names():
    """短すぎる名称で照合しない。「内科」だけの行が全国で衝突するため"""
    index = {"内科": [{"id": "node/1", "name": "内科",
                     "lat": 35.0, "lon": 139.0}]}
    got, _ = match([orow("内科")], index, 2000.0)
    if got:
        return False, "2文字の名称で照合した"
    return True, ""


def main():
    cases = [
        ("距離が既知の値と一致する", case_distance_matches_reference),
        ("0 と空文字を座標として採らない", case_usable_rejects_zero),
        ("1km規則の適用条件が3つとも効く", case_drift_rule_conditions),
        ("位置レベルごとに閾値が変わる", case_suspects_use_level_thresholds),
        ("ジオコーディングの行を疑いに入れない", case_suspects_skip_geocoded),
        ("レベル1に閾値を置かない", case_suspects_have_no_level1_threshold),
        ("疑いが距離の大きい順に並ぶ", case_suspects_sorted_desc),
        ("百分位が範囲外を返さない", case_percentiles_bounds),
        ("法人格と全半角と記号を吸収する", case_normalize_name),
        ("別の施設名を同じキーに潰さない", case_normalize_does_not_merge_different),
        ("osmium の面 id を復元する", case_decode_object_id),
        ("点と面から代表点を出す", case_centroid),
        ("双方で一意でなければ照合しない", case_match_requires_unique_both_sides),
        ("上限を超えた組み合わせを外す", case_match_drops_far),
        ("短すぎる名称で照合しない", case_match_skips_short_names),
    ]
    print("=== 座標の検算 逆テスト ===\n")
    failed = 0
    for label, fn in cases:
        ok, detail = fn()
        if not ok:
            failed += 1
        print(f"  {'PASS' if ok else 'FAIL'}  {label}"
              + (f"  {detail}" if detail else ""))
    print(f"\n  {len(cases) - failed}/{len(cases)} 件")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
