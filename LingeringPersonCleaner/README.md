# LingeringPersonCleaner：多人照片点击选人 + 背景修复

一个基于 **Gradio + YOLOv8-seg + OpenCV Inpaint** 的轻量级图像处理 Demo：上传多人照片后，点击想保留的人物，系统自动分割人物实例，擦除其他人物，并对背景进行修复。

> 适合放到 GitHub 作为计算机视觉 / 图像处理 / AI 应用 Demo。项目重点不只是“能跑”，还保留了 mask、alpha、背景修复等中间过程，方便写报告、答辩或继续优化。

---

## 1. 功能特性

- **多人实例分割**：使用 YOLOv8-seg 检测图片中的 `person` 实例。
- **点击式目标选择**：用户在图片上点击目标人物，系统优先根据 mask 命中判断目标人物。
- **非目标人物擦除**：自动合并其他人物的 mask，并进行背景修复。
- **目标保护机制**：修复其他人物时会保护目标人物区域，减少误擦除。
- **Alpha 羽化融合**：对目标人物边缘进行轻微腐蚀和高斯模糊，降低硬边感。
- **过程可视化**：输出目标 mask、待修复 mask、羽化 alpha、修复前后背景、最终结果。
- **Debug 结果保存**：每次处理会保存到 `debug_steps/时间戳/`，方便复盘和写论文/报告。

---

## 2. 项目结构

```text
LingeringPersonCleaner/
├── app.py                    # Gradio 前端入口
├── pipeline.py               # 核心图像处理流水线
├── requirements.txt          # 基础依赖
├── requirements-optional.txt # 可选依赖：rembg alpha 提取
├── run_windows.bat           # Windows 一键启动脚本
├── run_linux_mac.sh          # Linux/macOS 一键启动脚本
├── scripts/
│   └── clean_debug.py        # 清理 debug_steps
├── docs/
│   └── screenshots/          # 可放项目截图
├── .gitignore
├── LICENSE
└── README.md
```

---

## 3. 快速开始

### 3.1 Windows 一键运行

双击或在终端执行：

```bat
run_windows.bat
```

脚本会自动创建虚拟环境、安装依赖并启动 Gradio。

### 3.2 手动运行

```bash
# 1. 创建虚拟环境
python -m venv .venv

# 2. 激活环境
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# Windows CMD:
.venv\Scripts\activate.bat
# Linux / macOS:
source .venv/bin/activate

# 3. 安装依赖
python -m pip install --upgrade pip
pip install -r requirements.txt

# 4. 启动
python app.py
```

浏览器打开：

```text
http://127.0.0.1:7860
```

首次运行时，Ultralytics 会自动下载 `yolov8n-seg.pt` 权重。权重文件已被 `.gitignore` 忽略，不建议提交到 GitHub。

---

## 4. 使用方法

1. 上传一张多人照片。
2. 在左侧图片中点击想保留的人物，尽量点在身体主体区域。
3. 看到红圈 / 十字预览后，点击 **开始处理**。
4. 在右侧查看：
   - **最终效果**：一次性修复结果、逐人修复结果；
   - **中间过程**：目标人物 mask、待修复 mask、alpha、修复前后背景。
5. 每次处理结果会自动保存到：

```text
debug_steps/YYYYMMDD_HHMMSS/
```

---

## 5. 核心技术流程

```text
输入多人照片
   ↓
YOLOv8-seg 检测 person 实例
   ↓
根据点击坐标选择目标人物
   ↓
合并非目标人物 mask
   ↓
保护目标人物区域，避免误擦除
   ↓
OpenCV Inpaint 修复背景
   ↓
目标人物 alpha 羽化
   ↓
目标人物与修复背景融合
   ↓
输出最终图 + 中间过程
```

---

## 6. 环境变量配置

不改代码也能调参数。下面是常用参数：

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `YOLO_MODEL_PATH` | `yolov8n-seg.pt` | YOLO 分割模型路径 |
| `YOLO_CONF` | `0.25` | 检测置信度阈值 |
| `YOLO_IMGSZ` | `1024` | YOLO 推理尺寸 |
| `DILATE_KERNEL` | `13` | 待擦除 mask 膨胀核，越大擦得越干净，但可能误伤 |
| `DILATE_ITER` | `2` | mask 膨胀次数 |
| `PROTECT_TARGET_KERNEL` | `9` | 目标人物保护区域大小 |
| `INPAINT_RADIUS` | `5` | OpenCV 修复半径 |
| `ALPHA_BLUR_SIZE` | `9` | alpha 羽化模糊核 |
| `ENABLE_DEBUG_SAVE` | `1` | 是否保存 debug 中间结果 |
| `USE_REMBG` | `0` | 是否启用 rembg 辅助 alpha 提取 |

Windows PowerShell 示例：

```powershell
$env:DILATE_KERNEL="17"
$env:YOLO_CONF="0.35"
python app.py
```

Linux / macOS 示例：

```bash
DILATE_KERNEL=17 YOLO_CONF=0.35 python app.py
```

---

## 7. 可选：启用 rembg

默认版本只依赖 YOLO mask 生成 alpha，安装简单、运行稳定。如果想尝试更细的前景 alpha，可以安装可选依赖：

```bash
pip install -r requirements-optional.txt
```

启动时开启：

```bash
USE_REMBG=1 python app.py
```

Windows PowerShell：

```powershell
$env:USE_REMBG="1"
python app.py
```

---

## 8. 常见问题

### Q1：为什么背景修复有痕迹？

当前默认使用 OpenCV Telea Inpaint，速度快但不是生成式修复，复杂背景下会有涂抹感。后续可以接入 LaMa、Stable Diffusion Inpainting 或其他生成式修复模型。

### Q2：为什么选错人物？

请点击人物身体主体区域，不要点头发边缘、椅子、背景。系统选择优先级是：mask 命中 > bbox 命中 > 最近中心点。

### Q3：为什么有些人没有被检测出来？

可能是人物太小、遮挡严重、置信度低。可以尝试：

```bash
YOLO_CONF=0.15 python app.py
```

### Q4：为什么第一次运行很慢？

首次运行会下载 YOLO 权重，之后就会变快。

### Q5：GitHub 上传要不要上传 `debug_steps/`？

不要。`debug_steps/` 是运行输出，已经写入 `.gitignore`。GitHub 只提交代码、README、脚本和必要文档。

---

## 9. 后续优化方向

- 接入 LaMa / Diffusion Inpainting，提高复杂背景修复质量。
- 支持框选人物、多选保留、多选删除。
- 增加批量处理模式。
- 增加模型选择：`yolov8n-seg` / `yolov8s-seg` / `yolo11n-seg`。
- 增加人像边缘 Matting 模型，提升头发和衣服边缘质量。
- 增加一键导出报告图：原图、mask、修复背景、最终图四宫格。

---

## 10. GitHub 提交流程

```bash
git init
git add .
git commit -m "feat: add person selection and background inpainting demo"
git branch -M main
git remote add origin https://github.com/你的用户名/LingeringPersonCleaner.git
git push -u origin main
```

推荐仓库描述：

```text
A Gradio demo for click-based person selection and background inpainting using YOLOv8 segmentation and OpenCV.
```

---

## 11. License

MIT License
