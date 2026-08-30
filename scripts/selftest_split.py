#!/usr/bin/env python3
"""都道府県分割の逆テスト。

分割は行を落としうる。件数が保たれること、
壊れた入力で黙って進まないことを確かめる。
"""
import csv
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from prefectures import PREF  # noqa: E402
# build_osm.py は末尾が if __name__ == "__main__": main() なので、
# import しても main() は走らない。
from build_osm import split_by_pref  # noqa: E402


def rows_for(codes):
    """(fid, pref, lat, lon, origin, tags, review, note) の並びを作る"""
    return [(f"T{i:03d}", c, "35.0", "139.0", "元データ",
             {"amenity": "clinic", "name": f"施設{i}"}, "", "")
            for i, c in enumerate(codes)]


def features_for(rows):
    return [{"type": "Feature",
             "geometry": {"type": "Point", "coordinates": [139.0, 35.0]},
             "properties": {"ID": r[0]}} for r in rows]


KEYS = ["amenity", "name"]


def case_counts_match():
    """県別の合計が入力と一致する"""
    codes = ["01"] * 3 + ["13"] * 5 + ["47"] * 2
    rows = rows_for(codes)
    with tempfile.TemporaryDirectory() as d:
        n = split_by_pref(rows, features_for(rows), KEYS, d, "hospital")
        if n != 3:
            return False, f"都道府県数が 3 でなく {n}"
        total = 0
        for code, want in (("01", 3), ("13", 5), ("47", 2)):
            path = os.path.join(d, f"{code}_{PREF[code]}_hospital.csv")
            if not os.path.exists(path):
                return False, f"ファイルが無い: {path}"
            with open(path, encoding="utf-8-sig", newline="") as f:
                got = sum(1 for _ in csv.DictReader(f))
            if got != want:
                return False, f"{code} が {want} 件でなく {got} 件"
            total += got
            gj = os.path.join(d, f"{code}_{PREF[code]}_hospital.geojson")
            with open(gj, encoding="utf-8") as f:
                if len(json.load(f)["features"]) != want:
                    return False, f"{code} の geojson が {want} 件でない"
        if total != len(rows):
            return False, f"合計が {len(rows)} 件でなく {total} 件"
    return True, ""


def case_exits(codes):
    """壊れた入力で終了コード1になる。子プロセスで確かめる"""
    script = (
        "import sys, tempfile;"
        f"sys.path.insert(0, {os.path.join(ROOT, 'scripts')!r});"
        "from build_osm import split_by_pref;"
        f"codes = {codes!r};"
        "rows = [(f'T{i}', c, '35.0', '139.0', 'x', {'amenity': 'clinic'}, '', '')"
        " for i, c in enumerate(codes)];"
        "feats = [{'type': 'Feature', 'geometry': None, 'properties': {}} for _ in rows];"
        "d = tempfile.mkdtemp();"
        "split_by_pref(rows, feats, ['amenity'], d, 'hospital')"
    )
    r = subprocess.run([sys.executable, "-c", script],
                       capture_output=True, text=True)
    if r.returncode != 1:
        return False, f"終了コードが 1 でなく {r.returncode}"
    return True, ""


def main():
    cases = [
        ("県別の合計が入力と一致する", case_counts_match),
        ("都道府県コードが空なら落ちる", lambda: case_exits(["01", ""])),
        ("PREF に無いコードなら落ちる", lambda: case_exits(["01", "99"])),
    ]
    print("=== 都道府県分割 逆テスト ===\n")
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
