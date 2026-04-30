#!/usr/bin/env python3
"""
J.A.R.V.I.S — Einmal-Setup
Prüft Python-Version, installiert Pakete, erstellt _env aus Vorlage.

Verwendung:
    python setup.py
"""

import sys
import os
import subprocess
import shutil
from pathlib import Path

REQUIRED_PYTHON = (3, 10)

BANNER = """
╔══════════════════════════════════════════════════════════════════════╗
║               J.A.R.V.I.S — Setup                                  ║
╚══════════════════════════════════════════════════════════════════════╝
"""

def step(msg):
    print(f"\n{'─'*60}\n  {msg}\n{'─'*60}")

def ok(msg):  print(f"  ✅  {msg}")
def warn(msg): print(f"  ⚠️   {msg}")
def err(msg):  print(f"  ❌  {msg}")


def check_python():
    step("Python-Version prüfen")
    v = sys.version_info
    if v < REQUIRED_PYTHON:
        err(f"Python {REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]}+ benötigt — "
            f"du hast {v.major}.{v.minor}")
        sys.exit(1)
    ok(f"Python {v.major}.{v.minor}.{v.micro}")


def check_tkinter():
    step("tkinter prüfen (für die UI)")
    try:
        import tkinter
        ok("tkinter vorhanden")
    except ImportError:
        warn("tkinter fehlt!")
        print("       Linux:  sudo apt-get install python3-tk")
        print("       Mac:    brew install python-tk")


def install_requirements():
    step("Python-Pakete installieren")
    req = Path("requirements.txt")
    if not req.exists():
        err("requirements.txt nicht gefunden!")
        sys.exit(1)
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
    )
    if result.returncode != 0:
        warn("Einige Pakete konnten nicht installiert werden.")
        print("     Versuche manuell: pip install -r requirements.txt")
    else:
        ok("Alle Pakete installiert")


def setup_env():
    step("Konfigurationsdatei einrichten")
    env_path = Path("_env")
    example  = Path("_env.exemple")

    if env_path.exists():
        ok("'_env' existiert bereits — wird nicht überschrieben")
        return

    if not example.exists():
        err("'_env.exemple' nicht gefunden!")
        return

    shutil.copy(example, env_path)
    ok("'_env' aus Vorlage erstellt")
    print()
    print("  👉  JETZT WICHTIG: Öffne die Datei '_env' und trage deine API-Keys ein!")
    print()
    print("  Mindestens diese drei Keys werden benötigt:")
    print("    GEMINI_API_KEY      → https://aistudio.google.com/apikey")
    print("    TELEGRAM_TOKEN      → @BotFather in Telegram → /newbot")
    print("    OWNER_TELEGRAM_ID   → @userinfobot in Telegram → /start")


def main():
    print(BANNER)
    check_python()
    check_tkinter()
    install_requirements()
    setup_env()

    print(f"""
{'═'*60}
  Setup abgeschlossen!

  NÄCHSTE SCHRITTE:
  1. '_env' öffnen und API-Keys eintragen
  2. python jarvis_v5_8.py --selftest    (alles prüfen)
  3. python jarvis_fulltest.py           (vollständiger Test)
  4. python jarvis_v5_8.py              (JARVIS starten)

  HILFE:
    python jarvis_v5_8.py --help-terminal
{'═'*60}
""")


if __name__ == "__main__":
    main()
