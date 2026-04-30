# Final Pilot Manifest

Final pilot prescriptions are locked. Do not change this scope without creating a new manifest version.

## Final Prescriptions

| # | prescription_id | image_path | brand → generic | diagnosis extracted by NER | estimated duration |
|---:|---|---|---|---|---:|
| 1 | `VAIPE_P_TRAIN_904` | `/Users/Start Up/Research Project /VSL26/public_train/prescription/image/VAIPE_P_TRAIN_904.png` | PAMLONOR 5mg → Amlodipine | Bệnh lý tăng huyết áp: (G46?) Hội chứng mạch máu não trong bệnh mạch não (160- 167t) | 49s |
| 2 | `VAIPE_P_TRAIN_457` | `/Users/Start Up/Research Project /VSL26/public_train/prescription/image/VAIPE_P_TRAIN_457.png` | ENALAPRIL → Enalapril | (none) | 49s |
| 3 | `VAIPE_P_TRAIN_871` | `/Users/Start Up/Research Project /VSL26/public_train/prescription/image/VAIPE_P_TRAIN_871.png` | AMOXICILIN 500mg → Amoxicillin | (none) | 53s |
| 4 | `VAIPE_P_TRAIN_877` | `/Users/Start Up/Research Project /VSL26/public_train/prescription/image/VAIPE_P_TRAIN_877.png` | PANACTOL 500mg → Paracetamol | (none) | 55s |

## Complete Gloss Output

### VAIPE_P_TRAIN_904

- Drug: `PAMLONOR 5mg` → `Amlodipin`
- `dung_cho`: ["bác sĩ kê thuốc", "số 1", "giảm", "nguy cơ", "cao huyết áp"]
- `dung_nhu_nao`: ["uống", "2 viên", "buổi sáng", "mỗi ngày"]
- `luu_y`: ["uống", "đều đặn", "mỗi ngày", "không", "tự ý", "ngừng thuốc"]
- `ket_bai`: {"tac_dung_phu_cluster": ["trong quá trình", "sử dụng thuốc", "có thể", "tác dụng phụ", "dị ứng", "mề đay", "nốt đỏ", "phù mặt", "khó thở", "nguy hiểm", "tính mạng"], "if_one_of_three": ["nếu gặp", "1 trong 3", "triệu chứng trên"], "actions": [["1 là", "dừng thuốc", "ngay lập tức"], ["2 là", "mang theo", "vỏ hộp thuốc", "đi cấp cứu"], ["3 là", "không chắc chắn", "hỏi", "Dược sĩ", "Bác sĩ"]]}

### VAIPE_P_TRAIN_457

- Drug: `ENALAPRIL 5mg` → `Enalapril`
- `dung_cho`: ["bác sĩ kê thuốc", "số 1", "giảm", "nguy cơ", "cao huyết áp"]
- `dung_nhu_nao`: ["uống", "2 viên", "buổi sáng", "mỗi ngày"]
- `luu_y`: ["uống", "đều đặn", "mỗi ngày", "không", "tự ý", "ngừng thuốc"]
- `ket_bai`: {"tac_dung_phu_cluster": ["trong quá trình", "sử dụng thuốc", "có thể", "tác dụng phụ", "dị ứng", "mề đay", "nốt đỏ", "phù mặt", "khó thở", "nguy hiểm", "tính mạng"], "if_one_of_three": ["nếu gặp", "1 trong 3", "triệu chứng trên"], "actions": [["1 là", "dừng thuốc", "ngay lập tức"], ["2 là", "mang theo", "vỏ hộp thuốc", "đi cấp cứu"], ["3 là", "không chắc chắn", "hỏi", "Dược sĩ", "Bác sĩ"]]}

### VAIPE_P_TRAIN_871

- Drug: `AMOXICILIN 500MG 500mg` → `Amoxicillin`
- `dung_cho`: ["bác sĩ kê thuốc", "số 1", "đau họng", "giảm"]
- `dung_nhu_nao`: ["uống", "3 viên", "buổi sáng", "và", "3 viên", "buổi chiều", "mỗi ngày"]
- `luu_y`: ["BẮT BUỘC", "uống hết", "đơn thuốc", "KHÔNG", "dừng thuốc sớm", "có thể", "tiêu chảy"]
- `ket_bai`: {"tac_dung_phu_cluster": ["trong quá trình", "sử dụng thuốc", "có thể", "tác dụng phụ", "dị ứng", "mề đay", "nốt đỏ", "phù mặt", "khó thở", "nguy hiểm", "tính mạng"], "if_one_of_three": ["nếu gặp", "1 trong 3", "triệu chứng trên"], "actions": [["1 là", "dừng thuốc", "ngay lập tức"], ["2 là", "mang theo", "vỏ hộp thuốc", "đi cấp cứu"], ["3 là", "không chắc chắn", "hỏi", "Dược sĩ", "Bác sĩ"]]}

### VAIPE_P_TRAIN_877

- Drug: `PANACTOL 500mg` → `Paracetamol`
- `dung_cho`: ["bác sĩ kê thuốc", "số 1", "giúp bạn", "cảm thấy", "dễ chịu hơn"]
- `dung_nhu_nao`: ["uống", "2 viên", "buổi sáng", "và", "2 viên", "buổi chiều", "mỗi ngày"]
- `luu_y`: ["mỗi lần uống", "cách nhau", "4-6 tiếng", "không quá", "4 viên", "mỗi ngày", "uống nhiều", "hại gan"]
- `ket_bai`: {"tac_dung_phu_cluster": ["trong quá trình", "sử dụng thuốc", "có thể", "tác dụng phụ", "dị ứng", "mề đay", "nốt đỏ", "phù mặt", "khó thở", "nguy hiểm", "tính mạng"], "if_one_of_three": ["nếu gặp", "1 trong 3", "triệu chứng trên"], "actions": [["1 là", "dừng thuốc", "ngay lập tức"], ["2 là", "mang theo", "vỏ hộp thuốc", "đi cấp cứu"], ["3 là", "không chắc chắn", "hỏi", "Dược sĩ", "Bác sĩ"]]}

## Token Totals

- Total tokens across all 4 videos: 172
- Unique gloss tokens needed: 59

## Unique Gloss Tokens

- 1 là
- 1 trong 3
- 2 là
- 2 viên
- 3 là
- 3 viên
- 4 viên
- 4-6 tiếng
- Bác sĩ
- BẮT BUỘC
- Dược sĩ
- KHÔNG
- buổi chiều
- buổi sáng
- bác sĩ kê thuốc
- cao huyết áp
- cách nhau
- có thể
- cảm thấy
- dễ chịu hơn
- dị ứng
- dừng thuốc
- dừng thuốc sớm
- giúp bạn
- giảm
- hại gan
- hỏi
- khó thở
- không
- không chắc chắn
- không quá
- mang theo
- mề đay
- mỗi lần uống
- mỗi ngày
- ngay lập tức
- nguy cơ
- nguy hiểm
- ngừng thuốc
- nếu gặp
- nốt đỏ
- phù mặt
- số 1
- sử dụng thuốc
- tiêu chảy
- triệu chứng trên
- trong quá trình
- tác dụng phụ
- tính mạng
- tự ý
- uống
- uống hết
- uống nhiều
- và
- vỏ hộp thuốc
- đau họng
- đi cấp cứu
- đơn thuốc
- đều đặn
