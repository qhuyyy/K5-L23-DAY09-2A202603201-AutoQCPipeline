"""CHECK 6 — Ý kiến thứ hai: so nhãn với một model LỚN HƠN (yolo26l).   ★★★ (khó nhất, đáng điểm nhất)

Test:  pytest tests/test_second_opinion.py -q

Máy kiểm quy tắc, người kiểm ý nghĩa (slide). Các lỗi như thiếu nhãn / gán nhầm lớp hợp lệ / box lỏng
KHÔNG bắt được bằng quy tắc cú pháp. Ta nhờ một model mạnh hơn "nhìn lại" và CHỈ CẢNH BÁO (model cũng có thể sai):
những ảnh bị cờ sẽ vào hàng đợi cho NGƯỜI duyệt.

`preds[stem]` = list `[id_lớp, conf, cx, cy, w, h]` của model (lấy qua `get_preds(ds, cfg, "checker")` nếu preds=None).
`L = ds.valid_boxes(stem)` = list `(id_lớp, cx, cy, w, h)` của nhãn (đã bỏ dòng hỏng).
Ngưỡng ở `cfg["second_opinion"]`: conf, min_area_px, fp_conf, iou_missing, iou_match, iou_loose.

Thuật toán gợi ý, với từng ảnh (bỏ qua ảnh không có trong preds hoặc không có file nhãn):
  P = dự đoán có conf >= conf  VÀ diện tích px (w*W * h*H) >= min_area_px
  Với mỗi dự đoán r trong P: lấy các nhãn có IoU(r, nhãn) >= iou_missing  (cands)
   - không có cands                            -> POSSIBLE_MISSING     (model thấy vật mà nhãn không có box)
   - có cands cùng lớp, tốt nhất IoU < iou_loose -> POSSIBLE_LOOSE_BOX  (đúng vật, box lỏng/lệch)
   - không có cands cùng lớp, nhưng cands tốt nhất IoU >= iou_match (khác lớp) -> POSSIBLE_WRONG_CLASS
  Với mỗi dòng nhãn hợp lệ: nếu IoU với MỌI dự đoán (conf >= fp_conf, không lọc diện tích) đều < iou_missing
                                             -> POSSIBLE_FALSE_POS  (box nhãn không khớp vật nào model thấy; Issue.line = số dòng)

Chi tiết các ca biên (test kiểm đúng các ca này)
- `cands` gồm nhãn MỌI lớp có IoU >= iou_missing; "tốt nhất cùng lớp" = cands cùng lớp có IoU lớn nhất; "tốt nhất khác lớp" tương tự với cands khác lớp.
- Thứ tự quyết định cho mỗi dự đoán: (1) cands rỗng -> MISSING. (2) có cands cùng lớp: IoU tốt nhất < iou_loose -> LOOSE_BOX, ngược lại KHÔNG cờ
  (nhãn đúng lớp đã phủ vật này, kể cả khi còn nhãn khác lớp chồng lên). (3) không có cands cùng lớp: nếu IoU tốt nhất khác lớp >= iou_match -> WRONG_CLASS;
  nếu chỉ có khác lớp với IoU trong [iou_missing, iou_match) -> không cờ gì (mơ hồ: để cho FALSE_POS / lần duyệt khác).
- Một dự đoán sinh tối đa MỘT issue (MISSING / LOOSE_BOX / WRONG_CLASS); một ảnh có thể có nhiều issue.
- Thứ tự issue: theo `ds.image_files()` rồi theo thứ tự dự đoán trong `preds[stem]`, cuối cùng là các FALSE_POS theo số dòng; `Issue.image` = stem, `Issue.line` chỉ đặt cho FALSE_POS.

Lưu ý số dòng: dùng `ds.read_label_lines(stem)` (giữ số dòng gốc, kể cả dòng hỏng/trống) để lấy `Issue.line`; `valid_boxes` KHÔNG giữ số dòng.

Tất cả severity WARN; `Issue.extra` nên có {"conf": ...} hoặc {"iou": ...} (hàng đợi duyệt dùng conf để xếp ưu tiên).

Gợi ý
- `iou_xywh` có sẵn. Dòng nhãn hỏng không được làm script chết (dùng `ds.valid_boxes` và `parse_yolo_line` trong try).
- Kết quả phụ thuộc mạnh vào ngưỡng: calibrate chúng ở Bước 3 thay vì đoán.
"""
from ..common import WARN, Issue, iou_xywh, parse_yolo_line  # noqa: F401
from ..model_cache import get_preds  # noqa: F401

CHECK = "second_opinion"


def _labels_with_lines(ds, stem):
    """[(số dòng gốc, (id, cx, cy, w, h))] chỉ các dòng parse được và id lớp hợp lệ."""
    out = []
    for no, text in ds.read_label_lines(stem) or []:
        try:
            b = parse_yolo_line(text)
        except ValueError:
            continue
        if 0 <= b[0] < len(ds.classes):
            out.append((no, b))
    return out


def check_image(ds, stem, preds, cfg):
    c = cfg["second_opinion"]
    size = ds.image_size(stem)
    W, H = size if size else (0, 0)
    labels = _labels_with_lines(ds, stem)
    issues = []

    # --- mỗi dự đoán tin cậy: model thấy vật -> nhãn có phủ không?
    for p in preds:
        pcls, conf, pbox = int(p[0]), float(p[1]), tuple(p[2:6])
        if conf < c["conf"]:
            continue
        if size and pbox[2] * W * pbox[3] * H < c["min_area_px"]:
            continue
        cands = [(iou_xywh(pbox, lb[1:]), lb[0]) for _, lb in labels]
        cands = [(iou, lc) for iou, lc in cands if iou >= c["iou_missing"]]
        same = [iou for iou, lc in cands if lc == pcls]
        other = [(iou, lc) for iou, lc in cands if lc != pcls]
        name = ds.classes[pcls] if 0 <= pcls < len(ds.classes) else str(pcls)
        if not cands:
            issues.append(Issue(CHECK, WARN, "POSSIBLE_MISSING", stem,
                                f"model thấy {name} (conf {conf:.2f}) mà nhãn không có box",
                                extra={"conf": conf, "pred_class": pcls}))
        elif same:
            best = max(same)
            if best < c["iou_loose"]:
                issues.append(Issue(CHECK, WARN, "POSSIBLE_LOOSE_BOX", stem,
                                    f"box {name} lệch/lỏng so với model (IoU {best:.2f})",
                                    extra={"conf": conf, "iou": round(best, 4)}))
        else:
            best_iou, best_cls = max(other)
            if best_iou >= c["iou_match"]:
                lname = ds.classes[best_cls]
                issues.append(Issue(CHECK, WARN, "POSSIBLE_WRONG_CLASS", stem,
                                    f"nhãn {lname} nhưng model nói {name} (conf {conf:.2f}, IoU {best_iou:.2f})",
                                    extra={"conf": conf, "iou": round(best_iou, 4), "label_class": best_cls, "pred_class": pcls}))

    # --- mỗi box nhãn: có dự đoán nào (conf >= fp_conf, không lọc diện tích) khớp không?
    weak = [tuple(p[2:6]) for p in preds if float(p[1]) >= c["fp_conf"]]
    for no, lb in labels:
        best = max((iou_xywh(pb, lb[1:]) for pb in weak), default=0.0)
        if best < c["iou_missing"]:
            issues.append(Issue(CHECK, WARN, "POSSIBLE_FALSE_POS", stem,
                                f"box {ds.classes[lb[0]]} không khớp vật nào model thấy (IoU tốt nhất {best:.2f})",
                                no, {"iou": round(best, 4)}))
    return issues


def run(ds, cfg, preds=None):
    if preds is None:
        preds = get_preds(ds, cfg, "checker")
    issues = []
    for img in ds.image_files():
        stem = img.stem
        if stem not in preds or not ds.label_path(stem).exists():
            continue
        issues.extend(check_image(ds, stem, preds[stem], cfg))
    return issues
