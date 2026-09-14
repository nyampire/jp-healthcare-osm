#!/usr/bin/env python3
"""OSM 出力の一部を samples/ に複製して、リポジトリで直接読めるようにする。

入力:
  output/osm/<業態>/<県コード>_<県名>_<業態>.csv
  output/osm/<業態>/<県コード>_<県名>_<業態>.geojson

出力:
  samples/<県コード>_<県名>/  上記をそのまま複製したもの

生成物の output/ は .gitignore で追跡していない。全件は圧縮しても100MBを超え、
git は流し直すたびに全体を履歴へ積む。一方で、スクリプトを回せない OSM 編集者が
中身を確かめられないと、データの合意が取れない。

そこで1県だけをリポジトリに置く。GitHub の Web UI は .geojson を地図として、
.csv を表として描くので、読む人はダウンロードもツールも要らない。

既定は高知県（39）。5候補を比べたとき、255文字での短縮と、誤った町字のために
addr:neighbourhood を出さなかった行が、どちらも1件以上あるのは高知県だけだった。
どちらもこのスクリプトが判断を下している箇所で、見てもらう価値がある。

出力の形を変えたら、そのコミットで一緒に流し直す。流し直さないと、古い出力が
「今の出力」として残る。README の古い統計値とは違い、サンプルは当時の記録では
なく現在の見本として読まれるため。

使い方:
  python3 scripts/build_samples.py [--pref 39] [--out-dir output]
"""

import argparse
import csv
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prefectures import PREF  # noqa: E402

SECTORS = [("hospital", "病院"), ("clinic", "診療所"), ("dental", "歯科診療所"),
           ("maternity", "助産所"), ("pharmacy", "薬局")]

DEFAULT_PREF = "39"
SAMPLES_DIR = "samples"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--pref", default=DEFAULT_PREF)
    p.add_argument("--out-dir", default="output")
    args = p.parse_args()

    code = args.pref.zfill(2)
    if code not in PREF:
        sys.exit(f"県コードが不正です: {args.pref}")
    name = PREF[code]
    dest = os.path.join(SAMPLES_DIR, f"{code}_{name}")

    print(f"対象県   : {code} {name}")

    # 先に全ファイルの存在を確かめる。途中で気づくと、古いサンプルと新しい
    # サンプルが混ざった中途半端な状態が samples/ に残る。
    plan = []
    for sector, label in SECTORS:
        for ext in ("csv", "geojson"):
            src = os.path.join(args.out_dir, "osm", sector,
                               f"{code}_{name}_{sector}.{ext}")
            if not os.path.exists(src):
                sys.exit(f"元のファイルがありません: {src}\n"
                         f"先に npm run build を実行してください。")
            plan.append((sector, label, ext, src))

    # 県を変えたときに古い県のファイルが残らないよう、作り直す
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    os.makedirs(dest)

    total = 0
    for sector, label, ext, src in plan:
        dst = os.path.join(dest, os.path.basename(src))
        shutil.copyfile(src, dst)
        size = os.path.getsize(dst)
        total += size
        if ext == "csv":
            with open(dst, encoding="utf-8-sig", newline="") as f:
                n = sum(1 for _ in csv.reader(f)) - 1
            print(f"  {label:<6} {os.path.basename(dst):<28} "
                  f"{n:>6,} 行  {size / 1024:>7,.0f}KB")
        else:
            print(f"  {'':<6} {os.path.basename(dst):<28} "
                  f"{'':>6}     {size / 1024:>7,.0f}KB")

    print(f"\n出力: {dest}/  {len(plan)} ファイル  合計 {total / 1024:,.0f}KB")


if __name__ == "__main__":
    main()
