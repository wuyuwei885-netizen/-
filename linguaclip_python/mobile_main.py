from __future__ import annotations

import sys


if __name__ == "__main__":
    try:
        from linguaclip_py.mobile_app import run_mobile
    except ModuleNotFoundError as exc:
        if exc.name == "kivy":
            print(
                "\n当前 Python 环境没有安装 Kivy，所以不能运行 mobile_main.py。\n\n"
                "如果只是运行电脑桌面版，请执行：\n"
                "  python main.py\n\n"
                "如果要在电脑上预览安卓/Kivy 界面，请先执行：\n"
                "  python -m pip install -r requirements-mobile.txt\n"
                "  python mobile_main.py\n\n"
                "如果要打包 APK，请按 README 里的 WSL2 / Linux Buildozer 步骤操作。\n"
            )
            sys.exit(1)
        raise

    run_mobile()
