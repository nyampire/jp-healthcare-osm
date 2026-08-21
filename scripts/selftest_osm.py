#!/usr/bin/env python3
"""validate_osm.py 自身の逆テスト。

既知の不正なデータを検証器にかけ、狙った分類で検出されることを確かめる。
何も検出しない検証器は無意味なので、本番データが全件パスすることと同じくらい、
壊れた値をきちんと落とせることを確認する必要がある。

固定しているのは次の2件。
  T01 正常な地物。検出されないのが正しい
  T02 GeoJSON の座標が [緯度, 経度] の順で、name も空
"""

import csv
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXPECTED = {("T02", "coord_order"), ("T02", "name_missing")}


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
        extra = {x for x in got if x[0] == "T01"}
        ok = not extra
        if not ok:
            failed += 1
        print(f"  {'PASS' if ok else 'FAIL'}  T01（正常な地物）を検出しない")
        ok = r.returncode == 1
        if not ok:
            failed += 1
        print(f"  {'PASS' if ok else 'FAIL'}  不正データで終了コード 1 を返す")

        total = len(EXPECTED) + 2
        print(f"\n  {total - failed}/{total} 件")
        return 1 if failed else 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
