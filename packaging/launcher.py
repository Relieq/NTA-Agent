"""NTA-Agent.exe — a tiny PyInstaller stub: run the bundled Python on nta_agent.app.

Stdlib only; kept trivial so the exe never needs rebuilding for app updates.
"""
import subprocess
import sys
from pathlib import Path

root = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent
py = root / "runtime" / "python" / "python.exe"
subprocess.Popen([str(py), "-m", "nta_agent.app"], cwd=str(root / "app"),
                 creationflags=0x08000000)  # CREATE_NO_WINDOW
