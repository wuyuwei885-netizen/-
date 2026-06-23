from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

from .models import AppSettings, SentencePracticeItem, SubtitleItem, VideoProject, VocabularyItem
from .utils import now_ts, uid


class Storage:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._migrate()

    def _migrate(self) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                file_name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                duration REAL NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS subtitles (
                project_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS vocabulary (
                id TEXT PRIMARY KEY,
                word TEXT NOT NULL,
                sentence TEXT NOT NULL,
                translation TEXT NOT NULL,
                video_id TEXT NOT NULL,
                video_name TEXT NOT NULL,
                subtitle_id TEXT NOT NULL,
                timestamp REAL NOT NULL,
                note TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at REAL NOT NULL,
                review_count INTEGER NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS practices (
                id TEXT PRIMARY KEY,
                sentence TEXT NOT NULL,
                translation TEXT NOT NULL,
                video_id TEXT NOT NULL,
                video_name TEXT NOT NULL,
                subtitle_id TEXT NOT NULL,
                start REAL NOT NULL,
                end REAL NOT NULL,
                created_at REAL NOT NULL,
                practice_count INTEGER NOT NULL,
                completeness INTEGER NOT NULL,
                fluency INTEGER NOT NULL,
                clarity INTEGER NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                id TEXT PRIMARY KEY,
                payload TEXT NOT NULL
            )
            """
        )
        self.conn.commit()

    def list_projects(self) -> list[VideoProject]:
        rows = self.conn.execute("SELECT * FROM projects ORDER BY updated_at DESC").fetchall()
        return [VideoProject(**dict(row)) for row in rows]

    def save_project(self, project: VideoProject) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO projects VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project.id,
                project.name,
                project.file_name,
                project.file_path,
                project.duration,
                project.created_at,
                project.updated_at,
            ),
        )
        self.conn.commit()

    def touch_project(self, project_id: str) -> None:
        self.conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (now_ts(), project_id))
        self.conn.commit()

    def save_subtitles(self, project_id: str, subtitles: list[SubtitleItem]) -> None:
        payload = json.dumps([asdict(item) for item in subtitles], ensure_ascii=False)
        self.conn.execute(
            "INSERT OR REPLACE INTO subtitles VALUES (?, ?, ?)",
            (project_id, payload, now_ts()),
        )
        self.conn.commit()

    def load_subtitles(self, project_id: str) -> list[SubtitleItem]:
        row = self.conn.execute("SELECT payload FROM subtitles WHERE project_id = ?", (project_id,)).fetchone()
        if not row:
            return []
        return [SubtitleItem(**item) for item in json.loads(row["payload"])]

    def list_vocabulary(self) -> list[VocabularyItem]:
        rows = self.conn.execute("SELECT * FROM vocabulary ORDER BY created_at DESC").fetchall()
        return [VocabularyItem(**dict(row)) for row in rows]

    def add_vocabulary(self, item: VocabularyItem) -> bool:
        exists = self.conn.execute(
            "SELECT id FROM vocabulary WHERE word = ? AND sentence = ? AND video_id = ?",
            (item.word, item.sentence, item.video_id),
        ).fetchone()
        if exists:
            return False
        self.conn.execute(
            "INSERT INTO vocabulary VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                item.id,
                item.word,
                item.sentence,
                item.translation,
                item.video_id,
                item.video_name,
                item.subtitle_id,
                item.timestamp,
                item.note,
                item.status,
                item.created_at,
                item.review_count,
            ),
        )
        self.conn.commit()
        return True

    def update_vocabulary(self, item_id: str, status: str, note: str) -> None:
        self.conn.execute("UPDATE vocabulary SET status = ?, note = ? WHERE id = ?", (status, note, item_id))
        self.conn.commit()

    def delete_vocabulary(self, item_id: str) -> None:
        self.conn.execute("DELETE FROM vocabulary WHERE id = ?", (item_id,))
        self.conn.commit()

    def list_practices(self) -> list[SentencePracticeItem]:
        rows = self.conn.execute("SELECT * FROM practices ORDER BY created_at DESC").fetchall()
        return [SentencePracticeItem(**dict(row)) for row in rows]

    def add_practice(self, subtitle: SubtitleItem, project: VideoProject) -> bool:
        exists = self.conn.execute(
            "SELECT id FROM practices WHERE video_id = ? AND subtitle_id = ?",
            (project.id, subtitle.id),
        ).fetchone()
        if exists:
            return False
        item = SentencePracticeItem(
            id=uid("practice"),
            sentence=subtitle.text,
            translation=subtitle.translation,
            video_id=project.id,
            video_name=project.name,
            subtitle_id=subtitle.id,
            start=subtitle.start,
            end=subtitle.end,
            created_at=now_ts(),
            practice_count=0,
        )
        self.conn.execute(
            "INSERT INTO practices VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                item.id,
                item.sentence,
                item.translation,
                item.video_id,
                item.video_name,
                item.subtitle_id,
                item.start,
                item.end,
                item.created_at,
                item.practice_count,
                item.completeness,
                item.fluency,
                item.clarity,
            ),
        )
        self.conn.commit()
        return True

    def update_practice_score(self, item_id: str, completeness: int, fluency: int, clarity: int) -> None:
        self.conn.execute(
            """
            UPDATE practices
            SET practice_count = practice_count + 1, completeness = ?, fluency = ?, clarity = ?
            WHERE id = ?
            """,
            (completeness, fluency, clarity, item_id),
        )
        self.conn.commit()

    def get_settings(self) -> AppSettings:
        row = self.conn.execute("SELECT payload FROM settings WHERE id = 'default'").fetchone()
        if not row:
            settings = AppSettings()
            self.save_settings(settings)
            return settings
        return AppSettings(**json.loads(row["payload"]))

    def save_settings(self, settings: AppSettings) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO settings VALUES ('default', ?)",
            (json.dumps(asdict(settings), ensure_ascii=False),),
        )
        self.conn.commit()

    def export_all(self) -> str:
        payload = {
            "projects": [asdict(item) for item in self.list_projects()],
            "vocabulary": [asdict(item) for item in self.list_vocabulary()],
            "practices": [asdict(item) for item in self.list_practices()],
            "settings": asdict(self.get_settings()),
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def clear_all(self) -> None:
        for table in ("projects", "subtitles", "vocabulary", "practices", "settings"):
            self.conn.execute(f"DELETE FROM {table}")
        self.conn.commit()
