#!/usr/bin/env python3
"""validate_osm.py 自身の逆テスト。

既知の不正なデータを検証器にかけ、狙った分類で検出されることを確かめる。
何も検出しない検証器は無意味なので、本番データが全件パスすることと同じくらい、
壊れた値をきちんと落とせることを確認する必要がある。

固定しているのは次の2件。
  T01 正常な地物。検出されないのが正しい
  T02 GeoJSON の座標が [緯度, 経度] の順で、name も空

  addr_province_mismatch を都道府県コードで突き合わせる検査に変えたことで、
  T04 の都道府県コードが実際の所在地（福島県）と食い違っていたことが判明した。
  T04 は addr_note_chiban 専用の題材で province の食い違いを狙ったものでは
  ないため、コードを福島県のものに直した。

  T10, T11 は addr_province_mismatch を都道府県コードで突き合わせる検査
  （PREF[都道府県コード] と addr:province の比較）専用の組。
  T10 は都道府県コードと addr:province が一致するが addr:full の先頭は
  県名で始まらない。addr:full の先頭と比較していた旧ロジックなら誤検出する
  組み合わせで、検出されないのが正しい（EXPECTED に入れない）。
  T11 は都道府県コードが addr:province と食い違うが、addr:full は
  addr:province と同じ文字列で始まる。旧ロジックでは見逃していた食い違いで、
  検出されるのが正しい。
"""

import csv
import os
import json
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXPECTED = {("T02", "coord_order"), ("T02", "name_missing"),
            ("T03", "addr_hierarchy"), ("T04", "addr_note_chiban"),
            ("T05", "addr_province_mismatch"),
            ("T06", "coord_cross_city"), ("T07", "coord_cross_city"),
            ("T11", "addr_province_mismatch")}


def main():
    tmp = tempfile.mkdtemp(prefix="osm-iryo-selftest-")
    try:
        for ext in (".csv", ".geojson"):
            shutil.copy(os.path.join(ROOT, "tests", "known_bad_osm" + ext),
                        os.path.join(tmp, "bad_osm" + ext))
        r = subprocess.run(
            [sys.executable, os.path.join(ROOT, "scripts", "validate_osm.py"),
             os.path.join(tmp, "bad_osm")],
            capture_output=True, text=True)
        report = os.path.join(tmp, "bad_osm_validation.csv")
        if not os.path.exists(report):
            print("検証結果が出力されませんでした。検証器が動作していません。")
            return 1
        with open(report, encoding="utf-8-sig", newline="") as f:
            got = {(x["ID"], x["種別"]) for x in csv.DictReader(f)}

        failed = 0
        print("=== validate_osm.py 逆テスト ===\n")
        for ident, kind in sorted(EXPECTED):
            ok = (ident, kind) in got
            if not ok:
                failed += 1
            print(f"  {'PASS' if ok else 'FAIL'}  {ident} を {kind} として検出")
        extra = got - EXPECTED
        ok = not extra
        if not ok:
            failed += 1
        print(f"  {'PASS' if ok else 'FAIL'}  期待しない検出が無い")
        if not ok:
            for x in sorted(extra):
                print(f"        余分な検出: {x[0]} {x[1]}")
        ok = r.returncode == 1
        if not ok:
            failed += 1
        print(f"  {'PASS' if ok else 'FAIL'}  不正データで終了コード 1 を返す")

        # addr_note_chiban だけを含むファイルは通さなければならない。
        # 住居表示未実施の町字では NJA が解決できなかった残余が note に残り、
        # その数字は実質的に地番になる。値は落とさず残す方針なので、
        # 分割するかどうかは利用者が件数を見て判断する。
        # ここで落とすと、方針として残している事象でパイプライン全体が止まる。
        only = os.path.join(tmp, "only_note_chiban")
        with open(os.path.join(tmp, "bad_osm.csv"), encoding="utf-8-sig",
                  newline="") as f:
            reader = csv.DictReader(f)
            header = reader.fieldnames
            rows = [x for x in reader if x["ID"] == "T04"]
        with open(only + ".csv", "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=header)
            w.writeheader()
            w.writerows(rows)
        with open(os.path.join(tmp, "bad_osm.geojson"), encoding="utf-8") as f:
            gj = json.load(f)
        gj["features"] = [x for x in gj["features"]
                          if x["properties"].get("_id") == "T04"]
        with open(only + ".geojson", "w", encoding="utf-8") as f:
            json.dump(gj, f, ensure_ascii=False)
        r2 = subprocess.run(
            [sys.executable, os.path.join(ROOT, "scripts", "validate_osm.py"), only],
            capture_output=True, text=True)
        ok = r2.returncode == 0
        if not ok:
            failed += 1
        print(f"  {'PASS' if ok else 'FAIL'}  addr_note_chiban だけなら終了コード 0 を返す")
        if not ok:
            print(f"        期待: 0 / 実際: {r2.returncode}")

        total = len(EXPECTED) + 3
        print(f"\n  {total - failed}/{total} 件")
        return 1 if failed else 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
