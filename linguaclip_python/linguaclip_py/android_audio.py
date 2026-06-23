from __future__ import annotations

from pathlib import Path


class AndroidAudioRecorder:
    def __init__(self) -> None:
        self.recorder = None
        self.output_path: Path | None = None

    @property
    def available(self) -> bool:
        try:
            import jnius  # noqa: F401
        except Exception:
            return False
        return True

    def start(self, output_path: Path) -> bool:
        try:
            from jnius import autoclass

            media_recorder = autoclass("android.media.MediaRecorder")
            recorder = media_recorder()
            recorder.setAudioSource(media_recorder.AudioSource.MIC)
            recorder.setOutputFormat(media_recorder.OutputFormat.MPEG_4)
            recorder.setAudioEncoder(media_recorder.AudioEncoder.AAC)
            recorder.setOutputFile(str(output_path))
            recorder.prepare()
            recorder.start()
            self.recorder = recorder
            self.output_path = output_path
            return True
        except Exception:
            self.recorder = None
            self.output_path = None
            return False

    def stop(self) -> Path | None:
        if not self.recorder:
            return None
        try:
            self.recorder.stop()
            self.recorder.release()
            return self.output_path
        finally:
            self.recorder = None
