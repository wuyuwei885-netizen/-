"""
多人照片：点击锁定某个人物，保留该人物 + 背景修复（逐人修复 vs 一次性修复）

- YOLOv8-seg 做人物实例分割
- 用户用鼠标点击选择目标人物（通过 bbox/距离选中）
- LaMa/其他算法修掉其他所有人物，得到干净背景
- rembg 提取该人物 alpha（颜色用原图）
- alpha 羽化后，与背景做融合
- 中间结果（原图、mask、修复前后、alpha、最终结果）保存到 debug_steps/ 目录
- process_image_click 会把所有中间结果返回给 Gradio 界面显示
- ✅ 所有返回图像的尺寸与输入图像保持完全一致
"""

import os
import time
from typing import List, Tuple

import cv2
import numpy as np

# 下面两项依赖需要你在环境中安装好：
# pip install ultralytics rembg
try:
    from ultralytics import YOLO
except Exception:
    YOLO = None

try:
    from rembg import remove as rembg_remove
except Exception:
    rembg_remove = None


# ---------------------------------------------------------------------------
# 全局配置
# ---------------------------------------------------------------------------

YOLO_MODEL_PATH = os.environ.get("YOLO_MODEL_PATH", "yolov8n-seg.pt")
DEBUG_SAVE_DIR = "debug_steps"
ENABLE_DEBUG_SAVE = True


_yolo_model = None  # 懒加载


def _ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def get_yolo_model():
    """懒加载 YOLOv8-seg 模型。"""
    global _yolo_model
    if _yolo_model is None:
        if YOLO is None:
            raise RuntimeError("未安装 ultralytics，请先 `pip install ultralytics`。")
        _yolo_model = YOLO(YOLO_MODEL_PATH)
    return _yolo_model


# ---------------------------------------------------------------------------
# 1. 人物实例分割
# ---------------------------------------------------------------------------

def person_instance_seg(img_rgb: np.ndarray) -> Tuple[List[np.ndarray], List[Tuple[int, int, int, int]]]:
    """
    使用 YOLOv8-seg 做人物实例分割，只保留 `person` 类别的 mask 和 bbox。

    返回:
        person_masks: List[H,W] bool / uint8
        person_boxes: List[x1,y1,x2,y2]
    """
    model = get_yolo_model()

    # YOLO 期望 BGR，这里转换一下
    img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)
    results = model(img_bgr, verbose=False)[0]

    person_masks = []
    person_boxes = []

    if results.masks is None:
        return person_masks, person_boxes

    for i, box in enumerate(results.boxes):
        cls_id = int(box.cls.item())
        # COCO 中 0 是 person
        if cls_id != 0:
            continue

        xyxy = box.xyxy.cpu().numpy().astype(int)[0]
        x1, y1, x2, y2 = xyxy.tolist()

        mask_i = results.masks.data[i].cpu().numpy()  # [H,W] float
        mask_i = (mask_i > 0.5).astype(np.uint8)

        person_masks.append(mask_i)
        person_boxes.append((x1, y1, x2, y2))

    return person_masks, person_boxes


# ---------------------------------------------------------------------------
# 2. 根据点击坐标选目标人物
# ---------------------------------------------------------------------------

def select_target_by_click(
    person_boxes: List[Tuple[int, int, int, int]],
    click_xy: Tuple[int, int],
    img_shape: Tuple[int, int, int],
) -> Tuple[int, Tuple[int, int]]:
    """
    优先选择“点击点落在 bbox 内”的人物；
    如果没有任何 bbox 包含点击点，则按 bbox 中心点与点击点的距离最近的选。

    返回:
        target_idx: 选中的人物索引
        (x, y): 修正后的点击坐标（裁剪到图片范围内）
    """
    H, W = img_shape[:2]
    x_click, y_click = click_xy

    x = int(np.clip(x_click, 0, W - 1))
    y = int(np.clip(y_click, 0, H - 1))

    # 1) 先找所有包含点击点的 bbox
    candidates = []
    for idx, box in enumerate(person_boxes):
        x1, y1, x2, y2 = box
        if x1 <= x <= x2 and y1 <= y <= y2:
            area = max((x2 - x1) * (y2 - y1), 1e-6)
            candidates.append((area, idx))

    if candidates:
        # 面积最小的一般是“最近的前景人”
        candidates.sort(key=lambda t: t[0])
        best_idx = candidates[0][1]
        return best_idx, (x, y)

    # 2) 没有 bbox 包含点击点时，找 bbox 中心点距离最近的
    best_idx = -1
    best_dist2 = 1e18
    for idx, box in enumerate(person_boxes):
        x1, y1, x2, y2 = box
        cx = 0.5 * (x1 + x2)
        cy = 0.5 * (y1 + y2)
        dist2 = (cx - x) ** 2 + (cy - y) ** 2
        if dist2 < best_dist2:
            best_dist2 = dist2
            best_idx = idx

    if best_idx < 0:
        raise RuntimeError("未检测到任何人物，请换一张图试试。")

    return best_idx, (x, y)


# ---------------------------------------------------------------------------
# 3. “LaMa” 修复函数（这里用 cv2.inpaint 简化，你可以替换为真正的 LaMa）
# ---------------------------------------------------------------------------

def lama_inpaint(img_rgb: np.ndarray, inpaint_mask_u8: np.ndarray) -> np.ndarray:
    """
    占位实现：用 OpenCV 的 inpaint 代替 LaMa。
    如果你有自己的 LaMa 推理脚本，可以在这里替换实现。

    参数:
        img_rgb: H,W,3  RGB uint8
        inpaint_mask_u8: H,W  uint8，0/255

    返回:
        inpainted_rgb: H,W,3  RGB uint8
    """
    img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)
    # OpenCV 的 inpaint 需要 0/255 的单通道 mask
    mask = (inpaint_mask_u8 > 0).astype(np.uint8) * 255
    inpaint_bgr = cv2.inpaint(img_bgr, mask, 3, cv2.INPAINT_TELEA)
    inpaint_rgb = cv2.cvtColor(inpaint_bgr, cv2.COLOR_BGR2RGB)
    return inpaint_rgb


# ---------------------------------------------------------------------------
# 4. rembg 提取人物 + alpha
# ---------------------------------------------------------------------------

def extract_person_with_rembg(img_rgb: np.ndarray, M_target: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    用 rembg 提取整张图的前景，然后用目标人物的 mask 进行约束。

    返回:
        person_rgb: H,W,3  uint8
        alpha: H,W float32 0~1
    """
    H, W = img_rgb.shape[:2]

    if rembg_remove is None:
        # 没有 rembg 时，用目标人物 mask 直接当 alpha
        alpha = M_target.astype(np.float32)
        person_rgb = img_rgb.copy()
        return person_rgb, alpha

    # rembg 默认期望 RGBA，内部会自己转换；这里直接给 RGB 即可
    out = rembg_remove(img_rgb)  # 得到 RGBA
    if out.shape[2] == 4:
        rgb = out[..., :3]
        a = out[..., 3].astype(np.float32) / 255.0
    else:
        rgb = out
        a = np.ones((H, W), dtype=np.float32)

    # 只保留目标人物区域
    M_float = M_target.astype(np.float32)
    alpha = a * M_float

    person_rgb = img_rgb.copy()
    return person_rgb, alpha


# ---------------------------------------------------------------------------
# 5. alpha 羽化 & 融合
# ---------------------------------------------------------------------------

def feather_alpha(alpha: np.ndarray, blur_size: int = 7, erode_iter: int = 1) -> np.ndarray:
    """
    对 alpha 做一点腐蚀 + 高斯模糊，边缘更柔和。
    """
    alpha_u8 = (np.clip(alpha, 0.0, 1.0) * 255).astype(np.uint8)

    if erode_iter > 0:
        kernel = np.ones((3, 3), np.uint8)
        alpha_u8 = cv2.erode(alpha_u8, kernel, iterations=erode_iter)

    if blur_size > 1:
        k = blur_size if blur_size % 2 == 1 else blur_size + 1
        alpha_u8 = cv2.GaussianBlur(alpha_u8, (k, k), 0)

    alpha_f = alpha_u8.astype(np.float32) / 255.0
    return np.clip(alpha_f, 0.0, 1.0)


def composite_person(background_rgb: np.ndarray, person_rgb: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    """
    背景 + 前景 + alpha 做融合。
    """
    H, W = background_rgb.shape[:2]
    if person_rgb.shape[:2] != (H, W):
        person_rgb = cv2.resize(person_rgb, (W, H), interpolation=cv2.INTER_LINEAR)
    if alpha.shape[:2] != (H, W):
        alpha = cv2.resize(alpha, (W, H), interpolation=cv2.INTER_LINEAR)

    alpha_3 = np.stack([alpha] * 3, axis=-1)
    bg_f = background_rgb.astype(np.float32) / 255.0
    fg_f = person_rgb.astype(np.float32) / 255.0

    comp = fg_f * alpha_3 + bg_f * (1.0 - alpha_3)
    comp_u8 = np.clip(comp * 255.0 + 0.5, 0, 255).astype(np.uint8)
    return comp_u8


# ---------------------------------------------------------------------------
# 6. 保存中间结果
# ---------------------------------------------------------------------------

def save_debug_steps(
    img_rgb: np.ndarray,
    M_target: np.ndarray,
    background_multi: np.ndarray,
    background_single: np.ndarray,
    alpha_soft: np.ndarray,
    result_multi: np.ndarray,
    result_single: np.ndarray,
    bbox: Tuple[int, int, int, int],
    run_id: str,
    save_dir: str = DEBUG_SAVE_DIR,
):
    _ensure_dir(save_dir)
    run_dir = os.path.join(save_dir, run_id)
    _ensure_dir(run_dir)

    # 原图
    cv2.imwrite(
        os.path.join(run_dir, "01_input_rgb.png"),
        cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR),
    )

    # 目标人物 mask
    mask_u8 = (M_target.astype(np.uint8) * 255)
    cv2.imwrite(os.path.join(run_dir, "02_mask_target.png"), mask_u8)

    # 背景（逐人修复）
    cv2.imwrite(
        os.path.join(run_dir, "03_background_multi.png"),
        cv2.cvtColor(background_multi, cv2.COLOR_RGB2BGR),
    )

    # 背景（一次性修复）
    cv2.imwrite(
        os.path.join(run_dir, "04_background_single.png"),
        cv2.cvtColor(background_single, cv2.COLOR_RGB2BGR),
    )

    # alpha 可视化
    alpha_u8 = (np.clip(alpha_soft, 0.0, 1.0) * 255).astype(np.uint8)
    cv2.imwrite(os.path.join(run_dir, "05_alpha.png"), alpha_u8)

    # 最终融合结果（逐人）
    cv2.imwrite(
        os.path.join(run_dir, "06_result_multi.png"),
        cv2.cvtColor(result_multi, cv2.COLOR_RGB2BGR),
    )

    # 最终融合结果（一次性）
    cv2.imwrite(
        os.path.join(run_dir, "07_result_single.png"),
        cv2.cvtColor(result_single, cv2.COLOR_RGB2BGR),
    )

    # 在原图上画出目标 bbox
    x1, y1, x2, y2 = bbox
    vis = img_rgb.copy()
    cv2.rectangle(vis, (x1, y1), (x2, y2), (255, 0, 0), 2)
    cv2.imwrite(
        os.path.join(run_dir, "00_bbox_vis.png"),
        cv2.cvtColor(vis, cv2.COLOR_RGB2BGR),
    )


# ---------------------------------------------------------------------------
# 7. 背景修复：逐人修复 vs 一次性修复
# ---------------------------------------------------------------------------

def remove_non_target_with_lama(
    img_rgb: np.ndarray,
    person_masks: List[np.ndarray],
    target_idx: int,
    dilate_kernel: int = 9,
    dilate_iter: int = 2,
) -> np.ndarray:
    """
    逐人修复：对每个“非目标人物”的 mask 单独 dilate + inpaint 一次。
    """
    H, W = img_rgb.shape[:2]
    kernel = np.ones((dilate_kernel, dilate_kernel), np.uint8)

    background = img_rgb.copy()
    for i, pm in enumerate(person_masks):
        if i == target_idx:
            continue
        pm_uint8 = (pm.astype(np.uint8))
        pm_dil = cv2.dilate(pm_uint8, kernel, iterations=dilate_iter)
        inpaint_mask = (pm_dil * 255).astype(np.uint8)
        background = lama_inpaint(background, inpaint_mask)

    if background.shape[:2] != (H, W):
        background = cv2.resize(background, (W, H), interpolation=cv2.INTER_LINEAR)
    return background


def remove_non_target_with_lama_single(
    img_rgb: np.ndarray,
    person_masks: List[np.ndarray],
    target_idx: int,
    dilate_kernel: int = 9,
    dilate_iter: int = 2,
) -> np.ndarray:
    """
    一次性修复：将所有非目标人物的 mask 融合为一张，再整体 inpaint 一次。
    """
    H, W = img_rgb.shape[:2]
    kernel = np.ones((dilate_kernel, dilate_kernel), np.uint8)

    combined = np.zeros((H, W), dtype=np.uint8)
    for i, pm in enumerate(person_masks):
        if i == target_idx:
            continue
        pm_uint8 = (pm.astype(np.uint8))
        pm_dil = cv2.dilate(pm_uint8, kernel, iterations=dilate_iter)
        combined = np.maximum(combined, pm_dil)

    inpaint_mask = (combined * 255).astype(np.uint8)
    background = lama_inpaint(img_rgb, inpaint_mask)

    if background.shape[:2] != (H, W):
        background = cv2.resize(background, (W, H), interpolation=cv2.INTER_LINEAR)
    return background


# ---------------------------------------------------------------------------
# 8. 总入口：点击坐标 -> 各种中间结果
# ---------------------------------------------------------------------------

def process_image_click(img_rgb: np.ndarray, click_x: int, click_y: int):
    """
    点击选人版本入口：

    返回 7 张图 + 一段时间对比说明：
        result_multi        - 逐人修复 的最终融合结果
        result_single       - 一次性修复 的最终融合结果
        bg_before_rgb       - 修复前（原图）
        bg_after_multi_rgb  - 修复后背景（逐人修复）
        bg_after_single_rgb - 修复后背景（一次性修复）
        mask_vis_rgb        - 目标人物 mask 可视化（单通道堆成 3 通道）
        alpha_vis_rgb       - alpha 可视化（单通道堆成 3 通道）
        info_text           - 文本：两种方式的时间对比
    """
    if img_rgb is None:
        raise ValueError("img_rgb 为空。")

    run_id = time.strftime("%Y%m%d_%H%M%S")

    # 记录原始尺寸
    H0, W0 = img_rgb.shape[:2]
    target_size = (W0, H0)

    # 1) 分割所有人物
    person_masks, person_boxes = person_instance_seg(img_rgb)
    if not person_masks:
        raise RuntimeError("未检测到人物，请换一张图片。")

    # 2) 根据点击坐标选目标人物
    target_idx, (x_click, y_click) = select_target_by_click(
        person_boxes,
        (click_x, click_y),
        img_rgb.shape,
    )
    print(f"[INFO] 点击坐标 (x={x_click}, y={y_click}) 选中人物索引 {target_idx}")

    # 3) 目标人物 mask（原始大小）
    M_target = person_masks[target_idx].astype(np.uint8)

    # 4) 背景：逐人修复（多次 inpaint）
    t0 = time.time()
    background_multi = remove_non_target_with_lama(
        img_rgb,
        person_masks=person_masks,
        target_idx=target_idx,
        dilate_kernel=13,
        dilate_iter=2,
    )
    t1 = time.time()
    time_multi = t1 - t0

    if background_multi.shape[:2] != (H0, W0):
        background_multi = cv2.resize(
            background_multi, target_size, interpolation=cv2.INTER_LINEAR
        )

    # 4b) 背景：一次性修复（合并 mask 一次 inpaint）
    t2 = time.time()
    background_single = remove_non_target_with_lama_single(
        img_rgb,
        person_masks=person_masks,
        target_idx=target_idx,
        dilate_kernel=13,
        dilate_iter=2,
    )
    t3 = time.time()
    time_single = t3 - t2

    if background_single.shape[:2] != (H0, W0):
        background_single = cv2.resize(
            background_single, target_size, interpolation=cv2.INTER_LINEAR
        )

    # 5) rembg + alpha（本身就是原图尺寸）
    person_rgb, alpha_target = extract_person_with_rembg(img_rgb, M_target)

    # 6) alpha 羽化
    alpha_soft = feather_alpha(alpha_target, blur_size=7, erode_iter=1)

    # ✅ 确保前景和 alpha 尺寸都 = 原图尺寸
    if person_rgb.shape[:2] != (H0, W0):
        person_rgb = cv2.resize(person_rgb, target_size, interpolation=cv2.INTER_LINEAR)
    if alpha_soft.shape[:2] != (H0, H0):
        alpha_soft = cv2.resize(alpha_soft, target_size, interpolation=cv2.INTER_LINEAR)
    if M_target.shape[:2] != (H0, W0):
        M_target_vis = cv2.resize(M_target, target_size, interpolation=cv2.INTER_NEAREST)
    else:
        M_target_vis = M_target.copy()

    # 7) 融合：两种背景各出一张结果
    result_multi = composite_person(background_multi, person_rgb, alpha_soft)
    result_single = composite_person(background_single, person_rgb, alpha_soft)

    # 8) 组织可视化用的 mask / alpha
    mask_u8 = (M_target_vis.astype(np.uint8) * 255)
    mask_vis_rgb = np.stack([mask_u8] * 3, axis=-1)

    alpha_u8 = (np.clip(alpha_soft, 0.0, 1.0) * 255).astype(np.uint8)
    alpha_vis_rgb = np.stack([alpha_u8] * 3, axis=-1)

    # 9) 保存到本地（只保存一套即可，避免太多文件）
    if ENABLE_DEBUG_SAVE:
        bbox = person_boxes[target_idx]
        save_debug_steps(
            img_rgb=img_rgb,
            M_target=M_target_vis,
            background_multi=background_multi,
            background_single=background_single,
            alpha_soft=alpha_soft,
            result_multi=result_multi,
            result_single=result_single,
            bbox=bbox,
            run_id=run_id,
            save_dir=DEBUG_SAVE_DIR,
        )

    # 10) 时间对比说明
    if abs(time_multi - time_single) < 1e-3:
        faster_info = "两种方式速度几乎一样。"
    elif time_single < time_multi:
        faster_info = "一次性修复更快。"
    else:
        faster_info = "逐人修复更快（一般比较少见）。"

    info_text = (
        f"逐人修复：{time_multi:.2f} 秒\n"
        f"一次性修复：{time_single:.2f} 秒\n"
        f"时间差：{abs(time_multi - time_single):.2f} 秒\n"
        f"{faster_info}"
    )

    # 11) 组织 7 张输出图
    bg_before_rgb = img_rgb
    bg_after_multi_rgb = background_multi
    bg_after_single_rgb = background_single
    result_multi_rgb = result_multi
    result_single_rgb = result_single

    return (
        result_multi_rgb,
        result_single_rgb,
        bg_before_rgb,
        bg_after_multi_rgb,
        bg_after_single_rgb,
        mask_vis_rgb,
        alpha_vis_rgb,
        info_text,
    )


if __name__ == "__main__":
    print("此文件建议通过 app.py 的 Gradio 界面调用。")
