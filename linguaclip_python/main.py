from __future__ import annotations

import os


def is_android() -> bool:
    return "ANDROID_ARGUMENT" in os.environ or "ANDROID_PRIVATE" in os.environ


if __name__ == "__main__":
    if is_android():
        from linguaclip_py.mobile_app import run_mobile

        run_mobile()
    else:
        from linguaclip_py.main_window import run

        run()
