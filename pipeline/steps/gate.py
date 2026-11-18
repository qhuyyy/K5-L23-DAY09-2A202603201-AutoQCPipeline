"""BƯỚC 4 — Cửa chặn: quyết định Release / Hold / Rework.   ★

Test:  pytest tests/test_gate.py -q

Cây quyết định Day 07 (slide Day 09: "Lỗi bắt buộc chặn pipeline; lỗi cảnh báo chuyển người xem"):

  còn ≥ 1 lỗi bắt buộc (severity ERROR)                          -> "Rework"
  không còn lỗi bắt buộc, nhưng tỉ lệ ẢNH còn cảnh báo
      >= cfg["gate"]["warn_ratio_hold"]                          -> "Hold"
  còn lại                                                        -> "Release"

Tỉ lệ cảnh báo = (số ẢNH khác nhau có ≥ 1 cảnh báo) / (tổng số ảnh).  Chú ý:
- chỉ đếm issue có `image` nằm trong `image_stems` (bỏ "<dataset>", "data.yaml");
- bỏ qua ảnh nằm trong `reviewed` (người đã xem, cảnh báo của ảnh đó coi như đã xử lý) — nhưng LỖI BẮT BUỘC thì không bao giờ được bỏ qua;
- mẫu số là số ảnh, không phải số issue.

Trả về dict: decision, n_errors, n_warn_images, n_images, warn_ratio (làm tròn 4 chữ số), reasons (list[str], giải thích bằng tiếng Việt, có số liệu).
"""
from ..common import ERROR, WARN  # noqa: F401


def decide(issues, image_stems, cfg, reviewed=frozenset()):
    stems = set(image_stems)
    reviewed = set(reviewed)
    limit = cfg["gate"]["warn_ratio_hold"]

    # Lỗi bắt buộc: đếm TẤT CẢ (kể cả lỗi cấp dataset như data.yaml, kể cả ảnh đã duyệt)
    errors = [i for i in issues if i.severity == ERROR]
    # Cảnh báo: đếm theo ẢNH, chỉ ảnh thuộc dataset và chưa được người duyệt
    warn_images = {i.image for i in issues if i.severity == WARN and i.image in stems and i.image not in reviewed}

    n_images = len(stems)
    ratio = round(len(warn_images) / n_images, 4) if n_images else 0.0

    reasons = []
    if errors:
        codes = sorted({i.code for i in errors})
        decision = "Rework"
        reasons.append(f"còn {len(errors)} lỗi bắt buộc ({', '.join(codes)}): phải sửa trước khi xuất")
    elif ratio >= limit:
        decision = "Hold"
        reasons.append(f"{len(warn_images)}/{n_images} ảnh ({ratio:.1%}) còn cảnh báo chưa người duyệt, >= ngưỡng {limit:.0%}")
    else:
        decision = "Release"
        reasons.append(f"0 lỗi bắt buộc; {len(warn_images)}/{n_images} ảnh ({ratio:.1%}) còn cảnh báo, < ngưỡng {limit:.0%}")

    return {
        "decision": decision,
        "n_errors": len(errors),
        "n_warn_images": len(warn_images),
        "n_images": n_images,
        "warn_ratio": ratio,
        "reasons": reasons,
    }
