# LinguaClip 英语字幕学习助手

LinguaClip 是一个 Python 桌面 + 安卓端 MVP，用于本地英语视频学习。用户导入本地视频后，可以自动生成英文字幕，在视频上同步显示字幕，点击英文单词加入生词清单，并把句子加入跟读练习。

桌面版支持本地离线生成字幕：点击“生成字幕”后，程序会使用 `faster-whisper` 从视频音频中识别英文并生成字幕。

如果在设置页勾选“自动生成中文字幕（联网，可选）”，英文字幕生成完成后会继续调用 `deep-translator` 逐句生成中文翻译。这个功能不需要 API Key，但需要联网；网络不可用时只生成英文字幕。

## 技术栈

- Python 3.10+
- PySide6 桌面端
- Kivy 安卓端
- faster-whisper 自动字幕
- SQLite3 本地数据
- Qt Multimedia / Android MediaRecorder

## 在 PyCharm 中打开

1. 用 PyCharm 打开 `linguaclip_python` 目录。
2. 创建或选择 Python 虚拟环境。
3. 在 PyCharm Terminal 执行：

```bash
pip install -r requirements.txt
```

4. 运行 `main.py`。

## 桌面版运行

```bash
cd linguaclip_python
pip install -r requirements.txt
python main.py
```

## 自动生成字幕

桌面版导入视频后，点击顶部或首页的“生成字幕”。

首次使用 `faster-whisper` 会下载模型文件。模型越大越准，但越慢：

- `tiny`：速度最快，准确率较低。
- `base`：默认推荐，速度和准确率比较平衡。
- `small`：更准确，但更慢。
- `medium`：更慢，适合性能较好的电脑。

默认识别语言是 `en`。可以在设置页修改，留空则交给模型自动识别。

生成字幕时会弹出进度窗口，显示当前步骤、进度条和生成日志。Whisper 的进度按已识别到的视频时间估算，翻译进度按句子数量计算。

## 安卓手机版

项目提供 Kivy 安卓端入口：

```bash
python mobile_main.py
```

在电脑上运行 `mobile_main.py` 可以预览手机端界面。正式安装到安卓手机需要打 APK。

如果运行 `mobile_main.py` 报错 `No module named 'kivy'`，说明当前虚拟环境没有安装 Kivy。电脑预览只需要安装：

```bash
pip install -r requirements-mobile.txt
python mobile_main.py
```

### 安卓端依赖

```bash
pip install -r requirements-android.txt
```

`requirements-android.txt` 是给打 APK/Buildozer 用的；Windows 本地预览优先用 `requirements-mobile.txt`。

### 打包 APK

Buildozer 主要在 Linux 环境工作。Windows 用户建议使用 WSL2 Ubuntu 或 Linux 机器。不要直接在 Windows PowerShell 里打 APK。

WSL2 Ubuntu 示例：

```bash
sudo apt update
sudo apt install -y python3-pip python3-venv git zip unzip openjdk-17-jdk build-essential autoconf libtool pkg-config zlib1g-dev libncurses5-dev libncursesw5-dev libtinfo6 cmake libffi-dev libssl-dev
```

进入项目目录并创建虚拟环境：

```bash
cd /mnt/c/Users/96074/Documents/自动驾驶/linguaclip_python
python3 -m venv .buildozer-venv
source .buildozer-venv/bin/activate
pip install --upgrade pip
pip install buildozer cython
```

开始打包：

```bash
buildozer android debug
```

生成的 APK 通常位于：

```text
bin/
```

安装到手机：

```bash
buildozer android deploy run
```

或者把 `bin/*.apk` 复制到手机手动安装。

重要说明：

- `buildozer.spec` 已配置为排除 `.venv`、`.idea`、`data`、缓存目录，避免 APK 过大。
- 项目根目录的 `main.py` 会自动判断运行环境：电脑上启动 PySide6 桌面版，安卓 APK 中启动 Kivy 手机版。
- 安卓端当前不打包 `faster-whisper` 和 `deep-translator`，因此手机端不直接本机生成字幕。

安卓端当前不直接内置 Whisper 生成字幕。原因是 Whisper 模型和 `ctranslate2` 原生依赖会显著增加 APK 体积，并且 Android 兼容性不稳定。更稳的路线是先在桌面版生成字幕；后续可以改成轻量安卓模型、局域网桌面生成或云端识别。

## 已实现功能

- 导入本地视频文件。
- 桌面版自动从视频生成英文字幕。
- 保留导入并解析 SRT / VTT 字幕作为备用方式。
- 双语字幕拆分：含中文字符的行作为中文翻译，其余行作为英文字幕。
- 视频学习页使用自定义字幕层，不依赖播放器默认字幕轨道。
- 桌面字幕层可拖拽，位置保存到本地设置。
- 英文字幕按单词拆分，可点击单词。
- 点击单词后填写备注并加入生词清单。
- 生词清单支持搜索、状态筛选、备注修改、删除。
- 生词可跳回视频对应字幕时间。
- 当前句子可加入句子复习。
- 句子复习页支持播放原视频句子片段。
- 支持录音、停止录音、回放录音。
- 使用模拟评分生成完整度、流利度、清晰度。
- 设置页支持默认字幕模式、字号、字幕背景、循环当前句、自动字幕模型。
- 支持导出本地学习数据 JSON。
- 支持清空本地数据。

## 本地数据

桌面端数据保存在：

```text
linguaclip_python/data/linguaclip.db
```

桌面端录音文件保存在：

```text
linguaclip_python/data/recordings/
```

安卓端数据保存在 App 私有数据目录中，由 Kivy 的 `user_data_dir` 决定。

视频文件不会复制进项目目录，只保存本地文件路径。如果移动或删除原视频文件，需要重新导入。

## 后续可优化

- 使用 ffmpeg 导出真实句子视频片段。
- 自动翻译生成中文字幕。
- 接入更精准的发音评分 API 或本地语音评估模型。
- 安卓端接入轻量本地语音识别或局域网桌面转写。
- 增加 Anki / CSV 导出。
- 增加更细的复习计划和熟悉度统计。
