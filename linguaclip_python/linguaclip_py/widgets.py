from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .models import AppSettings, SubtitleItem, SubtitleMode
from .tokenizer import tokenize_sentence


def card_frame() -> QFrame:
    frame = QFrame()
    frame.setObjectName("card")
    return frame


def primary_button(text: str) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName("primaryButton")
    return button


class SubtitleOverlay(QWidget):
    word_clicked = Signal(str)
    moved = Signal(float, float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.subtitle: SubtitleItem | None = None
        self.mode: SubtitleMode = "bilingual"
        self.settings = AppSettings()
        self.word_rects: list[tuple[QRect, str]] = []
        self.dragging = False
        self.drag_start = QPoint()
        self.start_pos = QPoint()
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)

    def set_state(self, subtitle: SubtitleItem | None, mode: SubtitleMode, settings: AppSettings) -> None:
        self.subtitle = subtitle
        self.mode = mode
        self.settings = settings
        if subtitle:
            self.resize(max(500, self.parentWidget().width() - 120), 120)
            self.show()
            self.raise_()
        else:
            self.hide()
        self.update_position()
        self.update()

    def update_position(self) -> None:
        parent = self.parentWidget()
        if not parent:
            return
        x = int(parent.width() * self.settings.subtitle_x / 100 - self.width() / 2)
        y = int(parent.height() * self.settings.subtitle_y / 100 - self.height() / 2)
        self.move(max(0, min(parent.width() - self.width(), x)), max(0, min(parent.height() - self.height(), y)))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.dragging = True
        self.drag_start = event.globalPosition().toPoint()
        self.start_pos = self.pos()
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self.dragging:
            return
        delta = event.globalPosition().toPoint() - self.drag_start
        parent = self.parentWidget()
        if not parent:
            return
        next_pos = self.start_pos + delta
        next_pos.setX(max(0, min(parent.width() - self.width(), next_pos.x())))
        next_pos.setY(max(0, min(parent.height() - self.height(), next_pos.y())))
        self.move(next_pos)
        x_percent = ((self.x() + self.width() / 2) / parent.width()) * 100
        y_percent = ((self.y() + self.height() / 2) / parent.height()) * 100
        self.moved.emit(x_percent, y_percent)
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        move_distance = (event.globalPosition().toPoint() - self.drag_start).manhattanLength()
        self.dragging = False
        if move_distance < 5:
            point = event.position().toPoint()
            for rect, word in self.word_rects:
                if rect.contains(point):
                    self.word_clicked.emit(word)
                    break
        event.accept()

    def paintEvent(self, event) -> None:  # noqa: ANN001
        if not self.subtitle:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.settings.subtitle_background:
            painter.setBrush(QColor(0, 0, 0, 165))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(self.rect().adjusted(6, 6, -6, -6), 12, 12)

        size_map = {"small": 18, "medium": 24, "large": 30}
        font = QFont("Microsoft YaHei", size_map.get(self.settings.font_size, 24), QFont.Weight.Bold)
        painter.setFont(font)
        painter.setPen(QPen(QColor("#FFFFFF")))
        metrics = QFontMetrics(font)
        self.word_rects.clear()

        show_english = self.mode in ("original", "english", "bilingual")
        show_chinese = self.mode in ("chinese", "bilingual")
        y = 40 if show_english else 54
        if show_english:
            tokens = tokenize_sentence(self.subtitle.text)
            total_width = sum(metrics.horizontalAdvance(token) for token, _ in tokens)
            x = max(14, int((self.width() - total_width) / 2))
            for token, clean in tokens:
                width = metrics.horizontalAdvance(token)
                rect = QRect(x, y - metrics.ascent(), max(1, width), metrics.height())
                if clean:
                    self.word_rects.append((rect.adjusted(-2, -2, 2, 2), clean))
                painter.drawText(x, y, token)
                x += width

        if show_chinese:
            small_font = QFont("Microsoft YaHei", 15, QFont.Weight.Medium)
            painter.setFont(small_font)
            painter.setPen(QPen(QColor("#E2E8F0")))
            text = self.subtitle.translation or self.subtitle.text
            painter.drawText(self.rect().adjusted(18, 68 if show_english else 40, -18, -10), Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap, text)


class WordDialog(QDialog):
    def __init__(
        self,
        word: str,
        sentence: str,
        parent: QWidget,
        on_add: Callable[[str], None],
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("添加生词")
        self.setModal(True)
        self.resize(420, 260)
        layout = QVBoxLayout(self)
        title = QLabel(f"<h2>{word}</h2>")
        sentence_label = QLabel(sentence)
        sentence_label.setWordWrap(True)
        self.note_edit = QTextEdit()
        self.note_edit.setPlaceholderText("填写备注")
        add_button = primary_button("添加到生词清单")
        cancel_button = QPushButton("取消")

        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(cancel_button)
        buttons.addWidget(add_button)

        layout.addWidget(title)
        layout.addWidget(sentence_label)
        layout.addWidget(self.note_edit)
        layout.addLayout(buttons)

        cancel_button.clicked.connect(self.reject)
        add_button.clicked.connect(lambda: (on_add(self.note_edit.toPlainText().strip()), self.accept()))
