# 診療科目コードと healthcare:speciality の対応

`mapping/speciality_mapping.csv` の内容を読みやすくしたものです。
この文書は対応表から生成しています。
対応表を直したら `python3 scripts/build_speciality_doc.py` で作り直してください。

変換処理の考え方は [processing.md](processing.md) を参照してください。

## 対応の確度

各行には対応の確からしさを付けています。

- `exact` は、OSM 側に対応する値があるものです（73件）。
- `broader` は、対応する値が無く、上位概念に丸めたものです（54件）。

`broader` は情報が粗くなります。
なぜ丸めたかを備考に書いているので、値を見直すときの手がかりにしてください。

## 値から見た一覧

ひとつの OSM 値に複数の診療科が集まる場合があります。
どこで情報が粗くなっているかは、この向きで見ると分かります。

左の列は、その OSM 値が本来指す診療科です（確度 `exact`）。
右の列は、対応する値が無いため、やむを得ずその値へ寄せた診療科です（確度 `broader`）。
右の列に入った診療科は、OSM 側では左の列の診療科と区別が付きません。

たとえば `gastroenterology` の行はこう読みます。
消化器内科と胃腸内科は、この値が本来指す診療科です。
内視鏡内科には対応する値が無いため、この値へ寄せました。
その結果、内視鏡内科だけを持つ施設と消化器内科を持つ施設は、
タグの上では同じ `gastroenterology` になります。

右の列が空の行は、寄せた診療科が無く、情報が粗くなっていません。

| healthcare:speciality | 本来指す診療科 | 寄せた診療科 |
|---|---|---|
| `abdominal_surgery` | 腹部外科 | 消化器外科、消化器・移植外科、胃腸外科、肝臓外科、膵臓外科、胆のう外科、肝臓・胆のう・膵臓外科 |
| `otolaryngology` | 耳鼻いんこう科、気管食道・耳鼻いんこう科、頭頸部・耳鼻いんこう科、耳鼻咽喉科・頭頸部外科 | 気管食道内科、気管食道外科、頭頸部外科、小児耳鼻いんこう科 |
| `surgery` | 外科 | 食道外科、乳腺外科、乳腺・内分泌外科、女性乳腺外科、内視鏡外科、移植・内視鏡外科、その他（外科系） |
| `urology` | 皮膚泌尿器科、泌尿器科、腎臓・泌尿器科 | 腎臓外科、小児泌尿器科、男性泌尿器科、神経泌尿器科、女性泌尿器科 |
| `endocrinology` | 糖尿病内科、内分泌内科、糖尿病・内分泌内科、糖尿病・代謝内科、代謝・内分泌内科 | 代謝内科、脂質代謝内科 |
| `paediatrics` | 小児科 | 小児眼科、小児耳鼻いんこう科、小児皮膚科、小児泌尿器科、小児神経科 |
| `cardiothoracic_surgery` | 心臓外科、心臓血管外科 | 呼吸器外科、循環器外科、胸部外科 |
| `dermatology` | 皮膚科、皮膚泌尿器科 | 小児皮膚科、美容皮膚科、皮膚腫瘍科 |
| `gynaecology` | 産婦人科、産科、婦人科、産婦人科（生殖医療） | 女性診療科 |
| `psychiatry` | 精神科、老年精神科 | 神経科、心療内科、老年心療内科 |
| `geriatrics` | 老年・呼吸器内科、老年内科、老年精神科 | 老年心療内科 |
| `oncology` | 血液・腫瘍内科、腫瘍内科 | 腫瘍外科、小児腫瘍外科 |
| `anaesthetics` | 麻酔科 | ペインクリニック内科、ペインクリニック外科 |
| `cardiology` | 循環器内科、心臓内科、心臓血管内科 |  |
| `gastroenterology` | 消化器内科、胃腸内科 | 内視鏡内科 |
| `internal` | 内科 | 女性内科、インフルエンザ |
| `neurosurgery` | 脳神経外科、脳外科 | 脳・血管外科 |
| `ophthalmology` | 眼科 | 小児眼科、神経眼科 |
| `palliative` | 緩和ケア内科 | 疼痛緩和内科、緩和ケア外科 |
| `proctology` | 肛門外科、大腸・肛門外科 | 大腸外科 |
| `transplant` | 移植外科 | 消化器・移植外科、移植・内視鏡外科 |
| `allergology` | アレルギー疾患内科、アレルギー科 |  |
| `dental_oral_maxillo_facial_surgery` | 歯科口腔外科 | 口腔腫瘍外科 |
| `haematology` | 血液・腫瘍内科、血液内科 |  |
| `nephrology` | 腎臓内科、腎臓・泌尿器科 |  |
| `neurology` | 脳神経内科、神経内科 |  |
| `orthodontics` | 矯正歯科、小児矯正歯科 |  |
| `paediatric_dentistry` | 小児歯科、小児矯正歯科 |  |
| `paediatric_surgery` | 小児外科 | 小児腫瘍外科 |
| `plastic_surgery` | 形成外科 | 美容外科 |
| `pulmonology` | 呼吸器内科、老年・呼吸器内科 |  |
| `radiotherapy` | 放射線治療科、腫瘍放射線科 |  |
| `child_psychiatry` | 児童精神科 |  |
| `clinical_pathology` | 臨床検査科 |  |
| `dentistry` | 歯科 |  |
| `diagnostic_radiology` | 放射線診断科 |  |
| `dialysis` | 人工透析内科 |  |
| `emergency` | 救急科 |  |
| `fertility` | 産婦人科（生殖医療） |  |
| `general` |  | 総合診療科 |
| `hepatology` | 肝臓内科 |  |
| `infectious_diseases` | 感染症内科 |  |
| `neonatology` | 新生児内科 |  |
| `neuropsychiatry` |  | 神経精神科 |
| `orthopaedics` | 整形外科 |  |
| `pathology` | 病理診断科 |  |
| `physiatry` | リハビリテーション科 |  |
| `radiology` | 放射線科 |  |
| `rheumatology` | リウマチ科 |  |
| `traditional_chinese_medicine` |  | 漢方内科 |
| `vascular_surgery` | 血管外科 |  |
| `venereology` | 性感染症内科 |  |

## コードから見た一覧

施設数は、その診療科を持つ施設の数です。
同じ施設が複数の診療科を持つため、合計は施設総数と一致しません。

### 01 内科系

| コード | 診療科目名 | healthcare:speciality | 確度 | 病院 | 診療所 | 歯科 | 備考 |
|---|---|---|---|---:|---:|---:|---|
| `01001` | 内科 | `internal` | exact | 6,698 | 45,814 | 41 |  |
| `01002` | 感染症内科 | `infectious_diseases` | exact | 223 | 304 |  |  |
| `01003` | 性感染症内科 | `venereology` | exact | 3 | 217 |  |  |
| `01004` | 血液・腫瘍内科 | `haematology;oncology` | exact | 84 | 54 |  |  |
| `01005` | 血液内科 | `haematology` | exact | 733 | 324 | 1 |  |
| `01006` | 糖尿病内科 | `endocrinology` | exact | 974 | 3,012 | 1 | wikiの定義が「Endocrinology and Diabetes Mellitus」で糖尿病を含む |
| `01007` | 代謝内科 | `endocrinology` | broader | 94 | 349 |  |  |
| `01008` | 内分泌内科 | `endocrinology` | exact | 240 | 799 | 1 |  |
| `01009` | 脂質代謝内科 | `endocrinology` | broader | 19 | 468 | 1 |  |
| `01010` | 糖尿病・内分泌内科 | `endocrinology` | exact | 506 | 888 | 1 |  |
| `01011` | 糖尿病・代謝内科 | `endocrinology` | exact | 237 | 814 | 1 |  |
| `01012` | 代謝・内分泌内科 | `endocrinology` | exact | 146 | 332 |  |  |
| `01013` | 脳神経内科 | `neurology` | exact | 1,240 | 807 |  |  |
| `01014` | 呼吸器内科 | `pulmonology` | exact | 2,682 | 6,401 | 3 |  |
| `01015` | 老年・呼吸器内科 | `geriatrics;pulmonology` | exact | 5 | 113 | 2 |  |
| `01016` | 気管食道内科 | `otolaryngology` | broader | 9 | 71 |  | 気管食道科はOSMに対応値が無く耳鼻科に丸めた |
| `01017` | 循環器内科 | `cardiology` | exact | 3,875 | 10,940 | 4 |  |
| `01018` | 心臓内科 | `cardiology` | exact | 29 | 208 | 1 |  |
| `01019` | 心臓血管内科 | `cardiology` | exact | 26 | 132 |  |  |
| `01020` | 消化器内科 | `gastroenterology` | exact | 3,501 | 12,294 | 3 |  |
| `01021` | 胃腸内科 | `gastroenterology` | exact | 434 | 4,765 |  |  |
| `01022` | 腎臓内科 | `nephrology` | exact | 1,319 | 1,620 | 1 |  |
| `01023` | 人工透析内科 | `dialysis` | exact | 539 | 1,188 |  | wiki未文書化だが483件の実用あり。nephrologyに丸める案もある |
| `01024` | 肝臓内科 | `hepatology` | exact | 214 | 720 |  |  |
| `01025` | 神経内科 | `neurology` | exact | 1,429 | 1,858 | 1 |  |
| `01026` | 腫瘍内科 | `oncology` | exact | 286 | 128 |  |  |
| `01027` | 漢方内科 | `traditional_chinese_medicine` | broader | 122 | 1,061 |  | 漢方は中医学と同一ではない。要検討 |
| `01028` | 老年内科 | `geriatrics` | exact | 167 | 485 |  |  |
| `01029` | 女性内科 | `internal` | broader | 14 | 233 |  | 女性内科に対応する値が無い |
| `01030` | 内視鏡内科 | `gastroenterology` | broader | 198 | 1,404 |  | 内視鏡は消化器が主だが他領域も含む |
| `01031` | 疼痛緩和内科 | `palliative` | broader | 41 | 123 |  |  |
| `01032` | ペインクリニック内科 | `anaesthetics` | broader | 134 | 455 |  | 日本のペインクリニックは麻酔科が担当することが多い |
| `01033` | アレルギー疾患内科 | `allergology` | exact | 27 | 800 |  |  |
| `01034` | 緩和ケア内科 | `palliative` | exact | 453 | 454 |  |  |
| `01991` | インフルエンザ | `internal` | broader | 347 | 1,076 | 4 | 「その他（内科系）」の総括コード。149種の自由記述を含む |

### 02 外科系

| コード | 診療科目名 | healthcare:speciality | 確度 | 病院 | 診療所 | 歯科 | 備考 |
|---|---|---|---|---:|---:|---:|---|
| `02001` | 外科 | `surgery` | exact | 3,961 | 9,419 | 5 |  |
| `02002` | 脳神経外科 | `neurosurgery` | exact | 2,558 | 1,720 | 2 |  |
| `02003` | 脳外科 | `neurosurgery` | exact | 26 | 48 |  |  |
| `02004` | 脳・血管外科 | `neurosurgery` | broader | 15 | 20 |  |  |
| `02005` | 呼吸器外科 | `cardiothoracic_surgery` | broader | 993 | 95 | 1 | 呼吸器外科単独に対応する値が無い |
| `02006` | 食道外科 | `surgery` | broader | 25 | 8 |  | 食道外科に対応する値が無い |
| `02007` | 気管食道外科 | `otolaryngology` | broader | 29 | 57 |  |  |
| `02008` | 血管外科 | `vascular_surgery` | exact | 274 | 171 | 1 |  |
| `02009` | 循環器外科 | `cardiothoracic_surgery` | broader | 41 | 39 |  |  |
| `02010` | 心臓外科 | `cardiothoracic_surgery` | exact | 29 | 5 | 1 |  |
| `02011` | 心臓血管外科 | `cardiothoracic_surgery` | exact | 1,032 | 308 |  |  |
| `02012` | 消化器外科 | `abdominal_surgery` | broader | 1,659 | 472 |  |  |
| `02014` | 消化器・移植外科 | `abdominal_surgery;transplant` | broader | 6 | 13 |  |  |
| `02015` | 胃腸外科 | `abdominal_surgery` | broader | 71 | 94 |  |  |
| `02016` | 大腸外科 | `proctology` | broader | 40 | 39 |  |  |
| `02017` | 腎臓外科 | `urology` | broader | 18 | 16 |  |  |
| `02018` | 肝臓外科 | `abdominal_surgery` | broader | 35 | 9 |  |  |
| `02019` | 膵臓外科 | `abdominal_surgery` | broader | 15 | 7 |  |  |
| `02020` | 胆のう外科 | `abdominal_surgery` | broader | 20 | 11 |  |  |
| `02021` | 肝臓・胆のう・膵臓外科 | `abdominal_surgery` | broader | 63 | 13 |  |  |
| `02022` | 乳腺外科 | `surgery` | broader | 973 | 777 |  | 乳腺外科に対応する値が無い。影響施設が多く要検討 |
| `02023` | 乳腺・内分泌外科 | `surgery` | broader | 123 | 100 |  | 乳腺外科に対応する値が無い |
| `02024` | 女性乳腺外科 | `surgery` | broader | 10 | 49 |  | 乳腺外科に対応する値が無い |
| `02025` | 肛門外科 | `proctology` | exact | 887 | 2,475 |  |  |
| `02026` | 大腸・肛門外科 | `proctology` | exact | 100 | 139 |  |  |
| `02027` | ペインクリニック外科 | `anaesthetics` | broader | 85 | 221 |  |  |
| `02028` | 腫瘍外科 | `oncology` | broader | 43 | 11 |  |  |
| `02029` | 頭頸部外科 | `otolaryngology` | broader | 108 | 103 |  |  |
| `02030` | 胸部外科 | `cardiothoracic_surgery` | broader | 38 | 7 |  |  |
| `02031` | 腹部外科 | `abdominal_surgery` | exact | 18 | 14 |  |  |
| `02032` | 内視鏡外科 | `surgery` | broader | 139 | 56 |  |  |
| `02033` | 移植外科 | `transplant` | exact | 36 | 4 |  |  |
| `02034` | 移植・内視鏡外科 | `surgery;transplant` | broader |  | 2 |  | 診療所のみに出現 |
| `02035` | 整形外科 | `orthopaedics` | exact | 4,630 | 10,188 | 2 |  |
| `02036` | 形成外科 | `plastic_surgery` | exact | 1,420 | 2,151 | 4 |  |
| `02037` | 美容外科 | `plastic_surgery` | broader | 119 | 1,452 | 3 | 美容外科。wikiのplastic_surgeryは再建・美容の双方を含む |
| `02038` | 緩和ケア外科 | `palliative` | broader | 44 | 17 |  |  |
| `02991` | その他（外科系） | `surgery` | broader | 131 | 134 |  | 「その他（外科系）」の総括コード。80種の自由記述を含む |

### 03 小児科系

| コード | 診療科目名 | healthcare:speciality | 確度 | 病院 | 診療所 | 歯科 | 備考 |
|---|---|---|---|---:|---:|---:|---|
| `03001` | 小児科 | `paediatrics` | exact | 2,260 | 15,561 | 8 |  |
| `03002` | 小児眼科 | `paediatrics;ophthalmology` | broader | 7 | 155 | 1 |  |
| `03003` | 小児耳鼻いんこう科 | `paediatrics;otolaryngology` | broader | 7 | 544 |  |  |
| `03004` | 小児皮膚科 | `paediatrics;dermatology` | broader | 10 | 733 |  |  |
| `03005` | 児童精神科 | `child_psychiatry` | exact | 112 | 339 |  |  |
| `03006` | 小児外科 | `paediatric_surgery` | exact | 395 | 254 | 3 |  |
| `03007` | 小児泌尿器科 | `paediatrics;urology` | broader | 20 | 100 |  |  |
| `03008` | 新生児内科 | `neonatology` | exact | 58 | 70 | 1 |  |
| `03009` | 小児腫瘍外科 | `paediatric_surgery;oncology` | broader | 1 |  |  |  |
| `03991` | 小児神経科 | `paediatrics` | broader | 95 | 233 | 1 | 「その他（小児科系）」の総括コード。47種の自由記述を含む |

### 04 産婦人科系

| コード | 診療科目名 | healthcare:speciality | 確度 | 病院 | 診療所 | 歯科 | 備考 |
|---|---|---|---|---:|---:|---:|---|
| `04001` | 産婦人科 | `gynaecology` | exact | 1,006 | 2,099 | 3 | wikiの定義が「Obstetrics and gynaecology」で産科を含む |
| `04002` | 産科 | `gynaecology` | exact | 195 | 683 | 1 |  |
| `04003` | 婦人科 | `gynaecology` | exact | 841 | 2,058 | 1 |  |
| `04004` | 産婦人科（生殖医療） | `gynaecology;fertility` | exact | 21 | 351 |  |  |
| `04991` | 女性診療科 | `gynaecology` | broader | 11 | 54 |  | 「その他（産婦人科系）」の総括コード |

### 05 眼科と耳鼻いんこう科系

| コード | 診療科目名 | healthcare:speciality | 確度 | 病院 | 診療所 | 歯科 | 備考 |
|---|---|---|---|---:|---:|---:|---|
| `05001` | 眼科 | `ophthalmology` | exact | 2,183 | 6,922 | 4 |  |
| `05002` | 耳鼻いんこう科 | `otolaryngology` | exact | 1,730 | 4,761 | 5 |  |
| `05003` | 気管食道・耳鼻いんこう科 | `otolaryngology` | exact | 8 | 342 |  |  |
| `05004` | 頭頸部・耳鼻いんこう科 | `otolaryngology` | exact | 79 | 445 |  |  |
| `05991` | 神経眼科 | `ophthalmology` | broader | 2 | 58 |  |  |
| `05992` | 耳鼻咽喉科・頭頸部外科 | `otolaryngology` | exact | 12 | 105 |  |  |

### 06 皮膚科と泌尿器科系

| コード | 診療科目名 | healthcare:speciality | 確度 | 病院 | 診療所 | 歯科 | 備考 |
|---|---|---|---|---:|---:|---:|---|
| `06001` | 皮膚科 | `dermatology` | exact | 2,892 | 9,949 | 19 |  |
| `06002` | 美容皮膚科 | `dermatology` | broader | 57 | 2,859 | 21 |  |
| `06003` | 皮膚泌尿器科 | `dermatology;urology` | exact | 20 | 172 |  |  |
| `06004` | 泌尿器科 | `urology` | exact | 2,731 | 3,253 | 2 |  |
| `06005` | 男性泌尿器科 | `urology` | broader | 6 | 183 |  |  |
| `06006` | 神経泌尿器科 | `urology` | broader | 1 | 48 |  |  |
| `06007` | 腎臓・泌尿器科 | `nephrology;urology` | exact | 13 | 168 |  |  |
| `06991` | 皮膚腫瘍科 | `dermatology` | broader | 4 | 145 |  |  |
| `06992` | 女性泌尿器科 | `urology` | broader | 22 | 102 | 1 |  |

### 07 精神科系

| コード | 診療科目名 | healthcare:speciality | 確度 | 病院 | 診療所 | 歯科 | 備考 |
|---|---|---|---|---:|---:|---:|---|
| `07001` | 精神科 | `psychiatry` | exact | 2,606 | 5,746 | 5 |  |
| `07002` | 神経科 | `psychiatry` | broader | 356 | 498 |  | コード体系上07は精神科系。神経内科ではない |
| `07003` | 心療内科 | `psychiatry` | broader | 1,097 | 4,467 | 1 | 心療内科（心身医学）に対応する値が無い。影響施設が多く要検討 |
| `07004` | 老年精神科 | `psychiatry;geriatrics` | exact | 107 | 272 |  |  |
| `07005` | 老年心療内科 | `psychiatry;geriatrics` | broader | 6 | 140 |  |  |
| `07991` | 神経精神科 | `neuropsychiatry` | broader | 67 | 105 |  | 「その他（精神科系）」の総括コード |

### 08 歯科系

| コード | 診療科目名 | healthcare:speciality | 確度 | 病院 | 診療所 | 歯科 | 備考 |
|---|---|---|---|---:|---:|---:|---|
| `08001` | 歯科 | `dentistry` | exact | 1,106 | 734 | 53,313 | wiki未文書化だが1518件の実用あり |
| `08002` | 矯正歯科 | `orthodontics` | exact | 122 | 116 | 20,937 |  |
| `08003` | 歯科口腔外科 | `dental_oral_maxillo_facial_surgery` | exact | 1,014 | 168 | 22,906 |  |
| `08004` | 小児歯科 | `paediatric_dentistry` | exact | 133 | 169 | 36,500 |  |
| `08005` | 小児矯正歯科 | `orthodontics;paediatric_dentistry` | exact | 1 | 26 | 7,298 |  |
| `08991` | 口腔腫瘍外科 | `dental_oral_maxillo_facial_surgery` | broader | 8 | 14 | 1,500 | 「その他（歯科系）」の総括コード |

### 09 その他

| コード | 診療科目名 | healthcare:speciality | 確度 | 病院 | 診療所 | 歯科 | 備考 |
|---|---|---|---|---:|---:|---:|---|
| `09001` | アレルギー科 | `allergology` | exact | 360 | 7,129 | 1 |  |
| `09002` | リウマチ科 | `rheumatology` | exact | 1,302 | 4,035 | 1 |  |
| `09003` | リハビリテーション科 | `physiatry` | exact | 5,346 | 10,077 | 1 | wikiの定義が「Physical medicine and rehabilitation」 |
| `09004` | 放射線科 | `radiology` | exact | 2,790 | 2,343 | 1 |  |
| `09005` | 放射線診断科 | `diagnostic_radiology` | exact | 334 | 102 |  |  |
| `09006` | 放射線治療科 | `radiotherapy` | exact | 314 | 16 | 2 |  |
| `09007` | 腫瘍放射線科 | `radiotherapy` | exact | 12 | 5 |  |  |
| `09008` | 病理診断科 | `pathology` | exact | 920 | 46 |  |  |
| `09009` | 臨床検査科 | `clinical_pathology` | exact | 284 | 63 | 1 |  |
| `09010` | 救急科 | `emergency` | exact | 899 | 98 |  |  |
| `09011` | 麻酔科 | `anaesthetics` | exact | 2,577 | 1,495 | 2 |  |
| `09991` | 総合診療科 | `general` | broader | 186 | 655 | 88 | 「その他」の総括コード。151種の自由記述を含む |

## 業態別の上書き

同じコードが業態によって別の意味で使われることがあります。
その場合は業態を指定した行を置き、その業態でのみ優先します。

| 業態 | コード | 診療科目名 | healthcare:speciality | 確度 | 備考 |
|---|---|---|---|---|---|
| 歯科診療所 | `08991` | インプラント | `dentistry` | broader | 歯科診療所ではインプラント522/審美歯科372/訪問歯科219が主で口腔外科ではない |
| 歯科診療所 | `09991` | インプラント | `dentistry` | broader | 歯科診療所では歯科系の自由記述が主 |

## タグ値が 255 文字を超えたときの畳み先

診療科をすべて並べると OSM のタグ値の上限を超える施設があります。
超えた施設だけ、細分値を上位科へ畳みます。
主要な診療科は畳まずに残します。

| 値 | 畳み先 | 備考 |
|---|---|---|
| `abdominal_surgery` | `surgery` | 外科の細分。neurosurgery/orthopaedics/paediatric_surgery は主要科として畳まない |
| `cardiothoracic_surgery` | `surgery` | 外科の細分 |
| `vascular_surgery` | `surgery` | 外科の細分 |
| `transplant` | `surgery` | 外科の細分 |
| `proctology` | `surgery` | 外科の細分 |
| `plastic_surgery` | `surgery` | 外科の細分 |
| `hepatology` | `gastroenterology` | 消化器の細分 |
| `dialysis` | `nephrology` | 腎臓の細分。wiki未文書化値でもあるため畳む優先度は高い |
| `endocrinology` | `internal` | 内科の細分。cardiology/gastroenterology/nephrology/neurology/pulmonology/oncology は主要科として畳まない |
| `infectious_diseases` | `internal` | 内科の細分 |
| `haematology` | `internal` | 内科の細分 |
| `geriatrics` | `internal` | 内科の細分 |
| `allergology` | `internal` | 内科の細分 |
| `diagnostic_radiology` | `radiology` | 放射線科の細分 |
| `radiotherapy` | `radiology` | 放射線科の細分 |
| `nuclear` | `radiology` | 放射線科の細分 |
| `clinical_pathology` | `pathology` | 病理の細分 |
| `orthodontics` | `dentistry` | 歯科の細分 |
| `paediatric_dentistry` | `dentistry` | 歯科の細分 |
| `dental_oral_maxillo_facial_surgery` | `dentistry` | 歯科の細分 |
| `child_psychiatry` | `psychiatry` | 精神科の細分 |
| `neuropsychiatry` | `psychiatry` | 精神科の細分 |

## 対応値が無い診療科

OSM の語彙に対応する値が無く、上位概念へ丸めた診療科のうち、
影響する施設数が多いものを挙げます。
投入の合意を得る際の論点になります。

| 診療科目名 | 現在の値 | 施設数 | 論点 |
|---|---|---:|---|
| 心療内科 | `psychiatry` | 5,565 | 心療内科（心身医学）に対応する値が無い。影響施設が多く要検討 |
| 乳腺外科 | `surgery` | 1,750 | 乳腺外科に対応する値が無い。影響施設が多く要検討 |
| 漢方内科 | `traditional_chinese_medicine` | 1,183 | 漢方は中医学と同一ではない。要検討 |
