# jp-healthcare-osm

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

座標が `0.0, 0.0` の16,243件をジオコーディングで補完できるかの調査は
[docs/geocoding-investigation.md](docs/geocoding-investigation.md) にあります。
結論は出ておらず、未解決の問いと再現手順を残した引き継ぎ用の記録です。

診療科目コードと `healthcare:speciality` の対応は
[docs/speciality-mapping.md](docs/speciality-mapping.md) に一覧があります。
127コードすべてと、どの診療科がどの値に集まるかの逆引きを載せています。

## 使い方

```bash
git submodule update --init
npm install
npm run all
```

住所の構造化は `vendor/nja-osm-tags` が行うので、submodule の取得が要ります。
`nja-osm-tags` は型ストリッピングで TypeScript を直接実行するため、Node.js v26 以上が必要です。

住所データの取得先は環境変数 `NJA_API_BASE` で指定します。
未設定なら Geolonia の公開 API を読みますが、20万件を通すと1件ごとにリクエストが出ます。
手元に `japanese-addresses-v2` を構築して指すほうが速く、公開 API への負荷もかかりません。
構築の手順は `vendor/nja-osm-tags/docs/local-mirror.md` にあります。

```bash
export NJA_API_BASE=/path/to/japanese-addresses-v2/out/api/ja
```

`npm run all` は生成、逆テスト、検証を通しで実行します。
業態を絞るときは `npm run build:pharmacy` や `npm run validate:dental` のように指定します。

## 生成するタグ

| タグ | 対象業態 | 生成数 |
|---|---|---:|
| `amenity` | 助産所以外 | 194,712 |
| `healthcare` | 全業態 | 196,500 |
| `name` / `official_name` | 全業態 | 196,500 |
| `short_name` | 略称のある業態 | 95,231 |
| `name:ja-Hira` | 全業態 | 150,634 |
| `name:ja-Latn` | 全業態 | 76,140 |
| `name:en` | 全業態 | 81,579 |
| `opening_hours` | 全業態 | 190,657 |
| `healthcare:speciality` | 病院、診療所、歯科診療所 | 137,307 |
| `website` | 全業態 | 122,009 |
| `addr:full` | 全業態 | 196,500 |
| `addr:country` | 全業態 | 196,500 |
| `addr:province` | 全業態 | 196,500 |
| `addr:county` | 郡がある住所 | 11,648 |
| `addr:city` | 全業態 | 196,488 |
| `addr:suburb` | 政令指定都市の区など | 47,500 |
| `addr:quarter` | 町字の下に区分がある住所 | 8,609 |
| `addr:neighbourhood` | 全業態 | 192,874 |
| `addr:block_number` | 住居表示を実施した区域 | 113,657 |
| `addr:housenumber` | 住居表示を実施した区域 | 112,475 |
| `note` | 住所に未解釈の部分が残った施設 | 66,005 |
| `fixme` | 番地の要素が3つ以上ある施設 | 3,364 |
| `beds` | 病院、診療所 | 11,680 |
| `source` | 全業態 | 196,500 |

`ref` 系のタグは付けていません。
医療情報ネットの ID を OSM のどのキーで持つかは合意が要るため、`ID` 列を残すに留めています。

## 処理の流れ

業態ごとに5段階で処理します。

```
1. build_opening_hours.py  曜日フラグと時刻から opening_hours を組み立てる
2. build_speciality.py     診療科目コードを healthcare:speciality へ対応付ける
3. build_names.py          名称を正規化し name 系のタグを作る
4. build_addr.js           住所を addr:* に構造化し、座標が無い施設を補完する
5. build_osm.py            以上を ID で結合し、CSV と GeoJSON を出す
```

4 は住所データを参照します。
既定では Geolonia の公開 API を読みますが、20万件を通すなら手元にデータを構築して
環境変数 `NJA_API_BASE` で指すほうが現実的です。
全国のデータを手元に置いた環境では、全業態の生成と逆テストと検証が通しで14分でした。

## 構成

```
scripts/
  build_opening_hours.py     曜日フラグと時刻から opening_hours を組み立てる
  build_speciality.py        診療科目コードを healthcare:speciality へ対応付ける
  build_names.py             名称を正規化し name 系のタグを作る
  build_addr.js              住所を addr:* に構造化し、座標が無い施設を補完する
  addr_columns.js            住所と座標を出力列に畳む純関数
  build_osm.py               各タグを結合し CSV と GeoJSON を出す
  build_maproulette.py       MapRoulette のタスクファイルを出す
  build_speciality_doc.py    対応表から docs/speciality-mapping.md を生成する
  validate_opening_hours.js  OSM の参照実装 opening_hours.js で全件検証する
  validate_speciality.py     語彙、書式、タグ値長を検証する
  validate_names.py          法人格の残留やかな変換漏れを検証する
  validate_osm.py            座標の範囲と順序、タグの形式を検証する
  selftest.js                opening_hours 検証器の逆テスト
  selftest_addr.js           住所の列を畳む純関数の逆テスト
  selftest_osm.py            OSM 出力検証器の逆テスト
mapping/
  speciality_mapping.csv     診療科目コード127種から OSM 値への対応表
  speciality_rollup.csv      タグ値255文字を超えたときの畳み先
  facility_tags.csv          業態から amenity と healthcare への対応
  name_entity_prefixes.csv   法人格と運営主体の先頭パターン
  name_entity_suffixes.csv   法人名トークンの接尾辞
  name_facility_words.csv    施設種別語
tests/
  known_bad.csv              opening_hours 検証器の逆テスト用フィクスチャ
  known_bad_osm.csv          OSM 出力検証器の逆テスト用フィクスチャ
  known_bad_osm.geojson      同上
  known_bad_addr.csv         住所の列を畳む純関数の逆テスト用フィクスチャ
vendor/
  nja-osm-tags/              住所を addr:* に変換する submodule
```

判断を含む対応付けはスクリプトに埋め込まず、`mapping/` の CSV に外出ししています。
書き換えて再実行すれば出力が変わります。
各表の「備考」列に、対応値が無いものや判断に迷った点を記録しています。

## 出力

`output/` に業態ごとのファイルを生成します。
元データの列は書き換えず、変換後の値は別列として持ちます。
除外や保留をした行は理由とともに全件が一覧に残るので、第三者が対比して検証できます。

投入に使うのは次の2つです。

| ファイル | 内容 |
|---|---|
| `<業態>_osm.geojson` | 結合済みの点データ。JOSM で開ける |
| `<業態>_osm.csv` | 同じ内容の一覧。表計算ソフトで確認する用 |

MapRoulette を使う場合は `output/maproulette/` に別形式で出します。

```bash
npm run maproulette
```

都道府県ごとに分割した line-by-line GeoJSON を、233チャレンジ196,500タスク分出力します。
`index.csv` にチャレンジの一覧と件数が入ります。

途中の生成物と検証材料は次のとおりです。

| ファイル | 内容 |
|---|---|
| `<業態>_geocoded.csv` | 座標と住所。元の値、付与した値、出典、精度レベル |
| `<業態>_names.csv` | 元の名称列と name 系タグ |
| `<業態>_opening_hours.csv` | opening_hours と要確認フラグ、備考 |
| `<業態>_speciality.csv` | healthcare:speciality と丸めた診療科の内訳 |
| `<業態>_excluded.csv` | opening_hours から除外した区間の全件 |
| `<業態>_conflicts.csv` | 曜日フラグと時刻が矛盾する行と、採用した判断 |
| `<業態>_emergency.csv` | 救急科の診療時間（外来とは別枠） |
| `*_validation.csv` | 検証で検出した項目 |

## 現在の到達点

206,043施設のうち196,500件を出力しています。

| 業態 | 施設数 | 出力 | 座標が元データ | 座標を付与 | 座標なしで除外 |
|---|---:|---:|---:|---:|---:|
| 病院 | 7,715 | 7,527 | 7,447 | 80 | 188 |
| 診療所 | 80,155 | 77,142 | 75,190 | 1,952 | 3,013 |
| 歯科診療所 | 54,637 | 52,638 | 51,384 | 1,254 | 1,999 |
| 助産所 | 2,138 | 1,788 | 1,684 | 104 | 350 |
| 薬局 | 61,398 | 57,405 | 54,095 | 3,310 | 3,993 |
| 合計 | 206,043 | 196,500 | 189,800 | 6,700 | 9,543 |

除外した9,543件の内訳は、地番方式の住所が5,143件、位置レベルが足りないものが4,400件です。

致命的な検証項目は全業態で0件です。
`addr_note_chiban` は18,425件を検出していますが、これは欠陥ではなく人手での確認を促す申し送りです。
逆テストは opening_hours が10件、住所の列が6件、OSM 出力が8件で、すべて通ります。

## OSM へのインポートについて

このリポジトリは変換までを扱います。
実際に OSM へ投入する場合は
[Import Guidelines](https://wiki.openstreetmap.org/wiki/JA:Import/Guidelines) に沿って
imports メーリングリストでの合意形成が必要です。

wiki に掲載するデータソース解説ページの下書きを
[docs/wiki-iryo-joho-ja.md](docs/wiki-iryo-joho-ja.md) に用意しています。
元データの内容と利用上の注意を、これから使う人向けにまとめたものです。

wiki に掲載するインポート計画の下書きを
[docs/import-plan.md](docs/import-plan.md) に用意しています。
Import Guidelines が求める項目に沿って書いており、記入が必要な箇所には印を付けています。

合意で決めるべき項目が4つあります。

`ref` 系のタグをどのキーで持つか決まっていません。
医療情報ネットの ID を保持できると更新への追随や重複の判定に使えますが、
キーの命名は勝手に決められません。

診療所の `amenity` が暫定です。
病床数が空欄の31,399件を無床とみなして `doctors` に寄せており、73,809件が推定に該当します。
一律 `clinic` にする案もあります。

番地を `推定` で付けた30,931件を投入するかが決まっていません。
町字までは台帳で住居表示実施済みと分かっていますが、番地は入力文字列を機械的に切ったもので、
実在する組み合わせかは確認していません。
元の所在地が地番の書き方をしているものが1,587件、街区符号が100を超えるものが1,351件あり、
誤りが混ざっています。
根拠は `番地の根拠` 列で機械的に絞れます。
判定と絞り方は [docs/processing.md](docs/processing.md) の「番地の根拠」にまとめています。

`healthcare:speciality` に対応値が無い診療科があります。
心療内科5,565施設は `psychiatry` に、乳腺外科1,750施設は `surgery` に丸めています。
論点は [docs/speciality-mapping.md](docs/speciality-mapping.md) の末尾にまとめています。

データ側で残っている課題が3つあります。

座標が `0.0, 0.0` の16,243件のうち、9,543件は補完していません。
5,143件は地番方式の住所です。
地番のデータを参照して得た座標はライセンス上出力できないため、補完の対象から外しています。
残る4,400件は位置レベルが3以下で、建物から数百メートルずれるため採用していません。

`note` に住所の未解釈部分が66,005件残っています。
うち18,425件は数字で始まり、住居表示を実施していない町字で地番が残ったものが多くを占めます。
残りは建物名や階や部屋番号で、`addr:housename` や `addr:floor` に移せる可能性があります。
投入前に分割の方針を決める必要があります。

ジオコーディングで位置レベル8に届かない原因が未解明です。
参照データの有無では説明できない事例があり、
[docs/geocoding-investigation.md](docs/geocoding-investigation.md) に引き継ぎ用の記録を残しています。
