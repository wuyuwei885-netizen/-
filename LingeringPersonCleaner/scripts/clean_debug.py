from pathlib import Path
import shutil

root = Path("debug_steps")
if root.exists():
    shutil.rmtree(root)
    print("Deleted debug_steps/")
else:
    print("debug_steps/ does not exist")
