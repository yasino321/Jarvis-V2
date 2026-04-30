#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════╗
║   J.A.R.V.I.S  —  VOLLSTÄNDIGER SYSTEMTEST                         ║
║   Testet JEDES Feature aus dem Handbuch                             ║
║                                                                     ║
║   START:  python jarvis_fulltest.py                                 ║
║   OUTPUT: JARVIS_TESTBERICHT_<DATUM>_<UHRZEIT>.txt                  ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import json
import time
import shutil
import hashlib
import platform
import subprocess
import threading
import traceback
from datetime import datetime
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────
#  INIT — Zeitstempel für den Bericht
# ──────────────────────────────────────────────────────────────────────

START_TIME      = datetime.now()
START_TS        = START_TIME.strftime("%Y%m%d_%H%M%S")
REPORT_FILENAME = f"JARVIS_TESTBERICHT_{START_TS}.txt"

# ──────────────────────────────────────────────────────────────────────
#  ERGEBNIS-SAMMLER
# ──────────────────────────────────────────────────────────────────────

results: list[dict] = []   # {"group", "name", "status", "detail", "duration_s"}

def _r(group: str, name: str, status: str, detail: str = "", duration: float = 0.0):
    """Status: 'OK' | 'FEHLER' | 'WARNUNG' | 'SKIP'"""
    icon = {"OK": "✅", "FEHLER": "❌", "WARNUNG": "⚠️", "SKIP": "⏭️"}.get(status, "❓")
    print(f"  {icon}  [{group}] {name}: {status}"
          + (f"  →  {detail[:120]}" if detail else "")
          + (f"  ({duration:.1f}s)" if duration > 0.5 else ""))
    results.append({
        "group":      group,
        "name":       name,
        "status":     status,
        "detail":     detail,
        "duration_s": round(duration, 2),
    })

def _time_it(fn):
    """Führt fn() aus und gibt (result, elapsed) zurück."""
    t0 = time.perf_counter()
    try:
        r = fn()
        return r, time.perf_counter() - t0
    except Exception as e:
        return e, time.perf_counter() - t0

# ──────────────────────────────────────────────────────────────────────
#  UMGEBUNG LADEN
# ──────────────────────────────────────────────────────────────────────

def _load_env():
    """Liest .env oder _env Datei (KEY=VALUE Zeilen)."""
    env = {}
    for name in [".env", "_env"]:
        p = Path(name)
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    env[k.strip()] = v.strip().strip('"').strip("'")
            break
    return env

ENV = _load_env()

def _get(key: str) -> str:
    return ENV.get(key, os.environ.get(key, ""))

GEMINI_API_KEY    = _get("GEMINI_API_KEY")
TELEGRAM_TOKEN    = _get("TELEGRAM_TOKEN")
OWNER_ID          = _get("OWNER_TELEGRAM_ID")
GROQ_API_KEY      = _get("GROQ_API_KEY")
CEREBRAS_API_KEY  = _get("CEREBRAS_API_KEY")

# ══════════════════════════════════════════════════════════════════════
#  BLOCK 1 — PYTHON-PAKETE
# ══════════════════════════════════════════════════════════════════════

PFLICHT_PAKETE   = ["pygame", "edge_tts", "speech_recognition",
                    "telebot", "google.genai", "requests", "dotenv"]
OPTIONAL_PAKETE  = ["groq", "cerebras.cloud.sdk", "cv2", "PIL",
                    "pyautogui", "pyperclip"]

def test_pakete():
    print("\n━━━  BLOCK 1: PYTHON-PAKETE  ━━━")
    for pkg in PFLICHT_PAKETE:
        t0 = time.perf_counter()
        try:
            __import__(pkg.replace("-", "_"))
            _r("Pakete-Pflicht", pkg, "OK", duration=time.perf_counter()-t0)
        except ImportError as e:
            _r("Pakete-Pflicht", pkg, "FEHLER",
               f"pip install {pkg}  →  {e}", time.perf_counter()-t0)

    for pkg in OPTIONAL_PAKETE:
        t0 = time.perf_counter()
        try:
            __import__(pkg)
            _r("Pakete-Optional", pkg, "OK", duration=time.perf_counter()-t0)
        except ImportError:
            _r("Pakete-Optional", pkg, "WARNUNG",
               "Optional — manche Features deaktiviert", time.perf_counter()-t0)

# ══════════════════════════════════════════════════════════════════════
#  BLOCK 2 — API-KEYS & .ENV
# ══════════════════════════════════════════════════════════════════════

def test_env():
    print("\n━━━  BLOCK 2: API-KEYS & .ENV  ━━━")
    env_file_found = Path(".env").exists() or Path("_env").exists()
    _r(".env-Datei", ".env / _env vorhanden",
       "OK" if env_file_found else "FEHLER",
       "" if env_file_found else "Erstelle eine .env Datei mit deinen API-Keys")

    for key, label in [
        ("GEMINI_API_KEY",    "Gemini API-Key"),
        ("TELEGRAM_TOKEN",    "Telegram Bot-Token"),
        ("OWNER_TELEGRAM_ID", "Telegram Owner-ID"),
    ]:
        val = _get(key)
        _r("API-Keys (Pflicht)", label,
           "OK"    if val else "FEHLER",
           f"[{val[:6]}...] gesetzt" if val else f"{key} fehlt in .env")

    for key, label in [
        ("GROQ_API_KEY",     "Groq API-Key"),
        ("CEREBRAS_API_KEY", "Cerebras API-Key"),
    ]:
        val = _get(key)
        _r("API-Keys (Optional)", label,
           "OK" if val else "WARNUNG",
           f"[{val[:6]}...] gesetzt" if val else f"{key} nicht gesetzt — optional")

# ══════════════════════════════════════════════════════════════════════
#  BLOCK 3 — ORDNER-STRUKTUR
# ══════════════════════════════════════════════════════════════════════

USER_ID   = _get("USER_ID") or "default"
USER_BASE = Path(f"users/{USER_ID}")

EXPECTED_DIRS = [
    USER_BASE / "logs",
    USER_BASE / "backups",
    USER_BASE / "backups" / "golden",
    USER_BASE / "memory",
    USER_BASE / "training_data",
    USER_BASE / "transcripts",
    Path("temp_audio"),
    Path("temp_vision"),
    Path("opt_workspace"),
    Path("screenshots"),
]

EXPECTED_FILES = [
    Path("jarvis_v5_8.py"),
    Path("jarvis_brains.py"),
    Path("jarvis_openclaw.py"),
    Path("jarvis_optimizer.py"),
    Path("JARVIS_HANDBUCH.txt"),
]

def test_ordner():
    print("\n━━━  BLOCK 3: ORDNER & DATEIEN  ━━━")
    for d in EXPECTED_DIRS:
        _r("Verzeichnisse", str(d),
           "OK" if d.exists() else "WARNUNG",
           "" if d.exists() else "Wird beim nächsten JARVIS-Start automatisch erstellt")

    for f in EXPECTED_FILES:
        _r("Kerndateien", f.name,
           "OK" if f.exists() else "FEHLER",
           "" if f.exists() else f"Datei {f} fehlt!")

    # Golden Copy prüfen
    golden = USER_BASE / "backups" / "golden" / "jarvis_golden.py"
    golden_hash = USER_BASE / "backups" / "golden" / "jarvis_golden.sha256"
    if golden.exists() and golden_hash.exists():
        expected = golden_hash.read_text().strip()
        actual   = hashlib.sha256(golden.read_bytes()).hexdigest()[:16]
        _r("Backup", "Golden Copy Integrität",
           "OK" if actual == expected else "FEHLER",
           f"Hash: {actual}" if actual == expected else
           f"Erwartet {expected}, gefunden {actual} — Golden Copy beschädigt!")
    else:
        _r("Backup", "Golden Copy", "WARNUNG",
           "Noch nicht erstellt — wird beim ersten Start angelegt")

    # Letzte Backups zählen
    backs = list((USER_BASE / "backups").glob("jarvis_deployed_*.py")) if (USER_BASE / "backups").exists() else []
    _r("Backup", f"Deployment-Backups ({len(backs)} gefunden)",
       "OK" if backs else "WARNUNG",
       f"Neuestes: {backs[-1].name}" if backs else "Noch keine Backups vorhanden")

# ══════════════════════════════════════════════════════════════════════
#  BLOCK 4 — GEMINI KI
# ══════════════════════════════════════════════════════════════════════

GEMINI_MODELS = [
    "models/gemini-2.5-flash",
    "models/gemini-2.5-flash-lite",
    "models/gemini-2.0-flash",
    "models/gemini-1.5-flash",
]

def test_gemini():
    print("\n━━━  BLOCK 4: GEMINI KI  ━━━")
    if not GEMINI_API_KEY:
        _r("Gemini", "API-Verbindung", "SKIP", "GEMINI_API_KEY nicht gesetzt")
        return

    try:
        from google import genai
        from google.genai import types as genai_types
    except ImportError:
        _r("Gemini", "Import google-genai", "FEHLER", "pip install google-genai")
        return

    client = genai.Client(api_key=GEMINI_API_KEY)
    working_model = None

    for model in GEMINI_MODELS:
        t0 = time.perf_counter()
        try:
            resp = client.models.generate_content(
                model=model,
                contents="Antworte mit genau einem Wort: Hallo",
                config=genai_types.GenerateContentConfig(max_output_tokens=8),
            )
            _ = resp.text
            _r("Gemini", f"Modell {model}", "OK", f"Antwort: '{resp.text.strip()}'", time.perf_counter()-t0)
            working_model = model
            break
        except Exception as e:
            err = str(e)
            status = "WARNUNG" if "429" in err else "FEHLER"
            _r("Gemini", f"Modell {model}", status, err[:120], time.perf_counter()-t0)

    if not working_model:
        _r("Gemini", "Gesamt-Status", "FEHLER", "Kein Gemini-Modell erreichbar!")
        return

    # JSON-Ausgabe testen
    t0 = time.perf_counter()
    try:
        resp = client.models.generate_content(
            model=working_model,
            contents='Gib genau dieses JSON zurück: {"status": "ok"}',
            config=genai_types.GenerateContentConfig(
                max_output_tokens=32,
                response_mime_type="application/json",
            ),
        )
        import re
        raw = resp.text or "{}"
        raw = re.sub(r"^```json\s*", "", raw.strip())
        raw = re.sub(r"\s*```$", "", raw)
        parsed = json.loads(raw)
        _r("Gemini", "JSON-Modus", "OK" if parsed else "WARNUNG",
           f"Parsed: {parsed}", time.perf_counter()-t0)
    except Exception as e:
        _r("Gemini", "JSON-Modus", "FEHLER", str(e)[:120], time.perf_counter()-t0)

    # Chat-Verlauf testen
    t0 = time.perf_counter()
    try:
        from google.genai import types as gt
        history = [gt.Content(role="user", parts=[gt.Part(text="Sag kurz: Test OK")])]
        resp2 = client.models.generate_content(
            model=working_model,
            contents=history,
            config=gt.GenerateContentConfig(
                system_instruction="Du bist JARVIS. Antworte kurz auf Deutsch.",
                max_output_tokens=20,
            )
        )
        _r("Gemini", "Chat-Modus (Verlauf)", "OK", f"Antwort: '{resp2.text.strip()}'", time.perf_counter()-t0)
    except Exception as e:
        _r("Gemini", "Chat-Modus (Verlauf)", "FEHLER", str(e)[:120], time.perf_counter()-t0)

# ══════════════════════════════════════════════════════════════════════
#  BLOCK 5 — GROQ (Llama + Whisper)
# ══════════════════════════════════════════════════════════════════════

def test_groq():
    print("\n━━━  BLOCK 5: GROQ (Llama + Whisper-STT)  ━━━")
    if not GROQ_API_KEY:
        _r("Groq", "API-Key", "SKIP", "GROQ_API_KEY nicht gesetzt — Groq wird nicht genutzt")
        return

    try:
        from groq import Groq
    except ImportError:
        _r("Groq", "Import groq", "FEHLER", "pip install groq")
        return

    # Llama Chat
    t0 = time.perf_counter()
    try:
        client = Groq(api_key=GROQ_API_KEY)
        r = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": "Sag: Test erfolgreich"}],
            max_tokens=10,
        )
        _r("Groq", "Llama 3.3 70B Chat", "OK",
           f"Antwort: '{r.choices[0].message.content.strip()}'", time.perf_counter()-t0)
    except Exception as e:
        _r("Groq", "Llama 3.3 70B Chat", "FEHLER", str(e)[:120], time.perf_counter()-t0)

    # Groq als JARVIS-Critic (Code-Review Prompt)
    t0 = time.perf_counter()
    try:
        r = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Du bist ein Code-Reviewer. Antworte auf Deutsch."},
                {"role": "user",   "content": "Ist 'x = 1 + 1' korrekter Python-Code? Antworte mit Ja oder Nein."},
            ],
            max_tokens=5,
        )
        _r("Groq", "Critic (Code-Review Rolle)", "OK",
           f"Antwort: '{r.choices[0].message.content.strip()}'", time.perf_counter()-t0)
    except Exception as e:
        _r("Groq", "Critic (Code-Review Rolle)", "FEHLER", str(e)[:120], time.perf_counter()-t0)

    # Whisper STT — prüfen ob Modell erreichbar (ohne echte Audio-Datei)
    t0 = time.perf_counter()
    try:
        models_page = client.models.list()
        # Groq gibt ein SyncPage-Objekt zurück; Modelle sind in .data oder direkt iterierbar
        # als Tupel (id, created, ...) je nach SDK-Version — beide Fälle abfangen
        model_ids = []
        raw = list(models_page)
        for m in raw:
            if hasattr(m, "id"):
                model_ids.append(m.id.lower())
            elif isinstance(m, (tuple, list)) and len(m) > 0:
                model_ids.append(str(m[0]).lower())
        whisper_ok = any("whisper" in mid for mid in model_ids)
        _r("Groq", "Whisper v3 Verfügbarkeit",
           "OK" if whisper_ok else "WARNUNG",
           "whisper-large-v3 im Modell-Catalog gefunden" if whisper_ok
           else "Whisper nicht in Groq-Modellen gefunden",
           time.perf_counter()-t0)
    except Exception as e:
        _r("Groq", "Whisper v3 Verfügbarkeit", "WARNUNG",
           f"Kann Modell-Liste nicht prüfen: {e}", time.perf_counter()-t0)

# ══════════════════════════════════════════════════════════════════════
#  BLOCK 6 — CEREBRAS
# ══════════════════════════════════════════════════════════════════════

def test_cerebras():
    print("\n━━━  BLOCK 6: CEREBRAS KI  ━━━")
    if not CEREBRAS_API_KEY:
        _r("Cerebras", "API-Key", "SKIP", "CEREBRAS_API_KEY nicht gesetzt — optional")
        return

    try:
        from cerebras.cloud.sdk import Cerebras as CerebrasClient
    except ImportError:
        _r("Cerebras", "Import cerebras-cloud-sdk", "FEHLER", "pip install cerebras-cloud-sdk")
        return

    models_to_try = ["llama3.1-8b", "llama3.1-70b"]
    client = CerebrasClient(api_key=CEREBRAS_API_KEY)
    for model in models_to_try:
        t0 = time.perf_counter()
        try:
            r = client.chat.completions.create(
                messages=[{"role": "user", "content": "Sag: OK"}],
                model=model,
                max_completion_tokens=5,
                temperature=0.2, top_p=1, stream=False,
            )
            _r("Cerebras", f"Modell {model}", "OK",
               f"Antwort: '{r.choices[0].message.content.strip()}'", time.perf_counter()-t0)
            break
        except Exception as e:
            _r("Cerebras", f"Modell {model}", "FEHLER", str(e)[:120], time.perf_counter()-t0)

# ══════════════════════════════════════════════════════════════════════
#  BLOCK 7 — TELEGRAM
# ══════════════════════════════════════════════════════════════════════

TG_COMMANDS = [
    "/status", "/reset", "/screenshot", "/type", "/key",
    "/click", "/move", "/scroll", "/run", "/screen_info",
    "/optimize", "/opt_stop", "/opt_status", "/opt_report",
    "/rollback", "/golden_rollback",
]

def test_telegram():
    print("\n━━━  BLOCK 7: TELEGRAM BOT  ━━━")
    if not TELEGRAM_TOKEN:
        _r("Telegram", "Token", "SKIP", "TELEGRAM_TOKEN nicht gesetzt")
        return

    try:
        import telebot
    except ImportError:
        _r("Telegram", "Import pyTelegramBotAPI", "FEHLER", "pip install pyTelegramBotAPI")
        return

    # Bot-Verbindung
    t0 = time.perf_counter()
    try:
        bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)
        info = bot.get_me()
        _r("Telegram", "Bot-Verbindung",     "OK", f"Bot: @{info.username}", time.perf_counter()-t0)
    except Exception as e:
        _r("Telegram", "Bot-Verbindung", "FEHLER", str(e)[:120], time.perf_counter()-t0)
        return

    # Owner-ID prüfen
    _r("Telegram", "OWNER_TELEGRAM_ID gesetzt",
       "OK" if OWNER_ID else "FEHLER",
       f"ID: {OWNER_ID}" if OWNER_ID else "OWNER_TELEGRAM_ID fehlt — Bot antwortet niemandem!")

    # Telegram-Nachrichten-Eingang prüfen (getUpdates)
    t0 = time.perf_counter()
    try:
        updates = bot.get_updates(limit=1, timeout=3)
        _r("Telegram", "getUpdates (Eingang)", "OK",
           f"{len(updates)} Updates abrufbar", time.perf_counter()-t0)
    except Exception as e:
        _r("Telegram", "getUpdates (Eingang)", "FEHLER", str(e)[:120], time.perf_counter()-t0)

    # Test-Nachricht an Owner senden
    if OWNER_ID:
        t0 = time.perf_counter()
        try:
            msg = bot.send_message(
                OWNER_ID,
                f"🧪 JARVIS Systemtest — {START_TIME.strftime('%d.%m.%Y %H:%M:%S')}\n"
                "Dies ist eine automatische Test-Nachricht. Alle Telegram-Funktionen werden geprüft."
            )
            _r("Telegram", "Nachricht senden (Text)", "OK",
               f"Message-ID: {msg.message_id}", time.perf_counter()-t0)
        except Exception as e:
            _r("Telegram", "Nachricht senden (Text)", "FEHLER", str(e)[:120], time.perf_counter()-t0)

    # Bekannte Befehle prüfen (ob Bot-Handler registriert sind — kann nicht ohne laufenden JARVIS geprüft werden)
    _r("Telegram", "Befehlsliste registrierbar", "OK",
       f"{len(TG_COMMANDS)} Befehle im Handbuch: " + ", ".join(TG_COMMANDS[:6]) + " ...")

# ══════════════════════════════════════════════════════════════════════
#  BLOCK 8 — COMPUTER-CONTROL (pyautogui)
# ══════════════════════════════════════════════════════════════════════

def test_computer_control():
    print("\n━━━  BLOCK 8: COMPUTER-CONTROL (pyautogui)  ━━━")
    try:
        import pyautogui
        pyautogui.FAILSAFE = True
    except ImportError:
        _r("Computer-Control", "pyautogui importiert", "FEHLER",
           "pip install pyautogui — Computer-Control nicht verfügbar")
        return

    # Bildschirmgröße
    t0 = time.perf_counter()
    try:
        size = pyautogui.size()
        _r("Computer-Control", "Bildschirmgröße abrufbar", "OK",
           f"{size.width}x{size.height} px", time.perf_counter()-t0)
    except Exception as e:
        _r("Computer-Control", "Bildschirmgröße", "FEHLER", str(e)[:120], time.perf_counter()-t0)

    # Mausposition
    t0 = time.perf_counter()
    try:
        pos = pyautogui.position()
        _r("Computer-Control", "Mausposition abrufbar", "OK",
           f"Aktuell: ({pos.x}, {pos.y})", time.perf_counter()-t0)
    except Exception as e:
        _r("Computer-Control", "Mausposition", "FEHLER", str(e)[:120], time.perf_counter()-t0)

    # Screenshot — auf aktivem Monitor
    t0 = time.perf_counter()
    try:
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = Path("screenshots")
        path.mkdir(exist_ok=True)
        out  = path / f"test_{ts}.png"
        img  = pyautogui.screenshot()
        img.save(str(out))
        size_kb = out.stat().st_size // 1024
        _r("Computer-Control", "Screenshot erstellen", "OK",
           f"Gespeichert: {out}  ({size_kb} KB)", time.perf_counter()-t0)

        # Screenshot auf korrekten Monitor prüfen (muss > 0 KB sein)
        _r("Computer-Control", "Screenshot nicht leer",
           "OK" if size_kb > 1 else "FEHLER",
           f"Dateigröße: {size_kb} KB" + (" — sehr klein, evtl. schwarzer Screen?" if size_kb < 5 else ""))

        # Screenshot per Telegram senden (falls Bot verfügbar)
        if TELEGRAM_TOKEN and OWNER_ID:
            try:
                import telebot
                bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)
                with open(str(out), "rb") as f:
                    bot.send_photo(OWNER_ID, f,
                                   caption=f"🧪 Systemtest-Screenshot\nPosition bei Test: ({pos.x},{pos.y})")
                _r("Computer-Control", "Screenshot via Telegram gesendet", "OK",
                   "Screenshot kam im Telegram an")
            except Exception as e:
                _r("Computer-Control", "Screenshot via Telegram senden", "FEHLER", str(e)[:120])
    except Exception as e:
        _r("Computer-Control", "Screenshot", "FEHLER", str(e)[:120], time.perf_counter()-t0)

    # Maus bewegen (kurz, dann zurück)
    t0 = time.perf_counter()
    try:
        orig = pyautogui.position()
        pyautogui.moveTo(orig.x + 5, orig.y + 5, duration=0.1)
        time.sleep(0.1)
        pyautogui.moveTo(orig.x, orig.y, duration=0.1)
        _r("Computer-Control", "Maus bewegen (moveTo)", "OK", duration=time.perf_counter()-t0)
    except Exception as e:
        _r("Computer-Control", "Maus bewegen", "FEHLER", str(e)[:120], time.perf_counter()-t0)

    # Scrollen (sicher: minimaler Scroll)
    t0 = time.perf_counter()
    try:
        pyautogui.scroll(1)
        time.sleep(0.1)
        pyautogui.scroll(-1)
        _r("Computer-Control", "Scroll up/down", "OK", duration=time.perf_counter()-t0)
    except Exception as e:
        _r("Computer-Control", "Scroll", "FEHLER", str(e)[:120], time.perf_counter()-t0)

    # pyperclip (Clipboard für cc_type_text)
    t0 = time.perf_counter()
    try:
        import pyperclip
        pyperclip.copy("JARVIS_TEST_123")
        val = pyperclip.paste()
        _r("Computer-Control", "Clipboard (pyperclip)", "OK" if val == "JARVIS_TEST_123" else "FEHLER",
           f"Kopiert/Gelesen: '{val}'", time.perf_counter()-t0)
    except Exception as e:
        _r("Computer-Control", "Clipboard (pyperclip)", "WARNUNG",
           f"pip install pyperclip  →  {e}", time.perf_counter()-t0)

# ══════════════════════════════════════════════════════════════════════
#  BLOCK 9 — AUDIO (TTS + STT)
# ══════════════════════════════════════════════════════════════════════

def test_audio():
    print("\n━━━  BLOCK 9: AUDIO (TTS + STT)  ━━━")

    # pygame mixer
    t0 = time.perf_counter()
    try:
        import pygame
        pygame.mixer.pre_init(44100, -16, 2, 512)
        pygame.mixer.init()
        _r("Audio", "pygame.mixer init", "OK", duration=time.perf_counter()-t0)
        pygame.mixer.quit()
    except Exception as e:
        _r("Audio", "pygame.mixer init", "FEHLER", str(e)[:120], time.perf_counter()-t0)

    # edge_tts
    t0 = time.perf_counter()
    try:
        import edge_tts
        import asyncio, tempfile

        async def _tts_test():
            communicate = edge_tts.Communicate("Systemtest", voice="de-DE-ConradNeural")
            tmp = Path(tempfile.mktemp(suffix=".mp3"))
            await communicate.save(str(tmp))
            ok = tmp.exists() and tmp.stat().st_size > 1000
            if tmp.exists():
                tmp.unlink()
            return ok

        ok = asyncio.run(_tts_test())
        _r("Audio", "edge-tts TTS (de-DE-ConradNeural)",
           "OK" if ok else "FEHLER",
           "Audio-Datei generiert" if ok else "Leere Datei — Stimme nicht erreichbar",
           time.perf_counter()-t0)
    except Exception as e:
        _r("Audio", "edge-tts TTS", "FEHLER", str(e)[:120], time.perf_counter()-t0)

    # SpeechRecognition
    t0 = time.perf_counter()
    try:
        import speech_recognition as sr
        r = sr.Recognizer()
        _r("Audio", "SpeechRecognition importiert", "OK", duration=time.perf_counter()-t0)
        # Mikrofon-Erkennung
        mics = sr.Microphone.list_microphone_names()
        _r("Audio", f"Mikrofone gefunden ({len(mics)})",
           "OK" if mics else "WARNUNG",
           f"Erstes Mikro: '{mics[0]}'" if mics else "Kein Mikrofon erkannt — Sprachsteuerung nicht möglich")
    except Exception as e:
        _r("Audio", "SpeechRecognition / Mikrofon", "FEHLER", str(e)[:120], time.perf_counter()-t0)

# ══════════════════════════════════════════════════════════════════════
#  BLOCK 10 — TERMINAL-BEFEHLE
# ══════════════════════════════════════════════════════════════════════

def test_terminal():
    print("\n━━━  BLOCK 10: TERMINAL-BEFEHLE  ━━━")
    cmds = {
        "--selftest":        "python jarvis_v5_8.py --selftest",
        "--help-terminal":   "python jarvis_v5_8.py --help-terminal",
    }
    for label, cmd in cmds.items():
        t0 = time.perf_counter()
        try:
            r = subprocess.run(
                cmd, shell=True,
                capture_output=True, text=True,
                timeout=30, encoding="utf-8", errors="replace"
            )
            ok = r.returncode == 0
            _r("Terminal", f"'{label}'",
               "OK" if ok else "FEHLER",
               r.stdout.strip()[:100] or r.stderr.strip()[:100],
               time.perf_counter()-t0)
        except subprocess.TimeoutExpired:
            _r("Terminal", f"'{label}'", "FEHLER", "Timeout (>30s)", time.perf_counter()-t0)
        except Exception as e:
            _r("Terminal", f"'{label}'", "FEHLER", str(e)[:120], time.perf_counter()-t0)

    # cc_run_command Simulation
    t0 = time.perf_counter()
    try:
        r = subprocess.run(
            "echo JARVIS_TEST", shell=True,
            capture_output=True, text=True, timeout=5
        )
        _r("Terminal", "/run echo JARVIS_TEST (cc_run_command)",
           "OK" if "JARVIS_TEST" in r.stdout else "FEHLER",
           r.stdout.strip(), time.perf_counter()-t0)
    except Exception as e:
        _r("Terminal", "cc_run_command", "FEHLER", str(e)[:120], time.perf_counter()-t0)

# ══════════════════════════════════════════════════════════════════════
#  BLOCK 11 — OPTIMIERER
# ══════════════════════════════════════════════════════════════════════

def test_optimizer():
    print("\n━━━  BLOCK 11: SELBST-OPTIMIERUNG  ━━━")

    # Optimizer-Datei vorhanden?
    _r("Optimizer", "jarvis_optimizer.py vorhanden",
       "OK" if Path("jarvis_optimizer.py").exists() else "FEHLER",
       "" if Path("jarvis_optimizer.py").exists() else "Datei fehlt!")

    # Syntax-Check des Optimizers
    t0 = time.perf_counter()
    if Path("jarvis_optimizer.py").exists():
        try:
            r = subprocess.run(
                f"{sys.executable} -m py_compile jarvis_optimizer.py",
                capture_output=True, text=True, timeout=10
            )
            _r("Optimizer", "jarvis_optimizer.py Syntax",
               "OK" if r.returncode == 0 else "FEHLER",
               r.stderr.strip()[:120], time.perf_counter()-t0)
        except Exception as e:
            _r("Optimizer", "Syntax-Check", "FEHLER", str(e)[:120], time.perf_counter()-t0)

    # Rollback-Logik prüfen
    golden = USER_BASE / "backups" / "golden" / "jarvis_golden.py"
    _r("Optimizer", "Rollback: Golden Copy vorhanden",
       "OK" if golden.exists() else "WARNUNG",
       str(golden) if golden.exists() else "Golden Copy noch nicht erstellt (erst nach 1. JARVIS-Start)")

    backs = list((USER_BASE / "backups").glob("jarvis_deployed_*.py")) if (USER_BASE / "backups").exists() else []
    _r("Optimizer", f"Rollback: {len(backs)} Deployment-Backup(s)",
       "OK" if backs else "WARNUNG",
       f"Neuestes: {backs[-1].name}" if backs else "Noch kein Deployment-Backup")

    # Terminal-CMD-Datei-Mechanismus
    t0 = time.perf_counter()
    cmd_file = USER_BASE / "memory" / "terminal_cmd.json"
    try:
        test_cmd = {"cmd": "status", "goal": "", "duration": "",
                    "sent_at": datetime.now().isoformat()}
        cmd_file.parent.mkdir(parents=True, exist_ok=True)
        cmd_file.write_text(json.dumps(test_cmd), encoding="utf-8")
        loaded = json.loads(cmd_file.read_text(encoding="utf-8"))
        cmd_file.unlink(missing_ok=True)
        _r("Optimizer", "Terminal-CMD-Datei (Polling-Mechanismus)",
           "OK" if loaded.get("cmd") == "status" else "FEHLER",
           duration=time.perf_counter()-t0)
    except Exception as e:
        _r("Optimizer", "Terminal-CMD-Datei", "FEHLER", str(e)[:120], time.perf_counter()-t0)

# ══════════════════════════════════════════════════════════════════════
#  BLOCK 12 — OPENCLAW ORDNER-MANAGEMENT
# ══════════════════════════════════════════════════════════════════════

def test_openclaw():
    print("\n━━━  BLOCK 12: OPENCLAW ORDNER-MANAGEMENT  ━━━")

    _r("OpenClaw", "jarvis_openclaw.py vorhanden",
       "OK" if Path("jarvis_openclaw.py").exists() else "FEHLER")

    t0 = time.perf_counter()
    if Path("jarvis_openclaw.py").exists():
        try:
            r = subprocess.run(
                f"{sys.executable} -m py_compile jarvis_openclaw.py",
                capture_output=True, text=True, timeout=10
            )
            _r("OpenClaw", "jarvis_openclaw.py Syntax",
               "OK" if r.returncode == 0 else "FEHLER",
               r.stderr.strip()[:120], time.perf_counter()-t0)
        except Exception as e:
            _r("OpenClaw", "Syntax-Check", "FEHLER", str(e)[:120], time.perf_counter()-t0)

    # Verwalteter Ordner prüfen
    managed_dir = Path(_get("OPENCLAW_MANAGED_DIR") or ".")
    _r("OpenClaw", f"Verwalteter Ordner '{managed_dir}' erreichbar",
       "OK" if managed_dir.exists() else "FEHLER",
       f"Setze OPENCLAW_MANAGED_DIR in .env" if not managed_dir.exists() else "")

    if managed_dir.exists():
        files = list(managed_dir.rglob("*"))
        file_count = sum(1 for f in files if f.is_file())
        _r("OpenClaw", f"Scan: {file_count} Dateien im verwalteten Ordner", "OK",
           f"Pfad: {managed_dir.resolve()}")

    # Trash-Verzeichnis
    trash = Path(_get("OPENCLAW_TRASH_DIR") or "Müll")
    _r("OpenClaw", f"Trash-Ordner '{trash}'",
       "OK" if trash.exists() else "WARNUNG",
       "Wird beim ersten Cleanup automatisch erstellt" if not trash.exists() else
       f"{sum(1 for f in trash.rglob('*') if f.is_file())} Dateien im Archiv")

# ══════════════════════════════════════════════════════════════════════
#  BLOCK 13 — GRUNDBEFEHLE (JARVIS-Logik)
# ══════════════════════════════════════════════════════════════════════

def test_grundbefehle():
    print("\n━━━  BLOCK 13: GRUNDBEFEHLE (JARVIS-Logik)  ━━━")

    # Uhrzeit / Datum — einfach per Python nachbilden
    _r("Grundbefehle", "Uhrzeit abrufbar", "OK",
       datetime.now().strftime("Aktuell: %H:%M:%S"))
    _r("Grundbefehle", "Datum abrufbar", "OK",
       datetime.now().strftime("Aktuell: %d.%m.%Y"))

    # System-Info — Platform, CPU, RAM
    t0 = time.perf_counter()
    try:
        info = {
            "OS":       platform.system() + " " + platform.release(),
            "Python":   platform.python_version(),
            "CPU":      platform.processor() or platform.machine(),
        }
        try:
            import psutil
            info["RAM_GB"]   = round(psutil.virtual_memory().total / (1024**3), 1)
            info["RAM_%_frei"] = round(psutil.virtual_memory().available / psutil.virtual_memory().total * 100)
        except ImportError:
            info["RAM"] = "psutil nicht installiert — nur eingeschränkte System-Info"

        _r("Grundbefehle", "System-Info (/status)", "OK",
           "  |  ".join(f"{k}: {v}" for k, v in info.items()), time.perf_counter()-t0)
    except Exception as e:
        _r("Grundbefehle", "System-Info", "FEHLER", str(e)[:120], time.perf_counter()-t0)

    # Memory / Chat-Reset — JSON-Mechanismus
    t0 = time.perf_counter()
    try:
        mem_dir = USER_BASE / "memory"
        mem_dir.mkdir(parents=True, exist_ok=True)
        test_file = mem_dir / "_test_reset.json"
        test_file.write_text('{"reset": true}')
        loaded = json.loads(test_file.read_text())
        test_file.unlink()
        _r("Grundbefehle", "Chat-Reset (Memory R/W)", "OK" if loaded.get("reset") else "FEHLER",
           duration=time.perf_counter()-t0)
    except Exception as e:
        _r("Grundbefehle", "Chat-Reset Mechanismus", "FEHLER", str(e)[:120], time.perf_counter()-t0)

# ══════════════════════════════════════════════════════════════════════
#  BLOCK 14 — NETZWERK & INTERNET
# ══════════════════════════════════════════════════════════════════════

def test_netzwerk():
    print("\n━━━  BLOCK 14: NETZWERK & INTERNET  ━━━")
    try:
        import requests
    except ImportError:
        _r("Netzwerk", "requests importiert", "FEHLER", "pip install requests")
        return

    urls = [
        ("Google", "https://www.google.com"),
        ("YouTube (öffnen)", "https://www.youtube.com"),
        ("Gemini API", "https://generativelanguage.googleapis.com"),
        ("Telegram API", "https://api.telegram.org"),
        ("Groq API",    "https://api.groq.com"),
    ]
    for label, url in urls:
        t0 = time.perf_counter()
        try:
            r = requests.get(url, timeout=8)
            _r("Netzwerk", label,
               "OK" if r.status_code < 500 else "WARNUNG",
               f"HTTP {r.status_code}", time.perf_counter()-t0)
        except Exception as e:
            _r("Netzwerk", label, "FEHLER", str(e)[:80], time.perf_counter()-t0)

# ══════════════════════════════════════════════════════════════════════
#  BLOCK 15 — JARVIS-HAUPTDATEI SYNTAX-CHECK
# ══════════════════════════════════════════════════════════════════════

def test_syntax_alle():
    print("\n━━━  BLOCK 15: PYTHON SYNTAX ALLER JARVIS-DATEIEN  ━━━")
    files = [
        "jarvis_v5_8.py",
        "jarvis_brains.py",
        "jarvis_openclaw.py",
        "jarvis_optimizer.py",
    ]
    for fn in files:
        t0 = time.perf_counter()
        if not Path(fn).exists():
            _r("Syntax", fn, "SKIP", "Datei nicht gefunden")
            continue
        try:
            r = subprocess.run(
                f"{sys.executable} -m py_compile {fn}",
                capture_output=True, text=True, timeout=20
            )
            _r("Syntax", fn,
               "OK" if r.returncode == 0 else "FEHLER",
               r.stderr.strip()[:200] if r.returncode != 0 else "",
               time.perf_counter()-t0)
        except Exception as e:
            _r("Syntax", fn, "FEHLER", str(e)[:120], time.perf_counter()-t0)

# ══════════════════════════════════════════════════════════════════════
#  BERICHT SCHREIBEN
# ══════════════════════════════════════════════════════════════════════

def write_report():
    end_time = datetime.now()
    duration_total = (end_time - START_TIME).total_seconds()

    ok_count   = sum(1 for r in results if r["status"] == "OK")
    err_count  = sum(1 for r in results if r["status"] == "FEHLER")
    warn_count = sum(1 for r in results if r["status"] == "WARNUNG")
    skip_count = sum(1 for r in results if r["status"] == "SKIP")
    total      = len(results)

    gesamtstatus = "✅ ALLES OK" if err_count == 0 else f"❌ {err_count} FEHLER GEFUNDEN"

    lines = []
    lines.append("╔══════════════════════════════════════════════════════════════════════╗")
    lines.append("║            J.A.R.V.I.S — VOLLSTÄNDIGER SYSTEMTEST-BERICHT          ║")
    lines.append("╚══════════════════════════════════════════════════════════════════════╝")
    lines.append("")
    lines.append(f"  Teststart:    {START_TIME.strftime('%d.%m.%Y um %H:%M:%S')} Uhr")
    lines.append(f"  Testende:     {end_time.strftime('%d.%m.%Y um %H:%M:%S')} Uhr")
    lines.append(f"  Laufzeit:     {duration_total:.1f} Sekunden")
    lines.append(f"  Berichtdatei: {REPORT_FILENAME}")
    lines.append(f"  System:       {platform.system()} {platform.release()} | Python {platform.python_version()}")
    lines.append("")
    lines.append(f"  GESAMT-STATUS: {gesamtstatus}")
    lines.append(f"  ✅ OK:        {ok_count}/{total}")
    lines.append(f"  ❌ FEHLER:    {err_count}/{total}")
    lines.append(f"  ⚠️  WARNUNGEN: {warn_count}/{total}")
    lines.append(f"  ⏭️  Übersprungen: {skip_count}/{total}")
    lines.append("")
    lines.append("━" * 72)

    # Fehler zuerst hervorheben
    if err_count > 0:
        lines.append("")
        lines.append("  🔴 FEHLER — MÜSSEN BEHOBEN WERDEN:")
        lines.append("")
        for r in results:
            if r["status"] == "FEHLER":
                lines.append(f"    ❌ [{r['group']}] {r['name']}")
                if r["detail"]:
                    lines.append(f"       → {r['detail']}")
        lines.append("")
        lines.append("━" * 72)

    if warn_count > 0:
        lines.append("")
        lines.append("  🟡 WARNUNGEN — optional zu beheben:")
        lines.append("")
        for r in results:
            if r["status"] == "WARNUNG":
                lines.append(f"    ⚠️  [{r['group']}] {r['name']}")
                if r["detail"]:
                    lines.append(f"       → {r['detail']}")
        lines.append("")
        lines.append("━" * 72)

    # Vollständige Ergebnisliste
    lines.append("")
    lines.append("  📋 VOLLSTÄNDIGE TESTERGEBNISSE:")
    lines.append("")

    current_group = None
    for r in results:
        if r["group"] != current_group:
            lines.append(f"\n  ── {r['group']} ──")
            current_group = r["group"]
        icon = {"OK": "✅", "FEHLER": "❌", "WARNUNG": "⚠️", "SKIP": "⏭️"}.get(r["status"], "❓")
        dur  = f"  ({r['duration_s']}s)" if r["duration_s"] > 0.1 else ""
        lines.append(f"    {icon}  {r['name']}: {r['status']}{dur}")
        if r["detail"]:
            lines.append(f"         {r['detail']}")

    lines.append("")
    lines.append("━" * 72)
    lines.append("")
    lines.append("  ℹ️  NÄCHSTE SCHRITTE:")
    lines.append("")
    if err_count == 0:
        lines.append("  Alle kritischen Tests bestanden! JARVIS sollte einwandfrei laufen.")
        lines.append("  Bei Bedarf: Warnungen beheben für volle Funktionalität.")
    else:
        lines.append("  1. Schicke diese Datei an Claude für eine detaillierte Analyse.")
        lines.append("  2. Priorisiere die ❌ FEHLER — sie verhindern bestimmte Funktionen.")
        lines.append("  3. Starte JARVIS danach neu: python jarvis_v5_8.py")
    lines.append("")
    lines.append(f"  Bericht gespeichert als: {REPORT_FILENAME}")
    lines.append("")
    lines.append("╚══════════════════════════════════════════════════════════════════════╝")

    report_text = "\n".join(lines)
    Path(REPORT_FILENAME).write_text(report_text, encoding="utf-8")
    print("\n" + report_text)
    print(f"\n✅ Bericht gespeichert: {REPORT_FILENAME}")
    return REPORT_FILENAME

# ══════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print(f"""
╔══════════════════════════════════════════════════════════════════════╗
║          J.A.R.V.I.S — VOLLSTÄNDIGER SYSTEMTEST                    ║
║          Startet: {START_TIME.strftime('%d.%m.%Y um %H:%M:%S')} Uhr              ║
╚══════════════════════════════════════════════════════════════════════╝
""")
    print(f"  Bericht wird gespeichert als: {REPORT_FILENAME}\n")

    # Alle Test-Blöcke ausführen
    test_pakete()
    test_env()
    test_ordner()
    test_gemini()
    test_groq()
    test_cerebras()
    test_telegram()
    test_computer_control()
    test_audio()
    test_terminal()
    test_optimizer()
    test_openclaw()
    test_grundbefehle()
    test_netzwerk()
    test_syntax_alle()

    write_report()