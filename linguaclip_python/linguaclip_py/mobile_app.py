from __future__ import annotations

from pathlib import Path

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.core.audio import SoundLoader
from kivy.core.text import LabelBase
from kivy.metrics import dp
from kivy.properties import ObjectProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.filechooser import FileChooserIconView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import Screen, ScreenManager
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.video import Video
from kivy.uix.widget import Widget

from .models import SentencePracticeItem, SubtitleItem, VideoProject, VocabularyItem
from .android_audio import AndroidAudioRecorder
from .scoring import mock_score
from .storage import Storage
from .subtitle_parser import parse_subtitles
from .tokenizer import tokenize_sentence
from .utils import format_time, now_ts, uid

Window.clearcolor = (0.972, 0.98, 0.988, 1)


def register_chinese_font() -> None:
    candidates = [
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("C:/Windows/Fonts/simsun.ttc"),
        Path("/system/fonts/NotoSansCJK-Regular.ttc"),
        Path("/system/fonts/NotoSansSC-Regular.otf"),
        Path("/system/fonts/DroidSansFallback.ttf"),
    ]
    font_path = next((path for path in candidates if path.exists()), None)
    if not font_path:
        return

    # Kivy widgets default to the Roboto family. Re-registering Roboto here
    # makes all Label/Button text use a CJK-capable font without touching each widget.
    LabelBase.register(name="Roboto", fn_regular=str(font_path))
    LabelBase.register(name="LinguaCN", fn_regular=str(font_path))


register_chinese_font()


class Card(BoxLayout):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.orientation = kwargs.get("orientation", "vertical")
        self.padding = dp(12)
        self.spacing = dp(8)


class FilePicker(Popup):
    def __init__(self, title: str, filters: list[str], on_select, **kwargs) -> None:
        super().__init__(title=title, size_hint=(0.96, 0.88), **kwargs)
        root = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
        chooser = FileChooserIconView(filters=filters)
        buttons = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        cancel = Button(text="取消")
        confirm = Button(text="选择", background_color=(0.145, 0.388, 0.922, 1))
        buttons.add_widget(cancel)
        buttons.add_widget(confirm)
        root.add_widget(chooser)
        root.add_widget(buttons)
        self.content = root
        cancel.bind(on_release=lambda *_: self.dismiss())

        def choose(*_) -> None:
            if chooser.selection:
                on_select(chooser.selection[0])
                self.dismiss()

        confirm.bind(on_release=choose)


class NavBar(BoxLayout):
    def __init__(self, app: "LinguaClipMobileApp", **kwargs) -> None:
        super().__init__(**kwargs)
        self.size_hint_y = None
        self.height = dp(54)
        self.spacing = dp(4)
        self.padding = (dp(6), dp(6))
        for screen_name, label in (
            ("home", "首页"),
            ("study", "学习"),
            ("vocab", "生词"),
            ("practice", "练习"),
            ("settings", "设置"),
        ):
            button = Button(text=label, font_size=dp(13))
            button.bind(on_release=lambda _, name=screen_name: app.switch_screen(name))
            self.add_widget(button)


class HomeScreen(Screen):
    app_ref = ObjectProperty(None)

    def __init__(self, app: "LinguaClipMobileApp", **kwargs) -> None:
        super().__init__(name="home", **kwargs)
        self.app_ref = app
        self.root = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(12))
        self.add_widget(self.root)

    def refresh(self) -> None:
        self.root.clear_widgets()
        self.root.add_widget(Label(text="[b]LinguaClip 英语字幕学习助手[/b]", markup=True, size_hint_y=None, height=dp(36), color=(0.05, 0.09, 0.16, 1)))
        self.root.add_widget(Label(text="安卓端 MVP：本地视频、SRT/VTT 字幕、点击单词、生词和句子复习。", size_hint_y=None, height=dp(48), color=(0.28, 0.33, 0.42, 1)))
        actions = GridLayout(cols=2, spacing=dp(8), size_hint_y=None, height=dp(156))
        video_btn = Button(text="导入视频", background_color=(0.145, 0.388, 0.922, 1))
        gen_btn = Button(text="生成字幕")
        sub_btn = Button(text="导入字幕(可选)")
        study_btn = Button(text="开始学习")
        refresh_btn = Button(text="刷新列表")
        video_btn.bind(on_release=lambda *_: self.app_ref.pick_video())
        gen_btn.bind(on_release=lambda *_: self.app_ref.mobile_transcription_notice())
        sub_btn.bind(on_release=lambda *_: self.app_ref.pick_subtitle())
        study_btn.bind(on_release=lambda *_: self.app_ref.switch_screen("study"))
        refresh_btn.bind(on_release=lambda *_: self.refresh())
        for widget in (video_btn, gen_btn, sub_btn, study_btn, refresh_btn):
            actions.add_widget(widget)
        self.root.add_widget(actions)

        stats = Label(
            text=f"已添加单词 {len(self.app_ref.vocabulary)}    已练习句子 {sum(p.practice_count for p in self.app_ref.practices)}    视频 {len(self.app_ref.projects)}",
            size_hint_y=None,
            height=dp(34),
            color=(0.28, 0.33, 0.42, 1),
        )
        self.root.add_widget(stats)

        self.root.add_widget(Label(text="[b]最近学习[/b]", markup=True, size_hint_y=None, height=dp(30), color=(0.05, 0.09, 0.16, 1)))
        scroll = ScrollView()
        list_box = BoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=None)
        list_box.bind(minimum_height=list_box.setter("height"))
        if not self.app_ref.projects:
            list_box.add_widget(Label(text="还没有导入视频。", size_hint_y=None, height=dp(44), color=(0.4, 0.45, 0.53, 1)))
        for project in self.app_ref.projects:
            button = Button(text=f"{project.name}\n{project.file_name}", size_hint_y=None, height=dp(64))
            button.bind(on_release=lambda _, p=project: self.app_ref.select_project(p, switch=True))
            list_box.add_widget(button)
        scroll.add_widget(list_box)
        self.root.add_widget(scroll)


class StudyScreen(Screen):
    app_ref = ObjectProperty(None)

    def __init__(self, app: "LinguaClipMobileApp", **kwargs) -> None:
        super().__init__(name="study", **kwargs)
        self.app_ref = app
        self.root = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(8))
        self.video = Video(state="stop", options={"eos": "stop"})
        self.subtitle_btn = Button(
            text="导入视频和字幕后开始学习",
            markup=True,
            size_hint_y=None,
            height=dp(96),
            background_color=(0, 0, 0, 0.72),
            color=(1, 1, 1, 1),
        )
        self.subtitle_btn.bind(on_release=self.open_word_picker)
        self.sentence_label = Label(text="", size_hint_y=None, height=dp(74), color=(0.05, 0.09, 0.16, 1))
        self.translation_label = Label(text="", size_hint_y=None, height=dp(48), color=(0.28, 0.33, 0.42, 1))
        self.time_label = Label(text="00:00 / 00:00", size_hint_y=None, height=dp(28), color=(0.28, 0.33, 0.42, 1))
        self.root.add_widget(self.video)
        self.root.add_widget(self.subtitle_btn)
        self.root.add_widget(self.time_label)
        controls = GridLayout(cols=4, spacing=dp(6), size_hint_y=None, height=dp(46))
        for text, handler in (
            ("播放", self.toggle_play),
            ("-5秒", lambda *_: self.seek(-5)),
            ("+5秒", lambda *_: self.seek(5)),
            ("加句子", self.add_practice),
        ):
            button = Button(text=text)
            button.bind(on_release=handler)
            controls.add_widget(button)
        self.root.add_widget(controls)
        self.root.add_widget(self.sentence_label)
        self.root.add_widget(self.translation_label)
        self.add_widget(self.root)
        Clock.schedule_interval(self.tick, 0.25)

    def refresh_source(self) -> None:
        project = self.app_ref.current_project
        if project and Path(project.file_path).exists():
            self.video.source = project.file_path
            self.video.state = "stop"

    def tick(self, _dt: float) -> None:
        project = self.app_ref.current_project
        if not project:
            return
        current = self.video.position or 0
        subtitle = next((item for item in self.app_ref.subtitles if item.start <= current <= item.end), None)
        self.app_ref.current_subtitle = subtitle
        duration = self.video.duration if self.video.duration and self.video.duration > 0 else project.duration
        self.time_label.text = f"{format_time(current)} / {format_time(duration)}"
        if self.app_ref.settings.auto_loop_sentence and subtitle and current >= subtitle.end:
            self.video.seek(subtitle.start / max(1, duration))
        if not subtitle:
            self.subtitle_btn.text = "当前时间没有字幕"
            self.sentence_label.text = ""
            self.translation_label.text = ""
            return
        self.subtitle_btn.text = subtitle.text if self.app_ref.settings.default_subtitle_mode in ("original", "english") else f"{subtitle.text}\n{subtitle.translation}"
        self.sentence_label.text = subtitle.text
        self.translation_label.text = subtitle.translation or "当前字幕没有中文翻译。"

    def toggle_play(self, *_args) -> None:
        self.video.state = "pause" if self.video.state == "play" else "play"

    def seek(self, seconds: int) -> None:
        duration = self.video.duration or 1
        target = max(0, min(duration, (self.video.position or 0) + seconds))
        self.video.seek(target / duration)

    def open_word_picker(self, *_args) -> None:
        subtitle = self.app_ref.current_subtitle
        project = self.app_ref.current_project
        if not subtitle or not project:
            return
        words = [(display, clean) for display, clean in tokenize_sentence(subtitle.text) if clean]
        popup = Popup(title="选择要加入生词的单词", size_hint=(0.92, 0.75))
        root = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        scroll = ScrollView()
        box = GridLayout(cols=2, spacing=dp(8), size_hint_y=None)
        box.bind(minimum_height=box.setter("height"))
        for display, clean in words:
            button = Button(text=display, size_hint_y=None, height=dp(44))
            button.bind(on_release=lambda _, word=clean: (popup.dismiss(), self.show_add_word(word)))
            box.add_widget(button)
        scroll.add_widget(box)
        root.add_widget(scroll)
        popup.content = root
        popup.open()

    def show_add_word(self, word: str) -> None:
        subtitle = self.app_ref.current_subtitle
        project = self.app_ref.current_project
        if not subtitle or not project:
            return
        popup = Popup(title=f"添加生词：{word}", size_hint=(0.92, 0.7))
        root = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        root.add_widget(Label(text=subtitle.text, size_hint_y=None, height=dp(70), color=(0.05, 0.09, 0.16, 1)))
        note = TextInput(hint_text="备注", multiline=True, size_hint_y=None, height=dp(120))
        root.add_widget(note)
        add = Button(text="添加到生词清单", size_hint_y=None, height=dp(48), background_color=(0.145, 0.388, 0.922, 1))
        add.bind(on_release=lambda *_: (self.app_ref.add_vocabulary(word, note.text), popup.dismiss()))
        root.add_widget(add)
        popup.content = root
        popup.open()

    def add_practice(self, *_args) -> None:
        self.app_ref.add_current_practice()


class VocabularyScreen(Screen):
    def __init__(self, app: "LinguaClipMobileApp", **kwargs) -> None:
        super().__init__(name="vocab", **kwargs)
        self.app_ref = app
        self.root = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        self.search = TextInput(hint_text="搜索单词", multiline=False, size_hint_y=None, height=dp(44))
        self.search.bind(text=lambda *_: self.refresh())
        self.list_box = BoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=None)
        self.list_box.bind(minimum_height=self.list_box.setter("height"))
        scroll = ScrollView()
        scroll.add_widget(self.list_box)
        self.root.add_widget(self.search)
        self.root.add_widget(scroll)
        self.add_widget(self.root)

    def refresh(self) -> None:
        self.app_ref.reload()
        query = self.search.text.strip().lower()
        self.list_box.clear_widgets()
        for item in self.app_ref.vocabulary:
            if query and query not in item.word.lower():
                continue
            button = Button(
                text=f"{item.word}    {item.status}\n{item.sentence[:80]}\n{item.video_name} · {format_time(item.timestamp)}",
                size_hint_y=None,
                height=dp(92),
                halign="left",
            )
            button.bind(on_release=lambda _, vocab=item: self.show_actions(vocab))
            self.list_box.add_widget(button)

    def show_actions(self, item: VocabularyItem) -> None:
        popup = Popup(title=item.word, size_hint=(0.92, 0.72))
        root = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        root.add_widget(Label(text=item.sentence, size_hint_y=None, height=dp(80), color=(0.05, 0.09, 0.16, 1)))
        note = TextInput(text=item.note, multiline=True, size_hint_y=None, height=dp(100))
        root.add_widget(note)
        status_row = GridLayout(cols=3, spacing=dp(6), size_hint_y=None, height=dp(48))
        for value, label in (("unknown", "未掌握"), ("reviewing", "复习中"), ("mastered", "已掌握")):
            button = Button(text=label)
            button.bind(on_release=lambda _, s=value: (self.app_ref.storage.update_vocabulary(item.id, s, note.text), popup.dismiss(), self.refresh()))
            status_row.add_widget(button)
        root.add_widget(status_row)
        goto = Button(text="回到视频句子", size_hint_y=None, height=dp(48))
        delete = Button(text="删除", size_hint_y=None, height=dp(48))
        goto.bind(on_release=lambda *_: (popup.dismiss(), self.app_ref.goto_vocab(item)))
        delete.bind(on_release=lambda *_: (self.app_ref.storage.delete_vocabulary(item.id), popup.dismiss(), self.refresh()))
        root.add_widget(goto)
        root.add_widget(delete)
        popup.content = root
        popup.open()


class PracticeScreen(Screen):
    def __init__(self, app: "LinguaClipMobileApp", **kwargs) -> None:
        super().__init__(name="practice", **kwargs)
        self.app_ref = app
        self.selected: SentencePracticeItem | None = None
        self.recorder = AndroidAudioRecorder()
        self.recording_started_at = 0.0
        self.last_recording_path: Path | None = None
        self.root = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        self.video = Video(state="stop", size_hint_y=0.42)
        self.info = Label(text="选择一个句子开始练习。", size_hint_y=None, height=dp(90), color=(0.05, 0.09, 0.16, 1))
        controls = GridLayout(cols=3, spacing=dp(6), size_hint_y=None, height=dp(96))
        play = Button(text="播放片段")
        rec = Button(text="开始录音")
        stop_rec = Button(text="停止评分")
        replay = Button(text="回放录音")
        score = Button(text="模拟评分")
        refresh = Button(text="刷新")
        play.bind(on_release=self.play_segment)
        rec.bind(on_release=self.start_recording)
        stop_rec.bind(on_release=self.stop_recording)
        replay.bind(on_release=self.play_recording)
        score.bind(on_release=self.score_selected)
        refresh.bind(on_release=lambda *_: self.refresh())
        for widget in (play, rec, stop_rec, replay, score, refresh):
            controls.add_widget(widget)
        self.list_box = BoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=None)
        self.list_box.bind(minimum_height=self.list_box.setter("height"))
        scroll = ScrollView()
        scroll.add_widget(self.list_box)
        self.root.add_widget(self.video)
        self.root.add_widget(self.info)
        self.root.add_widget(controls)
        self.root.add_widget(scroll)
        self.add_widget(self.root)
        Clock.schedule_interval(self.stop_at_sentence_end, 0.2)

    def refresh(self) -> None:
        self.app_ref.reload()
        self.list_box.clear_widgets()
        for item in self.app_ref.practices:
            button = Button(
                text=f"{item.sentence[:80]}\n{item.video_name} · {format_time(item.start)} · 练习 {item.practice_count} 次",
                size_hint_y=None,
                height=dp(82),
            )
            button.bind(on_release=lambda _, practice=item: self.select(practice))
            self.list_box.add_widget(button)

    def select(self, item: SentencePracticeItem) -> None:
        self.selected = item
        self.info.text = (
            f"{item.sentence}\n{item.translation or '无中文翻译'}\n"
            f"完整度 {item.completeness or '-'} / 流利度 {item.fluency or '-'} / 清晰度 {item.clarity or '-'}"
        )
        project = next((project for project in self.app_ref.projects if project.id == item.video_id), None)
        if project and Path(project.file_path).exists():
            self.video.source = project.file_path

    def play_segment(self, *_args) -> None:
        if not self.selected:
            return
        duration = self.video.duration or max(1, self.selected.end)
        self.video.seek(self.selected.start / duration)
        self.video.state = "play"

    def stop_at_sentence_end(self, _dt: float) -> None:
        if self.selected and self.video.state == "play" and self.video.position >= self.selected.end:
            self.video.state = "pause"

    def score_selected(self, *_args) -> None:
        if not self.selected:
            return
        completeness, fluency, clarity = mock_score(self.selected.end - self.selected.start, self.selected.end - self.selected.start)
        self.app_ref.storage.update_practice_score(self.selected.id, completeness, fluency, clarity)
        self.refresh()

    def start_recording(self, *_args) -> None:
        if not self.selected:
            return
        recordings = Path(self.app_ref.user_data_dir) / "recordings"
        recordings.mkdir(parents=True, exist_ok=True)
        self.last_recording_path = recordings / f"{self.selected.id}_{int(now_ts())}.m4a"
        self.recording_started_at = now_ts()
        if not self.recorder.start(self.last_recording_path):
            popup_message("录音不可用", "当前环境无法启动 Android 原生录音；请在真机 APK 中测试。")

    def stop_recording(self, *_args) -> None:
        if not self.selected:
            return
        output = self.recorder.stop()
        if output:
            self.last_recording_path = output
        recording_seconds = max(1.0, now_ts() - self.recording_started_at)
        target_seconds = max(1.0, self.selected.end - self.selected.start)
        completeness, fluency, clarity = mock_score(recording_seconds, target_seconds)
        self.app_ref.storage.update_practice_score(self.selected.id, completeness, fluency, clarity)
        self.refresh()
        popup_message("评分完成", f"完整度 {completeness}\n流利度 {fluency}\n清晰度 {clarity}")

    def play_recording(self, *_args) -> None:
        if not self.last_recording_path or not self.last_recording_path.exists():
            popup_message("没有录音", "请先完成一次录音。")
            return
        sound = SoundLoader.load(str(self.last_recording_path))
        if sound:
            sound.play()
        else:
            popup_message("无法播放", "当前环境无法播放该录音文件。")


class SettingsScreen(Screen):
    def __init__(self, app: "LinguaClipMobileApp", **kwargs) -> None:
        super().__init__(name="settings", **kwargs)
        self.app_ref = app
        root = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(10))
        root.add_widget(Label(text="[b]设置[/b]", markup=True, size_hint_y=None, height=dp(34), color=(0.05, 0.09, 0.16, 1)))
        loop = Button(text="切换循环当前句")
        export = Button(text="导出数据到应用目录")
        clear = Button(text="清空本地数据")
        loop.bind(on_release=self.toggle_loop)
        export.bind(on_release=self.export_data)
        clear.bind(on_release=self.clear_data)
        root.add_widget(loop)
        root.add_widget(export)
        root.add_widget(clear)
        root.add_widget(Label(text="安卓端使用原生 MediaRecorder 录音；电脑预览移动端时可能无法录音。", color=(0.4, 0.45, 0.53, 1)))
        self.add_widget(root)

    def toggle_loop(self, *_args) -> None:
        self.app_ref.settings.auto_loop_sentence = not self.app_ref.settings.auto_loop_sentence
        self.app_ref.storage.save_settings(self.app_ref.settings)

    def export_data(self, *_args) -> None:
        path = Path(self.app_ref.user_data_dir) / "linguaclip-export.json"
        path.write_text(self.app_ref.storage.export_all(), encoding="utf-8")
        popup_message("导出完成", f"已导出到：\n{path}")

    def clear_data(self, *_args) -> None:
        self.app_ref.storage.clear_all()
        self.app_ref.reload()
        popup_message("已清空", "本地学习数据已清空。")


def popup_message(title: str, message: str) -> None:
    popup = Popup(title=title, content=Label(text=message), size_hint=(0.86, 0.4))
    popup.open()


class LinguaClipMobileApp(App):
    def build(self) -> Widget:
        self.storage = Storage(Path(self.user_data_dir) / "linguaclip.db")
        self.settings = self.storage.get_settings()
        self.projects: list[VideoProject] = []
        self.vocabulary: list[VocabularyItem] = []
        self.practices: list[SentencePracticeItem] = []
        self.subtitles: list[SubtitleItem] = []
        self.current_project: VideoProject | None = None
        self.current_subtitle: SubtitleItem | None = None
        self.reload()
        if self.projects:
            self.select_project(self.projects[0], switch=False)

        root = BoxLayout(orientation="vertical")
        self.screens = ScreenManager()
        self.home = HomeScreen(self)
        self.study = StudyScreen(self)
        self.vocab = VocabularyScreen(self)
        self.practice = PracticeScreen(self)
        self.settings_screen = SettingsScreen(self)
        for screen in (self.home, self.study, self.vocab, self.practice, self.settings_screen):
            self.screens.add_widget(screen)
        root.add_widget(self.screens)
        root.add_widget(NavBar(self))
        self.home.refresh()
        return root

    def reload(self) -> None:
        self.projects = self.storage.list_projects()
        self.vocabulary = self.storage.list_vocabulary()
        self.practices = self.storage.list_practices()

    def switch_screen(self, name: str) -> None:
        self.reload()
        self.screens.current = name
        if name == "home":
            self.home.refresh()
        elif name == "study":
            self.study.refresh_source()
        elif name == "vocab":
            self.vocab.refresh()
        elif name == "practice":
            self.practice.refresh()

    def select_project(self, project: VideoProject, switch: bool) -> None:
        self.current_project = project
        self.storage.touch_project(project.id)
        self.subtitles = self.storage.load_subtitles(project.id)
        if hasattr(self, "study"):
            self.study.refresh_source()
        if switch:
            self.switch_screen("study")

    def pick_video(self) -> None:
        FilePicker("选择视频", ["*.mp4", "*.webm", "*.mov", "*.mkv", "*.avi"], self.import_video).open()

    def pick_subtitle(self) -> None:
        if not self.current_project:
            popup_message("需要视频", "请先导入或选择一个视频。")
            return
        FilePicker("选择字幕", ["*.srt", "*.vtt"], self.import_subtitle).open()

    def mobile_transcription_notice(self) -> None:
        popup_message(
            "安卓端生成字幕",
            "当前安卓版先不直接内置 Whisper，本地生成字幕请在桌面版点击“生成字幕”。\n\n"
            "原因是 Whisper 模型和 ctranslate2 在 Android APK 中体积大、兼容性不稳定。\n\n"
            "后续可以改成：1. 轻量安卓模型；2. 局域网桌面生成；3. 云端识别。",
        )

    def import_video(self, path: str) -> None:
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
        self.reload()
        self.select_project(project, switch=True)

    def import_subtitle(self, path: str) -> None:
        if not self.current_project:
            return
        content = Path(path).read_text(encoding="utf-8-sig", errors="ignore")
        self.subtitles = parse_subtitles(content)
        self.storage.save_subtitles(self.current_project.id, self.subtitles)
        popup_message("字幕已导入", f"共解析 {len(self.subtitles)} 句字幕。")
        self.switch_screen("study")

    def add_vocabulary(self, word: str, note: str) -> None:
        project = self.current_project
        subtitle = self.current_subtitle
        if not project or not subtitle:
            return
        item = VocabularyItem(
            id=uid("word"),
            word=word,
            sentence=subtitle.text,
            translation=subtitle.translation,
            video_id=project.id,
            video_name=project.name,
            subtitle_id=subtitle.id,
            timestamp=subtitle.start,
            note=note.strip(),
            status="unknown",
            created_at=now_ts(),
            review_count=0,
        )
        if self.storage.add_vocabulary(item):
            self.reload()
            popup_message("已添加", "已加入生词清单。")
        else:
            popup_message("已存在", "这个单词已经添加过。")

    def add_current_practice(self) -> None:
        if not self.current_project or not self.current_subtitle:
            return
        if self.storage.add_practice(self.current_subtitle, self.current_project):
            self.reload()
            popup_message("已添加", "已加入句子复习。")
        else:
            popup_message("已存在", "当前句子已经加入复习。")

    def goto_vocab(self, item: VocabularyItem) -> None:
        project = next((project for project in self.projects if project.id == item.video_id), None)
        if not project:
            return
        self.select_project(project, switch=True)
        Clock.schedule_once(lambda _dt: self.study.video.seek(item.timestamp / max(1, self.study.video.duration or item.timestamp + 1)), 0.3)


def run_mobile() -> None:
    LinguaClipMobileApp().run()
