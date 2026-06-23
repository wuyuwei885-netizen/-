"""
Gradio app for LingeringPersonCleaner.

Run:
    python app.py
"""

from __future__ import annotations

# NumPy 2.x compatibility for old dependencies that still reference np.bool8.
import numpy as np

if not hasattr(np, "bool8"):
    np.bool8 = np.bool_

import gradio as gr

from pipeline import draw_click_preview, process_image_click

APP_TITLE = "多人照片点击选人 + 背景修复"
APP_SUBTITLE = "上传多人照片，点击想保留的人，系统自动擦除其他人物并修复背景。"

DESCRIPTION = f"""
# {APP_TITLE}

{APP_SUBTITLE}

**操作流程：**上传图片 → 点击目标人物 → 查看红圈预览 → 点击开始处理 → 下载最终结果。  
**技术路线：**YOLOv8-seg 人物实例分割 + 点击选中实例 + OpenCV Inpaint 背景修复 + Alpha 羽化融合。
"""

CUSTOM_CSS = """
.gradio-container {
    max-width: 1440px !important;
}
#status-box {
    border-radius: 12px;
    padding: 12px 14px;
    background: rgba(59, 130, 246, 0.08);
    border: 1px solid rgba(59, 130, 246, 0.22);
}
#tips-box {
    border-radius: 12px;
    padding: 12px 14px;
    background: rgba(16, 185, 129, 0.08);
    border: 1px solid rgba(16, 185, 129, 0.20);
}
"""


def reset_click_state():
    """Reset selected point when input image changes."""
    return None, None, "状态：已上传新图片，请在左侧图片上点击要保留的人物。"


def on_click(img, click_state, evt: gr.SelectData):
    """Handle image click and preview the selected location."""
    if img is None:
        return None, click_state, "⚠️ 请先上传图片，然后在人物身体区域单击。"
    if evt is None or evt.index is None:
        return None, click_state, "⚠️ 未获取到点击坐标，请重新点击。"

    try:
        x, y = evt.index
    except Exception:
        return None, click_state, "⚠️ 点击坐标格式异常，请重新点击。"

    h, w = img.shape[:2]
    x = int(np.clip(x, 0, w - 1))
    y = int(np.clip(y, 0, h - 1))
    preview = draw_click_preview(img, x, y)
    message = f"✅ 已选择点：({x}, {y})。现在点击 **开始处理**。"
    return preview, (x, y), message


def run_pipeline(img, click_state):
    """Run backend pipeline and map outputs to Gradio components."""
    empty_outputs = [None] * 9

    if img is None:
        return (*empty_outputs, "⚠️ 请先上传一张多人照片。")
    if click_state is None:
        return (*empty_outputs, "⚠️ 请先在图片上点击你想保留的人物。")

    x, y = click_state
    try:
        return process_image_click(img, int(x), int(y))
    except Exception as exc:
        return (*empty_outputs, f"❌ 处理失败：{exc}")


with gr.Blocks(title=APP_TITLE, theme=gr.themes.Soft(), css=CUSTOM_CSS) as demo:
    gr.Markdown(DESCRIPTION)

    click_state = gr.State(value=None)

    with gr.Row(equal_height=False):
        with gr.Column(scale=1, min_width=480):
            input_img = gr.Image(
                label="① 上传多人照片：点击目标人物",
                type="numpy",
                interactive=True,
                height=460,
            )
            click_preview = gr.Image(
                label="② 已选择人物预览：红圈 / 十字位置",
                type="numpy",
                interactive=False,
                height=460,
            )
            run_btn = gr.Button("③ 开始处理", variant="primary", size="lg")
            status = gr.Markdown("状态：等待上传图片。", elem_id="status-box")

            gr.Markdown(
                """
                **点击建议：**点在人物身体主体区域，尽量不要点背景、椅子、头发边缘。  
                **效果建议：**如果擦除不干净，换更清晰的图片，或在环境变量里增大 `DILATE_KERNEL`。
                """,
                elem_id="tips-box",
            )

        with gr.Column(scale=1, min_width=520):
            with gr.Tabs():
                with gr.Tab("最终效果"):
                    result_single = gr.Image(
                        label="推荐结果：一次性修复（速度快，适合 GitHub 演示）",
                        type="numpy",
                        height=520,
                    )
                    result_multi = gr.Image(
                        label="对比结果：逐人修复",
                        type="numpy",
                        height=520,
                    )

                with gr.Tab("中间过程"):
                    bbox_vis = gr.Image(
                        label="选中人物定位：bbox + click",
                        type="numpy",
                        height=280,
                    )
                    with gr.Row():
                        target_mask = gr.Image(
                            label="目标人物 mask：白 = 保留人物",
                            type="numpy",
                            height=240,
                        )
                        remove_mask = gr.Image(
                            label="待修复 mask：白 = 被擦除人物区域",
                            type="numpy",
                            height=240,
                        )
                    with gr.Row():
                        alpha_img = gr.Image(
                            label="羽化 alpha：白 = 不透明，黑 = 透明",
                            type="numpy",
                            height=240,
                        )
                        bg_before = gr.Image(
                            label="原图",
                            type="numpy",
                            height=240,
                        )
                    with gr.Row():
                        bg_after_single = gr.Image(
                            label="一次性修复背景",
                            type="numpy",
                            height=240,
                        )
                        bg_after_multi = gr.Image(
                            label="逐人修复背景",
                            type="numpy",
                            height=240,
                        )

    input_img.change(
        fn=reset_click_state,
        inputs=[],
        outputs=[click_preview, click_state, status],
    )

    input_img.select(
        fn=on_click,
        inputs=[input_img, click_state],
        outputs=[click_preview, click_state, status],
    )

    run_btn.click(
        fn=run_pipeline,
        inputs=[input_img, click_state],
        outputs=[
            result_single,
            result_multi,
            bg_before,
            bg_after_single,
            bg_after_multi,
            target_mask,
            remove_mask,
            alpha_img,
            bbox_vis,
            status,
        ],
    )


if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
