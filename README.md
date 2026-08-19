# osm-iryo-joho

厚生労働省「医療情報ネット」のオープンデータを、OpenStreetMap で使えるタグへ変換する作業リポジトリです。

## 元データ

2026年6月1日時点 医療情報ネットのオープンデータ（厚生労働省）を使います。

配布元は https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/kenkou_iryou/iryou/newpage_43373.html です。
定義書は [医療情報ネット_オープンデータ定義書（利用者向け）](https://www.mhlw.go.jp/content/11121000/001306376.xlsx) にあります。

対象は5業態 206,043施設です。

| 業態 | ファイル | 施設数 |
|---|---|---:|
| 病院 | `01-1_hospital_facility_info_20260601.csv` / `01-2_hospital_speciality_hours_20260601.csv` | 7,715 |
| 診療所 | `02-1_clinic_facility_info_20260601.csv` / `02-2_clinic_speciality_hours_20260601.csv` | 80,155 |
| 歯科診療所 | `03-1_dental_facility_info_20260601.csv` / `03-2_dental_speciality_hours_20260601.csv` | 54,637 |
| 助産所 | `04_maternity_home_20260601.csv` | 2,138 |
| 薬局 | `05_pharmacy_20260601.csv` | 61,398 |

元データと生成物はこのリポジトリに含めていません。
合計約500MBあり、うち2ファイルは GitHub の100MB制限を超えるためです。
配布元から取得してリポジトリ直下に置き、`npm run all` を実行すれば `output/` に再現できます。

## ライセンスと出典

元データには公共データ利用規約（第1.0版）(PDL1.0) が適用されています。

> 本利用ルールは、クリエイティブ・コモンズ・ライセンスの表示4.0国際ライセンスに
> 規定される著作権利用許諾条件（CC BY）と互換性があります。
>
> [公共データ利用規約（第1.0版）](https://www.digital.go.jp/resources/open_data/public_data_license_v1.0)

`output/` に出力されるデータは、上記データを編集、加工したものです。

出典は厚生労働省「医療情報ネットのオープンデータ」（2026年6月1日時点）
https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/kenkou_iryou/iryou/newpage_43373.html です。
加工者は本リポジトリの管理者です。
加工内容は、営業時間の `opening_hours` 形式への変換、診療科目コードの
`healthcare:speciality` への対応付け、名称の正規化です。
詳細は各スクリプト冒頭に書いています。

PDL1.0 は「編集・加工した情報を、あたかも国又は府省等が作成した未加工のままであるかの
ような態様で公表・利用してはいけません」と定めています。
生成物を再配布する際は、加工済みである旨と加工者を明示してください。

スクリプトと対応表など、このリポジトリで作成した部分は CC0 とします。

## 解説

元データの構造と品質は [docs/data.md](docs/data.md) に書いています。
業態ごとの違い、フラグの論理が列名と逆になる点、実データに含まれる誤入力の傾向を扱います。

変換処理の設計と、各判断の根拠となる実測値は [docs/processing.md](docs/processing.md) にあります。

## 使い方

```bash
npm install
npm run all
```

`npm run all` は生成、逆テスト、検証を通しで実行します。
業態を絞るときは `npm run build:pharmacy` や `npm run validate:dental` のように指定します。

## 生成するタグ

| タグ | 対象業態 | 生成数 |
|---|---|---:|
| `opening_hours` | 全業態 | 199,456 |
| `healthcare:speciality` | 病院、診療所、歯科診療所 | 142,507 |
| `name` / `official_name` / `short_name` | 全業態 | 206,043 |
| `name:ja-Hira` | 全業態 | 158,358 |
| `name:ja-Latn` | 全業態 | 79,122 |
| `name:en` | 全業態 | 83,552 |

## 構成

```
scripts/
  build_opening_hours.py     曜日フラグと時刻から opening_hours を組み立てる
  build_speciality.py        診療科目コードを healthcare:speciality へ対応付ける
  build_names.py             名称を正規化し name 系のタグを作る
  validate_opening_hours.js  OSM の参照実装 opening_hours.js で全件検証する
  validate_speciality.py     語彙、書式、タグ値長を検証する
  validate_names.py          法人格の残留やかな変換漏れを検証する
  selftest.js                検証器そのものの逆テスト
mapping/
  speciality_mapping.csv     診療科目コード126種から OSM 値への対応表
  speciality_rollup.csv      タグ値255文字を超えたときの畳み先
  name_entity_prefixes.csv   法人格と運営主体の先頭パターン
  name_entity_suffixes.csv   法人名トークンの接尾辞
  name_facility_words.csv    施設種別語
tests/
  known_bad.csv              検証器の逆テスト用フィクスチャ
```

判断を含む対応付けはスクリプトに埋め込まず、`mapping/` の CSV に外出ししています。
書き換えて再実行すれば出力が変わります。
各表の「備考」列に、対応値が無いものや判断に迷った点を記録しています。

## 出力

`output/` に業態ごとの CSV を生成します。
元データの列は書き換えず、変換後の値は別列として持ちます。
除外や保留をした行は理由とともに全件が一覧に残るので、第三者が対比して検証できます。

| ファイル | 内容 |
|---|---|
| `<業態>_opening_hours.csv` | opening_hours と要確認フラグ、備考 |
| `<業態>_names.csv` | 元の名称列と name 系タグ |
| `<業態>_speciality.csv` | healthcare:speciality と丸めた診療科の内訳 |
| `<業態>_excluded.csv` | opening_hours から除外した区間の全件 |
| `<業態>_conflicts.csv` | 曜日フラグと時刻が矛盾する行と、採用した判断 |
| `<業態>_emergency.csv` | 救急科の診療時間（外来とは別枠） |
| `*_validation.csv` | 検証で検出した項目 |

## OSM へのインポートについて

このリポジトリは変換までを扱います。
実際に OSM へ投入する場合は
[Import Guidelines](https://wiki.openstreetmap.org/wiki/JA:Import/Guidelines) に沿って
imports メーリングリストでの合意形成が必要です。

未解決の課題は次の3点です。

座標が `0.0, 0.0` の欠損レコードがあります（病院票で268件、北海道31%、沖縄48%と地域偏在）。
測地系が定義書に記載されておらず未確定です。
`healthcare:speciality` に対応値が無い診療科があります（乳腺外科973施設、心療内科1,097施設ほか）。
