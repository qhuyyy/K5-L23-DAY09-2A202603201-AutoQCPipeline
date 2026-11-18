# Báo cáo Day 09 — Bùi Quang Huy, 2A202603201

## 1. Kết luận trước
**HOLD** (mã thoát 10). Vào **224** ảnh, cửa vào loại **22**, còn **202** ảnh đi qua QC. Bộ `submission/export/clean_v1/` có 202 ảnh và nhãn, nhưng đây chỉ là **bản nháp để thử nghiệm**, chưa được phát hành.
Lý do: sau khi máy sửa và người duyệt hết ngân sách 80 ảnh thì không còn lỗi bắt buộc nào (`n_errors = 0`). Tuy vậy vẫn còn **38/202 ảnh (18,8 %)** có cảnh báo mà chưa ai xem, cao hơn ngưỡng 10 % (`08_summary.json`).

## 2. Lỗi và phân việc
Lấy từ `02_error_list_v1.csv` (211 dòng trên 224 ảnh) và `03_fixes.csv` (35 thay đổi).

| Mã lỗi | Số dòng (số ảnh) | Ai sửa | Vì sao |
|---|---:|---|---|
| DUP_IMAGE_EXACT | 8 (8) | máy: `remove_image` | md5 trùng từng byte, chắc chắn |
| DUP_IMAGE_NEAR | 4 (4) | máy: `remove_image` | phash ≤ 12; đã mở xem cả 4 cặp, đều là cùng một ảnh (cắt hoặc đổi sáng) |
| LEAK_TEST | 5 (5) | máy: `remove_image` | ảnh trùng với tập test, để lại sẽ làm số đo cuối bị lạc quan |
| BAD_SIZE / CORRUPT_IMAGE | 3 (3) / 2 (2) | máy: `remove_image` | cạnh ngắn < 250 px / không mở được |
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX | 3 / 6 / 4 / 7 dòng | máy: `drop_line` (20 dòng) | dòng hỏng thì không có nghĩa, không đoán được giá trị đúng |
| BOX_OUT_OF_IMAGE | 8 (8) | máy: `clip_box` (8) | cắt về [0,1] mà vẫn giữ lớp, vd. `img_0030` dòng 9: x −0.0038 → 0.0077 |
| BAD_CLASS_NAME | 2 dòng (data.yaml) | máy: `rename_classes` | ghi lại `names` cho đúng `cfg.classes` |
| MISSING_LABEL_FILE | 6 (6) | **người**: `needs_label` | máy không bịa nhãn; cũng không tạo file rỗng, vì file rỗng nghĩa là "ảnh nền" |
| POSSIBLE_MISSING | 53 (52) | người | model lớn thấy vật mà nhãn không có; model cũng có thể sai |
| POSSIBLE_WRONG_CLASS | 18 (18) | người | car / truck / bus là chuyện ngữ nghĩa, chỉ người mới quyết được |
| POSSIBLE_LOOSE_BOX | 28 (24) | người | box lệch hay lỏng, cần mắt người để vẽ lại |
| POSSIBLE_FALSE_POS | 29 (27) | người | box nhãn không khớp vật nào model thấy |
| EMPTY_LABEL / BOX_TINY / BOX_HUGE | 12 / 6 (4) / 3 | người | đây là cảnh báo, máy không tự xoá |
| CLASS_RARE | 4 (`<dataset>`) | người, ở mức guideline | lớp lạ / ít box, cấp dataset, không chặn cổng |

**Hàng đợi** (`05_review_queue.csv`, 125 ảnh): điểm của mỗi ảnh = Σ trọng số mã × (1 + conf). `NEEDS_LABEL` có trọng số 10, nên 6 ảnh chưa có nhãn nằm ngay đầu hàng. Riêng `img_0020` đứng thứ 1 (11,5 điểm) vì dồn cả 3 thứ: FIXED_DROP_LINE (id 93 đã bị xoá), WRONG_CLASS và MISSING. Tiếp theo là các ảnh có WRONG_CLASS (trọng số 3) hoặc MISSING (trọng số 2) với conf cao. BOX_TINY / DENSE (0,3) xếp cuối.
Với ngân sách 80 ảnh (`06_review_log.csv`), người duyệt đi tới ảnh có điểm 3,34. Trong 80 ảnh đó có **74 ảnh mang ít nhất một cảnh báo ngữ nghĩa**, gồm toàn bộ 18/18 ảnh WRONG_CLASS và 50/52 ảnh MISSING. Bên ngoài ngân sách còn 45 ảnh. Phần lớn là LOOSE_BOX (16 ảnh) và FALSE_POS (11 ảnh), vì hai mã này có trọng số thấp hơn.

## 3. Calibration (2 ngưỡng)
Số liệu lấy từ `submission/calibration/calibration_report.md` (39 ảnh calib).

| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau) | Lý do (đánh đổi) |
|---|---|---|---|---|
| `duplicates.phash_dist` | 2 | **12** | NEAR: 1.00 / 0.50 → 1.00 / 0.67 (EXACT giữ 1.00 / 1.00) | Từ 4 đến 14 cho cùng một kết quả trên calib. Mình chọn 12 ở giữa đoạn đó để có biên an toàn cả hai phía. Trên raw, mức 10 bắt được cặp `img_0186`~`img_0061` (đúng là ảnh trùng, có cắt và đổi sáng), mức 2 thì bỏ sót cặp này. Mức 16 tuy recall calib cao hơn (0.83) nhưng làm hỏng dữ liệu thật (xem bên dưới). |
| `second_opinion.conf` | 0.25 | **0.6** | MISSING 0.50 / 1.00 → 0.57 / 1.00 · WRONG_CLASS 0.56 / 0.83 → 0.62 / 0.83 · LOOSE 0.29 / 0.40 → 0.20 / 0.20 | 0.6 là ngưỡng cao nhất mà vẫn giữ recall MISSING = 1.00 và WRONG_CLASS = 0.83, nên precision tăng mà không mất lỗi nào. Lên 0.7 thì MISSING rơi xuống 0.88, lên 0.8 thì còn 0.75. Cái giá phải trả là recall LOOSE_BOX giảm từ 0.40 xuống 0.20. Chấp nhận được, vì trên calib LOOSE_BOX vốn có precision thấp nhất. Hàng đợi giảm từ 143 xuống 125 ảnh. |

**Calibration có thể đánh lừa ở đâu (có bằng chứng):**
1. *Ngưỡng tốt nhất trên calib lại sai trên raw.* Trên calib, `phash_dist = 16` có F1 cao nhất (0.91). Thử trên raw thì số ảnh bị loại tăng từ 17 lên 26: thêm **6 LEAK_TEST** và **3 DUP_IMAGE_NEAR**, tất cả chỉ xuất hiện khi ngưỡng tăng từ 14 lên 16. Mở ảnh ra xem thì đó là các cặp hoàn toàn khác nhau, ví dụ `img_0013` (bàn làm việc với laptop) bị gán là "trùng" `test_087` (sân bóng chày), `img_0011` (tennis) "trùng" `img_0008` (trượt tuyết). Lên mức 20 thì có tới 105 ảnh bị cho là rò rỉ test. Tập calib chỉ có 6 cặp near-dup, quá ít để thấy được lỗi gộp nhầm này.
2. *Chọn ngưỡng để qua cổng.* Với `conf = 0.8` pipeline ra **Release** (16/202 = 7,9 %) vì ít cảnh báo hơn, nhưng khi đó recall MISSING trên calib chỉ còn 0.75 (2/8 ảnh thiếu nhãn lọt qua). Mình không chọn 0.8, vì như vậy là tối ưu cho cổng chứ không phải cho chất lượng nhãn.

## 4. Cửa chặn và điều pipeline KHÔNG bắt được
**(a) Gate chặn đúng.** Chạy `python -m pipeline.run --budget 0 --reports work/rep_nb --export-dir work/exp_nb`: kết luận **REWORK, còn 6 lỗi bắt buộc (MISSING_LABEL_FILE)**, **mã thoát 20**, log in ra `Bước 5/5 KHÔNG xuất: còn lỗi bắt buộc (Rework)`, và thư mục `work/exp_nb` không được tạo ra. Ở lần chạy chính, 6 ảnh này được người gán nhãn (nằm ở đầu hàng đợi) nên lỗi bắt buộc về 0 và kết luận chuyển sang Hold.
Kiểm bằng mắt bằng `scripts/viz_labels.py`: `img_0001` có người lính bên phải không có box (khớp với POSSIBLE_MISSING person conf 0.95) và có một box person bị lặp (DUP_BOX dòng 3); `img_0030` có box ở mép trái tràn ra ngoài ảnh (BOX_OUT_OF_IMAGE dòng 9, đã được `clip_box`).

**(b) Điểm mù.**
1. *Ảnh trùng bị biến đổi mạnh.* Trong calib, hai cặp near-dup ở mức biến đổi 3–4 có phash cách nhau **16 và 18**, nên với ngưỡng 12 chúng lọt qua (recall NEAR 0.67). Nâng ngưỡng để bắt chúng thì lại loại nhầm ảnh khác trên raw (mục 3). Nói cách khác, phash không thể bắt được loại trùng này mà không trả giá bằng precision.
2. *Nhầm lớp mà model lớn cũng nhầm, hoặc model nhầm ngược.* Sau khi nhãn đã được người thay (`07_error_list_v3`), vẫn còn 3 cờ WRONG_CLASS trên ảnh đã duyệt (`img_0078`, `img_0083`, `img_0220`): người gán **truck**, còn model nói **car** (IoU > 0.9). Như vậy ý kiến thứ hai có thể sai. Ngược lại, khi nhãn sai mà model cũng sai giống vậy thì sẽ không có cờ nào bật lên.
3. *Box lỏng nhẹ.* Recall LOOSE_BOX trên calib chỉ 0.20 với box phóng to khoảng 1,5 lần. Trên raw còn 16 ảnh LOOSE_BOX nằm ngoài ngân sách duyệt.

## 5. Train: raw vs clean (tùy chọn, chấm riêng)
**Chưa chạy.** Bản này chỉ nộp phần lõi (`make check-core`). Dataset `clean_v1` đã được xuất (bản nháp, vì kết luận là Hold) để có thể train trên Colab sau.

## 6. Quyết định và ghi chú AI
**(a)** Quyết định: **Hold**. Không phát hành. Không có lỗi bắt buộc nào, nhưng 38/202 ảnh vẫn còn cảnh báo chưa được người xem. Muốn thành **Release** cần cho người duyệt thêm ít nhất **18 ảnh** trong số 38 ảnh đó (để còn dưới 20/202 < 10 %), theo đúng thứ tự `05_review_queue.csv` (chủ yếu là LOOSE_BOX / FALSE_POS / EMPTY_LABEL). Một cách khác là tăng ngân sách duyệt trong guideline của dự án, chứ không phải nâng `conf` để giấu cảnh báo.
**(b) Có dùng AI (Claude Code):**
- *Prompt chính:* cho AI đọc docstring và test của từng stub (đầu vào, đầu ra, mã lỗi / severity, các bẫy như số dòng gốc, dòng trống, dòng có 2 lỗi, ngưỡng lấy từ `cfg`), yêu cầu không ghi vào `data/raw` và không đọc MANIFEST / test trong code kiểm.
- *Cách kiểm:* chạy `pytest` (79/79 xanh), `make calibrate` trên lỗi chèn sẵn, chạy pipeline nhiều lần, đọc `03_fixes.csv` (trước → sau), mở ảnh viz và ảnh cặp trùng để đối chiếu.
- *Một lần AI có thể dẫn sai:* nếu chỉ đọc bảng sweep thì `phash_dist = 16` (F1 cao nhất) và `conf = 0.8` (ra Release) trông có vẻ là lựa chọn tốt. Mở ảnh ra kiểm mới thấy 16 loại nhầm 9 ảnh khác nhau, còn 0.8 làm mất 25 % recall MISSING. Vì vậy cả hai giá trị đều bị loại.
