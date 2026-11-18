"""CHECK 2 — Dòng nhãn YOLO: sai định dạng, ID lớp lạ, box tràn ảnh, box rỗng, box lặp.   (Script 2 trong slide)   ★★

Test:  pytest tests/test_label_format.py -q

Mỗi dòng nhãn: `id cx cy w h` (5 số, toạ độ 0–1). Trả về list[Issue]; `Issue.line` = số dòng (đếm từ 1).

| code             | severity | khi nào                                                                  |
|------------------|----------|--------------------------------------------------------------------------|
| BAD_FORMAT       | ERROR    | không đúng 5 cột số (dùng `parse_yolo_line`, bắt `ValueError`)           |
| BAD_CLASS_ID     | ERROR    | id lớp ngoài 0..len(ds.classes)-1                                        |
| BOX_ZERO         | ERROR    | w <= 0 hoặc h <= 0                                                       |
| BOX_OUT_OF_IMAGE | ERROR    | mép box vượt [0,1] quá `cfg["label_format"]["overflow_tol"]`; extra={"overflow": mức tràn} |
| DUP_BOX          | ERROR    | cùng lớp với một dòng TRƯỚC ĐÓ và IoU > `dup_box_iou`; báo ở dòng SAU    |
| BOX_TINY         | WARN     | cạnh ngắn của box (px) < `min_box_px`  (cần `ds.image_size(stem)`)       |
| BOX_HUGE         | WARN     | w*h > `max_box_frac`                                                     |

Gợi ý
- Mép trái = x - w/2, mép phải = x + w/2 (xem câu hỏi "dòng YOLO nào lỗi?" trong slide).
- Một dòng hỏng (BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO) thì `continue`, đừng kiểm tiếp hình học của dòng đó.
- Dòng thiếu cột làm script của slide dừng giữa chừng: đây là lý do phải `try/except`.
- `iou_xywh(a, b)` có sẵn trong common.py.
- Ngưỡng nằm trong `cfg["label_format"]` — đừng viết cứng số vào code.
"""
from ..common import ERROR, WARN, Issue, iou_xywh, parse_yolo_line  # noqa: F401

CHECK = "label_format"


def _overflow(cx, cy, w, h):
    """Mức tràn lớn nhất ra ngoài [0,1] trên 4 cạnh (<= 0 nghĩa là nằm trong ảnh)."""
    return max(0.0 - (cx - w / 2), (cx + w / 2) - 1.0, 0.0 - (cy - h / 2), (cy + h / 2) - 1.0)


def check_file(ds, stem, cfg):
    c = cfg["label_format"]
    n_cls = len(ds.classes)
    size = ds.image_size(stem)              # (W, H) hoặc None nếu ảnh không mở được / không có ảnh
    issues = []
    seen = []                                # [(số dòng, box)] các dòng hợp lệ trước đó, để bắt DUP_BOX

    def add(sev, code, line, msg, **extra):
        issues.append(Issue(CHECK, sev, code, stem, msg, line, extra))

    for ln_no, text in ds.read_label_lines(stem) or []:   # số dòng gốc, đã bỏ dòng trống
        # 1) định dạng: dòng hỏng không được làm chết script
        try:
            cls, cx, cy, w, h = parse_yolo_line(text)
        except ValueError as e:
            add(ERROR, "BAD_FORMAT", ln_no, f"dòng sai định dạng ({e}): {text.strip()!r}")
            continue
        # 2) id lớp
        if not 0 <= cls < n_cls:
            add(ERROR, "BAD_CLASS_ID", ln_no, f"id lớp {cls} ngoài 0..{n_cls - 1}", cls=cls)
            continue
        # 3) box rỗng
        if w <= 0 or h <= 0:
            add(ERROR, "BOX_ZERO", ln_no, f"box rộng/cao <= 0 (w={w}, h={h})")
            continue
        box = (cx, cy, w, h)
        # 4) tràn ảnh (có dung sai)
        over = _overflow(cx, cy, w, h)
        if over > c["overflow_tol"]:
            add(ERROR, "BOX_OUT_OF_IMAGE", ln_no, f"box tràn ảnh {over:.4f}", overflow=round(over, 6))
        # 5) box lặp: cùng lớp với dòng TRƯỚC, IoU cao -> báo ở dòng sau
        for prev_no, (pcls, pbox) in seen:
            if pcls == cls:
                iou = iou_xywh(pbox, box)
                if iou > c["dup_box_iou"]:
                    add(ERROR, "DUP_BOX", ln_no, f"trùng box dòng {prev_no} (IoU {iou:.2f})", iou=round(iou, 4), dup_of=prev_no)
                    break
        seen.append((ln_no, (cls, box)))
        # 6) cảnh báo kích thước
        if size:
            W, H = size
            short = min(w * W, h * H)
            if short < c["min_box_px"]:
                add(WARN, "BOX_TINY", ln_no, f"cạnh ngắn {short:.1f}px < {c['min_box_px']}px", short_px=round(short, 2))
        if w * h > c["max_box_frac"]:
            add(WARN, "BOX_HUGE", ln_no, f"box chiếm {w * h:.0%} ảnh", frac=round(w * h, 4))
    return issues


def run(ds, cfg):
    issues = []
    for lf in ds.label_files():              # ảnh thiếu file nhãn do check missing_labels báo
        issues.extend(check_file(ds, lf.stem, cfg))
    return issues
