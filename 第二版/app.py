"""
Gradio 前端（统一显示尺寸版）：
- 左侧：上传 + 点击预览 + 状态 + 按钮
- 右侧：Tabs
    - 最终效果：大图（和输入显示尺寸一致）
    - 中间处理过程：2x2 网格对比（mask / 原图 / 修复后背景 / alpha）
"""

# ---- NumPy 2.x 兼容补丁：避免 gradio 里用到 np.bool8 报错 ----
import numpy as np

if not hasattr(np, "bool8"):
    np.bool8 = np.bool_

# ----------------------------------------------------------------

import gradio as gr
import cv2

from pipeline import process_image_click


DESCRIPTION = """
# 多人照片：点击锁定人物 + 背景修复

**使用说明：**

1. 左侧上传一张多人照片。
2. 在图片上 **单击** 想保留的人物（点在人物身体上即可）。
3. 左侧“已选择人物预览”会出现红圈，表示锁定位置。
4. 点击下方 **“开始处理”** 按钮。
5. 右侧：
   - **最终效果** Tab：查看最终结果（显示尺寸与输入一致）；
   - **中间处理过程** Tab：查看分割 mask / 修复前后 / alpha 的 2×2 对比。
6. 所有中间结果也会保存到项目目录的 `debug_steps/` 中。
"""


def on_click(img, click_state, evt: gr.SelectData):
    """
    处理图片点击事件：
    - Gradio 的 evt.index = (x, y)
    - 在该点画红圈做预览
    - 把 (x, y) 存到 click_state
    """
    if img is None:
        return None, click_state, "⚠️ 请先上传图片，然后在人物上单击。"

    if evt is None or evt.index is None:
        return None, click_state, "⚠️ 未获取到点击坐标，请重试。"

    try:
        x, y = evt.index   # 注意顺序：先 x 再 y
    except Exception:
        return None, click_state, "⚠️ 点击事件数据格式异常，请重试。"

    h, w = img.shape[:2]
    x = int(np.clip(x, 0, w - 1))
    y = int(np.clip(y, 0, h - 1))

    vis = img.copy()
    cv2.circle(vis, (x, y), 10, (255, 0, 0), 2)

    msg = f"✅ 已选择点：({x}, {y})，请点击下方“开始处理”按钮。"
    return vis, (x, y), msg


def run_pipeline(img, click_state):
    """
    调用 pipeline 的点击版本，返回所有中间结果用于显示。
    """
    if img is None:
        return None, None, None, None, None, "⚠️ 请先上传一张图片。"

    if click_state is None:
        return None, None, None, None, None, "⚠️ 请在图片上点击你想保留的人物。"

    x, y = click_state
    try:
        (
            result,
            mask_vis_rgb,
            bg_before_rgb,
            bg_after_rgb,
            alpha_vis_rgb,
        ) = process_image_click(img, x, y)

        msg = (
            "✅ 处理完成：\n"
            "- “最终效果”Tab：保留目标人物 + 修复背景 的最终结果\n"
            "- “中间处理过程”Tab：分割 mask / 修复前（原图）/ 修复后背景 / 羽化 alpha\n"
            "所有中间结果也已保存到 debug_steps/ 目录。"
        )
        return result, mask_vis_rgb, bg_before_rgb, bg_after_rgb, alpha_vis_rgb, msg

    except Exception as e:
        return None, None, None, None, None, f"❌ 处理过程中出错：{e}"


with gr.Blocks(theme="soft") as demo:
    gr.Markdown(DESCRIPTION)

    click_state = gr.State(value=None)

    with gr.Row():
        # 左侧操作区，和右侧同等宽度（scale=1）
        with gr.Column(scale=1, min_width=480):
            input_img = gr.Image(
                label="① 上传多人照片（点击人物进行选择）",
                type="numpy",
                interactive=True,
                height=480,      # 输入显示高度
            )

            click_preview = gr.Image(
                label="② 已选择人物预览（红圈位置）",
                type="numpy",
                height=480,      # 预览显示高度，与输入一致
            )

            status = gr.Markdown("状态：等待处理...")

            run_btn = gr.Button(
                "③ 开始处理",
                variant="primary",
                size="lg"
            )

        # 右侧展示区，同样宽度（scale=1）
        with gr.Column(scale=1, min_width=480):
            with gr.Tabs():
                with gr.Tab("最终效果"):
                    # 最终结果显示高度也设为 480，与左侧保持一致
                    output_img = gr.Image(
                        label="最终结果（保留目标人物 + 修复背景）",
                        type="numpy",
                        height=480,
                    )

                with gr.Tab("中间处理过程"):
                    with gr.Row():
                        mask_img = gr.Image(
                            label="分割 mask（白 = 目标人物）",
                            type="numpy",
                            height=220,
                        )
                        bg_before_img = gr.Image(
                            label="修复前（原图）",
                            type="numpy",
                            height=220,
                        )

                    with gr.Row():
                        bg_after_img = gr.Image(
                            label="修复后背景（其他人已擦掉）",
                            type="numpy",
                            height=220,
                        )
                        alpha_img = gr.Image(
                            label="羽化后的 alpha（白 = 不透明，黑 = 透明）",
                            type="numpy",
                            height=220,
                        )

    # 点击事件
    input_img.select(
        fn=on_click,
        inputs=[input_img, click_state],
        outputs=[click_preview, click_state, status],
    )

    # “开始处理”按钮
    run_btn.click(
        fn=run_pipeline,
        inputs=[input_img, click_state],
        outputs=[
            output_img,
            mask_img,
            bg_before_img,
            bg_after_img,
            alpha_img,
            status,
        ],
    )

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
