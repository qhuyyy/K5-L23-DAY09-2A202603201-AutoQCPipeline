"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |

Bẫy cần nghĩ tới (có test cho từng cái)
- Một file có NHIỀU dòng lỗi: số dòng trong `issues` là số dòng GỐC. Nếu xoá từng dòng một thì số dòng lệch.
  Gom theo file, rồi ghi lại MỘT lần.
- Sau khi cắt, box có thể không còn diện tích (nằm hẳn ngoài ảnh): lúc đó xoá dòng thay vì ghi box rỗng.
- Một dòng có 2 lỗi (vd. BOX_OUT_OF_IMAGE + DUP_BOX): xoá dòng thắng, chỉ ghi 1 fix `drop_line`, không ghi thêm `clip_box`. Dòng trống ở giữa file vẫn đếm vào số dòng gốc.
- Ảnh vừa bị xoá (DUP_IMAGE_*...) mà còn issue dòng của chính nó: bỏ qua êm, không được báo lỗi/chết.
- Không động tới lỗi WARN (cảnh báo là việc của người). Không sửa file ở `data/raw/` — chỉ sửa `ds`.
- Chạy lần 2 trên dữ liệu đã sửa phải không làm gì thêm (idempotent) — NGOẠI LỆ duy nhất: `needs_label` được ghi lại mỗi lần còn lỗi `MISSING_LABEL_FILE` (vì ảnh vẫn chưa có nhãn).

- `needs_label` KHÔNG tạo file nhãn rỗng (rỗng = "ảnh nền", khác với "chưa gán"). `review_queue` sẽ đẩy ảnh này lên đầu hàng đợi cho người.

Gợi ý: `yaml.safe_load / safe_dump`.
"""
from collections import defaultdict  # noqa: F401

import yaml  # noqa: F401

from ..common import ERROR, parse_yolo_line  # noqa: F401

DROP_CODES = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}
CLIP_CODES = {"BOX_OUT_OF_IMAGE"}
REMOVE_CODES = {"LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"}          # + mọi mã bắt đầu bằng DUP_IMAGE_


def _is_remove(code):
    return code in REMOVE_CODES or code.startswith("DUP_IMAGE_")


def _fx(image, line, action, before, after):
    return {"image": image, "line": line, "action": action, "before": before, "after": after}


def _clip(text):
    """Cắt box về [0,1]. Trả về dòng mới, hoặc None nếu box không còn diện tích (nằm hẳn ngoài ảnh)."""
    cls, cx, cy, w, h = parse_yolo_line(text)
    x1, x2 = max(0.0, cx - w / 2), min(1.0, cx + w / 2)
    y1, y2 = max(0.0, cy - h / 2), min(1.0, cy + h / 2)
    if x2 <= x1 or y2 <= y1:
        return None
    nw, nh = x2 - x1, y2 - y1
    return f"{cls} {x1 + nw / 2:.6f} {y1 + nh / 2:.6f} {nw:.6f} {nh:.6f}"


def _remove_image(ds, stem):
    """Xoá mọi file ảnh có stem này (mọi đuôi) + file nhãn. Trả về list tên file đã xoá."""
    removed = []
    for p in ds.image_files():
        if p.stem == stem:
            p.unlink()
            removed.append(p.name)
    lp = ds.label_path(stem)
    if lp.exists():
        lp.unlink()
        removed.append(lp.name)
    return removed


def _fix_label_file(ds, stem, drop_lines, clip_lines):
    """Sửa MỘT file nhãn theo số dòng GỐC, ghi lại một lần. Xoá dòng thắng cắt box."""
    lp = ds.label_path(stem)
    if not lp.exists():                     # ảnh đã bị xoá / chưa có nhãn: bỏ qua êm
        return []
    raw = lp.read_text(encoding="utf-8", errors="replace").splitlines()
    fixes, out = [], []
    for no, text in enumerate(raw, 1):       # đếm cả dòng trống -> khớp số dòng gốc của check
        if no in drop_lines:
            fixes.append(_fx(stem, no, "drop_line", text, ""))
            continue
        if no in clip_lines:
            try:
                new = _clip(text)
            except ValueError:               # dòng hỏng mà không bị báo BAD_FORMAT: an toàn nhất là xoá
                new = None
            if new is None:
                fixes.append(_fx(stem, no, "drop_line", text, ""))
                continue
            fixes.append(_fx(stem, no, "clip_box", text, new))
            out.append(new)
            continue
        out.append(text)
    if fixes:
        lp.write_text("".join(l + "\n" for l in out), encoding="utf-8")
    return fixes


def fix(ds, issues, cfg):
    errors = [i for i in issues if i.severity == ERROR]
    fixes = []

    # 1) Lỗi cấp ảnh: xoá ảnh + nhãn (làm trước để bỏ qua issue dòng của ảnh đã xoá)
    removed = set()
    for i in errors:
        if _is_remove(i.code) and i.image not in removed:
            files = _remove_image(ds, i.image)
            removed.add(i.image)
            if files:
                fixes.append(_fx(i.image, "", "remove_image", ", ".join(files), f"(đã xoá: {i.code})"))

    # 2) Lỗi dòng: gom theo file
    drops, clips = defaultdict(set), defaultdict(set)
    for i in errors:
        if i.image in removed or i.line is None:
            continue
        if i.code in DROP_CODES:
            drops[i.image].add(i.line)
        elif i.code in CLIP_CODES:
            clips[i.image].add(i.line)
    for stem in sorted(set(drops) | set(clips)):
        fixes.extend(_fix_label_file(ds, stem, drops[stem], clips[stem] - drops[stem]))

    # 3) Thiếu file nhãn: không bịa nhãn, chỉ ghi lại để chuyển người gán
    for stem in sorted({i.image for i in errors if i.code == "MISSING_LABEL_FILE"} - removed):
        if not ds.label_path(stem).exists():
            fixes.append(_fx(stem, "", "needs_label", "(không có file)", "chuyển người gán"))

    # 4) Tên lớp trong data.yaml
    if any(i.code == "BAD_CLASS_NAME" for i in errors):
        d = {}
        if ds.yaml_path.exists():
            d = yaml.safe_load(ds.yaml_path.read_text(encoding="utf-8")) or {}
        before = d.get("names")
        want = {k: n for k, n in enumerate(cfg["classes"])}
        if ds.yaml_names() != want:
            d["names"] = want
            ds.yaml_path.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf-8")
            fixes.append(_fx("data.yaml", "", "rename_classes", str(before), str(want)))
    return fixes
