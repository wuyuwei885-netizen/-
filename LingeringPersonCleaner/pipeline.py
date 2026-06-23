"""
Core image-processing pipeline for LingeringPersonCleaner.

Goal
----
Click one person in a multi-person photo, keep the selected person, and remove
other detected people from the background.

Pipeline
--------
1. YOLOv8 segmentation detects all person instances.
2. Click coordinate selects the target instance.
3. Non-target person masks are expanded and inpainted.
4. Target mask is feathered into alpha.
5. Target person is composited back onto the repaired background.

Notes
-----
- This project uses OpenCV inpaint as the default background repair backend.
- rembg is optional. If USE_REMBG=1 and rembg is installed, rembg alpha is used
  together with the YOLO target mask. Otherwise the YOLO mask is used directly.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence, Tuple

import cv2
import numpy as np

try:
    from ultralytics import YOLO
except Exception:  # pragma: no cover - handled at runtime with clear message
    YOLO = None

try:
    from rembg import remove as rembg_remove
except Exception:  # pragma: no cover - rembg is optional
    rembg_remove = None

Box = Tuple[int, int, int, int]
Mask = np.ndarray


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class PipelineConfig:
    """Runtime configuration. Values can be overridden by environment variables."""

    yolo_model_path: str = os.environ.get("YOLO_MODEL_PATH", "yolov8n-seg.pt")
    yolo_conf: float = float(os.environ.get("YOLO_CONF", "0.25"))
    yolo_imgsz: int = int(os.environ.get("YOLO_IMGSZ", "1024"))
    debug_save_dir: str = os.environ.get("DEBUG_SAVE_DIR", "debug_steps")
    enable_debug_save: bool = _env_bool("ENABLE_DEBUG_SAVE", True)
    use_rembg: bool = _env_bool("USE_REMBG", False)
    inpaint_radius: int = int(os.environ.get("INPAINT_RADIUS", "5"))
    dilate_kernel: int = int(os.environ.get("DILATE_KERNEL", "13"))
    dilate_iter: int = int(os.environ.get("DILATE_ITER", "2"))
    protect_target_kernel: int = int(os.environ.get("PROTECT_TARGET_KERNEL", "9"))
    alpha_blur_size: int = int(os.environ.get("ALPHA_BLUR_SIZE", "9"))
    alpha_erode_iter: int = int(os.environ.get("ALPHA_ERODE_ITER", "1"))


CONFIG = PipelineConfig()
_yolo_model = None


def _ensure_rgb_uint8(img: np.ndarray) -> np.ndarray:
    """Normalize a Gradio/OpenCV input image to contiguous RGB uint8 HWC."""
    if img is None:
        raise ValueError("输入图像为空。")

    arr = np.asarray(img)
    if arr.ndim == 2:
        arr = cv2.cvtColor(arr, cv2.COLOR_GRAY2RGB)
    elif arr.ndim == 3 and arr.shape[2] == 4:
        arr = arr[:, :, :3]
    elif arr.ndim != 3 or arr.shape[2] != 3:
        raise ValueError(f"不支持的图像形状：{arr.shape}")

    if arr.dtype != np.uint8:
        arr = np.clip(arr, 0, 255).astype(np.uint8)
    return np.ascontiguousarray(arr)


def _odd_kernel(value: int, minimum: int = 1) -> int:
    value = max(int(value), minimum)
    return value if value % 2 == 1 else value + 1


def _ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_yolo_model():
    """Lazy-load YOLO segmentation model."""
    global _yolo_model
    if _yolo_model is None:
        if YOLO is None:
            raise RuntimeError(
                "未安装 ultralytics。请先执行：pip install -r requirements.txt"
            )
        _yolo_model = YOLO(CONFIG.yolo_model_path)
    return _yolo_model


def person_instance_seg(img_rgb: np.ndarray) -> Tuple[List[Mask], List[Box]]:
    """Detect person instances and return masks plus xyxy boxes in original size."""
    img_rgb = _ensure_rgb_uint8(img_rgb)
    h, w = img_rgb.shape[:2]

    model = get_yolo_model()

    # Ultralytics accepts OpenCV BGR ndarray well. Gradio gives RGB, so convert.
    img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)
    result = model(
        img_bgr,
        conf=CONFIG.yolo_conf,
        imgsz=CONFIG.yolo_imgsz,
        verbose=False,
    )[0]

    person_masks: List[Mask] = []
    person_boxes: List[Box] = []

    if result.masks is None or result.boxes is None:
        return person_masks, person_boxes

    masks_data = result.masks.data
    for i, box in enumerate(result.boxes):
        cls_id = int(box.cls.item())
        if cls_id != 0:  # COCO class 0 = person
            continue

        x1, y1, x2, y2 = box.xyxy.cpu().numpy().astype(int)[0].tolist()
        x1 = int(np.clip(x1, 0, w - 1))
        y1 = int(np.clip(y1, 0, h - 1))
        x2 = int(np.clip(x2, 0, w - 1))
        y2 = int(np.clip(y2, 0, h - 1))
        if x2 <= x1 or y2 <= y1:
            continue

        mask_i = masks_data[i].cpu().numpy().astype(np.float32)
        if mask_i.shape[:2] != (h, w):
            mask_i = cv2.resize(mask_i, (w, h), interpolation=cv2.INTER_LINEAR)
        mask_i = (mask_i > 0.5).astype(np.uint8)

        # Remove tiny noise components.
        mask_i = cv2.morphologyEx(mask_i, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        if int(mask_i.sum()) < 20:
            continue

        person_masks.append(mask_i)
        person_boxes.append((x1, y1, x2, y2))

    return person_masks, person_boxes


def select_target_by_click(
    person_masks: Sequence[Mask],
    person_boxes: Sequence[Box],
    click_xy: Tuple[int, int],
    img_shape: Tuple[int, int, int],
) -> Tuple[int, Tuple[int, int], str]:
    """
    Select target person by click.

    Priority:
    1. Click falls inside a person mask.
    2. Click falls inside a person bbox.
    3. Nearest bbox center.
    """
    h, w = img_shape[:2]
    x_click, y_click = click_xy
    x = int(np.clip(x_click, 0, w - 1))
    y = int(np.clip(y_click, 0, h - 1))

    mask_hits = []
    for idx, mask in enumerate(person_masks):
        if mask.shape[:2] == (h, w) and mask[y, x] > 0:
            area = int(mask.sum())
            mask_hits.append((area, idx))
    if mask_hits:
        mask_hits.sort(key=lambda item: item[0])
        return mask_hits[0][1], (x, y), "点击点命中人物 mask"

    bbox_hits = []
    for idx, box in enumerate(person_boxes):
        x1, y1, x2, y2 = box
        if x1 <= x <= x2 and y1 <= y <= y2:
            area = max((x2 - x1) * (y2 - y1), 1)
            bbox_hits.append((area, idx))
    if bbox_hits:
        bbox_hits.sort(key=lambda item: item[0])
        return bbox_hits[0][1], (x, y), "点击点命中人物 bbox"

    best_idx = -1
    best_dist2 = float("inf")
    for idx, box in enumerate(person_boxes):
        x1, y1, x2, y2 = box
        cx = 0.5 * (x1 + x2)
        cy = 0.5 * (y1 + y2)
        dist2 = (cx - x) ** 2 + (cy - y) ** 2
        if dist2 < best_dist2:
            best_dist2 = dist2
            best_idx = idx

    if best_idx < 0:
        raise RuntimeError("未检测到人物，请换一张更清晰的多人照片。")
    return best_idx, (x, y), "点击点未命中实例，已选择最近人物"


def build_non_target_mask(
    person_masks: Sequence[Mask],
    target_idx: int,
    dilate_kernel: int,
    dilate_iter: int,
    protect_target_kernel: int,
) -> np.ndarray:
    """Merge all non-target person masks and protect the selected target area."""
    if not person_masks:
        raise RuntimeError("没有可用的人物 mask。")

    h, w = person_masks[0].shape[:2]
    combined = np.zeros((h, w), dtype=np.uint8)
    kernel_size = _odd_kernel(dilate_kernel, 3)
    kernel = np.ones((kernel_size, kernel_size), np.uint8)

    for idx, mask in enumerate(person_masks):
        if idx == target_idx:
            continue
        pm = mask.astype(np.uint8)
        pm = cv2.dilate(pm, kernel, iterations=max(int(dilate_iter), 0))
        combined = np.maximum(combined, pm)

    protect_size = _odd_kernel(protect_target_kernel, 1)
    protect_kernel = np.ones((protect_size, protect_size), np.uint8)
    target_protect = cv2.dilate(
        person_masks[target_idx].astype(np.uint8), protect_kernel, iterations=1
    )
    combined[target_protect > 0] = 0

    # Fill small holes and smooth mask shape.
    close_kernel = np.ones((5, 5), np.uint8)
    combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, close_kernel)
    return (combined > 0).astype(np.uint8)


def opencv_inpaint(img_rgb: np.ndarray, inpaint_mask_u8: np.ndarray) -> np.ndarray:
    """Repair masked regions with OpenCV Telea inpaint."""
    img_rgb = _ensure_rgb_uint8(img_rgb)
    mask = (inpaint_mask_u8 > 0).astype(np.uint8) * 255
    if int(mask.sum()) == 0:
        return img_rgb.copy()

    img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)
    repaired_bgr = cv2.inpaint(
        img_bgr,
        mask,
        inpaintRadius=max(int(CONFIG.inpaint_radius), 1),
        flags=cv2.INPAINT_TELEA,
    )
    return cv2.cvtColor(repaired_bgr, cv2.COLOR_BGR2RGB)


def remove_non_target_single_pass(
    img_rgb: np.ndarray,
    person_masks: Sequence[Mask],
    target_idx: int,
) -> Tuple[np.ndarray, np.ndarray]:
    """Inpaint all non-target people in one pass. Usually faster and more stable."""
    remove_mask = build_non_target_mask(
        person_masks=person_masks,
        target_idx=target_idx,
        dilate_kernel=CONFIG.dilate_kernel,
        dilate_iter=CONFIG.dilate_iter,
        protect_target_kernel=CONFIG.protect_target_kernel,
    )
    background = opencv_inpaint(img_rgb, remove_mask)
    return background, remove_mask


def remove_non_target_multi_pass(
    img_rgb: np.ndarray,
    person_masks: Sequence[Mask],
    target_idx: int,
) -> Tuple[np.ndarray, np.ndarray]:
    """Inpaint non-target people one by one for comparison."""
    if not person_masks:
        raise RuntimeError("没有可用的人物 mask。")

    h, w = person_masks[0].shape[:2]
    background = img_rgb.copy()
    union_mask = np.zeros((h, w), dtype=np.uint8)

    protect_size = _odd_kernel(CONFIG.protect_target_kernel, 1)
    target_protect = cv2.dilate(
        person_masks[target_idx].astype(np.uint8),
        np.ones((protect_size, protect_size), np.uint8),
        iterations=1,
    )

    kernel_size = _odd_kernel(CONFIG.dilate_kernel, 3)
    kernel = np.ones((kernel_size, kernel_size), np.uint8)
    for idx, mask in enumerate(person_masks):
        if idx == target_idx:
            continue
        pm = cv2.dilate(
            mask.astype(np.uint8), kernel, iterations=max(int(CONFIG.dilate_iter), 0)
        )
        pm[target_protect > 0] = 0
        background = opencv_inpaint(background, pm)
        union_mask = np.maximum(union_mask, pm)

    return background, union_mask


def extract_target_alpha(img_rgb: np.ndarray, target_mask: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Extract foreground RGB and alpha.

    Default alpha = YOLO target mask. Optional rembg alpha is available via
    USE_REMBG=1, but the final alpha is still constrained by YOLO target mask.
    """
    img_rgb = _ensure_rgb_uint8(img_rgb)
    h, w = img_rgb.shape[:2]
    mask = target_mask.astype(np.float32)
    if mask.shape[:2] != (h, w):
        mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)

    alpha = np.clip(mask, 0.0, 1.0)

    if CONFIG.use_rembg:
        if rembg_remove is None:
            raise RuntimeError(
                "USE_REMBG=1，但未安装 rembg。请执行：pip install -r requirements-optional.txt"
            )
        out = rembg_remove(img_rgb)
        if out.ndim == 3 and out.shape[2] == 4:
            rembg_alpha = out[..., 3].astype(np.float32) / 255.0
            if rembg_alpha.shape[:2] != (h, w):
                rembg_alpha = cv2.resize(rembg_alpha, (w, h), interpolation=cv2.INTER_LINEAR)
            alpha = rembg_alpha * alpha

    return img_rgb.copy(), alpha


def feather_alpha(alpha: np.ndarray, blur_size: int, erode_iter: int) -> np.ndarray:
    """Slightly erode and blur alpha for softer edges."""
    alpha_u8 = (np.clip(alpha, 0.0, 1.0) * 255).astype(np.uint8)

    if int(erode_iter) > 0:
        alpha_u8 = cv2.erode(alpha_u8, np.ones((3, 3), np.uint8), iterations=int(erode_iter))

    blur_size = _odd_kernel(blur_size, 1)
    if blur_size > 1:
        alpha_u8 = cv2.GaussianBlur(alpha_u8, (blur_size, blur_size), 0)

    return np.clip(alpha_u8.astype(np.float32) / 255.0, 0.0, 1.0)


def composite_person(background_rgb: np.ndarray, person_rgb: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    """Alpha composite selected person onto repaired background."""
    background_rgb = _ensure_rgb_uint8(background_rgb)
    person_rgb = _ensure_rgb_uint8(person_rgb)
    h, w = background_rgb.shape[:2]

    if person_rgb.shape[:2] != (h, w):
        person_rgb = cv2.resize(person_rgb, (w, h), interpolation=cv2.INTER_LINEAR)
    if alpha.shape[:2] != (h, w):
        alpha = cv2.resize(alpha, (w, h), interpolation=cv2.INTER_LINEAR)

    alpha_3 = np.repeat(alpha[..., None], 3, axis=2).astype(np.float32)
    bg = background_rgb.astype(np.float32)
    fg = person_rgb.astype(np.float32)
    result = fg * alpha_3 + bg * (1.0 - alpha_3)
    return np.clip(result + 0.5, 0, 255).astype(np.uint8)


def draw_click_preview(img_rgb: np.ndarray, x: int, y: int) -> np.ndarray:
    """Draw a visible click marker on the preview image."""
    img_rgb = _ensure_rgb_uint8(img_rgb)
    h, w = img_rgb.shape[:2]
    x = int(np.clip(x, 0, w - 1))
    y = int(np.clip(y, 0, h - 1))

    vis = img_rgb.copy()
    radius = max(8, min(h, w) // 80)
    thickness = max(2, min(h, w) // 260)
    cv2.circle(vis, (x, y), radius, (255, 0, 0), thickness)
    cv2.line(vis, (x - radius, y), (x + radius, y), (255, 0, 0), thickness)
    cv2.line(vis, (x, y - radius), (x, y + radius), (255, 0, 0), thickness)
    return vis


def mask_to_rgb(mask: np.ndarray) -> np.ndarray:
    """Convert a single-channel mask/alpha to RGB visualization."""
    mask_u8 = (np.clip(mask, 0.0, 1.0) * 255).astype(np.uint8)
    return np.repeat(mask_u8[..., None], 3, axis=2)


def draw_bbox_and_click(
    img_rgb: np.ndarray,
    bbox: Box,
    click_xy: Tuple[int, int],
    label: str = "target",
) -> np.ndarray:
    """Visualize selected bbox and click point."""
    vis = _ensure_rgb_uint8(img_rgb).copy()
    x1, y1, x2, y2 = bbox
    cv2.rectangle(vis, (x1, y1), (x2, y2), (255, 0, 0), 3)
    x, y = click_xy
    cv2.circle(vis, (x, y), 10, (255, 0, 0), 3)
    cv2.putText(
        vis,
        label,
        (x1, max(y1 - 8, 20)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (255, 0, 0),
        2,
        cv2.LINE_AA,
    )
    return vis


def save_debug_steps(
    *,
    run_id: str,
    img_rgb: np.ndarray,
    target_mask: np.ndarray,
    remove_mask: np.ndarray,
    alpha_soft: np.ndarray,
    bbox_vis: np.ndarray,
    background_single: np.ndarray,
    background_multi: np.ndarray,
    result_single: np.ndarray,
    result_multi: np.ndarray,
) -> Path:
    """Save reproducible debug images for GitHub/demo/report use."""
    run_dir = _ensure_dir(Path(CONFIG.debug_save_dir) / run_id)

    def write_rgb(name: str, arr: np.ndarray) -> None:
        cv2.imwrite(str(run_dir / name), cv2.cvtColor(_ensure_rgb_uint8(arr), cv2.COLOR_RGB2BGR))

    write_rgb("00_selected_bbox.png", bbox_vis)
    write_rgb("01_input.png", img_rgb)
    cv2.imwrite(str(run_dir / "02_target_mask.png"), (target_mask > 0).astype(np.uint8) * 255)
    cv2.imwrite(str(run_dir / "03_remove_mask.png"), (remove_mask > 0).astype(np.uint8) * 255)
    cv2.imwrite(str(run_dir / "04_alpha_soft.png"), (np.clip(alpha_soft, 0, 1) * 255).astype(np.uint8))
    write_rgb("05_background_single_pass.png", background_single)
    write_rgb("06_background_multi_pass.png", background_multi)
    write_rgb("07_result_single_pass.png", result_single)
    write_rgb("08_result_multi_pass.png", result_multi)
    return run_dir


def process_image_click(img_rgb: np.ndarray, click_x: int, click_y: int):
    """
    Main entry for Gradio.

    Returns
    -------
    tuple
        result_single, result_multi, bg_before, bg_after_single, bg_after_multi,
        target_mask_vis, remove_mask_vis, alpha_vis, bbox_vis, info_text
    """
    img_rgb = _ensure_rgb_uint8(img_rgb)
    h, w = img_rgb.shape[:2]
    run_id = time.strftime("%Y%m%d_%H%M%S")

    person_masks, person_boxes = person_instance_seg(img_rgb)
    if not person_masks:
        raise RuntimeError("未检测到人物。建议换一张人物更清晰、遮挡更少的照片。")

    target_idx, click_xy, select_reason = select_target_by_click(
        person_masks, person_boxes, (int(click_x), int(click_y)), img_rgb.shape
    )
    target_mask = person_masks[target_idx].astype(np.uint8)

    t0 = time.perf_counter()
    background_single, remove_mask_single = remove_non_target_single_pass(
        img_rgb, person_masks, target_idx
    )
    t1 = time.perf_counter()

    t2 = time.perf_counter()
    background_multi, remove_mask_multi = remove_non_target_multi_pass(
        img_rgb, person_masks, target_idx
    )
    t3 = time.perf_counter()

    person_rgb, alpha_raw = extract_target_alpha(img_rgb, target_mask)
    alpha_soft = feather_alpha(
        alpha_raw,
        blur_size=CONFIG.alpha_blur_size,
        erode_iter=CONFIG.alpha_erode_iter,
    )

    # Final result: single-pass is usually better for speed; multi-pass is retained for comparison.
    result_single = composite_person(background_single, person_rgb, alpha_soft)
    result_multi = composite_person(background_multi, person_rgb, alpha_soft)

    bbox_vis = draw_bbox_and_click(
        img_rgb, person_boxes[target_idx], click_xy, label=f"target #{target_idx}"
    )
    target_mask_vis = mask_to_rgb(target_mask.astype(np.float32))
    remove_mask_vis = mask_to_rgb(remove_mask_single.astype(np.float32))
    alpha_vis = mask_to_rgb(alpha_soft)

    run_dir_text = "未保存"
    if CONFIG.enable_debug_save:
        run_dir = save_debug_steps(
            run_id=run_id,
            img_rgb=img_rgb,
            target_mask=target_mask,
            remove_mask=remove_mask_single,
            alpha_soft=alpha_soft,
            bbox_vis=bbox_vis,
            background_single=background_single,
            background_multi=background_multi,
            result_single=result_single,
            result_multi=result_multi,
        )
        run_dir_text = str(run_dir)

    single_time = t1 - t0
    multi_time = t3 - t2
    speed_note = "一次性修复更快" if single_time <= multi_time else "逐人修复更快"
    info_text = (
        f"✅ 处理完成\n\n"
        f"- 图像尺寸：{w} × {h}\n"
        f"- 检测到人物：{len(person_masks)} 个\n"
        f"- 选中人物索引：{target_idx}\n"
        f"- 选择依据：{select_reason}\n"
        f"- 一次性修复耗时：{single_time:.3f} 秒\n"
        f"- 逐人修复耗时：{multi_time:.3f} 秒\n"
        f"- 速度结论：{speed_note}\n"
        f"- Debug 输出目录：`{run_dir_text}`"
    )

    return (
        result_single,
        result_multi,
        img_rgb,
        background_single,
        background_multi,
        target_mask_vis,
        remove_mask_vis,
        alpha_vis,
        bbox_vis,
        info_text,
    )


if __name__ == "__main__":
    print("请通过 app.py 启动 Gradio 界面：python app.py")
