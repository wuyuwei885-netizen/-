from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QEvent, QThread, QTimer, QUrl, Qt, Signal
from PySide6.QtMultimedia import (
    QAudioInput,
    QAudioOutput,
    QMediaCaptureSession,
    QMediaPlayer,
    QMediaRecorder,
)
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .models import AppSettings, SentencePracticeItem, SubtitleItem, VideoProject, VocabularyItem
from .scoring import mock_score
from .storage import Storage
from .styles import APP_STYLE
from .subtitle_parser import parse_subtitles
from .transcriber import TranscriptionUnavailable, generate_subtitles_from_video
from .translator import TranslationUnavailable, translate_subtitles_to_chinese
from .utils import format_time, now_ts, uid
from .widgets import SubtitleOverlay, WordDialog, card_frame, primary_button


class TranscriptionWorker(QThread):
    finished_ok = Signal(list)
    failed = Signal(str)
    status = Signal(str)
    progress = Signal(int)

    def __init__(self, video_path: str, model_size: str, language: str, generate_translation: bool) -> None:
        super().__init__()
        self.video_path = video_path
        self.model_size = model_size
        self.language = language
        self.generate_translation = generate_translation

    def run(self) -> None:
        try:
            def report(message: str, percent: int | None = None) -> None:
                self.status.emit(message)
                if percent is not None:
                    self.progress.emit(percent)

            subtitles = generate_subtitles_from_video(
                self.video_path,
                model_size=self.model_size,
                language=self.language,
                progress=report,
            )
            if self.generate_translation:
                subtitles = translate_subtitles_to_chinese(subtitles, progress=report)
            self.finished_ok.emit(subtitles)
        except (TranscriptionUnavailable, TranslationUnavailable, FileNotFoundError, RuntimeError, ValueError) as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(f"字幕生成失败：{exc}")


class TranscriptionProgressDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("正在生成字幕")
        self.setModal(True)
        self.resize(520, 280)
        layout = QVBoxLayout(self)
        self.title_label = QLabel("准备开始生成字幕")
        self.title_label.setWordWrap(True)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.close_btn = QPushButton("后台运行")
        self.close_btn.clicked.connect(self.hide)
        layout.addWidget(self.title_label)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.log)
        layout.addWidget(self.close_btn)

    def add_status(self, message: str) -> None:
        self.title_label.setText(message)
        self.log.append(message)

    def set_progress(self, value: int) -> None:
        self.progress_bar.setValue(max(0, min(100, value)))


def clear_layout(layout: QVBoxLayout | QHBoxLayout | QGridLayout) -> None:
    while layout.count():
        child = layout.takeAt(0)
        if child.widget():
            child.widget().deleteLater()
        elif child.layout():
            clear_layout(child.layout())


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("LinguaClip 英语字幕学习助手")
        self.resize(1280, 820)
        self.storage = Storage(Path(__file__).resolve().parents[1] / "data" / "linguaclip.db")
        self.projects: list[VideoProject] = []
        self.vocabulary: list[VocabularyItem] = []
        self.practices: list[SentencePracticeItem] = []
        self.subtitles: list[SubtitleItem] = []
        self.current_project: VideoProject | None = None
        self.current_subtitle: SubtitleItem | None = None
        self.settings = self.storage.get_settings()
        self.subtitle_mode = self.settings.default_subtitle_mode
        self.current_practice: SentencePracticeItem | None = None
        self.recording_started_at = 0.0
        self.last_recording_path: Path | None = None

        self.study_player = QMediaPlayer(self)
        self.study_audio = QAudioOutput(self)
        self.study_player.setAudioOutput(self.study_audio)
        self.practice_player = QMediaPlayer(self)
        self.practice_audio = QAudioOutput(self)
        self.practice_player.setAudioOutput(self.practice_audio)
        self.recorded_player = QMediaPlayer(self)
        self.recorded_audio = QAudioOutput(self)
        self.recorded_player.setAudioOutput(self.recorded_audio)

        self.rec_session = QMediaCaptureSession(self)
        self.rec_audio_input = QAudioInput(self)
        self.recorder = QMediaRecorder(self)
        self.rec_session.setAudioInput(self.rec_audio_input)
        self.rec_session.setRecorder(self.recorder)

        self.reload_data()
        self.build_shell()
        self.build_home_page()
        self.build_study_page()
        self.build_vocabulary_page()
        self.build_practice_page()
        self.build_settings_page()
        if self.projects:
            self.select_project(self.projects[0], switch_to_study=False)
        self.show_page(0)

    def reload_data(self) -> None:
        self.projects = self.storage.list_projects()
        self.vocabulary = self.storage.list_vocabulary()
        self.practices = self.storage.list_practices()

    def build_shell(self) -> None:
        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        sidebar = QFrame()
        sidebar.setFixedWidth(230)
        sidebar.setStyleSheet("QFrame { background: #FFFFFF; border-right: 1px solid #E2E8F0; }")
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(16, 18, 16, 18)
        title = QLabel("<h2>LinguaClip</h2><p style='color:#64748B'>英语字幕学习助手</p>")
        side_layout.addWidget(title)

        self.nav_buttons: list[QPushButton] = []
        for index, label in enumerate(["首页", "视频学习", "生词清单", "口语练习", "设置"]):
            button = QPushButton(label)
            button.setObjectName("navButton")
            button.clicked.connect(lambda checked=False, i=index: self.show_page(i))
            self.nav_buttons.append(button)
            side_layout.addWidget(button)
        side_layout.addStretch()

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        topbar = QFrame()
        topbar.setFixedHeight(64)
        topbar.setStyleSheet("QFrame { background: #FFFFFF; border-bottom: 1px solid #E2E8F0; }")
        top_layout = QHBoxLayout(topbar)
        top_layout.setContentsMargins(24, 10, 24, 10)
        top_layout.addWidget(QLabel("本地视频 + 自动字幕 + 可点击单词 + 跟读录音"))
        top_layout.addStretch()
        video_btn = primary_button("导入视频")
        sub_btn = QPushButton("导入字幕（可选）")
        gen_btn = QPushButton("生成字幕")
        video_btn.clicked.connect(self.import_video)
        sub_btn.clicked.connect(self.import_subtitle)
        gen_btn.clicked.connect(self.generate_subtitles)
        top_layout.addWidget(video_btn)
        top_layout.addWidget(sub_btn)
        top_layout.addWidget(gen_btn)

        self.stack = QStackedWidget()
        self.home_page = QWidget()
        self.study_page = QWidget()
        self.vocab_page = QWidget()
        self.practice_page = QWidget()
        self.settings_page = QWidget()
        for page in (self.home_page, self.study_page, self.vocab_page, self.practice_page, self.settings_page):
            self.stack.addWidget(page)

        content_layout.addWidget(topbar)
        content_layout.addWidget(self.stack)
        root_layout.addWidget(sidebar)
        root_layout.addWidget(content)
        self.setCentralWidget(root)

    def show_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        for i, button in enumerate(self.nav_buttons):
            button.setProperty("active", i == index)
            button.style().unpolish(button)
            button.style().polish(button)
        if index == 0:
            self.refresh_home()
        elif index == 2:
            self.refresh_vocabulary_table()
        elif index == 3:
            self.refresh_practice_page()
        elif index == 4:
            self.refresh_settings_page()

    def build_home_page(self) -> None:
        self.home_layout = QVBoxLayout(self.home_page)
        self.home_layout.setContentsMargins(24, 24, 24, 24)
        self.refresh_home()

    def refresh_home(self) -> None:
        clear_layout(self.home_layout)
        self.home_layout.setSpacing(16)

        intro = card_frame()
        intro_layout = QVBoxLayout(intro)
        intro_layout.setSpacing(12)
        intro_layout.setContentsMargins(20, 18, 20, 18)

        brand = QLabel("<span style='color:#2563EB;font-size:16px;font-weight:700'>LinguaClip 英语字幕学习助手</span>")
        brand.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        headline = QLabel("<span style='font-size:28px;font-weight:800;color:#0F172A'>把本地视频变成可复习的英语学习材料</span>")
        headline.setWordWrap(True)
        headline.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        copy = QLabel("导入视频后点击“自动生成字幕”，即可获得可点击的英文字幕；可选生成中文字幕，用于双语学习和口语跟读。")
        copy.setWordWrap(True)
        copy.setStyleSheet("color:#475569; font-size:14px; line-height: 160%;")
        copy.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        intro_layout.addWidget(brand)
        intro_layout.addWidget(headline)
        intro_layout.addWidget(copy)

        step_grid = QGridLayout()
        step_grid.setSpacing(10)
        for index, (title, body) in enumerate(
            (
                ("1. 导入视频", "选择本地 mp4、webm、mov 等视频文件。"),
                ("2. 自动生成字幕", "使用本地 Whisper 生成英文字幕，可选联网翻译中文。"),
                ("3. 点击单词", "把字幕中的生词加入清单，保留句子上下文。"),
                ("4. 跟读复习", "保存句子片段，录音跟读并查看模拟评分。"),
            )
        ):
            step = card_frame()
            step.setStyleSheet("QFrame#card { background:#F8FAFC; border:1px solid #E2E8F0; border-radius:10px; }")
            step_layout = QVBoxLayout(step)
            step_layout.setContentsMargins(12, 10, 12, 10)
            step_title = QLabel(f"<b>{title}</b>")
            step_body = QLabel(body)
            step_body.setWordWrap(True)
            step_body.setStyleSheet("color:#64748B;")
            step_layout.addWidget(step_title)
            step_layout.addWidget(step_body)
            step_grid.addWidget(step, index // 2, index % 2)
        intro_layout.addLayout(step_grid)

        btns = QHBoxLayout()
        video_btn = primary_button("导入视频")
        gen_btn = QPushButton("自动生成字幕")
        sub_btn = QPushButton("导入字幕（可选）")
        start_btn = QPushButton("开始学习")
        video_btn.clicked.connect(self.import_video)
        gen_btn.clicked.connect(self.generate_subtitles)
        sub_btn.clicked.connect(self.import_subtitle)
        start_btn.clicked.connect(lambda: self.show_page(1))
        btns.addWidget(video_btn)
        btns.addWidget(gen_btn)
        btns.addWidget(sub_btn)
        btns.addWidget(start_btn)
        btns.addStretch()
        intro_layout.addLayout(btns)
        self.home_layout.addWidget(intro)

        lower = QGridLayout()
        lower.setSpacing(16)
        stats = QGridLayout()
        stats.setSpacing(10)
        for label, value in (
            ("已添加单词数", len(self.vocabulary)),
            ("已练习句子次数", sum(item.practice_count for item in self.practices)),
            ("已学习视频数", len(self.projects)),
        ):
            frame = card_frame()
            layout = QVBoxLayout(frame)
            layout.setContentsMargins(14, 12, 14, 12)
            layout.addWidget(QLabel(f"<p style='color:#64748B'>{label}</p>"))
            layout.addWidget(QLabel(f"<h2>{value}</h2>"))
            stats.addWidget(frame, 0, stats.count())
        lower.addLayout(stats, 0, 0)

        recent = card_frame()
        recent_layout = QVBoxLayout(recent)
        recent_layout.setContentsMargins(16, 14, 16, 14)
        recent_layout.addWidget(QLabel("<h3>最近学习</h3>"))
        if not self.projects:
            empty = QLabel("还没有导入视频。先点“导入视频”，再点“自动生成字幕”。")
            empty.setStyleSheet("color:#64748B;")
            recent_layout.addWidget(empty)
        for project in self.projects[:5]:
            button = QPushButton(f"{project.name}    {format_time(project.duration)}\n{project.file_name}")
            button.setMinimumHeight(54)
            button.clicked.connect(lambda checked=False, p=project: self.select_project(p, switch_to_study=True))
            recent_layout.addWidget(button)
        recent_layout.addStretch()
        lower.addWidget(recent, 1, 0)
        self.home_layout.addLayout(lower)
        self.home_layout.addStretch()

    def build_study_page(self) -> None:
        layout = QHBoxLayout(self.study_page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)

        left = QVBoxLayout()
        self.video_frame = QFrame()
        self.video_frame.setMinimumHeight(520)
        self.video_frame.setStyleSheet("QFrame { background: #020617; border-radius: 12px; }")
        self.video_frame.installEventFilter(self)
        self.video_widget = QVideoWidget(self.video_frame)
        self.study_player.setVideoOutput(self.video_widget)
        self.subtitle_overlay = SubtitleOverlay(self.video_frame)
        self.subtitle_overlay.word_clicked.connect(self.open_word_dialog)
        self.subtitle_overlay.moved.connect(self.save_subtitle_position)
        left.addWidget(self.video_frame, 1)

        controls = card_frame()
        controls_layout = QVBoxLayout(controls)
        row = QHBoxLayout()
        self.play_btn = primary_button("播放")
        self.play_btn.clicked.connect(self.toggle_play)
        for text, handler in (
            ("快退 5 秒", lambda: self.seek_relative(-5)),
            ("快进 5 秒", lambda: self.seek_relative(5)),
            ("上一句", lambda: self.go_subtitle(-1)),
            ("下一句", lambda: self.go_subtitle(1)),
        ):
            btn = QPushButton(text)
            btn.clicked.connect(handler)
            row.addWidget(btn)
        row.insertWidget(0, self.play_btn)
        self.time_label = QLabel("00:00 / 00:00")
        row.addStretch()
        row.addWidget(self.time_label)
        controls_layout.addLayout(row)

        options = QHBoxLayout()
        self.mode_combo = QComboBox()
        for value, label in (("original", "原字幕"), ("english", "英文"), ("chinese", "中文"), ("bilingual", "中英双语")):
            self.mode_combo.addItem(label, value)
        self.mode_combo.setCurrentIndex(max(0, self.mode_combo.findData(self.settings.default_subtitle_mode)))
        self.mode_combo.currentIndexChanged.connect(lambda: self.update_overlay())
        self.font_combo = QComboBox()
        for value, label in (("small", "小字号"), ("medium", "中字号"), ("large", "大字号")):
            self.font_combo.addItem(label, value)
        self.font_combo.setCurrentIndex(max(0, self.font_combo.findData(self.settings.font_size)))
        self.font_combo.currentIndexChanged.connect(self.change_font_size)
        self.bg_check = QCheckBox("半透明黑底")
        self.bg_check.setChecked(self.settings.subtitle_background)
        self.bg_check.toggled.connect(self.change_subtitle_background)
        self.loop_check = QCheckBox("循环当前句")
        self.loop_check.setChecked(self.settings.auto_loop_sentence)
        self.loop_check.toggled.connect(self.change_auto_loop)
        for widget in (QLabel("字幕模式"), self.mode_combo, QLabel("字号"), self.font_combo, self.bg_check, self.loop_check):
            options.addWidget(widget)
        options.addStretch()
        controls_layout.addLayout(options)
        left.addWidget(controls)

        side = card_frame()
        side.setFixedWidth(350)
        side_layout = QVBoxLayout(side)
        side_layout.addWidget(QLabel("<h3>当前句子学习面板</h3>"))
        self.study_title = QLabel("请先导入视频和字幕。")
        self.study_title.setWordWrap(True)
        self.study_translation = QLabel("")
        self.study_translation.setWordWrap(True)
        self.study_words = QLabel("")
        self.study_words.setWordWrap(True)
        add_practice = primary_button("加入句子复习")
        add_practice.clicked.connect(self.add_current_practice)
        for widget in (QLabel("英文句子"), self.study_title, QLabel("中文含义"), self.study_translation, QLabel("当前句生词"), self.study_words, add_practice):
            side_layout.addWidget(widget)
        side_layout.addStretch()

        layout.addLayout(left, 1)
        layout.addWidget(side)

        self.study_player.positionChanged.connect(self.on_study_position)
        self.study_player.durationChanged.connect(self.on_study_duration)
        self.study_player.playbackStateChanged.connect(self.on_playback_state)

    def eventFilter(self, obj, event) -> bool:  # noqa: ANN001
        if obj is getattr(self, "video_frame", None) and event.type() == QEvent.Type.Resize:
            self.video_widget.setGeometry(self.video_frame.rect())
            self.subtitle_overlay.update_position()
        return super().eventFilter(obj, event)

    def select_project(self, project: VideoProject, switch_to_study: bool) -> None:
        self.current_project = project
        self.storage.touch_project(project.id)
        self.subtitles = self.storage.load_subtitles(project.id)
        if Path(project.file_path).exists():
            self.study_player.setSource(QUrl.fromLocalFile(project.file_path))
            self.practice_player.setSource(QUrl.fromLocalFile(project.file_path))
        self.update_overlay()
        self.refresh_study_panel()
        if switch_to_study:
            self.show_page(1)

    def import_video(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择视频", "", "Video Files (*.mp4 *.webm *.mov *.mkv *.avi)")
        if not path:
            return
        file_path = Path(path)
        project = VideoProject(
            id=uid("video"),
            name=file_path.stem,
            file_name=file_path.name,
            file_path=str(file_path),
            duration=0,
            created_at=now_ts(),
            updated_at=now_ts(),
        )
        self.storage.save_project(project)
        self.reload_data()
        self.select_project(project, switch_to_study=True)
        QMessageBox.information(self, "导入成功", "视频已导入，请继续导入字幕。")

    def import_subtitle(self) -> None:
        if not self.current_project:
            QMessageBox.warning(self, "需要视频", "请先导入或选择一个视频。")
            return
        path, _ = QFileDialog.getOpenFileName(self, "选择字幕", "", "Subtitle Files (*.srt *.vtt)")
        if not path:
            return
        raw = Path(path).read_text(encoding="utf-8-sig", errors="ignore")
        self.subtitles = parse_subtitles(raw)
        self.storage.save_subtitles(self.current_project.id, self.subtitles)
        self.update_overlay()
        QMessageBox.information(self, "字幕已导入", f"共解析 {len(self.subtitles)} 句字幕。")

    def generate_subtitles(self) -> None:
        if not self.current_project:
            QMessageBox.warning(self, "需要视频", "请先导入或选择一个视频。")
            return
        if not Path(self.current_project.file_path).exists():
            QMessageBox.warning(self, "视频不存在", "原视频文件不存在，请重新导入视频。")
            return
        if hasattr(self, "transcription_worker") and self.transcription_worker.isRunning():
            QMessageBox.information(self, "正在生成", "字幕生成任务正在运行。")
            return

        self.statusBar().showMessage("正在准备生成字幕...")
        self.transcription_dialog = TranscriptionProgressDialog(self)
        self.transcription_dialog.add_status("正在准备生成字幕...")
        self.transcription_dialog.show()
        self.transcription_worker = TranscriptionWorker(
            self.current_project.file_path,
            self.settings.asr_model_size,
            self.settings.asr_language,
            self.settings.generate_chinese_translation,
        )
        self.transcription_worker.status.connect(self.statusBar().showMessage)
        self.transcription_worker.status.connect(self.transcription_dialog.add_status)
        self.transcription_worker.progress.connect(self.transcription_dialog.set_progress)
        self.transcription_worker.finished_ok.connect(self.on_transcription_finished)
        self.transcription_worker.failed.connect(self.on_transcription_failed)
        self.transcription_worker.start()

    def on_transcription_finished(self, subtitles: list[SubtitleItem]) -> None:
        if not self.current_project:
            return
        self.subtitles = subtitles
        self.storage.save_subtitles(self.current_project.id, subtitles)
        self.statusBar().showMessage(f"字幕生成完成，共 {len(subtitles)} 句。", 5000)
        if hasattr(self, "transcription_dialog"):
            self.transcription_dialog.set_progress(100)
            self.transcription_dialog.add_status(f"完成：共生成 {len(subtitles)} 句字幕。")
        self.update_overlay()
        translation_note = "，包含中文字幕" if any(item.translation for item in subtitles) else ""
        QMessageBox.information(self, "字幕生成完成", f"共生成 {len(subtitles)} 句英文字幕{translation_note}。")

    def on_transcription_failed(self, message: str) -> None:
        self.statusBar().showMessage("字幕生成失败", 5000)
        if hasattr(self, "transcription_dialog"):
            self.transcription_dialog.add_status(f"失败：{message}")
        QMessageBox.warning(self, "字幕生成失败", message)

    def on_study_duration(self, duration_ms: int) -> None:
        if self.current_project and duration_ms > 0:
            self.current_project.duration = duration_ms / 1000
            self.storage.save_project(self.current_project)

    def on_playback_state(self, state) -> None:  # noqa: ANN001
        self.play_btn.setText("暂停" if state == QMediaPlayer.PlaybackState.PlayingState else "播放")

    def on_study_position(self, position_ms: int) -> None:
        seconds = position_ms / 1000
        if self.current_project:
            self.time_label.setText(f"{format_time(seconds)} / {format_time(self.current_project.duration)}")
        self.current_subtitle = next((item for item in self.subtitles if item.start <= seconds <= item.end), None)
        if self.settings.auto_loop_sentence and self.current_subtitle and seconds >= self.current_subtitle.end:
            self.study_player.setPosition(int(self.current_subtitle.start * 1000))
            return
        self.update_overlay()
        self.refresh_study_panel()

    def update_overlay(self) -> None:
        if not hasattr(self, "subtitle_overlay"):
            return
        self.subtitle_mode = self.mode_combo.currentData() if hasattr(self, "mode_combo") else self.settings.default_subtitle_mode
        self.subtitle_overlay.set_state(self.current_subtitle, self.subtitle_mode, self.settings)

    def refresh_study_panel(self) -> None:
        if not hasattr(self, "study_title"):
            return
        if not self.current_subtitle:
            self.study_title.setText("当前时间没有匹配到字幕。")
            self.study_translation.setText("")
            self.study_words.setText("")
            return
        self.study_title.setText(self.current_subtitle.text)
        self.study_translation.setText(self.current_subtitle.translation or "当前字幕没有中文翻译。")
        words = [
            item.word
            for item in self.vocabulary
            if self.current_project and item.video_id == self.current_project.id and item.subtitle_id == self.current_subtitle.id
        ]
        self.study_words.setText("、".join(words) if words else "点击字幕中的英文单词添加。")

    def toggle_play(self) -> None:
        if self.study_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.study_player.pause()
        else:
            self.study_player.play()

    def seek_relative(self, seconds: int) -> None:
        self.study_player.setPosition(max(0, self.study_player.position() + seconds * 1000))

    def go_subtitle(self, offset: int) -> None:
        if not self.subtitles:
            return
        current = self.current_subtitle or self.subtitles[0]
        index = self.subtitles.index(current) if current in self.subtitles else 0
        target = self.subtitles[max(0, min(len(self.subtitles) - 1, index + offset))]
        self.study_player.setPosition(int(target.start * 1000))

    def save_subtitle_position(self, x: float, y: float) -> None:
        self.settings.subtitle_x = x
        self.settings.subtitle_y = y
        self.storage.save_settings(self.settings)

    def change_font_size(self) -> None:
        self.settings.font_size = self.font_combo.currentData()
        self.storage.save_settings(self.settings)
        self.update_overlay()

    def change_subtitle_background(self, checked: bool) -> None:
        self.settings.subtitle_background = checked
        self.storage.save_settings(self.settings)
        self.update_overlay()

    def change_auto_loop(self, checked: bool) -> None:
        self.settings.auto_loop_sentence = checked
        self.storage.save_settings(self.settings)

    def open_word_dialog(self, word: str) -> None:
        if not self.current_project or not self.current_subtitle:
            return

        def add(note: str) -> None:
            item = VocabularyItem(
                id=uid("word"),
                word=word,
                sentence=self.current_subtitle.text,
                translation=self.current_subtitle.translation,
                video_id=self.current_project.id,
                video_name=self.current_project.name,
                subtitle_id=self.current_subtitle.id,
                timestamp=self.current_subtitle.start,
                note=note,
                status="unknown",
                created_at=now_ts(),
                review_count=0,
            )
            if self.storage.add_vocabulary(item):
                self.vocabulary = self.storage.list_vocabulary()
                self.refresh_study_panel()
                QMessageBox.information(self, "已添加", "已加入生词清单。")
            else:
                QMessageBox.information(self, "已存在", "这个单词已经在当前句子中添加过。")

        WordDialog(word, self.current_subtitle.text, self, add).exec()

    def add_current_practice(self) -> None:
        if not self.current_project or not self.current_subtitle:
            return
        if self.storage.add_practice(self.current_subtitle, self.current_project):
            self.practices = self.storage.list_practices()
            QMessageBox.information(self, "已添加", "已加入句子复习。")
        else:
            QMessageBox.information(self, "已存在", "当前句子已经加入复习。")

    def build_vocabulary_page(self) -> None:
        layout = QVBoxLayout(self.vocab_page)
        layout.setContentsMargins(24, 24, 24, 24)
        top = QHBoxLayout()
        self.vocab_search = QLineEdit()
        self.vocab_search.setPlaceholderText("搜索单词")
        self.vocab_status = QComboBox()
        for value, label in (("all", "全部状态"), ("unknown", "未掌握"), ("reviewing", "复习中"), ("mastered", "已掌握")):
            self.vocab_status.addItem(label, value)
        self.vocab_search.textChanged.connect(self.refresh_vocabulary_table)
        self.vocab_status.currentIndexChanged.connect(self.refresh_vocabulary_table)
        top.addWidget(self.vocab_search)
        top.addWidget(self.vocab_status)
        layout.addLayout(top)

        self.vocab_table = QTableWidget(0, 7)
        self.vocab_table.setHorizontalHeaderLabels(["单词", "原句", "视频名", "时间戳", "状态", "备注", "ID"])
        self.vocab_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.vocab_table.setColumnHidden(6, True)
        self.vocab_table.itemSelectionChanged.connect(self.on_vocab_selection)
        layout.addWidget(self.vocab_table, 1)

        controls = QHBoxLayout()
        self.vocab_note = QTextEdit()
        self.vocab_note.setFixedHeight(70)
        self.vocab_note.setPlaceholderText("选中生词后修改备注")
        self.vocab_edit_status = QComboBox()
        for value, label in (("unknown", "未掌握"), ("reviewing", "复习中"), ("mastered", "已掌握")):
            self.vocab_edit_status.addItem(label, value)
        save_btn = primary_button("保存状态/备注")
        goto_btn = QPushButton("回到视频句子")
        delete_btn = QPushButton("删除生词")
        save_btn.clicked.connect(self.save_vocab_edit)
        goto_btn.clicked.connect(self.goto_selected_vocab)
        delete_btn.clicked.connect(self.delete_selected_vocab)
        controls.addWidget(self.vocab_note, 1)
        controls.addWidget(self.vocab_edit_status)
        controls.addWidget(save_btn)
        controls.addWidget(goto_btn)
        controls.addWidget(delete_btn)
        layout.addLayout(controls)

    def refresh_vocabulary_table(self) -> None:
        if not hasattr(self, "vocab_table"):
            return
        query = self.vocab_search.text().strip().lower() if hasattr(self, "vocab_search") else ""
        status_filter = self.vocab_status.currentData() if hasattr(self, "vocab_status") else "all"
        rows = [
            item
            for item in self.storage.list_vocabulary()
            if (not query or query in item.word.lower())
            and (status_filter == "all" or item.status == status_filter)
        ]
        self.vocab_table.setRowCount(len(rows))
        for row, item in enumerate(rows):
            values = [item.word, item.sentence, item.video_name, format_time(item.timestamp), item.status, item.note, item.id]
            for col, value in enumerate(values):
                self.vocab_table.setItem(row, col, QTableWidgetItem(str(value)))
        self.vocabulary = self.storage.list_vocabulary()

    def selected_vocab_id(self) -> str:
        row = self.vocab_table.currentRow()
        if row < 0:
            return ""
        item = self.vocab_table.item(row, 6)
        return item.text() if item else ""

    def selected_vocab(self) -> VocabularyItem | None:
        item_id = self.selected_vocab_id()
        return next((item for item in self.storage.list_vocabulary() if item.id == item_id), None)

    def on_vocab_selection(self) -> None:
        item = self.selected_vocab()
        if not item:
            return
        self.vocab_note.setPlainText(item.note)
        index = self.vocab_edit_status.findData(item.status)
        if index >= 0:
            self.vocab_edit_status.setCurrentIndex(index)

    def save_vocab_edit(self) -> None:
        item_id = self.selected_vocab_id()
        if not item_id:
            return
        self.storage.update_vocabulary(item_id, self.vocab_edit_status.currentData(), self.vocab_note.toPlainText().strip())
        self.refresh_vocabulary_table()

    def delete_selected_vocab(self) -> None:
        item_id = self.selected_vocab_id()
        if not item_id:
            return
        self.storage.delete_vocabulary(item_id)
        self.refresh_vocabulary_table()

    def goto_selected_vocab(self) -> None:
        item = self.selected_vocab()
        if not item:
            return
        project = next((project for project in self.storage.list_projects() if project.id == item.video_id), None)
        if project:
            self.select_project(project, switch_to_study=True)
            self.study_player.setPosition(int(item.timestamp * 1000))

    def build_practice_page(self) -> None:
        layout = QHBoxLayout(self.practice_page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)
        self.practice_list = QListWidget()
        self.practice_list.setFixedWidth(330)
        self.practice_list.currentItemChanged.connect(self.on_practice_selected)
        layout.addWidget(self.practice_list)

        right = QVBoxLayout()
        self.practice_video = QVideoWidget()
        self.practice_video.setMinimumHeight(390)
        self.practice_video.setStyleSheet("background:#020617;border-radius:12px;")
        self.practice_player.setVideoOutput(self.practice_video)
        right.addWidget(self.practice_video)
        info = card_frame()
        info_layout = QVBoxLayout(info)
        self.practice_sentence = QLabel("选择一个句子开始练习。")
        self.practice_sentence.setWordWrap(True)
        self.practice_translation = QLabel("")
        self.practice_translation.setWordWrap(True)
        self.practice_score = QLabel("完整度 - / 流利度 - / 清晰度 -")
        btns = QHBoxLayout()
        for text, handler in (
            ("播放句子片段", self.play_practice_segment),
            ("开始录音", self.start_recording),
            ("停止录音并评分", self.stop_recording),
            ("回放录音", self.play_recording),
        ):
            btn = primary_button(text) if text == "播放句子片段" else QPushButton(text)
            btn.clicked.connect(handler)
            btns.addWidget(btn)
        info_layout.addWidget(QLabel("英文句子"))
        info_layout.addWidget(self.practice_sentence)
        info_layout.addWidget(QLabel("中文含义"))
        info_layout.addWidget(self.practice_translation)
        info_layout.addWidget(self.practice_score)
        info_layout.addLayout(btns)
        right.addWidget(info)
        layout.addLayout(right, 1)

        self.practice_timer = QTimer(self)
        self.practice_timer.timeout.connect(self.stop_segment_if_needed)
        self.practice_timer.start(120)

    def refresh_practice_page(self) -> None:
        if not hasattr(self, "practice_list"):
            return
        self.practices = self.storage.list_practices()
        self.practice_list.clear()
        for item in self.practices:
            list_item = QListWidgetItem(f"{item.sentence[:70]}\n{item.video_name} · {format_time(item.start)} · 练习 {item.practice_count} 次")
            list_item.setData(Qt.ItemDataRole.UserRole, item.id)
            self.practice_list.addItem(list_item)

    def on_practice_selected(self, current: QListWidgetItem | None) -> None:
        if not current:
            return
        item_id = current.data(Qt.ItemDataRole.UserRole)
        self.current_practice = next((item for item in self.storage.list_practices() if item.id == item_id), None)
        if not self.current_practice:
            return
        self.practice_sentence.setText(self.current_practice.sentence)
        self.practice_translation.setText(self.current_practice.translation or "当前句子没有中文翻译。")
        self.practice_score.setText(
            f"完整度 {self.current_practice.completeness or '-'} / "
            f"流利度 {self.current_practice.fluency or '-'} / "
            f"清晰度 {self.current_practice.clarity or '-'}"
        )
        project = next((project for project in self.storage.list_projects() if project.id == self.current_practice.video_id), None)
        if project and Path(project.file_path).exists():
            self.practice_player.setSource(QUrl.fromLocalFile(project.file_path))

    def play_practice_segment(self) -> None:
        if not self.current_practice:
            return
        self.practice_player.setPosition(int(self.current_practice.start * 1000))
        self.practice_player.play()

    def stop_segment_if_needed(self) -> None:
        if self.current_practice and self.practice_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            if self.practice_player.position() / 1000 >= self.current_practice.end:
                self.practice_player.pause()
                self.practice_player.setPosition(int(self.current_practice.start * 1000))

    def start_recording(self) -> None:
        if not self.current_practice:
            return
        recordings = Path(__file__).resolve().parents[1] / "data" / "recordings"
        recordings.mkdir(parents=True, exist_ok=True)
        self.last_recording_path = recordings / f"{self.current_practice.id}_{int(now_ts())}.m4a"
        self.recorder.setOutputLocation(QUrl.fromLocalFile(str(self.last_recording_path)))
        self.recording_started_at = now_ts()
        self.recorder.record()

    def stop_recording(self) -> None:
        if not self.current_practice:
            return
        self.recorder.stop()
        recording_seconds = max(1.0, now_ts() - self.recording_started_at)
        target_seconds = self.current_practice.end - self.current_practice.start
        completeness, fluency, clarity = mock_score(recording_seconds, target_seconds)
        self.storage.update_practice_score(self.current_practice.id, completeness, fluency, clarity)
        self.refresh_practice_page()
        self.practice_score.setText(f"完整度 {completeness} / 流利度 {fluency} / 清晰度 {clarity}")

    def play_recording(self) -> None:
        if self.last_recording_path and self.last_recording_path.exists():
            self.recorded_player.setSource(QUrl.fromLocalFile(str(self.last_recording_path)))
            self.recorded_player.play()

    def build_settings_page(self) -> None:
        self.settings_layout = QVBoxLayout(self.settings_page)
        self.settings_layout.setContentsMargins(24, 24, 24, 24)
        self.refresh_settings_page()

    def refresh_settings_page(self) -> None:
        if not hasattr(self, "settings_layout"):
            return
        clear_layout(self.settings_layout)
        frame = card_frame()
        layout = QVBoxLayout(frame)
        layout.addWidget(QLabel("<h2>设置</h2>"))
        self.default_mode_combo = QComboBox()
        for value, label in (("original", "原字幕"), ("english", "英文"), ("chinese", "中文"), ("bilingual", "中英双语")):
            self.default_mode_combo.addItem(label, value)
        self.default_mode_combo.setCurrentIndex(self.default_mode_combo.findData(self.settings.default_subtitle_mode))
        self.default_font_combo = QComboBox()
        for value, label in (("small", "小字号"), ("medium", "中字号"), ("large", "大字号")):
            self.default_font_combo.addItem(label, value)
        self.default_font_combo.setCurrentIndex(self.default_font_combo.findData(self.settings.font_size))
        self.settings_bg = QCheckBox("默认启用半透明字幕背景")
        self.settings_bg.setChecked(self.settings.subtitle_background)
        self.settings_loop = QCheckBox("默认循环当前句")
        self.settings_loop.setChecked(self.settings.auto_loop_sentence)
        self.generate_translation_check = QCheckBox("自动生成中文字幕（联网，可选）")
        self.generate_translation_check.setChecked(self.settings.generate_chinese_translation)
        self.asr_model_combo = QComboBox()
        for value, label in (("tiny", "tiny - 更快"), ("base", "base - 推荐"), ("small", "small - 更准"), ("medium", "medium - 较慢")):
            self.asr_model_combo.addItem(label, value)
        self.asr_model_combo.setCurrentIndex(max(0, self.asr_model_combo.findData(self.settings.asr_model_size)))
        self.asr_language = QLineEdit(self.settings.asr_language)
        self.asr_language.setPlaceholderText("例如 en，留空为自动识别")
        save = primary_button("保存设置")
        export = QPushButton("导出数据")
        clear = QPushButton("清空数据")
        save.clicked.connect(self.save_settings_page)
        export.clicked.connect(self.export_data)
        clear.clicked.connect(self.clear_data)
        for widget in (
            QLabel("默认字幕语言"),
            self.default_mode_combo,
            QLabel("字幕字号"),
            self.default_font_combo,
            self.settings_bg,
            self.settings_loop,
            self.generate_translation_check,
            QLabel("自动字幕模型"),
            self.asr_model_combo,
            QLabel("识别语言"),
            self.asr_language,
            save,
            export,
            clear,
        ):
            layout.addWidget(widget)
        layout.addStretch()
        self.settings_layout.addWidget(frame)

    def save_settings_page(self) -> None:
        self.settings.default_subtitle_mode = self.default_mode_combo.currentData()
        self.settings.font_size = self.default_font_combo.currentData()
        self.settings.subtitle_background = self.settings_bg.isChecked()
        self.settings.auto_loop_sentence = self.settings_loop.isChecked()
        self.settings.generate_chinese_translation = self.generate_translation_check.isChecked()
        self.settings.asr_model_size = self.asr_model_combo.currentData()
        self.settings.asr_language = self.asr_language.text().strip()
        self.storage.save_settings(self.settings)
        QMessageBox.information(self, "已保存", "设置已保存。")

    def export_data(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "导出数据", "linguaclip-data.json", "JSON Files (*.json)")
        if not path:
            return
        Path(path).write_text(self.storage.export_all(), encoding="utf-8")
        QMessageBox.information(self, "导出完成", "数据已导出。")

    def clear_data(self) -> None:
        if QMessageBox.question(self, "确认清空", "确定清空所有本地学习数据吗？") != QMessageBox.StandardButton.Yes:
            return
        self.storage.clear_all()
        self.current_project = None
        self.current_subtitle = None
        self.subtitles = []
        self.reload_data()
        self.refresh_home()
        self.refresh_vocabulary_table()
        self.refresh_practice_page()


def run() -> None:
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_STYLE)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
