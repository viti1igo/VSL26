# Wave 1 Validation Report

Validation reran OCR → NER → Mapper on 10 training prescriptions selected from annotations containing Wave 1 drug names.

## Coverage Summary

- Before Wave 1: 11/29 drugs matched (37.9%)
- After Wave 1: 19/29 drugs matched (65.5%)
- Coverage improvement: +27.6% points

## Prescription Details

### VAIPE_P_TRAIN_1012

- Wave 1 target terms in annotation: chorlatcyn
- Annotation drug rows: 1) MEGLUCON 1000 1000mg | 2) GOLDDICRON 30mg | 3) HANGITOR PLUS 40mg+12,5mg | 4) KAGASDINE 20mg | 5) CHORLATCYN 125mg+50mg+50mg+25mg
- OCR regions: 103
- Diagnoses extracted by NER: (none)
- Drugs detected by NER: 1) MEGLUCON 1000 1000 mg | 2) GOLDDICRON 30mg | 3) HANGITOR PLUS 40mg712,5mg | 4) KAGASDINE 20mg | 5)

| name_extracted | name_normalized | confidence | mapped_illness | drug_class | sanity |
|---|---|---:|---|---|---|
| 1) MEGLUCON 1000 1000 mg | Metformin | 92.9 |  | Hoạt chất nhập từ WHO ATC/DDD | OK: NER không trích xuất chẩn đoán để đối chiếu. |
| 2) GOLDDICRON 30mg | 2 golddicron | 63.6 |  |  | FLAG: Không map được vào KB. |
| 3) HANGITOR PLUS 40mg712,5mg | telmisartan and diuretics | 72.2 |  | Hoạt chất nhập từ WHO ATC/DDD | OK: NER không trích xuất chẩn đoán để đối chiếu. |
| 4) KAGASDINE 20mg | Amlodipin | 76.2 | Tăng huyết áp; Cao huyết áp | Thuốc hạ huyết áp | OK: NER không trích xuất chẩn đoán để đối chiếu. |
| 5) | 5 | 18.2 |  |  | FLAG: Không map được vào KB. |

### VAIPE_P_TRAIN_1021

- Wave 1 target terms in annotation: vitamin c stada
- Annotation drug rows: 1) PANACTOL 500mg | 2) VITAMIN C STADA 1G 1g
- OCR regions: 48
- Diagnoses extracted by NER: Chẩn đoán: M54.2
- Drugs detected by NER: 1) PANACTOL 500mg | 2) VITAMINCSTADA 1G 1g

| name_extracted | name_normalized | confidence | mapped_illness | drug_class | sanity |
|---|---|---:|---|---|---|
| 1) PANACTOL 500mg | Paracetamol | 88.9 | Đau; Sốt | Thuốc giảm đau hạ sốt | OK: Không có rule chẩn đoán cụ thể; không thấy sai rõ ràng. |
| 2) VITAMINCSTADA 1G 1g | ascorbic acid | 92.9 |  | Hoạt chất nhập từ WHO ATC/DDD | OK: Không có rule chẩn đoán cụ thể; không thấy sai rõ ràng. |

### VAIPE_P_TRAIN_1023

- Wave 1 target terms in annotation: dixirein
- Annotation drug rows: 1) CEFADROXIL 500MG 0,5g | 2) DIXIREIN 375mg | 3) PARTAMOL TAB. 500mg
- OCR regions: 65
- Diagnoses extracted by NER: (none)
- Drugs detected by NER: 1) CEFADROXIL 500MG 0,5g | 2) DIXIREIN 375mg | 3) PARTAMOL TAB. 500mg

| name_extracted | name_normalized | confidence | mapped_illness | drug_class | sanity |
|---|---|---:|---|---|---|
| 1) CEFADROXIL 500MG 0,5g | Cefadroxil | 90.9 |  | Hoạt chất nhập từ WHO ATC/DDD | OK: NER không trích xuất chẩn đoán để đối chiếu. |
| 2) DIXIREIN 375mg | Carbocistein | 88.9 |  | Hoạt chất nhập từ WHO ATC/DDD | OK: NER không trích xuất chẩn đoán để đối chiếu. |
| 3) PARTAMOL TAB. 500mg | Paracetamol | 92.9 | Đau; Sốt | Thuốc giảm đau hạ sốt | OK: NER không trích xuất chẩn đoán để đối chiếu. |

### VAIPE_P_TRAIN_1039

- Wave 1 target terms in annotation: mezafen
- Annotation drug rows: 1) HANGITOR PLUS 40mg+12,5mg | 2) MEZAFEN 60mg
- OCR regions: 59
- Diagnoses extracted by NER: (M25.4)Tràn dịch khớp gối (P)
- Drugs detected by NER: HANGITOR PLUS 40mg+12,5mg | 1) | 2) MEZAFEN 60mg

| name_extracted | name_normalized | confidence | mapped_illness | drug_class | sanity |
|---|---|---:|---|---|---|
| HANGITOR PLUS 40mg+12,5mg | telmisartan and diuretics | 100.0 |  | Hoạt chất nhập từ WHO ATC/DDD | FLAG: Chẩn đoán cơ-xương-khớp nhưng thuốc không giống nhóm giảm đau/chống viêm. |
| 1) | 1 | 22.2 |  |  | FLAG: Không map được vào KB. |
| 2) MEZAFEN 60mg | Loxoprofen | 87.5 |  | Hoạt chất nhập từ WHO ATC/DDD | OK: Nhóm thuốc phù hợp với ít nhất một chẩn đoán/rule. |

### VAIPE_P_TRAIN_104

- Wave 1 target terms in annotation: fudcime
- Annotation drug rows: 1) FUDCIME 200MG 200mg | 2) BROMHEXIN ACTAVIS 8MG 8mg | 3) VIPREDNI 16MG 16mg | 4) PARTAMOL TAB. 500mg
- OCR regions: 67
- Diagnoses extracted by NER: PARTAMOL TAB.
- Drugs detected by NER: 1) FUDCIME 200MG 200mg | 2) BROMHEXIN ACTAVIS 8MG | 3) VIPREDNI 16MG | 500mg

| name_extracted | name_normalized | confidence | mapped_illness | drug_class | sanity |
|---|---|---:|---|---|---|
| 1) FUDCIME 200MG 200mg | cefixime | 87.5 |  | Hoạt chất nhập từ WHO ATC/DDD | OK: Không có rule chẩn đoán cụ thể; không thấy sai rõ ràng. |
| 2) BROMHEXIN ACTAVIS 8MG | bromhexine | 94.4 |  | Hoạt chất nhập từ WHO ATC/DDD | OK: Không có rule chẩn đoán cụ thể; không thấy sai rõ ràng. |
| 3) VIPREDNI 16MG | Methylprednisolon | 88.9 |  | Hoạt chất nhập từ WHO ATC/DDD | OK: Không có rule chẩn đoán cụ thể; không thấy sai rõ ràng. |
| 500mg |  | 0.0 |  |  | FLAG: Không map được vào KB. |

### VAIPE_P_TRAIN_1041

- Wave 1 target terms in annotation: livonic
- Annotation drug rows: 1) HOẠT HUYẾT DƯỠNG NÃO QN 150mg+20mg | 2) LIVONIC 2500mg+400mg+500mg+85mg
- OCR regions: 48
- Diagnoses extracted by NER: (none)
- Drugs detected by NER: 1) HOẠT HUYẾT DƯỜNG NÃO QN 150mg+20mg | 2) LIVONIC

| name_extracted | name_normalized | confidence | mapped_illness | drug_class | sanity |
|---|---|---:|---|---|---|
| 1) HOẠT HUYẾT DƯỜNG NÃO QN 150mg+20mg | 1 hoạt huyết dường não qn | 40.8 |  |  | FLAG: Không map được vào KB. |
| 2) LIVONIC | livonic | 87.5 | Bổ gan; Hỗ trợ chức năng gan | Thuốc đông y / thảo dược | OK: Thuốc đông y/thảo dược; cần người review ngữ cảnh nhưng không sai rõ ràng. |

### VAIPE_P_TRAIN_1044

- Wave 1 target terms in annotation: anpemux
- Annotation drug rows: 1) Cefalexin (Firstlexin 500) 0,5g | 2) Methyl prednisolon (Methylprednisolon 4) 4mg | 3) Carbocistein (Anpemux) 250mg
- OCR regions: 33
- Diagnoses extracted by NER: (none)
- Drugs detected by NER: 1 ) Cefalexin (Firstlexin 500) 0,5g | 2 ) Methyl prednisolon (Methylprednisolon 4) 4mg | 3 ) Carbocistein (Anpemux) 250mg

| name_extracted | name_normalized | confidence | mapped_illness | drug_class | sanity |
|---|---|---:|---|---|---|
| 1 ) Cefalexin (Firstlexin 500) 0,5g | 1 cefalexin firstlexin 500 | 51.4 |  |  | FLAG: Không map được vào KB. |
| 2 ) Methyl prednisolon (Methylprednisolon 4) 4mg | 2 methyl prednisolon methylprednisolon 4 | 62.1 |  |  | FLAG: Không map được vào KB. |
| 3 ) Carbocistein (Anpemux) 250mg | 3 carbocistein anpemux | 68.6 |  |  | FLAG: Không map được vào KB. |

### VAIPE_P_TRAIN_1052

- Wave 1 target terms in annotation: medibogan
- Annotation drug rows: 1) KAVASDIN 5 5mg | 2) MEDIBOGAN 200mg + 150mg + 16mg
- OCR regions: 51
- Diagnoses extracted by NER: (none)
- Drugs detected by NER: 1) KAVASDIN 55 mg | 2) MEDIBOGAN 200mg % 150mg %

| name_extracted | name_normalized | confidence | mapped_illness | drug_class | sanity |
|---|---|---:|---|---|---|
| 1) KAVASDIN 55 mg | Amlodipin | 90.0 | Tăng huyết áp; Cao huyết áp | Thuốc hạ huyết áp | OK: NER không trích xuất chẩn đoán để đối chiếu. |
| 2) MEDIBOGAN 200mg % 150mg % | medibogan | 90.0 | Bổ gan; Hỗ trợ chức năng gan | Thuốc đông y / thảo dược | OK: Thuốc đông y/thảo dược; cần người review ngữ cảnh nhưng không sai rõ ràng. |

### VAIPE_P_TRAIN_106

- Wave 1 target terms in annotation: famogast
- Annotation drug rows: 1) METRONIDAZOL 250mg | 2) FAMOGAST 40mg
- OCR regions: 54
- Diagnoses extracted by NER: (none)
- Drugs detected by NER: 1) METRONIDAZOL 250mg | 2) FAMOGAST 40mg

| name_extracted | name_normalized | confidence | mapped_illness | drug_class | sanity |
|---|---|---:|---|---|---|
| 1) METRONIDAZOL 250mg | Metronidazol | 88.9 |  | Hoạt chất nhập từ WHO ATC/DDD | OK: NER không trích xuất chẩn đoán để đối chiếu. |
| 2) FAMOGAST 40mg | famotidine | 88.9 |  | Hoạt chất nhập từ WHO ATC/DDD | OK: NER không trích xuất chẩn đoán để đối chiếu. |

### VAIPE_P_TRAIN_1066

- Wave 1 target terms in annotation: sergurop, bloza
- Annotation drug rows: 1) BLOZA 50mg | 2) SERGUROP 10mg
- OCR regions: 46
- Diagnoses extracted by NER: Chần đoán: 110 - Bệnh lý tăng huyết áp; (J11) Cúm, virus kỳ
- Drugs detected by NER: 1) | 50mg | 2) SERGUROP 10mg

| name_extracted | name_normalized | confidence | mapped_illness | drug_class | sanity |
|---|---|---:|---|---|---|
| 1) | 1 | 22.2 |  |  | FLAG: Không map được vào KB. |
| 50mg |  | 0.0 |  |  | FLAG: Không map được vào KB. |
| 2) SERGUROP 10mg | Loratadin | 88.9 | Dị ứng; Viêm mũi dị ứng | Thuốc chống dị ứng | OK: Nhóm thuốc phù hợp với ít nhất một chẩn đoán/rule. |

## Flagged Potentially Wrong Mappings

- **VAIPE_P_TRAIN_1012**: `2) GOLDDICRON 30mg` → `2 golddicron` (63.6) — Không map được vào KB.
- **VAIPE_P_TRAIN_1012**: `5)` → `5` (18.2) — Không map được vào KB.
- **VAIPE_P_TRAIN_1039**: `HANGITOR PLUS 40mg+12,5mg` → `telmisartan and diuretics` (100.0) — Chẩn đoán cơ-xương-khớp nhưng thuốc không giống nhóm giảm đau/chống viêm.
- **VAIPE_P_TRAIN_1039**: `1)` → `1` (22.2) — Không map được vào KB.
- **VAIPE_P_TRAIN_104**: `500mg` → `` (0.0) — Không map được vào KB.
- **VAIPE_P_TRAIN_1041**: `1) HOẠT HUYẾT DƯỜNG NÃO QN 150mg+20mg` → `1 hoạt huyết dường não qn` (40.8) — Không map được vào KB.
- **VAIPE_P_TRAIN_1044**: `1 ) Cefalexin (Firstlexin 500) 0,5g` → `1 cefalexin firstlexin 500` (51.4) — Không map được vào KB.
- **VAIPE_P_TRAIN_1044**: `2 ) Methyl prednisolon (Methylprednisolon 4) 4mg` → `2 methyl prednisolon methylprednisolon 4` (62.1) — Không map được vào KB.
- **VAIPE_P_TRAIN_1044**: `3 ) Carbocistein (Anpemux) 250mg` → `3 carbocistein anpemux` (68.6) — Không map được vào KB.
- **VAIPE_P_TRAIN_1066**: `1)` → `1` (22.2) — Không map được vào KB.
- **VAIPE_P_TRAIN_1066**: `50mg` → `` (0.0) — Không map được vào KB.

## Notes

- This is a rule-based smoke test, not clinical validation.
- A `FLAG` means the mapper output deserves manual inspection; it does not prove the mapping is wrong.
- The before/after comparison uses the same OCR and NER output, then maps once with `vaipe_drugs.db.backup_wave1` and once with the current `vaipe_drugs.db`.
