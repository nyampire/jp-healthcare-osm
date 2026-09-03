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

スクリプトと対応表など、このリポジトリで作成した部分は MIT ライセンスです。
全文は [LICENSE](LICENSE) にあります。
`output/` に生成されるデータには適用されません。
生成物は元データを編集、加工したものなので、上記の PDL1.0 に従います。

## 解説

元データの構造と品質は [docs/data.md](docs/data.md) に書いています。
業態ごとの違い、フラグの論理が列名と逆になる点、実データに含まれる誤入力の傾向を扱います。

変換処理の設計と、各判断の根拠となる実測値は [docs/processing.md](docs/processing.md) にあります。

座標が `0.0, 0.0` の16,243件をジオコーディングで補完できるかの調査は
[docs/geocoding-investigation.md](docs/geocoding-investigation.md) にあります。
結論は出ておらず、未解決の問いと再現手順を残した引き継ぎ用の記録です。

出力した座標が実際にその施設を指しているかの検算は
[docs/coord-verification.md](docs/coord-verification.md) にあります。
3つの方法の実測値と、それぞれが届かない範囲を書いています。
検算は `npm run verify:coords:addr` と `npm run verify:coords:osm` で実行します。
前者は外部への通信がなく、後者は日本全体の `.osm.pbf` と `osmium` が要ります。

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
設定は必須で、未設定なら `build_addr.js` が終了コード2で落ちます。
公開 API を指した場合も落とします。
公開 API が配信しているデータは手元に構築したものより古く、
20万件の問い合わせは相手にも負荷をかけるためです。
`japanese-addresses-v2` を手元に構築して指してください。
構築の手順は `vendor/nja-osm-tags/docs/local-mirror.md` にあります。

```bash
export NJA_API_BASE=/path/to/japanese-addresses-v2/out/api/ja
```

`npm run all` は生成、逆テスト、検証を通しで実行します。
業態を絞るときは `npm run build:pharmacy` や `npm run validate:dental` のように指定します。

## 生成するタグ

| タグ | 対象業態 | 生成数 |
|---|---|---:|
| `amenity` | 助産所以外 | 194,871 |
| `healthcare` | 全業態 | 196,679 |
| `name` / `official_name` | 全業態 | 196,679 |
| `short_name` | 略称のある業態 | 95,230 |
| `name:ja-Hira` | 全業態 | 150,773 |
| `name:ja-Latn` | 全業態 | 76,199 |
| `name:en` | 全業態 | 81,588 |
| `opening_hours` | 全業態 | 190,824 |
| `healthcare:speciality` | 病院、診療所、歯科診療所 | 137,360 |
| `website` | 全業態 | 122,080 |
| `addr:full` | 全業態 | 196,679 |
| `addr:country` | 全業態 | 196,679 |
| `addr:province` | 全業態 | 196,679 |
| `addr:county` | 郡がある住所 | 11,633 |
| `addr:city` | 全業態 | 196,667 |
| `addr:suburb` | 政令指定都市の区など | 47,622 |
| `addr:quarter` | 町字の下に区分がある住所 | 8,599 |
| `addr:neighbourhood` | 全業態 | 193,055 |
| `addr:block_number` | 住居表示の明細と照合できた行 | 88,113 |
| `addr:housenumber` | 住居表示の明細と照合できた行 | 88,113 |
| `beds` | 病院、診療所 | 11,677 |
| `source` | 全業態 | 196,679 |

`ref` 系のタグは付けていません。
医療情報ネットの ID を OSM のどのキーで持つかは合意が要るため、`ID` 列を残すに留めています。

`note` と `fixme` もタグにしていません。
住所のうち解釈できなかった残余（66,251件）と、番地の要素が3つ以上あった申し送り
（3,640件）は、`<業態>_osm.csv` の末尾の非タグ列と MapRoulette のタスクに載せ、
作業者に見せます。

タグにしない理由は、中身が入力住所から導けるためです。
病院データで測ると、`note` が付いた1,482件のうち1,384件（93.4%）は正規化すれば
元の住所文字列の部分文字列で、全件がパースの止まった位置で一致しました。
価値があるのは中身ではなく「入力のどこを解釈できなかったか」という指し示しのほうで、
それは作業者に見せる経路があれば足ります。元の住所は `addr:full` に載るので
あとから参照もできます。詳細は上流の
[nja-osm-tags Issue 5](https://github.com/nyampire/nja-osm-tags/issues/5) にあります。

## 処理の流れ

業態ごとに4段階で下ごしらえし、全業態が揃ってから座標を直し、最後に結合します。

```
1. build_opening_hours.py  曜日フラグと時刻から opening_hours を組み立てる
2. build_speciality.py     診療科目コードを healthcare:speciality へ対応付ける
3. build_names.py          名称を正規化し name 系のタグを作る
4. build_addr.js           住所を addr:* に構造化し、座標が無い施設を補完する
                           番地が推定になった行は番地だけの住所で照合し直す
--- ここまで業態ごと。以降は全業態が揃ってから ---
5. fix_placeholder_coords.js  元データが穴埋めに入れた座標を捨てる
6. build_osm.py            以上を ID で結合し、CSV と GeoJSON を出す
```

5 は都道府県庁の代表点のように、複数の市区町村の施設が共有している座標を探します。
業態をまたいで数えないと見つからないので、1 から 4 とは別の段にしてあります。

4 は住所データを参照します。
取得先は環境変数 `NJA_API_BASE` で指定し、手元に構築したデータを指していなければ落ちます。
全国のデータを手元に置いた環境では、全業態の生成と逆テストと検証が通しで14分でした。

## 構成

```
scripts/
  build_opening_hours.py     曜日フラグと時刻から opening_hours を組み立てる
  build_speciality.py        診療科目コードを healthcare:speciality へ対応付ける
  build_names.py             名称を正規化し name 系のタグを作る
  build_addr.js              住所を addr:* に構造化し、座標が無い施設を補完する
  addr_columns.js            住所と座標を出力列に畳む純関数
  fix_placeholder_coords.js  元データが穴埋めに入れた座標を捨てる
  build_osm.py               各タグを結合し CSV と GeoJSON を出す
  build_maproulette.py       MapRoulette のタスクファイルを出す
  build_pref_bbox.js         都道府県の外接矩形の表を nja から生成する
  build_speciality_doc.py    対応表から docs/speciality-mapping.md を生成する
  validate_opening_hours.js  OSM の参照実装 opening_hours.js で全件検証する
  validate_speciality.py     語彙、書式、タグ値長を検証する
  validate_names.py          法人格の残留やかな変換漏れを検証する
  validate_osm.py            座標の範囲と順序、タグの形式を検証する
  selftest.js                opening_hours 検証器の逆テスト
  selftest_addr.js           住所の列を畳む純関数の逆テスト
  selftest_placeholder.js    穴埋めの座標を見分ける処理の逆テスト
  selftest_osm.py            OSM 出力検証器の逆テスト
mapping/
  speciality_mapping.csv     診療科目コード127種から OSM 値への対応表
  speciality_rollup.csv      タグ値255文字を超えたときの畳み先
  facility_tags.csv          業態から amenity と healthcare への対応
  name_entity_prefixes.csv   法人格と運営主体の先頭パターン
  name_entity_suffixes.csv   法人名トークンの接尾辞
  name_facility_words.csv    施設種別語
  pref_bbox.csv              都道府県の外接矩形。県外を指す座標の判定に使う
tests/
  known_bad.csv              opening_hours 検証器の逆テスト用フィクスチャ
  known_bad_osm.csv          OSM 出力検証器の逆テスト用フィクスチャ
  known_bad_osm.geojson      同上
  known_bad_addr.csv         住所の列を畳む純関数の逆テスト用フィクスチャ
  known_bad_placeholder.csv  穴埋めの座標の逆テスト用フィクスチャ
  known_bad_placeholder_2.csv  同上。業態をまたぐ共有を作るための2つ目
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

`output/` は役割ごとに分かれています。

| ディレクトリ | 中身 |
| --- | --- |
| `osm/<業態>/` | OSM 向けの成果物。全国1ファイルと、都道府県別のファイル |
| `build/` | 途中経過。`build_osm.py` の入力 |
| `reports/` | 検証結果と、除外・重複などの調査用ファイル |
| `maproulette/` | MapRoulette 向けのタスク（`npm run maproulette` で作る） |

都道府県別のファイルは `{コード}_{県名}_{業態}` の名前です。
`osm/hospital/13_東京都_hospital.csv` のようになります。

投入に使うのは次の2つです。

| ファイル | 内容 |
|---|---|
| `osm/<業態>/<業態>_osm.geojson` | 結合済みの点データ（全国）。JOSM で開ける |
| `osm/<業態>/<業態>_osm.csv` | 同じ内容の一覧（全国）。表計算ソフトで確認する用 |

MapRoulette を使う場合は `output/maproulette/` に別形式で出します。

```bash
npm run maproulette
```

都道府県ごとに分割した line-by-line GeoJSON を、233チャレンジ196,679タスク分出力します。
`index.csv` にチャレンジの一覧と件数が入ります。

途中の生成物と検証材料は次のとおりです。

| ファイル | 内容 |
|---|---|
| `build/<業態>_geocoded.csv` | 座標と住所。元の値、付与した値、住所から得た点、出典、精度レベル |
| `build/<業態>_names.csv` | 元の名称列と name 系タグ |
| `build/<業態>_opening_hours.csv` | opening_hours と要確認フラグ、備考 |
| `build/<業態>_speciality.csv` | healthcare:speciality と丸めた診療科の内訳 |
| `reports/<業態>_excluded.csv` | opening_hours から除外した区間の全件 |
| `reports/<業態>_conflicts.csv` | 曜日フラグと時刻が矛盾する行と、採用した判断 |
| `reports/<業態>_emergency.csv` | 救急科の診療時間（外来とは別枠） |
| `reports/*_validation.csv` | 検証で検出した項目 |

## 現在の到達点

206,043施設のうち196,680件を出力しています。

| 業態 | 施設数 | 出力 | 座標が元データ | 座標を付与 | 座標なしで除外 |
|---|---:|---:|---:|---:|---:|
| 病院 | 7,715 | 7,526 | 7,436 | 90 | 189 |
| 診療所 | 80,155 | 77,188 | 75,040 | 2,148 | 2,967 |
| 歯科診療所 | 54,637 | 52,647 | 51,281 | 1,366 | 1,990 |
| 助産所 | 2,138 | 1,808 | 1,663 | 145 | 330 |
| 薬局 | 61,398 | 57,511 | 53,975 | 3,536 | 3,887 |
| 合計 | 206,043 | 196,680 | 189,395 | 7,285 | 9,363 |

「座標を付与」7,285件のうち297件は、元データに座標がありながら
ジオコーダ座標から1km以上離れていたため、ジオコーダ座標を採ったものです。
さらに7件は、元データの座標が住所の都道府県ではなく別の都道府県の範囲に
落ちていたため、住所から求めた点に差し替えたものです。
判定の条件は [docs/processing.md](docs/processing.md) の
「元データの座標がジオコーダ座標から離れている場合」と
「住所の県ではない県を指す座標」にまとめています。
捨てた元データの座標は `備考` に書くので、作業者が値を見て判断できます。
1kmの規則、県外の規則、穴埋めの規則で捨てた405件が対象です。

除外した9,363件の内訳は、地番方式の住所が5,187件、位置レベルが足りないものが4,176件です。

致命的な検証項目は全業態で0件です。
`addr_note_chiban` は18,684件を検出していますが、これは欠陥ではなく人手での確認を促す申し送りです。
逆テストは8つのファイルに合計113件あり、すべて通ります（`npm run selftest`）。

## OSM へのインポートについて

このリポジトリは変換までを扱います。
実際に OSM へ投入する場合は
[Import Guidelines](https://wiki.openstreetmap.org/wiki/JA:Import/Guidelines) に沿って
imports メーリングリストでの合意形成が必要です。

wiki に掲載するデータソース解説ページの下書きを
[docs/wiki-iryo-joho-ja.md](docs/wiki-iryo-joho-ja.md) に用意しています。
元データの内容と利用上の注意を、これから使う人向けにまとめたものです。

住所と番地の扱いはサブページに分けて
[docs/wiki-iryo-joho-ja-addr.md](docs/wiki-iryo-joho-ja-addr.md) に置いています。
番地の根拠の3分類、住居表示台帳と突き合わせた結果、確かめられない範囲をまとめたものです。

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

番地を `推定` で付けた行は出力しません。
町字までは台帳で住居表示実施済みと分かっていますが、番地は入力文字列を機械的に切ったもので、
住居表示台帳と突き合わせられた8,219件のうち番地が実在したのは33.9%でした。
街区符号が100を超える545件は正解が0件です。
判定と根拠は [docs/processing.md](docs/processing.md) の「推定を台帳と突き合わせた」にまとめています。

`healthcare:speciality` に対応値が無い診療科があります。
心療内科5,565施設は `psychiatry` に、乳腺外科1,750施設は `surgery` に丸めています。
論点は [docs/speciality-mapping.md](docs/speciality-mapping.md) の末尾にまとめています。

データ側で残っている課題が4つあります。

座標が `0.0, 0.0` の16,243件のうち、9,266件は補完していません。
これに、元データが穴埋めに入れた座標を捨てて住所からも補えなかった98件が加わり、座標を持たない施設は9,364件です。
5,187件は地番方式の住所です。
地番のデータを参照して得た座標はライセンス上出力できないため、補完の対象から外しています。
残る4,177件は位置レベルが3以下で、建物から数百メートルずれるため採用していません。

`推定` の番地28,120件を出力していません。
住居表示台帳と突き合わせられた8,219件のうち、番地が実在したのは33.9%でした。
施設と `addr:full` は残るので情報は失われませんが、
外した番地を `note` に出すかは上流の Issue 5 の結論待ちです。
詳細は [docs/processing.md](docs/processing.md) の「推定を台帳と突き合わせた」にあります。

`note` に住所の未解釈部分が66,251件残っています。
うち18,684件は数字で始まり、住居表示を実施していない町字で地番が残ったものが多くを占めます。
残りは建物名や階や部屋番号で、`addr:housename` や `addr:floor` に移せる可能性があります。
投入前に分割の方針を決める必要があります。

ジオコーディングで位置レベル8に届かない原因が未解明です。
参照データの有無では説明できない事例があり、
[docs/geocoding-investigation.md](docs/geocoding-investigation.md) に引き継ぎ用の記録を残しています。
