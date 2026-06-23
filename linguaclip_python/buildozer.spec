[app]
title = LinguaClip
package.name = linguaclip
package.domain = org.linguaclip
source.dir = .
source.include_exts = py,kv,txt,md
source.exclude_dirs = .venv,venv,.idea,data,__pycache__,outputs
version = 0.1.0
requirements = python3,kivy,pyjnius
orientation = portrait
fullscreen = 0

android.permissions = INTERNET,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,READ_MEDIA_VIDEO,READ_MEDIA_AUDIO,RECORD_AUDIO
android.api = 35
android.minapi = 23

[buildozer]
log_level = 2
warn_on_root = 1
