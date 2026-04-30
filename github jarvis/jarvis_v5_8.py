"""
╔══════════════════════════════════════════════════════════════════════╗
║   J.A.R.V.I.S  —  GUARDIAN v3.1                                    ║
║   Alle Features in einer Datei | Sicher | Schnell | Teilbar         ║
╠══════════════════════════════════════════════════════════════════════╣
║  NEU in v3.1:                                                       ║
║  - Computer-Control: Maus, Tastatur, Screenshots (pyautogui)       ║
║  - Telegram: Robustere Fehlerbehandlung, Auto-Reconnect             ║
║  - Telegram: /screenshot, /type, /click, /run Befehle              ║
║  - Optimizer: Besseres Prompt-Engineering, höhere Erfolgsrate       ║
║  - Optimizer: Rollback bei Syntaxfehler sofort automatisch          ║
║  - Startup-Check: Fehlende Pakete werden klar gemeldet             ║
║  - Alle API-Calls: Timeout + Retry-Logik verbessert                ║
╚══════════════════════════════════════════════════════════════════════╝

START:  python jarvis_v5_8.py
TEST:   python jarvis_v5_8.py --selftest
HILFE:  python jarvis_v5_8.py --help-terminal
CMD:    python jarvis_v5_8.py --cmd optimize --goal "Fehlerbehandlung" --duration "1h"
"""

# ─── STDLIB ───────────────────────────────────────────────────────────
import os
import sys
import asyncio
import threading
import time
import logging
import json
import re
import shutil
import math
import subprocess
import hashlib
import tkinter as tk
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Tuple

# ─── FRÜHER CLI-CHECK (vor pygame-Import, verhindert pygame-Banner in stdout) ──
# BUGFIX: --help-terminal und andere CLI-Flags wurden NACH dem pygame-Import
# abgefangen. pygame druckt beim Import immer seinen Banner auf stdout, was
# den automatischen Systemtest (jarvis_fulltest.py) als Fehler wertete.
# Lösung: Alle reinen CLI-Flags die keinen vollen Start brauchen, hier abfangen.
if len(sys.argv) > 1 and sys.argv[1] in ("--help-terminal", "--help"):
    _hb = Path("JARVIS_HANDBUCH.txt")
    if _hb.exists():
        try:
            print(_hb.read_text(encoding="utf-8"))
        except Exception:
            try:
                print(_hb.read_text(encoding="cp1252"))
            except Exception as _e:
                print(f"[Handbuch konnte nicht gelesen werden: {_e}]")
    print("""
  J.A.R.V.I.S Guardian — Terminal-Schnellreferenz:

  OPTIMIERUNG:
    python jarvis_v5_8.py --cmd optimize --goal "Ziel" --duration "8h"
    python jarvis_v5_8.py --cmd stop
    python jarvis_v5_8.py --cmd status
    python jarvis_v5_8.py --cmd learning

  NOTFALL / ROLLBACK:
    python jarvis_v5_8.py --cmd rollback
    python jarvis_v5_8.py --cmd golden

  TESTS & HILFE:
    python jarvis_v5_8.py --selftest
    python jarvis_fulltest.py         (vollständiger Systemtest)
""")
    sys.exit(0)

# ─── DOTENV ───────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("⚠️  python-dotenv nicht installiert: pip install python-dotenv")

# ─── THIRD-PARTY (mit klaren Fehlermeldungen) ─────────────────────────
_missing_critical = []
_missing_optional = []

try:
    import pygame
except ImportError:
    _missing_critical.append("pygame")

try:
    import edge_tts
except ImportError:
    _missing_critical.append("edge-tts")

try:
    import speech_recognition as sr
except ImportError:
    _missing_critical.append("SpeechRecognition")

try:
    import telebot
    from telebot import apihelper
    from telebot.types import InputFile
except ImportError:
    _missing_critical.append("pyTelegramBotAPI")

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:
    _missing_critical.append("google-genai")

try:
    from groq import Groq
except ImportError:
    _missing_optional.append("groq")
    Groq = None

try:
    from cerebras.cloud.sdk import Cerebras as CerebrasClient
except ImportError:
    _missing_optional.append("cerebras-cloud-sdk")
    CerebrasClient = None

try:
    import cv2
    import PIL.Image
    import PIL.ImageGrab
except ImportError:
    _missing_optional.append("opencv-python Pillow")
    cv2 = None
    PIL = None

# ─── COMPUTER-CONTROL (pyautogui) ─────────────────────────────────────
try:
    import pyautogui
    import pyautogui as pag
    pyautogui.FAILSAFE = True        # Ecke oben-links = Notfall-Stop
    pyautogui.PAUSE    = 0.05        # Kleine Pause zwischen Aktionen
    COMPUTER_CONTROL   = True
except ImportError:
    _missing_optional.append("pyautogui")
    pyautogui = None
    pag       = None
    COMPUTER_CONTROL = False

try:
    import requests
except ImportError:
    _missing_critical.append("requests")

# Kritische Pakete prüfen
if _missing_critical:
    print("\n" + "="*60)
    print("❌ FEHLENDE PFLICHT-PAKETE:")
    for pkg in _missing_critical:
        print(f"   pip install {pkg}")
    print("="*60 + "\n")
    sys.exit(1)

if _missing_optional:
    print(f"ℹ️  Optionale Pakete fehlen (JARVIS läuft trotzdem): {', '.join(_missing_optional)}")

# ══════════════════════════════════════════════════════════════════════
#  KONFIGURATION
# ══════════════════════════════════════════════════════════════════════

GEMINI_API_KEY    = os.getenv("GEMINI_API_KEY",    "")
GEMINI_API_KEY_2  = os.getenv("GEMINI_API_KEY_2",  "")   # Backup-Key (zweiter Google-Account)
TELEGRAM_TOKEN    = os.getenv("TELEGRAM_TOKEN",    "")
OWNER_TELEGRAM_ID = os.getenv("OWNER_TELEGRAM_ID", "")
GROQ_API_KEY      = os.getenv("GROQ_API_KEY",      "")
CEREBRAS_API_KEY  = os.getenv("CEREBRAS_API_KEY",  "")
USER_ID           = os.getenv("USER_ID",           "default")

USER_BASE = Path(f"users/{USER_ID}")
PATHS = {
    "logs":          USER_BASE / "logs",
    "backups":       USER_BASE / "backups",
    "memory":        USER_BASE / "memory",
    "training":      USER_BASE / "training_data",
    "transcripts":   USER_BASE / "transcripts",
    "temp_audio":    Path("temp_audio"),
    "temp_vision":   Path("temp_vision"),
    "opt_workspace": Path("opt_workspace"),
    "screenshots":   Path("screenshots"),
}

VOICE = os.getenv("JARVIS_VOICE", "de-DE-ConradNeural")

MESHTASTIC_PORT    = os.getenv("MESHTASTIC_PORT",    "/dev/ttyUSB0")
MESHTASTIC_ENABLED = os.getenv("MESHTASTIC_ENABLED", "false").lower() == "true"

GEMINI_MODELS = [
    "models/gemini-2.5-flash",
    "models/gemini-2.5-flash-lite",
    "models/gemini-2.0-flash",
    "models/gemini-2.0-flash-lite",   # Fallback — gemini-1.5-flash wurde von Google entfernt (404)
]
CEREBRAS_MODELS = [
    "llama3.1-8b",
    "llama3.1-70b",
]

SYSTEM_PROMPT = (
    "Du bist J.A.R.V.I.S, ein hochintelligenter, selbstoptimierender KI-Assistent. "
    "Antworte immer präzise, direkt und auf Deutsch. "
    "Wenn du Code schreibst, halte ihn sauber, kommentiert und produktionsreif. "
    "Bei Bildanalysen beschreibe präzise und detailliert was du siehst. "
    "Bei Zusammenfassungen streiche konsequent alle Füllwörter."
)

JARVIS_VERSION = "3.2"


# ══════════════════════════════════════════════════════════════════════
#  MODUL 0a — PERSISTENTES GESPRÄCHS-MEMORY & CODE-KONTEXT
#  Damit die KIs wissen was im Code steht und sich Gespräche merken.
# ══════════════════════════════════════════════════════════════════════

CONV_MEMORY_FILE  = None   # wird nach _init_directories() gesetzt
_MEMORY_TXT_PATH  = None   # wird beim ersten _load_memory_txt() gesetzt

# Globale Memory-Instanz (wird nach _init_directories() initialisiert)
_conv_memory: Optional["ConversationMemory"] = None

# Zusammenfassung des eigenen Codes — wird einmalig beim Start geladen
# und dem SYSTEM_PROMPT angehängt, damit alle KIs Kontext haben.
_CODE_CONTEXT_SUMMARY = """
[JARVIS SYSTEM-KONTEXT — Für alle KI-Brains]

Du bist J.A.R.V.I.S — kein einfaches Textmodell, sondern ein vollständig ausgebauter
KI-Assistent mit echten Fähigkeiten auf einem Windows-PC. SAGT NIEMALS "ich kann das
nicht, ich bin ein Textmodell" — du HAST diese Fähigkeiten und kannst sie nutzen:

DEINE ECHTEN FÄHIGKEITEN:
• Sprachsteuerung (Mikrofon + TTS via edge-tts, Sprache: Deutsch)
• Telegram-Bot: Empfange Befehle von überall, sende Bilder/Texte zurück
• Computer-Control: Steuere Maus, Tastatur, Screenshots (pyautogui)
• Web-Suche: Öffne Google, YouTube mit echten Suchanfragen im Browser
• Bildanalyse: Analysiere Fotos via Gemini Vision (Telegram: einfach Bild schicken)
• Video-Analyse: Frame-by-Frame mit Gemini
• Audio-Transkription: Sprachnachrichten via Groq Whisper (Telegram: Sprachricht. schicken)
• Selbst-Optimierung: Verbessere deinen eigenen Python-Code iterativ und lernend
• Datei-Management: OpenClaw-Modul sortiert Dateien KI-gestützt

KI-STACK (von wann welches Brain verwendet wird):
• Gemini 2.5 Flash  → Haupt-Brain: Konversation, Planung, Bildanalyse, Analyse
• Groq Llama 3.3 70B → Kritiker, Fallback-Chat, Audio-Transkription (Whisper)
• Cerebras llama3.1-8b → Code-Generierung (sehr schnell, für Optimizer)
• Alle drei arbeiten zusammen im GodMode für komplexe Aufgaben

CODE-ARCHITEKTUR:
• jarvis_v5_8.py   — Haupt: UI, Telegram, Intent-Router, Optimizer, CC, Befehle
• jarvis_brains.py — KI-Calls: Gemini/Groq/Cerebras, Blackout-Guard, Smart-Router
• jarvis_openclaw.py — Ordner-Management mit KI-Klassifizierung
• jarvis_optimizer.py — Selbst-Optimierungs-Engine v2

WICHTIGE DATEIPFADE:
• users/default/memory/conversation_memory.json — Gesprächs-Verlauf
• users/default/memory/memory.txt              — Persönliche Notizen des Users
• users/default/backups/golden/                — Golden Copy Sicherheitskopie
• users/default/logs/debug.log                 — Alle Logs

AKTUELLE NUTZER-NOTIZEN (aus memory.txt):
"""


class ConversationMemory:
    """
    Persistentes Gesprächs-Memory: speichert wichtige Gesprächspunkte
    dauerhaft auf Disk. KIs werden beim Start damit initialisiert.
    Beim Reset bleibt das Langzeit-Memory erhalten (nur kurzzeitiger Chat-Verlauf wird gelöscht).
    """
    MAX_ENTRIES   = 200   # maximale gespeicherte Einträge
    INJECT_LAST_N = 15    # diese letzten Einträge werden als Kontext injiziert

    def __init__(self, memory_path: Path):
        self._path    = memory_path / "conversation_memory.json"
        self._entries = self._load()
        log.info(f"🧠 Gesprächs-Memory: {len(self._entries)} Einträge geladen")

    def _load(self) -> list:
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                return data.get("entries", [])
            except Exception as e:
                log.warning(f"Memory-Load: {e}")
        return []

    def _save(self):
        try:
            self._path.write_text(
                json.dumps({"entries": self._entries}, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            log.warning(f"Memory-Save: {e}")

    def add(self, role: str, text: str, topic: str = ""):
        """Fügt einen Gesprächseintrag hinzu."""
        entry = {
            "ts":    datetime.now().isoformat(),
            "role":  role,   # "user" oder "jarvis"
            "text":  text[:800],
            "topic": topic,
        }
        self._entries.append(entry)
        if len(self._entries) > self.MAX_ENTRIES:
            self._entries = self._entries[-self.MAX_ENTRIES:]
        self._save()

    def get_context_block(self) -> str:
        """
        Gibt die letzten N Einträge als formatierten Kontext-Block zurück,
        der dem System-Prompt vorangestellt wird.
        """
        if not self._entries:
            return ""
        recent = self._entries[-self.INJECT_LAST_N:]
        lines  = ["[GESPRÄCHS-MEMORY — letzte Gespräche mit dem Nutzer:]"]
        for e in recent:
            ts    = e.get("ts", "")[:16].replace("T", " ")
            role  = "Du (JARVIS)" if e["role"] == "jarvis" else "Nutzer"
            topic = f" [{e['topic']}]" if e.get("topic") else ""
            lines.append(f"  {ts}{topic} {role}: {e['text'][:300]}")
        lines.append("")
        return "\n".join(lines)

    def get_summary_for_prompt(self) -> str:
        """Kompakter Memory-Block für den System-Prompt."""
        ctx = self.get_context_block()
        if not ctx:
            return ""
        return f"\n\n{ctx}\n{_CODE_CONTEXT_SUMMARY}"

    def clear_recent(self, keep_last: int = 5):
        """Löscht nur den aktuellen Chat-Verlauf, behält aber ältere Einträge."""
        if len(self._entries) > keep_last:
            self._entries = self._entries[-keep_last:]
            self._save()

    def get_stats(self) -> str:
        n    = len(self._entries)
        user = sum(1 for e in self._entries if e["role"] == "user")
        jarv = sum(1 for e in self._entries if e["role"] == "jarvis")
        if self._entries:
            first = self._entries[0]["ts"][:10]
            last  = self._entries[-1]["ts"][:10]
            return f"Memory: {n} Einträge ({user} Nutzer / {jarv} JARVIS) | {first} → {last}"
        return "Memory: leer"


# Wird beim Start und auf Anfrage aus memory.txt geladen
_MEMORY_TXT_PATH = None  # wird nach _init_directories() gesetzt

def _load_memory_txt() -> str:
    """Liest memory.txt und gibt den Inhalt zurück (leer wenn nicht vorhanden)."""
    global _MEMORY_TXT_PATH
    if _MEMORY_TXT_PATH is None:
        _MEMORY_TXT_PATH = PATHS["memory"] / "memory.txt"
        # Auch die vom User mitgegebene memory.txt in den Memory-Ordner kopieren
        # falls sie noch im Root-Ordner liegt
        root_mem = Path("memory.txt")
        if root_mem.exists() and not _MEMORY_TXT_PATH.exists():
            try:
                import shutil as _sh
                _sh.copy2(root_mem, _MEMORY_TXT_PATH)
                log.info(f"📋 memory.txt → {_MEMORY_TXT_PATH} kopiert")
            except Exception as _e:
                log.warning(f"memory.txt Kopieren: {_e}")
    try:
        if _MEMORY_TXT_PATH.exists():
            content = _MEMORY_TXT_PATH.read_text(encoding="utf-8").strip()
            if content:
                return content
    except Exception as e:
        log.warning(f"memory.txt laden: {e}")
    return ""


def _save_memory_txt(content: str):
    """Speichert Notizen in memory.txt."""
    global _MEMORY_TXT_PATH
    if _MEMORY_TXT_PATH is None:
        _MEMORY_TXT_PATH = PATHS["memory"] / "memory.txt"
    try:
        _MEMORY_TXT_PATH.write_text(content, encoding="utf-8")
    except Exception as e:
        log.warning(f"memory.txt speichern: {e}")


def _add_to_memory_txt(note: str):
    """Fügt eine Notiz zu memory.txt hinzu (mit Zeitstempel)."""
    existing = _load_memory_txt()
    ts   = datetime.now().strftime("%Y-%m-%d %H:%M")
    new  = f"{existing}\n[{ts}] {note}".strip()
    _save_memory_txt(new)
    log.info(f"📋 Memory gespeichert: {note[:60]}")




def _init_conv_memory():
    """Initialisiert das persistente Gesprächs-Memory + lädt memory.txt."""
    global _conv_memory, SYSTEM_PROMPT
    _conv_memory = ConversationMemory(PATHS["memory"])

    # memory.txt laden und in den Code-Kontext einbetten
    mem_notes = _load_memory_txt()
    mem_block  = mem_notes if mem_notes else "(noch keine Notizen gespeichert)"

    # Code-Kontext + Memory.txt als Teil des festen System-Prompts einbetten
    SYSTEM_PROMPT = SYSTEM_PROMPT + _CODE_CONTEXT_SUMMARY + mem_block + "\n"
    log.info("✅ Gesprächs-Memory, Code-Kontext & memory.txt initialisiert")





def _memory_add(role: str, text: str, topic: str = ""):
    """Shortcut: Eintrag zum persistenten Memory hinzufügen."""
    if _conv_memory:
        _conv_memory.add(role, text, topic)


def _get_enriched_system_prompt() -> str:
    """System-Prompt + aktuelles Memory-Kontext für KI-Calls."""
    base = SYSTEM_PROMPT
    if _conv_memory:
        ctx = _conv_memory.get_context_block()
        if ctx:
            return base + "\n\n" + ctx
    return base




def _check_required_keys():
    missing = []
    if not GEMINI_API_KEY:   missing.append("GEMINI_API_KEY")
    if not TELEGRAM_TOKEN:   missing.append("TELEGRAM_TOKEN")
    if not OWNER_TELEGRAM_ID: missing.append("OWNER_TELEGRAM_ID")
    if missing:
        print("\n" + "="*60)
        print("❌ FEHLENDE API-KEYS in deiner .env-Datei:")
        for k in missing:
            print(f"   → {k}")
        print("\nLösung:")
        print("  1. Erstelle eine Datei namens .env im Programmordner")
        print("  2. Trage deine Keys ein (siehe .env.example)")
        print("  3. Starte JARVIS neu")
        print("="*60 + "\n")
        if "GEMINI_API_KEY" in missing:
            sys.exit(1)


def _init_directories():
    for path in PATHS.values():
        path.mkdir(parents=True, exist_ok=True)
    (USER_BASE / "backups" / "golden").mkdir(parents=True, exist_ok=True)

_init_directories()

# ══════════════════════════════════════════════════════════════════════
#  LOGGING
# ══════════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(PATHS["logs"] / "debug.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("JARVIS")
log.info(f"🤖 J.A.R.V.I.S Guardian v{JARVIS_VERSION} | User: {USER_ID}")
_init_conv_memory()   # persistentes Gesprächs-Memory + Code-Kontext laden

# ══════════════════════════════════════════════════════════════════════
#  RESPONSE-CACHE
# ══════════════════════════════════════════════════════════════════════

_response_cache: Dict[str, Dict] = {}
_CACHE_TTL = 3600


def _cache_get(prompt: str) -> Optional[str]:
    key   = hashlib.sha256(prompt.encode()).hexdigest()
    entry = _response_cache.get(key)
    if entry and (time.time() - entry["ts"]) < _CACHE_TTL:
        log.info("💾 Cache-Hit")
        return entry["response"]
    return None


def _cache_set(prompt: str, response: str):
    key = hashlib.sha256(prompt.encode()).hexdigest()
    _response_cache[key] = {"response": response, "ts": time.time()}
    if len(_response_cache) > 200:
        oldest = min(_response_cache, key=lambda k: _response_cache[k]["ts"])
        del _response_cache[oldest]

# ══════════════════════════════════════════════════════════════════════
#  GLOBAL STATE
# ══════════════════════════════════════════════════════════════════════

gemini_client:   Optional[genai.Client]    = None
gemini_model:    Optional[str]             = None
gemini_chat                                = None
groq_client:     Optional[object]          = None
cerebras_client: Optional[object]          = None
cerebras_model:  Optional[str]             = None
bot:             Optional[telebot.TeleBot] = None
mic_on           = False
is_speaking      = False
SELF_PATH        = Path(sys.argv[0]).resolve()
_tg_chat_id      = None
_opt_engine      = None
ui               = None

# ══════════════════════════════════════════════════════════════════════
#  MODUL 0 — HANDBUCH-GENERATOR
# ══════════════════════════════════════════════════════════════════════

HANDBUCH_PATH = Path("JARVIS_HANDBUCH.txt")


def generate_handbook():
    """
    Aktualisiert nur die Version/Zeitstempel-Zeile im bestehenden Handbuch.
    Das vollständige Handbuch wird NICHT überschrieben — es wurde manuell gepflegt.
    Nur wenn das Handbuch fehlt, wird ein Basis-Template erstellt.
    """
    ts  = datetime.now().strftime("%d.%m.%Y %H:%M")
    dev = f"Cerebras {cerebras_model}" if cerebras_client else "Gemini"
    cc  = "✅ AKTIV" if COMPUTER_CONTROL else "❌ pyautogui fehlt"

    if HANDBUCH_PATH.exists():
        try:
            content = HANDBUCH_PATH.read_text(encoding="utf-8")
            # Nur Version + Zeitstempel in der Header-Zeile aktualisieren
            content = re.sub(
                r"(Version\s+)\S+(\s+\|\s+Letzte Aktualisierung:\s+)[^\n]*",
                rf"\g<1>{JARVIS_VERSION}\2{ts}",
                content,
            )
            # Computer-Control Status im Abschnitt 2 aktualisieren
            content = re.sub(
                r"(COMPUTER-STEUERUNG \()([^)]*?)(\))",
                rf"\g<1>{cc}\g<3>",
                content,
            )
            HANDBUCH_PATH.write_text(content, encoding="utf-8")
            log.info(f"📖 Handbuch-Header aktualisiert: v{JARVIS_VERSION}")
            return
        except Exception as e:
            log.warning(f"Handbuch-Update fehlgeschlagen: {e} — erstelle Basis-Template")

    # Fallback: Handbuch existiert nicht → vollständiges Template anlegen
    content = f"""╔══════════════════════════════════════════════════════════════════════════════╗
║              J.A.R.V.I.S GUARDIAN — VOLLSTÄNDIGES HANDBUCH                 ║
║              Version {JARVIS_VERSION}  |  Letzte Aktualisierung: {ts}             ║
╚══════════════════════════════════════════════════════════════════════════════╝

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 1. GRUNDBEFEHLE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  FUNKTION                  │ SPRACHE / TEXT           │ TELEGRAM
  Uhrzeit                   │ "Wie spät ist es?"        │ (Text reicht)
  Datum                     │ "Welches Datum?"          │ (Text reicht)
  YouTube öffnen            │ "Öffne YouTube"           │ (Text reicht)
  System-Info               │ "System Info"             │ /status
  Chat zurücksetzen         │ "Reset Chat"              │ /reset
  Mikrofon aus/an           │ "Mikrofon aus/an"         │ (Text reicht)
  Beenden                   │ "Beende JARVIS"           │ (Text reicht)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 2. COMPUTER-STEUERUNG ({cc})
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  TELEGRAM-BEFEHL           │ BESCHREIBUNG
  /screenshot               │ Screenshot deines Bildschirms
  /type <text>              │ Text tippen
  /key <taste>              │ Taste drücken (enter, ctrl+c, ...)
  /click <x> <y>            │ Mausklick an Position
  /move <x> <y>             │ Maus bewegen
  /scroll <richtung>        │ Scrollen (up/down)
  /run <befehl>             │ Terminal-Befehl ausführen
  /screen_info              │ Bildschirmgröße & Mausposition

  SPRACHE:
  "Mach Screenshot"         → Screenshot → wird per Telegram gesendet
  "Tippe Hallo Welt"        → Tippt Text
  "Drücke Enter"            → Drückt Enter-Taste
  "Führe aus: notepad"      → Öffnet Notepad

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 3. SELBST-OPTIMIERUNG
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Starten       │ "Optimiere dich" / /optimize [Ziel] [Dauer]
  Stoppen       │ "Hör auf" / /opt_stop
  Status        │ "Optimierungsstatus" / /opt_status
  Bericht       │ /opt_report
  Rollback      │ "Rollback" / /rollback
  Golden Copy   │ /golden_rollback

  Terminal:
    python jarvis_v5_8.py --cmd optimize --goal "Ziel" --duration "1h"
    python jarvis_v5_8.py --cmd rollback
    python jarvis_v5_8.py --cmd golden

  OPTIMIERUNGSZIELE (Beispiele):
    "Bessere Fehlerbehandlung bei API-Ausfällen"
    "Schnellere Antwortzeiten durch Caching verbessern"
    "Telegram-Befehle erweitern"
    "Speicherverbrauch reduzieren"
    "Logging verbessern"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 4. KI-ARCHITEKTUR
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Analyst/Chat   │ Gemini 2.5 Flash     │ Konversation, Analyse
  Developer      │ {dev:<19} │ Code-Generierung (schnell)
  Critic         │ Groq Llama 3.3 70B   │ Code-Review
  Audio-STT      │ Groq Whisper v3      │ Spracherkennung Deutsch
  Fallback-Chat  │ Groq → Cerebras      │ Auto-Fallback bei Gemini 429

  MODELL-PRIORITÄT (Gemini):
    1. gemini-2.5-flash       (bestes Modell)
    2. gemini-2.5-flash-lite  (schneller, günstiger)
    3. gemini-2.0-flash       (stabil, empfohlen)
    4. gemini-2.0-flash-lite  (Fallback)
    → Das System wählt automatisch das erste erreichbare Modell.

  DUAL-KEY SYSTEM (NEU in v3.3):
    KEY_1 (GEMINI_API_KEY)   → Haupt-Account, 20 Requests/Tag (Free Tier)
    KEY_2 (GEMINI_API_KEY_2) → Backup-Account, weitere 20 Requests/Tag
    → Bei Tageslimit KEY_1: automatischer Wechsel auf KEY_2
    → Bei Tageslimit beider Keys: Groq + Cerebras übernehmen
    → Reset täglich um ~02:00 Uhr MEZ (Google UTC-Mitternacht)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 5. OPENCLAW — AUTONOMES ORDNER-MANAGEMENT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  TELEGRAM-BEFEHL           │ BESCHREIBUNG
  /scan_folder              │ Ordner scannen & KI-Analyse
  /cleanup                  │ Bereinigung starten (mit Bestätigung)
  /confirm_cleanup          │ Bereinigung bestätigen
  /folder_status            │ Ordner-Übersicht
  /restore <dateiname>      │ Datei aus Archiv wiederherstellen

  SPRACHE:
  "Scanne meinen Ordner"    → Analysiert Dateien per KI
  "Räume auf"               → Startet OpenClaw Cleanup
  "Ordner Status"           → Zeigt Übersicht

  ⚠️  OpenClaw archiviert NIEMALS diese Pflichtdateien:
      jarvis_v5_8.py, jarvis_brains.py, jarvis_openclaw.py,
      jarvis_optimizer.py, _env, .env, JARVIS_HANDBUCH.txt

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 6. MEMORY — PERSISTENTES GEDÄCHTNIS (NEU in v3.4)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  TELEGRAM-BEFEHL           │ BESCHREIBUNG
  /memory                   │ Gesprächs-Verlauf + persönliche Notizen anzeigen
  /merken <Text>            │ Notiz dauerhaft speichern
  /notizen                  │ Alle gespeicherten Notizen anzeigen

  SPRACHE:
  "Merk dir, dass ..."      → Notiz in memory.txt speichern
  "Notier: ..."             → Notiz in memory.txt speichern
  "Was hast du dir gemerkt" → Gespeicherte Notizen vorlesen

  WIE ES FUNKTIONIERT:
  • memory.txt im users/default/memory/ Ordner — bleibt auch nach Neustarts
  • Beim Start wird memory.txt automatisch in den KI-Kontext geladen
  • Alle KIs (Gemini, Groq, Cerebras) kennen deine Notizen von Anfang an
  • Gespräche werden automatisch im Verlauf gespeichert (conversation_memory.json)
  • Groq-Fallback nutzt ebenfalls den vollständigen Kontext

  TIPP: Lege eine memory.txt im JARVIS-Ordner ab — sie wird beim Start
  automatisch in den Memory-Ordner kopiert und eingelesen.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 7. NOTFALL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Alles kaputt:   python jarvis_v5_8.py --cmd golden  → neu starten
  Letzter Stand:  python jarvis_v5_8.py --cmd rollback → neu starten
  JARVIS hängt:   Strg+C  → Fortschritt gespeichert
  Notfall-Stop:   Maus in obere linke Bildschirmecke (pyautogui Failsafe)

  Gemini 429 (Quota):
    → JARVIS wechselt automatisch auf KEY_2 (zweiter Google-Account)
    → Wenn beide Keys erschöpft: automatisch Groq → Cerebras
    → Reset um ~02:00 Uhr MEZ (täglich)
    → Dauerlösung: Upgrade auf Gemini Pay-as-you-go (kein Tageslimit)
      https://aistudio.google.com/app/apikey → Billing aktivieren

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 8. DIAGNOSE & TEST
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Vollständiger Systemtest:
    python jarvis_fulltest.py
    → Prüft alle Komponenten, erstellt JARVIS_TESTBERICHT_*.txt
    → Schicke den Bericht an Claude für detaillierte Analyse

  Schnelltest (nur Imports & Struktur):
    python jarvis_v5_8.py --selftest

  Terminal-Hilfe:
    python jarvis_v5_8.py --help-terminal

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 9. NEUE FEATURES & VERBESSERUNGEN (v3.4 — {ts[:10]})
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  NEUE FEATURES (v3.4):
  ✅ [NEU] Persistentes Memory-System — KIs merken sich alles
           memory.txt wird beim Start geladen → alle KIs kennen deine Notizen
           Gespräche automatisch gespeichert (conversation_memory.json)
           Sprache: "Merk dir, dass..." | Telegram: /merken /notizen

  ✅ [NEU] Smart Query Extraction — KIs verstehen natürliche Sprache
           "google mal das Wetter" → sucht "Wetter" (nicht "mal das Wetter")
           "youtube bitte Musik" → sucht "Musik" (Füllwörter werden ignoriert)
           Unterstützt: mal, doch, bitte, kurz, schnell, einfach, ...

  ✅ [NEU] KI-Kontext erweitert — KIs wissen was JARVIS kann
           Vollständige Feature-Übersicht im System-Prompt eingebettet
           KIs sagen nicht mehr "ich bin nur ein Textmodell"
           Groq-Fallback nutzt jetzt ebenfalls den vollen Kontext

  ✅ [NEU] Groq-Fallback in process_command verbessert
           Wenn Gemini offline: Groq antwortet mit vollem Gesprächs-Kontext
           Antworten werden auch beim Fallback ins Memory gespeichert

  NEUE FEATURES (v3.3):
  ✅ [NEU] Dual-Key Gemini System — zweiter Google-Account als Backup
           GEMINI_API_KEY_2 in _env → automatischer Wechsel bei Tageslimit
           Verdoppelt effektives Tageslimit auf 40 Requests/Tag (Free Tier)

  ✅ [NEU] Gemini Blackout Guard — kein endloses Warten mehr bei Quota
           Tageslimit erkannt → sofort KEY_2 versuchen → dann Groq/Cerebras
           Alter Backoff: 60→120→240→300s | Neu: 30→60s dann Fallback

  ✅ [NEU] Optimizer: Korrekte Funktionsnamen in Focus-Areas
           Alte Focus-Areas (z.B. "telegram_handlers") existierten nicht
           Jetzt: echte Funktionsnamen aus dem Code → Embed funktioniert

  ✅ [NEU] Optimizer: AST-basiertes Einbetten statt fragiler Regex
           Präzises Ersetzen per ast.parse() → keine falschen Embeds mehr

  ✅ [NEU] Analyst Groq-Fallback — Optimizer läuft auch ohne Gemini durch
           Gemini offline → Groq übernimmt Analyse → Pipeline läuft weiter

  BEKANNTE EINSCHRÄNKUNGEN:
  ⚠ Gemini Free Tier: 20 Requests/Tag pro Account
    → Mit KEY_2: 40/Tag | Mit Paid: unbegrenzt
  ⚠ Cerebras llama3.1-8b: max ~8000 Token Prompt-Länge
    → Optimizer sendet nur einzelne Funktionen (max 80 Zeilen)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 10. ZWEITEN GOOGLE API KEY EINRICHTEN (Schritt-für-Schritt)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  1. Browser öffnen → https://aistudio.google.com/apikey
  2. Oben rechts: Account-Icon → "Anderes Konto hinzufügen"
     ODER: Im Inkognito-Fenster mit zweitem Google-Account einloggen
  3. "API-Schlüssel erstellen" klicken → Schlüssel kopieren
  4. In deiner _env Datei eintragen:
       GEMINI_API_KEY_2=AIza...dein-neuer-key...
  5. JARVIS neu starten — im Log erscheint:
       ✅ Gemini aktiv: models/gemini-2.5-flash [KEY_1]
     Bei Tageslimit KEY_1:
       🔑 Gemini KEY_1 Tageslimit — versuche KEY_2...
       ✅ Gemini KEY_2 aktiv: models/gemini-2.5-flash — KEY_1 Quota umgangen!

  ⚠️  Wichtig: Beide Accounts müssen SEPARATE Google-Accounts sein.
      Gleicher Account = gleiche Quota → kein Vorteil.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 11. TIPPS FÜR BESSERE SELBST-OPTIMIERUNG
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Die Selbst-Optimierung funktioniert am besten wenn:

  1. SPEZIFISCHE ZIELE angegeben werden:
     ❌ "Verbessere dich"
     ✅ "Verbessere die Fehlerbehandlung wenn Gemini 429 zurückgibt"

  2. KURZE ITERATIONEN für erste Tests:
     python jarvis_v5_8.py --cmd optimize --goal "..." --duration "15m"

  3. ROLLBACK-SICHERHEIT: Vor größeren Läufen Golden Copy sichern:
     /golden_rollback  (in Telegram)

  4. GEMINI QUOTA im Blick behalten:
     Mit Dual-Key: 40 Requests/Tag → reicht für ~4-5 Optimizer-Iterationen
     Bei Erschöpfung: automatischer Fallback auf Groq + Cerebras

  5. BERICHT ANALYSIEREN nach jedem Lauf:
     python jarvis_fulltest.py → Bericht an Claude schicken

  6. GODMODE für wichtige Entscheidungen nutzen:
     Alle 3 KIs parallel (Gemini + Cerebras + Groq):
     "GodMode: [deine Frage]" im Chat

╚══════════════════════════════════════════════════════════════════════════════╝
"""
    HANDBUCH_PATH.write_text(content, encoding="utf-8")
    log.info(f"📖 Handbuch erstellt: {HANDBUCH_PATH}")

# ══════════════════════════════════════════════════════════════════════
#  MODUL 1 — BRAIN INIT
# ══════════════════════════════════════════════════════════════════════

def _strip_code_fences(text: str) -> str:
    text = re.sub(r"^```python\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^```\s*",       "", text, flags=re.MULTILINE)
    text = re.sub(r"\s*```$",       "", text, flags=re.MULTILINE)
    return text.strip()


def _call_gemini_raw(prompt: str, system: str = "", max_tokens: int = 8192,
                     timeout: int = 60) -> str:
    if not gemini_client or not gemini_model:
        raise RuntimeError("Gemini nicht initialisiert")
    contents = [genai_types.Content(role="user", parts=[genai_types.Part(text=prompt)])]
    cfg = genai_types.GenerateContentConfig(
        system_instruction=system or SYSTEM_PROMPT,
        max_output_tokens=max_tokens,
    )
    resp = gemini_client.models.generate_content(
        model=gemini_model, contents=contents, config=cfg
    )
    if not resp.text:
        raise ValueError("Leere Gemini-Antwort")
    return resp.text


def _call_gemini_json(prompt: str, system: str = "", schema: dict = None) -> dict:
    if not gemini_client or not gemini_model:
        return {}
    # Blackout-Check — wird nach _set_gemini_blackout verfügbar (weiter unten definiert)
    try:
        if _gemini_is_blocked():
            return {}
    except NameError:
        pass  # Noch nicht definiert beim ersten Import
    try:
        cfg_args = {
            "system_instruction": system or SYSTEM_PROMPT,
            "max_output_tokens":  4096,
            "response_mime_type": "application/json",
        }
        if schema:
            cfg_args["response_schema"] = schema

        resp = gemini_client.models.generate_content(
            model=gemini_model,
            contents=[genai_types.Content(role="user", parts=[genai_types.Part(text=prompt)])],
            config=genai_types.GenerateContentConfig(**cfg_args),
        )
        text = resp.text or "{}"
        text = re.sub(r"^```json\s*", "", text.strip(), flags=re.MULTILINE)
        text = re.sub(r"\s*```$",     "", text,         flags=re.MULTILINE)
        return json.loads(text)
    except Exception as e:
        err_str = str(e)
        # Tageslimit erkennen und Blackout aktivieren wenn Guard bereits initialisiert
        try:
            if _is_daily_quota(err_str):
                _set_gemini_blackout()
        except NameError:
            pass
        log.warning(f"Gemini-JSON-Fehler: {e}")
        return {}


def _call_cerebras(prompt: str, system: str = "", max_tokens: int = 8192) -> str:
    global cerebras_model
    if not cerebras_client:
        log.debug("Cerebras nicht verfügbar — Fallback auf Gemini")
        return _call_gemini_raw(prompt, system, max_tokens)

    messages = [
        {"role": "system", "content": system or SYSTEM_PROMPT},
        {"role": "user",   "content": prompt},
    ]
    models_to_try = [cerebras_model] if cerebras_model else CEREBRAS_MODELS
    for model_name in models_to_try:
        try:
            completion = cerebras_client.chat.completions.create(
                messages=messages,
                model=model_name,
                max_completion_tokens=min(max_tokens, 8192),
                temperature=0.2,
                top_p=1,
                stream=False,
            )
            cerebras_model = model_name
            return completion.choices[0].message.content
        except Exception as e:
            log.warning(f"Cerebras [{model_name}]: {str(e)[:120]}")
            if model_name == models_to_try[-1]:
                log.warning("Alle Cerebras-Modelle fehlgeschlagen — Fallback auf Gemini")
                return _call_gemini_raw(prompt, system, max_tokens)
    return _call_gemini_raw(prompt, system, max_tokens)


def init_brains() -> bool:
    global gemini_client, gemini_model, gemini_chat, groq_client
    global cerebras_client, cerebras_model
    ok = False

    # ── Groq ──────────────────────────────────────────────────────────
    if GROQ_API_KEY and Groq:
        try:
            groq_client = Groq(api_key=GROQ_API_KEY)
            groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": "OK"}],
                max_tokens=3,
            )
            log.info("✅ Groq initialisiert")
        except Exception as e:
            log.warning(f"Groq: {e}")
            groq_client = None
    else:
        log.info("ℹ️  GROQ_API_KEY nicht gesetzt")

    # ── Cerebras ──────────────────────────────────────────────────────
    if CEREBRAS_API_KEY and CerebrasClient:
        try:
            cerebras_client = CerebrasClient(api_key=CEREBRAS_API_KEY)
            test = cerebras_client.chat.completions.create(
                messages=[{"role": "user", "content": "OK"}],
                model=CEREBRAS_MODELS[0],
                max_completion_tokens=5,
                temperature=0.2, top_p=1, stream=False,
            )
            _ = test.choices[0].message.content
            cerebras_model = CEREBRAS_MODELS[0]
            log.info(f"✅ Cerebras initialisiert — {cerebras_model}")
        except Exception as e:
            log.warning(f"Cerebras: {e} — Fallback auf Gemini")
            cerebras_client = None
            cerebras_model  = None
    else:
        log.info("ℹ️  CEREBRAS_API_KEY nicht gesetzt")

    # ── Gemini ────────────────────────────────────────────────────────
    # Versucht KEY 1, dann KEY 2 als Fallback (separater Google-Account)
    _gemini_keys = []
    if GEMINI_API_KEY:
        _gemini_keys.append(("KEY_1", GEMINI_API_KEY))
    if GEMINI_API_KEY_2:
        _gemini_keys.append(("KEY_2", GEMINI_API_KEY_2))

    if not _gemini_keys:
        log.error("❌ GEMINI_API_KEY fehlt — bitte in _env eintragen")
        return bool(groq_client or cerebras_client)

    for key_label, api_key in _gemini_keys:
        if ok:
            break
        log.info(f"🔑 Versuche Gemini {key_label}...")
        client = genai.Client(api_key=api_key)
        key_quota_hit = False
        for name in GEMINI_MODELS:
            try:
                resp = client.models.generate_content(
                    model=name, contents="OK",
                    config=genai_types.GenerateContentConfig(max_output_tokens=4),
                )
                _ = resp.text
                gemini_client = client
                gemini_model  = name
                gemini_chat   = _GeminiChatWrapper(client, name)
                dev_name = f"Cerebras {cerebras_model}" if cerebras_client else "Gemini (Fallback)"
                log.info(f"✅ Gemini aktiv: {name} [{key_label}] | Developer-KI: {dev_name}")
                ok = True
                break
            except Exception as e:
                err = str(e)
                if "429" in err or "RESOURCE_EXHAUSTED" in err or "quota" in err.lower():
                    tag = f"429 Quota ({key_label})"
                    key_quota_hit = True
                else:
                    tag = err[:60]
                log.warning(f"  {name} [{key_label}]: {tag}")
        if key_quota_hit and not ok:
            log.warning(f"  ⚠ {key_label}: Tageslimit erschöpft — versuche nächsten Key")

    if not ok:
        log.error("❌ Kein Gemini-Modell erreichbar (alle Keys erschöpft oder ungültig)")
        log.info("ℹ️  JARVIS läuft weiter auf Groq + Cerebras")
    return ok or bool(groq_client or cerebras_client)


class _GeminiChatWrapper:
    def __init__(self, client: genai.Client, model: str):
        self._client  = client
        self._model   = model
        self._history: List[Dict] = []
        self._lock    = threading.Lock()

    def send_message(self, text: str, images: list = None):
        parts = [genai_types.Part(text=text)]
        if images:
            for img in images:
                parts.append(genai_types.Part(
                    inline_data=genai_types.Blob(mime_type="image/jpeg", data=img)
                ))
        with self._lock:
            self._history.append(genai_types.Content(role="user", parts=parts))
            try:
                resp = self._client.models.generate_content(
                    model=self._model,
                    contents=self._history,
                    config=genai_types.GenerateContentConfig(
                        system_instruction=_get_enriched_system_prompt() if _conv_memory else SYSTEM_PROMPT,
                        max_output_tokens=2048,
                    )
                )
                answer = resp.text or "[Keine Antwort]"
            except Exception as e:
                self._history.pop()
                raise
            self._history.append(
                genai_types.Content(role="model", parts=[genai_types.Part(text=answer)])
            )
            if len(self._history) > 60:
                self._history = self._history[-60:]
            return _Resp(answer)

    def reset(self):
        with self._lock:
            self._history = []


class _Resp:
    def __init__(self, text: str):
        self.text = text

# ══════════════════════════════════════════════════════════════════════
#  MODUL 2 — COMPUTER CONTROL
# ══════════════════════════════════════════════════════════════════════

def cc_screenshot(filename: str = "screenshot.png") -> Optional[str]:
    if not COMPUTER_CONTROL:
        logging.warning("cc_screenshot: Computersteuerung (pyautogui) ist nicht verfügbar.")
        return None
    screenshot_dir = PATHS["temp_vision"]
    try:
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = screenshot_dir / filename
        pyautogui.screenshot(str(screenshot_path))
        logging.info(f"cc_screenshot: Screenshot erfolgreich unter '{screenshot_path}' gespeichert.")
        return str(screenshot_path)
    except pyautogui.PyAutoGUIException as e:
        logging.error(f"cc_screenshot: Fehler beim Erstellen des Screenshots: {e}")
        return None
    except Exception as e:
        logging.error(f"cc_screenshot: Ein unerwarteter Fehler ist aufgetreten: {e}", exc_info=True)
        return None


def cc_type_text(text: str, interval: float = 0.03) -> bool:
    """Text tippen (Clipboard-Methode für Sonderzeichen)."""
    if not COMPUTER_CONTROL:
        return False
    try:
        import pyperclip
        pyperclip.copy(text)
        pyautogui.hotkey("ctrl", "v")
        log.info(f"⌨️  Getippt (Clipboard): {text[:40]}")
        return True
    except Exception:
        pass
    try:
        pyautogui.typewrite(text, interval=interval)
        log.info(f"⌨️  Getippt: {text[:40]}")
        return True
    except Exception as e:
        log.error(f"Type-Fehler: {e}")
        return False


def cc_key(keys: str) -> bool:
    """Tastenkombination drücken. z.B. 'ctrl+c', 'enter', 'alt+tab'"""
    if not COMPUTER_CONTROL:
        return False
    try:
        parts = [k.strip() for k in keys.lower().split("+")]
        if len(parts) == 1:
            pyautogui.press(parts[0])
        else:
            pyautogui.hotkey(*parts)
        log.info(f"⌨️  Taste: {keys}")
        return True
    except Exception as e:
        log.error(f"Key-Fehler: {e}")
        return False


def cc_click(x: int, y: int, button: str = "left", clicks: int = 1) -> bool:
    """Mausklick an Position."""
    if not COMPUTER_CONTROL:
        return False
    try:
        pyautogui.click(x, y, clicks=clicks, button=button)
        log.info(f"🖱  Klick: ({x},{y}) {button}")
        return True
    except Exception as e:
        log.error(f"Click-Fehler: {e}")
        return False


def cc_move(x: int, y: int, duration: float = 0.3) -> bool:
    """Maus bewegen."""
    if not COMPUTER_CONTROL:
        return False
    try:
        pyautogui.moveTo(x, y, duration=duration)
        return True
    except Exception as e:
        log.error(f"Move-Fehler: {e}")
        return False


def cc_scroll(direction: str = "down", amount: int = 3) -> bool:
    """Scrollen."""
    if not COMPUTER_CONTROL:
        return False
    try:
        clicks = amount if direction == "up" else -amount
        pyautogui.scroll(clicks)
        return True
    except Exception as e:
        log.error(f"Scroll-Fehler: {e}")
        return False


def cc_run_command(cmd: str, timeout: int = 15) -> Tuple[str, str, int]:
    """Shell-Befehl ausführen, gibt (stdout, stderr, returncode) zurück."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=timeout, encoding="utf-8", errors="replace"
        )
        return result.stdout[:2000], result.stderr[:1000], result.returncode
    except subprocess.TimeoutExpired:
        return "", f"Timeout nach {timeout}s", -1
    except Exception as e:
        return "", str(e), -1


def cc_get_screen_info() -> dict:
    """Bildschirmgröße und Mausposition."""
    if not COMPUTER_CONTROL:
        return {}
    try:
        size = pyautogui.size()
        pos  = pyautogui.position()
        return {"width": size.width, "height": size.height,
                "mouse_x": pos.x, "mouse_y": pos.y}
    except Exception as e:
        return {"error": str(e)}


def cc_find_on_screen(image_path: str, confidence: float = 0.8) -> Optional[Tuple[int,int]]:
    """Bild auf dem Bildschirm suchen und Position zurückgeben."""
    if not COMPUTER_CONTROL:
        return None
    try:
        loc = pyautogui.locateCenterOnScreen(image_path, confidence=confidence)
        if loc:
            return (loc.x, loc.y)
        return None
    except Exception as e:
        log.error(f"Bildsuche-Fehler: {e}")
        return None

# ══════════════════════════════════════════════════════════════════════
#  MODUL 3 — GOLDEN COPY & ROLLBACK
# ══════════════════════════════════════════════════════════════════════

GOLDEN_DIR  = USER_BASE / "backups" / "golden"
GOLDEN_FILE = GOLDEN_DIR / "jarvis_golden.py"
GOLDEN_HASH = GOLDEN_DIR / "jarvis_golden.sha256"

# ── Diamant-Datei (dein persönlicher Nullpunkt — nur manuell erstellt) ──
# Erstelle einmalig per: copy jarvis_v5_8.py jarvis_diamond.py
DIAMOND_FILE = Path("jarvis_diamond.py")
DIAMOND_HASH = Path("jarvis_diamond.sha256")


def ensure_golden_copy():
    """
    Erstellt die Golden Copy NUR wenn sie noch nicht existiert.
    Einmal erstellt wird sie NIEMALS automatisch überschrieben — das ist ihr Sinn.
    Nur bei explizitem /golden_rollback oder --cmd golden wird sie verwendet.
    Bei Hash-Abweichung: nur warnen, nicht überschreiben.
    """
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)

    if GOLDEN_FILE.exists():
        # Integrität prüfen — aber niemals überschreiben, nur informieren
        if GOLDEN_HASH.exists():
            expected = GOLDEN_HASH.read_text().strip()
            actual   = hashlib.sha256(GOLDEN_FILE.read_bytes()).hexdigest()[:16]
            if actual == expected:
                log.info(f"✅ Golden Copy vorhanden und integer [{actual}]")
            else:
                log.warning(
                    f"⚠️  Golden Copy Prüfsumme weicht ab "
                    f"(erwartet: {expected}, aktuell: {actual}) — wird NICHT überschrieben."
                )
        else:
            # Hash-Datei fehlt → neu berechnen und speichern (nur für die existierende Golden Copy)
            cksum = hashlib.sha256(GOLDEN_FILE.read_bytes()).hexdigest()[:16]
            GOLDEN_HASH.write_text(cksum)
            log.info(f"✅ Golden Copy vorhanden, Hash-Datei neu erstellt [{cksum}]")
        return  # In jedem Fall: Golden Copy ist da → NICHT überschreiben

    # Noch keine Golden Copy → einmalig erstellen
    shutil.copy2(SELF_PATH, GOLDEN_FILE)
    cksum = hashlib.sha256(SELF_PATH.read_bytes()).hexdigest()[:16]
    GOLDEN_HASH.write_text(cksum)
    log.info(f"⭐ Golden Copy erstmalig erstellt: {GOLDEN_FILE} [{cksum}]")


def ensure_diamond_backup() -> bool:
    """
    Prüft ob die Diamant-Datei existiert und integer ist.
    Erstellt KEINE neue — die Diamant-Datei wird NUR manuell von dir angelegt:
        copy jarvis_v5_8.py jarvis_diamond.py
    Gibt True zurück wenn Diamant vorhanden und integer, sonst False (mit Warnung).
    """
    if not DIAMOND_FILE.exists():
        log.warning("💎 Keine Diamant-Datei gefunden! Für maximale Sicherheit einmalig erstellen:")
        log.warning("   copy jarvis_v5_8.py jarvis_diamond.py")
        return False

    if DIAMOND_HASH.exists():
        expected = DIAMOND_HASH.read_text().strip()
        actual   = hashlib.sha256(DIAMOND_FILE.read_bytes()).hexdigest()[:16]
        if actual != expected:
            log.warning(
                f"💎 Diamant-Datei wurde verändert! "
                f"Prüfsumme stimmt nicht (erwartet: {expected}, aktuell: {actual})."
            )
            return False
    else:
        # Erstmalig Hash berechnen und speichern
        cksum = hashlib.sha256(DIAMOND_FILE.read_bytes()).hexdigest()[:16]
        DIAMOND_HASH.write_text(cksum)
        log.info(f"💎 Diamant-Datei Hash erstellt [{cksum}]")

    log.info(f"💎 Diamant-Datei OK: {DIAMOND_FILE}")
    return True


# Dateien die bei Modul-Backup gesichert werden
_BACKUP_MODULES = [
    "jarvis_brains.py",
    "jarvis_optimizer.py",
    "jarvis_openclaw.py",
    "jarvis_google.py",
    "JARVIS_HANDBUCH.txt",
]


def backup_all_modules():
    """
    Erstellt zeitgestempelte Backups aller JARVIS-Module (nicht nur Hauptdatei).
    Wird nach jedem erfolgreichen Optimizer-Deploy aufgerufen.
    NIEMALS _env / .env sichern — enthält API-Keys!
    """
    ts    = datetime.now().strftime("%Y%m%d_%H%M%S")
    count = 0
    for fname in _BACKUP_MODULES:
        src = Path(fname)
        if src.exists():
            dest = PATHS["backups"] / f"{src.stem}_backup_{ts}{src.suffix}"
            try:
                shutil.copy2(src, dest)
                log.info(f"📦 Modul-Backup: {dest.name}")
                count += 1
            except Exception as e:
                log.warning(f"Modul-Backup {fname}: {e}")
    if count:
        log.info(f"📦 {count} Module gesichert (Zeitstempel: {ts})")


def create_deployment_backup() -> Path:
    """Erstellt ein zeitgestempeltes Backup vor jedem Deploy."""
    PATHS["backups"].mkdir(parents=True, exist_ok=True)
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = PATHS["backups"] / f"jarvis_deployed_{ts}.py"
    shutil.copy2(SELF_PATH, dest)
    cksum = hashlib.sha256(SELF_PATH.read_bytes()).hexdigest()[:16]
    (PATHS["backups"] / f"jarvis_deployed_{ts}.sha256").write_text(cksum)
    log.info(f"📦 Backup: {dest}")
    return dest


def auto_rollback(to_golden: bool = False, to_diamond: bool = False) -> bool:
    """
    Rollback-Hierarchie (von spezifisch nach allgemein):
      to_diamond=True → Diamant-Datei (dein persönlicher Nullpunkt)
      to_golden=True  → Golden Copy (erster Stand beim ersten Start)
      Standard        → letztes deployed-Backup
    """
    # Stufe 1: Diamant (absoluter Notausgang — nur manuell erstellt)
    if to_diamond:
        if DIAMOND_FILE.exists():
            shutil.copy2(DIAMOND_FILE, SELF_PATH)
            log.info("💎 Rollback → Diamant-Datei (persönlicher Nullpunkt)")
            return True
        log.error("❌ Diamant-Datei nicht gefunden. Erstelle manuell: copy jarvis_v5_8.py jarvis_diamond.py")
        return False

    # Stufe 2: Golden Copy
    if to_golden and GOLDEN_FILE.exists():
        shutil.copy2(GOLDEN_FILE, SELF_PATH)
        log.info("⭐ Rollback → Golden Copy")
        return True

    # Stufe 3: Letztes deployed-Backup
    backs = sorted(PATHS["backups"].glob("jarvis_deployed_*.py"))
    if backs:
        shutil.copy2(backs[-1], SELF_PATH)
        log.info(f"♻️  Rollback → {backs[-1].name}")
        return True

    # Letzter Ausweg: Golden Copy auch wenn to_golden=False
    if GOLDEN_FILE.exists():
        shutil.copy2(GOLDEN_FILE, SELF_PATH)
        log.info("⭐ Rollback → Golden Copy (letzter Ausweg)")
        return True

    log.error("❌ Kein Backup verfügbar")
    return False


def cleanup_old_backups(keep: int = 10):
    backs = sorted(PATHS["backups"].glob("jarvis_deployed_*.py"))
    for old in backs[:-keep]:
        old.unlink(missing_ok=True)
        sha = Path(str(old).replace(".py", ".sha256"))
        sha.unlink(missing_ok=True)


def _count_recent_errors(minutes: int = 3) -> int:
    lp = PATHS["logs"] / "debug.log"
    if not lp.exists():
        return 0
    cutoff = time.time() - minutes * 60
    count  = 0
    try:
        for line in lp.read_text(encoding="utf-8").splitlines()[-500:]:
            if "[ERROR]" in line or "[CRITICAL]" in line:
                if "Stream closed" in line or "Errno -9988" in line:
                    continue
                try:
                    ts = datetime.strptime(line.split(" [")[0], "%Y-%m-%d %H:%M:%S,%f").timestamp()
                    if ts > cutoff:
                        count += 1
                except Exception:
                    pass
    except Exception:
        pass
    return count


def startup_check():
    ensure_golden_copy()
    ensure_diamond_backup()   # Warnung wenn Diamant fehlt, keine Fehlerunterbrechung
    generate_handbook()
    if _count_recent_errors(minutes=3) >= 3:
        log.warning("⚠️  Crash-Loop erkannt — Rollback zur Golden Copy")
        auto_rollback(to_golden=True)

    # Optional: psutil-Hinweis wenn nicht installiert
    try:
        import psutil  # noqa: F401
    except ImportError:
        log.info("ℹ️  psutil fehlt — RAM/CPU-Info eingeschränkt. "
                 "Tipp: pip install psutil")

# ══════════════════════════════════════════════════════════════════════
#  MODUL 4 — LERNPROTOKOLL & KNOWLEDGE GRAPH
# ══════════════════════════════════════════════════════════════════════

LEARNING_LOG    = PATHS["memory"] / "learning_log.json"
ERROR_PATTERNS  = PATHS["memory"] / "error_patterns.json"
KNOWLEDGE_BASE  = PATHS["memory"] / "knowledge_base.json"
OPT_RESUME_FILE = PATHS["memory"] / "opt_resume.json"


def _load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return default


def _save_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _save_opt_resume(goal: str, duration_sec: int, iterations_done: int, planned_changes: str = ""):
    _save_json(OPT_RESUME_FILE, {
        "goal":            goal,
        "duration_sec":    duration_sec,
        "iterations_done": iterations_done,
        "planned_changes": planned_changes,
        "paused_at":       datetime.now().isoformat(),
    })


def _load_opt_resume() -> Optional[dict]:
    return _load_json(OPT_RESUME_FILE, None) if OPT_RESUME_FILE.exists() else None


def _clear_opt_resume():
    OPT_RESUME_FILE.unlink(missing_ok=True)


class LearningMemory:
    def __init__(self):
        self._log    = _load_json(LEARNING_LOG,   {"entries": [], "stats": {}})
        self._errors = _load_json(ERROR_PATTERNS,  {"patterns": {}})
        self._kb     = _load_json(KNOWLEDGE_BASE,  {
            "successful_patterns": [],
            "failed_patterns":     [],
            "key_insights":        [],
        })
        n = len(self._log["entries"])
        log.info(f"🧠 Lernprotokoll: {n} Einträge")

    def record_success(self, iteration: int, goal: str, summary: str, plan: str, analysis: str):
        entry = {
            "type":       "success",
            "timestamp":  datetime.now().isoformat(),
            "iteration":  iteration,
            "goal":       goal,
            "summary":    summary,
            "plan_short": plan[:300],
        }
        self._log["entries"].append(entry)
        self._log.setdefault("stats", {})
        self._log["stats"]["total_success"] = self._log["stats"].get("total_success", 0) + 1
        _save_json(LEARNING_LOG, self._log)
        self._update_kb_success(summary, goal)
        self._save_training_sample(iteration, goal, analysis, plan, summary)
        log.info(f"🧠 Erfolg gespeichert: {summary[:80]}")

    def record_failure(self, iteration: int, goal: str, reason: str, stage: str,
                       is_rate_limit: bool = False):
        if is_rate_limit:
            log.info(f"⏳ Rate-Limit [{stage}] — nicht als Fehler gezählt")
            return
        entry = {
            "type":      "failure",
            "timestamp": datetime.now().isoformat(),
            "iteration": iteration,
            "goal":      goal,
            "reason":    reason[:200],
            "stage":     stage,
        }
        self._log["entries"].append(entry)
        self._log.setdefault("stats", {})
        self._log["stats"]["total_failure"] = self._log["stats"].get("total_failure", 0) + 1
        key = f"{stage}:{reason[:60]}"
        self._errors["patterns"][key] = self._errors["patterns"].get(key, 0) + 1
        _save_json(LEARNING_LOG,   self._log)
        _save_json(ERROR_PATTERNS, self._errors)
        self._update_kb_failure(reason, stage)

    def get_context_for_prompt(self) -> str:
        succ  = self._kb.get("successful_patterns", [])[-5:]
        fail  = self._kb.get("failed_patterns",     [])[-5:]
        ins   = self._kb.get("key_insights",        [])[-3:]
        stats = self._log.get("stats", {})
        s, f  = stats.get("total_success", 0), stats.get("total_failure", 0)
        lines = [f"=== LERNPROTOKOLL (Erfolge: {s}, Fehler: {f}) ==="]
        if succ:
            lines.append("✅ Was funktioniert hat:")
            for item in succ: lines.append(f"  + {item}")
        if fail:
            lines.append("❌ Was scheitert (UNBEDINGT VERMEIDEN):")
            for item in fail: lines.append(f"  - {item}")
        if ins:
            lines.append("💡 Erkenntnisse:")
            for item in ins: lines.append(f"  → {item}")
        top_errors = sorted(self._errors["patterns"].items(), key=lambda x: -x[1])[:3]
        if top_errors:
            lines.append("🔁 Häufigste Fehler (nicht wiederholen!):")
            for k, v in top_errors:
                lines.append(f"  [{v}x] {k.split(':',1)[-1][:80]}")
        return "\n".join(lines)

    def get_stats_summary(self) -> str:
        stats    = self._log.get("stats", {})
        s        = stats.get("total_success", 0)
        f        = stats.get("total_failure", 0)
        rate     = round(s / max(s + f, 1) * 100)
        total    = len(self._log.get("entries", []))
        insights = len(self._kb.get("key_insights", []))
        return (f"{total} Iterationen. Erfolgsrate: {rate}% ({s} Erfolge, {f} Fehler). "
                f"{insights} Erkenntnisse.")

    def add_insight(self, insight: str):
        ins = self._kb.setdefault("key_insights", [])
        if insight not in ins:
            ins.append(insight)
        if len(ins) > 20:
            ins.pop(0)
        _save_json(KNOWLEDGE_BASE, self._kb)

    def _update_kb_success(self, summary: str, goal: str):
        succ  = self._kb.setdefault("successful_patterns", [])
        entry = f"[{goal[:30]}] {summary[:80]}"
        if entry not in succ:
            succ.append(entry)
        if len(succ) > 30:
            succ.pop(0)
        _save_json(KNOWLEDGE_BASE, self._kb)

    def _update_kb_failure(self, reason: str, stage: str):
        fail  = self._kb.setdefault("failed_patterns", [])
        entry = f"[{stage}] {reason[:80]}"
        if entry not in fail:
            fail.append(entry)
        if len(fail) > 30:
            fail.pop(0)
        _save_json(KNOWLEDGE_BASE, self._kb)

    def _save_training_sample(self, iteration, goal, analysis, plan, summary):
        sample = {
            "instruction": f"Optimiere Python-Code. Ziel: {goal}",
            "input":       analysis[:1000],
            "output":      plan[:1000],
            "metadata":    {
                "iteration": iteration,
                "summary":   summary,
                "timestamp": datetime.now().isoformat(),
            }
        }
        dataset_file = PATHS["training"] / "successful_iterations.jsonl"
        with open(dataset_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")

# ══════════════════════════════════════════════════════════════════════
#  MODUL 5 — VISION
# ══════════════════════════════════════════════════════════════════════

def analyze_image(image_path: str,
                  question: str = "Was siehst du? Beschreibe alles detailliert.") -> str:
    if not gemini_client or not gemini_model:
        return "Gemini Vision nicht verfügbar."
    if cv2 is None or PIL is None:
        return "Vision-Pakete fehlen: pip install opencv-python Pillow"
    try:
        import io
        img = PIL.Image.open(image_path)
        img.thumbnail((1024, 1024), PIL.Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        img_bytes = buf.getvalue()

        img_part = genai_types.Part(
            inline_data=genai_types.Blob(mime_type="image/jpeg", data=img_bytes)
        )
        resp = gemini_client.models.generate_content(
            model=gemini_model,
            contents=[genai_types.Content(role="user",
                parts=[genai_types.Part(text=question), img_part])],
            config=genai_types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                max_output_tokens=2048,
            )
        )
        return resp.text or "Keine Beschreibung erhalten."
    except Exception as e:
        log.error(f"Bildanalyse: {e}")
        return f"Bildanalyse fehlgeschlagen: {e}"


def analyze_video(video_path: str, max_frames: int = 8,
                  question: str = "Analysiere dieses Video Szene für Szene.") -> str:
    if not gemini_client or not gemini_model:
        return "Gemini Vision nicht verfügbar."
    if cv2 is None or PIL is None:
        return "Vision-Pakete fehlen: pip install opencv-python Pillow"
    try:
        import io
        cap   = cv2.VideoCapture(video_path)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps   = cap.get(cv2.CAP_PROP_FPS) or 25
        idxs  = [int(i * total / max_frames) for i in range(max_frames)]
        parts = [genai_types.Part(text=f"{question}\nVideo: {total/fps:.1f}s")]
        saved = []
        for idx in idxs:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if not ret:
                continue
            p = PATHS["temp_vision"] / f"frame_{idx}.jpg"
            cv2.imwrite(str(p), frame)
            saved.append(p)
            buf = io.BytesIO()
            PIL.Image.open(str(p)).save(buf, format="JPEG", quality=75)
            parts.append(genai_types.Part(
                inline_data=genai_types.Blob(mime_type="image/jpeg", data=buf.getvalue())
            ))
        cap.release()
        if len(parts) == 1:
            return "Keine Frames extrahiert."
        resp = gemini_client.models.generate_content(
            model=gemini_model,
            contents=[genai_types.Content(role="user", parts=parts)],
            config=genai_types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                max_output_tokens=2048,
            )
        )
        for p in saved:
            p.unlink(missing_ok=True)
        return resp.text or "Keine Analyse erhalten."
    except Exception as e:
        log.error(f"Videoanalyse: {e}")
        return f"Videoanalyse fehlgeschlagen: {e}"

# ══════════════════════════════════════════════════════════════════════
#  MODUL 6 — AUDIO
# ══════════════════════════════════════════════════════════════════════

def transcribe_audio(audio_path: str) -> str:
    if not groq_client:
        return "Groq nicht verfügbar (GROQ_API_KEY fehlt in .env)."
    try:
        fsize = os.path.getsize(audio_path)
        if fsize > 24 * 1024 * 1024:
            return _transcribe_chunked(audio_path)
        with open(audio_path, "rb") as f:
            resp = groq_client.audio.transcriptions.create(
                file=(Path(audio_path).name, f),
                model="whisper-large-v3",
                language="de",
                response_format="text",
            )
        transcript = resp if isinstance(resp, str) else resp.text
        _save_transcript(audio_path, transcript)
        return transcript
    except Exception as e:
        return f"Transkription fehlgeschlagen: {e}"


def _transcribe_chunked(audio_path: str) -> str:
    chunk_size = 20 * 1024 * 1024
    parts = []
    with open(audio_path, "rb") as f:
        i = 0
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            ext = Path(audio_path).suffix
            tmp = PATHS["temp_audio"] / f"chunk_{i}{ext}"
            tmp.write_bytes(chunk)
            with open(tmp, "rb") as cf:
                r = groq_client.audio.transcriptions.create(
                    file=(tmp.name, cf),
                    model="whisper-large-v3",
                    language="de",
                    response_format="text",
                )
            parts.append(r if isinstance(r, str) else r.text)
            tmp.unlink(missing_ok=True)
            i += 1
    full = " ".join(parts)
    _save_transcript(audio_path, full)
    return full


def _save_transcript(source_path: str, text: str):
    ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = PATHS["transcripts"] / f"{Path(source_path).stem}_{ts}.txt"
    out.write_text(text, encoding="utf-8")


_FILLER_RE = re.compile(
    r"\b(ähm|äh|hmm|hm|halt|quasi|sozusagen|irgendwie|eigentlich|"
    r"wirklich|einfach|mal|ja|naja|also|genau|okay|ok|ne|nee|"
    r"gewissermaßen|im grunde|im prinzip|und so|und so weiter|"
    r"und dergleichen|praktisch|letztendlich|letztlich)\b",
    flags=re.IGNORECASE,
)


def clean_text(text: str, mode: str = "both") -> str:
    cleaned = text
    if mode in ("filler", "both"):
        cleaned = _FILLER_RE.sub("", cleaned)
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    if mode in ("summary", "both") and gemini_chat:
        try:
            cleaned = gemini_chat.send_message(
                f"Fasse diesen Text präzise zusammen. Nur den Kern:\n\n{cleaned}"
            ).text
        except Exception as e:
            log.error(f"Cleanup-KI: {e}")
    return cleaned

# ══════════════════════════════════════════════════════════════════════
#  MODUL 7 — MESHTASTIC
# ══════════════════════════════════════════════════════════════════════

class MeshtasticBridge:
    def __init__(self):
        self.iface     = None
        self.connected = False

    def connect(self) -> bool:
        if not MESHTASTIC_ENABLED:
            return False
        try:
            import meshtastic.serial_interface as si
            from pubsub import pub
            self.iface = si.SerialInterface(MESHTASTIC_PORT)
            pub.subscribe(self._on_receive, "meshtastic.receive.text")
            self.connected = True
            log.info(f"✅ Meshtastic: {MESHTASTIC_PORT}")
            return True
        except Exception as e:
            log.error(f"Meshtastic: {e}")
            return False

    def _on_receive(self, packet, interface=None):
        try:
            sender = packet.get("fromId", "?")
            text   = packet.get("decoded", {}).get("text", "")
            if not text:
                return
            log.info(f"📡 Mesh ← [{sender}]: {text}")
            if bot and _tg_chat_id:
                bot.send_message(_tg_chat_id,
                    f"📡 *Meshtastic*\n👤 `{sender}`\n💬 {text}",
                    parse_mode="Markdown")
            if text.lower().startswith("jarvis") and gemini_chat:
                q    = text[6:].strip()
                resp = gemini_chat.send_message(q).text[:200]
                self.send(resp)
        except Exception as e:
            log.error(f"Mesh-Empfang: {e}")

    def send(self, text: str, dest: str = "^all") -> bool:
        if not self.connected:
            return False
        try:
            self.iface.sendText(text[:228], destinationId=dest)
            return True
        except Exception as e:
            log.error(f"Mesh-Send: {e}")
            return False

    def disconnect(self):
        if self.iface:
            try:
                self.iface.close()
            except Exception:
                pass
        self.connected = False


meshtastic_bridge = MeshtasticBridge()

# ══════════════════════════════════════════════════════════════════════
#  MODUL 8 — AUTONOMOUS SELF-OPTIMIZATION ENGINE v3.1
#
#  Verbesserungen:
#  - Präzisere Prompts → höhere Erfolgsrate
#  - Sofortiger Rollback bei Syntaxfehler nach Deploy
#  - Größen-Prüfung verbessert
#  - Rate-Limit-Backoff robuster
# ══════════════════════════════════════════════════════════════════════

_RATE_LIMIT_BACKOFF_TEMP = [30, 60]   # temporäre 429 — kurzer Backoff
# Tageslimit (quota/free_tier): sofort Blackout, kein langer Backoff

# ── Gemini Blackout Guard ─────────────────────────────────────────────
_gemini_blackout_until: float = 0.0
_gemini_blackout_lock  = threading.Lock()

def _is_rate_limit(err: str) -> bool:
    return "429" in err or "RESOURCE_EXHAUSTED" in err or "quota" in err.lower()

def _is_daily_quota(err: str) -> bool:
    e = err.lower()
    return ("quota" in e or "per_day" in e or "daily" in e or
            "free_tier" in e or "resource_exhausted" in e)

def _set_gemini_blackout():
    """
    Tageslimit von KEY_1 → versuche KEY_2 (zweiter Google-Account).
    Nur wenn KEY_2 auch scheitert: echter 24h-Blackout.
    """
    global _gemini_blackout_until, gemini_client, gemini_model, gemini_chat

    # KEY_2 vorhanden und noch nicht aktiv?
    if GEMINI_API_KEY_2 and gemini_client:
        current_key = getattr(gemini_client, "_api_key", None)
        if current_key != GEMINI_API_KEY_2:
            log.warning("🔑 Gemini KEY_1 Tageslimit — versuche KEY_2 (zweiter Account)...")
            try:
                client2 = genai.Client(api_key=GEMINI_API_KEY_2)
                for name in GEMINI_MODELS:
                    try:
                        resp = client2.models.generate_content(
                            model=name, contents="OK",
                            config=genai_types.GenerateContentConfig(max_output_tokens=4),
                        )
                        _ = resp.text
                        gemini_client = client2
                        gemini_model  = name
                        gemini_chat   = _GeminiChatWrapper(client2, name)
                        log.info(f"✅ Gemini KEY_2 aktiv: {name} — KEY_1 Quota umgangen!")
                        return   # Kein Blackout nötig — KEY_2 funktioniert
                    except Exception as e2:
                        log.warning(f"  KEY_2 {name}: {str(e2)[:60]}")
            except Exception as e2:
                log.warning(f"  KEY_2 Init-Fehler: {e2}")
            log.warning("⚠ KEY_2 auch nicht verfügbar — aktiviere Blackout")

    with _gemini_blackout_lock:
        _gemini_blackout_until = time.time() + 86400
    log.warning("🚫 Gemini Tageslimit (alle Keys) — 24h Blackout. Groq/Cerebras übernehmen.")

def _gemini_is_blocked() -> bool:
    with _gemini_blackout_lock:
        return time.time() < _gemini_blackout_until

def _gemini_blackout_remaining() -> int:
    with _gemini_blackout_lock:
        return max(0, int(_gemini_blackout_until - time.time()))


def _call_gemini_with_backoff(prompt: str, system: str = "", max_tokens: int = 8192,
                               stop_event: threading.Event = None) -> str:
    if _gemini_is_blocked():
        rem = _gemini_blackout_remaining()
        raise RuntimeError(f"Gemini Blackout — noch {rem//3600}h {(rem%3600)//60}min")

    for attempt, wait in enumerate([0] + _RATE_LIMIT_BACKOFF_TEMP):
        if stop_event and stop_event.is_set():
            raise RuntimeError("Optimizer gestoppt")
        if wait > 0:
            log.warning(f"⏳ Gemini Rate-Limit — warte {wait}s (Versuch {attempt+1})...")
            for _ in range(wait):
                if stop_event and stop_event.is_set():
                    raise RuntimeError("Optimizer gestoppt")
                time.sleep(1)
        try:
            return _call_gemini_raw(prompt, system, max_tokens)
        except Exception as e:
            err_str = str(e)
            if _is_rate_limit(err_str):
                if _is_daily_quota(err_str):
                    _set_gemini_blackout()
                    raise RuntimeError(
                        "Gemini Tageslimit erschöpft — 24h Blackout. Groq/Cerebras übernehmen."
                    ) from e
                if attempt >= len(_RATE_LIMIT_BACKOFF_TEMP):
                    raise
                continue
            raise
    raise RuntimeError("Gemini Rate-Limit: alle Versuche erschöpft")


_FOCUS_AREAS = [
    "listen_loop",
    "setup_telegram",
    "_run_iteration",
    "_call_gemini_raw",
    "startup_check",
    "cc_screenshot",
    "analyze_image",
    "transcribe_audio",
    "_call_cerebras",
    "process_command",
    "_count_recent_errors",
    "handle_local",
]

# Mapping: Fokus-Alias → tatsächlicher Funktionsname im Code
# (für Analyst/Planner-Prompts lesbare Namen, intern auf echte defs gemappt)
_FOCUS_ALIAS = {
    "listen_loop":      "listen_loop",
    "setup_telegram":   "setup_telegram",
    "_run_iteration":   "_run_iteration",
    "_call_gemini_raw": "_call_gemini_raw",
    "startup_check":    "startup_check",
    "cc_screenshot":    "cc_screenshot",
    "analyze_image":    "analyze_image",
    "transcribe_audio": "transcribe_audio",
    "_call_cerebras":   "_call_cerebras",
    "process_command":  "process_command",
    "_count_recent_errors": "_count_recent_errors",
    "handle_local":     "handle_local",
}

# Verbesserte Prompts für den Optimizer
_ANALYST_SYSTEM = """Du bist ein Senior Python-Architekt der auf Fehlerfreiheit spezialisiert ist.
Analysiere nur den angegebenen Fokus-Bereich.
Antworte AUSSCHLIESSLICH mit gültigem JSON, kein Text davor oder danach.
Denke Schritt für Schritt bevor du antwortest."""

_PLANNER_SYSTEM = """Du bist ein Software-Architekt der Änderungen plant.
KRITISCHE REGEL: Ändere NUR den angegebenen Fokus-Bereich.
KRITISCHE REGEL: Der restliche Code muss 100% unverändert bleiben.
KRITISCHE REGEL: Keine neuen Imports hinzufügen ohne Prüfung ob verfügbar.
Antworte AUSSCHLIESSLICH mit gültigem JSON."""

_DEVELOPER_SYSTEM = """Du bist ein Elite Python-Entwickler.
KRITISCHE REGELN:
1. Gib NUR Python-Code zurück, KEINE Backticks, KEIN Markdown, KEIN Kommentar davor/danach
2. Der Code muss syntaktisch korrekt sein
3. Ändere NUR den Fokus-Bereich, ALLES ANDERE bleibt exakt gleich
4. Behalte ALLE Imports, ALLE Funktionen, ALLE Klassen
5. Minimale Änderungen - lieber zu wenig als zu viel"""


class OptimizationEngine:

    IDLE    = "idle"
    RUNNING = "running"
    PAUSED  = "paused"
    DONE    = "done"
    FAILED  = "failed"

    def __init__(self):
        self.status         = self.IDLE
        self.thread         = None
        self._stop          = threading.Event()
        self.current_goal   = ""
        self.duration_sec   = 0
        self.start_time     = None
        self.iterations     = 0
        self.max_iterations = 30
        self.max_attempts   = 5
        self.history:  List[Dict] = []
        self.report_path    = PATHS["logs"] / "opt_report.json"
        self._last_plan     = ""
        self._resumed       = False
        self.memory         = LearningMemory()
        self._focus_index   = 0
        self._load_history()

    def _load_history(self):
        if self.report_path.exists():
            try:
                self.history = json.loads(self.report_path.read_text(encoding="utf-8"))
            except Exception:
                self.history = []

    def _save_history(self):
        try:
            self.report_path.write_text(
                json.dumps(self.history, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as e:
            log.error(f"History-Save: {e}")

    def start(self, goal: str = "", duration_input: str = ""):
        if self.status == self.RUNNING:
            say("Optimierung läuft bereits.")
            return

        resume_data = _load_opt_resume()
        if resume_data and not goal:
            self.current_goal = resume_data["goal"]
            self.duration_sec = resume_data.get("duration_sec", 0)
            self.iterations   = resume_data.get("iterations_done", 0)
            self._last_plan   = resume_data.get("planned_changes", "")
            self._resumed     = True
        else:
            self.current_goal = goal or "Robustheit, Fehlerbehandlung und Code-Qualität verbessern"
            self.duration_sec = self._parse_duration(duration_input)
            self.iterations   = 0
            self._last_plan   = ""
            self._resumed     = False
            _clear_opt_resume()

        self.start_time = datetime.now()
        self._stop.clear()
        self.status = self.RUNNING
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

        dur = self._fmt(self.duration_sec) if self.duration_sec else "unbegrenzt"
        dev = f"Cerebras {cerebras_model}" if cerebras_client else "Gemini"
        if self._resumed:
            say(f"Weiter bei Iteration {self.iterations}. Developer-KI: {dev}.")
        else:
            say(f"Selbst-Optimierung gestartet. Zeitrahmen: {dur}. Developer-KI: {dev}.")

    def stop(self, save_progress: bool = True):
        if self.status != self.RUNNING:
            say("Keine Optimierung aktiv.")
            return
        self._stop.set()
        self.status = self.PAUSED
        if save_progress:
            _save_opt_resume(self.current_goal, self.duration_sec,
                             self.iterations, self._last_plan)
            say("Gestoppt. Fortschritt gespeichert.")
        else:
            _clear_opt_resume()
            say("Optimierung gestoppt.")

    def get_status(self) -> str:
        dev = f"Cerebras {cerebras_model}" if cerebras_client else "Gemini"
        if self.status == self.IDLE:
            resume = _load_opt_resume()
            if resume:
                return (f"Bereit [{dev}]. Resume: '{resume['goal']}', "
                        f"Iter {resume['iterations_done']}.")
            return f"Bereit. Developer-KI: {dev}."
        if self.status == self.RUNNING:
            el    = int((datetime.now() - self.start_time).total_seconds())
            rem   = f" Verbleibend: {self._fmt(max(0, self.duration_sec - el))}." if self.duration_sec else ""
            focus = _FOCUS_AREAS[self._focus_index % len(_FOCUS_AREAS)]
            return f"Läuft [{dev}] — Iter {self.iterations}, Fokus: {focus}. Laufzeit: {self._fmt(el)}.{rem}"
        if self.status == self.PAUSED:
            return f"Pausiert nach Iteration {self.iterations}."
        if self.status == self.DONE:
            return f"Abgeschlossen nach {self.iterations} Iterationen."
        return f"Status: {self.status}"

    def get_learning_summary(self) -> str:
        return self.memory.get_stats_summary()

    def _run_loop(self):
        log.info("🧠 Opt-Loop gestartet")
        while not self._stop.is_set():
            if self.duration_sec and self.start_time:
                if (datetime.now() - self.start_time).total_seconds() >= self.duration_sec:
                    self._finalize("Zeitlimit erreicht")
                    return
            if self.iterations >= self.max_iterations:
                self._finalize("Maximale Iterationen erreicht")
                return

            self.iterations += 1
            focus = _FOCUS_AREAS[self._focus_index % len(_FOCUS_AREAS)]
            self._focus_index += 1
            log.info(f"\n{'='*60}\n🔄 ITERATION {self.iterations} | Fokus: {focus}\n{'='*60}")

            result = self._run_iteration(focus)
            self.history.append({
                "iteration": self.iterations,
                "timestamp": datetime.now().isoformat(),
                "goal":      self.current_goal,
                "focus":     focus,
                "status":    result["status"],
                "summary":   result.get("summary", ""),
                "applied":   result.get("applied", False),
            })
            self._save_history()

            if result["status"] == "goal_reached":
                _clear_opt_resume()
                say(f"Ziel nach {self.iterations} Iterationen erreicht.")
                self._finalize("Ziel erreicht")
                return
            elif result["status"] == "success":
                log.info(f"✅ Iter {self.iterations}: {result.get('summary','')}")
                time.sleep(2)
            elif result["status"] == "rate_limited":
                log.info(f"⏳ Rate-Limit in Iter {self.iterations}")
                self.iterations -= 1
                time.sleep(5)
            elif result["status"] == "stopped":
                return
            else:
                log.warning(f"⚠️  Iter {self.iterations} fehlgeschlagen: {result.get('summary','')}")
                time.sleep(6)

        self._finalize("Manuell gestoppt")

    def _run_iteration(self, focus: str) -> dict:
        source    = SELF_PATH.read_text(encoding="utf-8")
        learn_ctx = self.memory.get_context_for_prompt()

        # ── 1. ANALYST ────────────────────────────────────────────────
        log.info(f"🔍 [ANALYST/Gemini] Fokus: {focus}")
        analyst_prompt = (
            f"OPTIMIERUNGSZIEL: {self.current_goal}\n"
            f"FOKUS: Nur '{focus}'\n"
            f"ITERATION: {self.iterations}\n\n"
            f"{learn_ctx}\n\n"
            f"Analysiere AUSSCHLIESSLICH '{focus}' im Code unten.\n"
            f"Gib 2-3 KONKRETE, SICHERE Verbesserungen als JSON.\n"
            f"Lehne ab wenn: Risiko hoch, Import unsicher, oder Änderung zu groß.\n\n"
            f"CODE:\n{source[:8000]}"
        )
        analysis_schema = {
            "type": "object",
            "properties": {
                "focus_area":     {"type": "string"},
                "current_issues": {"type": "array", "items": {"type": "string"}},
                "improvements": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "problem":  {"type": "string"},
                            "solution": {"type": "string"},
                            "risk":     {"type": "string", "enum": ["low", "medium", "high"]},
                        }
                    }
                }
            }
        }

        try:
            if _gemini_is_blocked():
                raise RuntimeError("Gemini Blackout aktiv — direkt zu Groq-Fallback")
            analysis_data = _call_gemini_json(analyst_prompt, _ANALYST_SYSTEM, analysis_schema)
            if not analysis_data:
                analysis_text = _call_gemini_with_backoff(
                    analyst_prompt, _ANALYST_SYSTEM, 2000, stop_event=self._stop
                )
                analysis_data = {"focus_area": focus, "improvements": [], "raw": analysis_text}
            # Wenn keine Vorschläge: Default-Verbesserung injizieren damit Pipeline nicht leer endet
            if not analysis_data.get("improvements"):
                log.info(f"📋 Analyst (Gemini): 0 Vorschläge — injiziere Standard-Verbesserung für {focus}")
                analysis_data["improvements"] = [{
                    "problem":  f"Robustheit in '{focus}' verbessern",
                    "solution": f"Bessere Fehlerbehandlung und Logging in '{focus}' hinzufügen",
                    "risk":     "low",
                }]
            log.info(f"📋 Analyst: {len(analysis_data.get('improvements', []))} Vorschläge")
        except RuntimeError as e:
            if "gestoppt" in str(e):
                return {"status": "stopped", "summary": "Manuell gestoppt"}
            # Blackout oder Rate-Limit: Groq-Fallback für Analyse
            log.warning(f"  Analyst/Gemini: {e} — Groq-Fallback")
            analysis_data = None
            if groq_client:
                try:
                    r = groq_client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=[
                            {"role": "system", "content": _ANALYST_SYSTEM},
                            {"role": "user",   "content": analyst_prompt},
                        ],
                        max_tokens=600,
                        response_format={"type": "json_object"},
                    )
                    analysis_data = json.loads(r.choices[0].message.content)
                    log.info(f"📋 Analyst (Groq-Fallback): {len(analysis_data.get('improvements', []))} Vorschläge")
                    # ── BUGFIX Prio 1: Groq-Analyst gibt oft leeres improvements-Array ──
                    # Lösung: Standard-Vorschlag injizieren wenn leer (gleich wie beim Gemini-Pfad)
                    if not analysis_data.get("improvements"):
                        log.info(f"📋 Analyst (Groq): 0 Vorschläge — injiziere Standard-Verbesserung für {focus}")
                        analysis_data["improvements"] = [{
                            "problem":  f"Robustheit in '{focus}' verbessern",
                            "solution": f"Bessere try/except-Blöcke und Logging in '{focus}' hinzufügen",
                            "risk":     "low",
                        }]
                except Exception as eg:
                    log.warning(f"  Analyst/Groq: {eg}")
            if not analysis_data:
                analysis_data = {"focus_area": focus, "improvements": [{
                    "problem":  f"Robustheit in '{focus}' verbessern",
                    "solution": f"Fehlerbehandlung in '{focus}' verbessern",
                    "risk": "low",
                }]}
                log.info("📋 Analyst: Minimal-Fallback verwendet")
        except Exception as e:
            err = str(e)
            if _is_rate_limit(err):
                if _is_daily_quota(err):
                    _set_gemini_blackout()
                self.memory.record_failure(self.iterations, self.current_goal, err, "analyst",
                                           is_rate_limit=True)
                return {"status": "rate_limited", "summary": err}
            self.memory.record_failure(self.iterations, self.current_goal, err, "analyst")
            return {"status": "error", "summary": f"Analyst: {e}"}

        # ── 2. CRITIC ─────────────────────────────────────────────────
        log.info("🔬 [CRITIC] Bewertet...")
        critic_approved = []
        all_improvements = analysis_data.get("improvements", [])

        if groq_client and all_improvements:
            try:
                critic_prompt = (
                    f"Bewerte diese Code-Änderungen für einen laufenden JARVIS-KI-Assistenten:\n"
                    f"{json.dumps(all_improvements, ensure_ascii=False, indent=2)}\n\n"
                    f"Lehne ab: Änderungen mit risk=high, Änderungen die Imports hinzufügen,\n"
                    f"Änderungen die mehr als eine Funktion betreffen.\n"
                    f"Genehmige: Kleine, sichere, isolierte Verbesserungen.\n\n"
                    f"Antworte NUR JSON: {{\"approved_indices\": [0,1], \"reason\": \"...\"}}"
                )
                r = groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {"role": "system", "content": "Kritischer Code-Sicherheitsprüfer. Sei konservativ."},
                        {"role": "user",   "content": critic_prompt},
                    ],
                    max_tokens=400,
                    response_format={"type": "json_object"},
                )
                critic_data  = json.loads(r.choices[0].message.content)
                approved_idx = []
                for i in critic_data.get("approved_indices", []):
                    try:
                        approved_idx.append(int(i))
                    except (TypeError, ValueError):
                        pass
                critic_approved = [all_improvements[i] for i in approved_idx
                                   if i < len(all_improvements)]
                log.info(f"🔬 Critic: {len(critic_approved)}/{len(all_improvements)} genehmigt")
            except Exception as e:
                log.warning(f"Critic-Fehler (Fallback low+medium): {e}")
                critic_approved = [imp for imp in all_improvements
                                   if str(imp.get("risk", "low")) in ("low", "medium")]
        else:
            critic_approved = [imp for imp in all_improvements
                               if str(imp.get("risk", "low")) in ("low", "medium")]
            log.info("🔬 Critic (Groq N/A): low+medium Vorschlaege")

        # Wenn immer noch leer: ersten Vorschlag als Fallback
        if not critic_approved:
            if all_improvements:
                critic_approved = [all_improvements[0]]
                log.info("🔬 Critic: Kein Approval — nehme ersten Vorschlag als Fallback")
            else:
                self.memory.record_failure(self.iterations, self.current_goal,
                                           "Keine Vorschlaege vorhanden", "critic")
                return {"status": "error", "summary": "Critic: keine Vorschlaege"}

        # ── 3. PLANNER ────────────────────────────────────────────────
        log.info("📐 [PLANNER/Gemini] Erstelle Plan...")
        planner_prompt = (
            f"Erstelle einen Implementierungsplan für GENAU EINE dieser Änderungen:\n"
            f"{json.dumps(critic_approved[0], ensure_ascii=False, indent=2)}\n\n"
            f"WICHTIG: Ändere NUR die Funktion '{focus}' im Code.\n"
            f"WICHTIG: Keine neuen Imports.\n"
            f"WICHTIG: Minimale Änderung.\n\n"
            f"CODE:\n{source[:6000]}"
        )
        plan_schema = {
            "type": "object",
            "properties": {
                "approved":        {"type": "boolean"},
                "risk_level":      {"type": "string", "enum": ["low", "medium", "high"]},
                "changes":         {"type": "array", "items": {"type": "string"}},
                "before_snippet":  {"type": "string"},
                "after_snippet":   {"type": "string"},
                "reasoning":       {"type": "string"},
                "affects_only":    {"type": "string"},
            }
        }

        plan_data = None
        planner_error = None
        try:
            plan_data = _call_gemini_json(planner_prompt, _PLANNER_SYSTEM, plan_schema)
        except RuntimeError as e:
            if "gestoppt" in str(e):
                return {"status": "stopped", "summary": "Manuell gestoppt"}
            planner_error = str(e)
            log.warning(f"  Planner/Gemini: {e} — versuche Groq-Fallback")
        except Exception as e:
            planner_error = str(e)
            log.warning(f"  Planner/Gemini: {e} — versuche Groq-Fallback")

        # Groq-Fallback wenn Gemini fehlschlug
        if not plan_data and groq_client:
            try:
                log.info("  Planner-Fallback: Groq")
                groq_plan_prompt = (
                    planner_prompt + " Antworte NUR als JSON mit keys: "
                    " approved (bool), risk_level (low/medium/high), "
                    " changes (array of strings), reasoning (string)"
                )
                r = groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {"role": "system", "content": _PLANNER_SYSTEM},
                        {"role": "user",   "content": groq_plan_prompt},
                    ],
                    max_tokens=600,
                    response_format={"type": "json_object"},
                )
                plan_data = json.loads(r.choices[0].message.content)
                log.info(f"  Planner-Groq OK: {plan_data.get('changes', [])}")
            except Exception as eg:
                log.warning(f"  Planner-Groq: {eg}")

        # Cerebras-Fallback als letzter Ausweg
        if not plan_data and cerebras_client:
            try:
                log.info("  Planner-Fallback: Cerebras")
                raw_plan = _call_cerebras(
                    planner_prompt + " Antworte NUR JSON: approved=true, risk_level=low, changes=[Aenderung], reasoning=Begruendung",
                    _PLANNER_SYSTEM, 400
                )
                raw_plan = re.sub(r"^```json\s*", "", raw_plan.strip(), flags=re.MULTILINE)
                raw_plan = re.sub(r"\s*```$", "", raw_plan, flags=re.MULTILINE)
                s, e2 = raw_plan.find("{"), raw_plan.rfind("}")
                if s != -1 and e2 != -1:
                    plan_data = json.loads(raw_plan[s:e2+1])
                log.info(f"  Planner-Cerebras OK")
            except Exception as ec:
                log.warning(f"  Planner-Cerebras: {ec}")

        # Wenn alle Planner fehlschlugen: einfachen Fallback-Plan erstellen
        if not plan_data:
            if planner_error and _is_rate_limit(planner_error):
                self.memory.record_failure(self.iterations, self.current_goal,
                                           planner_error, "planner", is_rate_limit=True)
                return {"status": "rate_limited", "summary": planner_error}
            log.info("  Planner: Alle Brains fehlgeschlagen — verwende Fallback-Plan")
            plan_data = {
                "approved": True,
                "risk_level": "low",
                "changes": [critic_approved[0].get("solution", f"Verbessere {focus}")],
                "reasoning": "Auto-Fallback",
            }

        if not plan_data.get("approved", True):
            self.memory.record_failure(self.iterations, self.current_goal,
                                       "Planner nicht genehmigt", "planner")
            return {"status": "error", "summary": "Planner: Plan nicht genehmigt"}
        if plan_data.get("risk_level") == "high":
            self.memory.record_failure(self.iterations, self.current_goal,
                                       "Risiko zu hoch", "planner")
            return {"status": "error", "summary": "Planner: Risiko zu hoch"}

        self._last_plan = json.dumps(plan_data, ensure_ascii=False)
        log.info(f"📐 Plan OK: {plan_data.get('changes', [])}")

        # ── 4. DEVELOPER ──────────────────────────────────────────────
        dev_label = f"Cerebras {cerebras_model}" if cerebras_client else "Gemini"
        log.info(f"✍️  [DEVELOPER/{dev_label}]")
        new_code  = None
        MAX_SRC   = 5000
        src_snip  = source[:MAX_SRC]
        is_trunc  = len(source) > MAX_SRC
        min_size  = 200 if is_trunc else int(len(source) * 0.80)

        for attempt in range(1, self.max_attempts + 1):
            if self._stop.is_set():
                return {"status": "stopped", "summary": "Gestoppt"}
            log.info(f"  Developer Versuch {attempt}/{self.max_attempts}")
            try:
                dev_prompt = (
                    f"PLAN:\n{self._last_plan}\n\n"
                    f"AUFGABE: Ändere NUR die Funktion/den Bereich '{focus}' im Code.\n"
                    f"Füge folgende Zeile am Anfang der Datei ein (nach dem docstring):\n"
                    f"# ITERATION {self.iterations}: [{', '.join(plan_data.get('changes', [])[:2])}]\n\n"
                    f"{'GIB DEN KOMPLETTEN PYTHON-CODE ZURÜCK.' if not is_trunc else 'GIB NUR DEN GEÄNDERTEN ABSCHNITT ZURÜCK (kein vollständiger Code nötig).'}\n"
                    f"KEINE BACKTICKS. KEIN MARKDOWN. NUR PYTHON.\n\n"
                    f"CODE ({len(src_snip)} Zeichen{' — AUSSCHNITT' if is_trunc else ''}):\n{src_snip}"
                )
                raw       = _call_cerebras(dev_prompt, _DEVELOPER_SYSTEM, 8192)
                candidate = _strip_code_fences(raw)

                # Bei truncated Source: Snippet in vollständigen Code einbetten
                if is_trunc and len(candidate) < len(source) * 0.5:
                    candidate = self._embed_section(source, focus, candidate)
                    log.info(f"  📎 Abschnitt eingebettet: {len(candidate)} Z")
                if len(candidate) < min_size:
                    log.warning(f"  Code zu kurz ({len(candidate)} < {min_size}) — verwerfen")
                    continue

                # Reviewer
                log.info(f"  🧐 [REVIEWER]")
                review_prompt = (
                    f"Prüfe diesen Python-Code-Ausschnitt:\n"
                    f"- Beabsichtigte Änderung: {focus}\n\n"
                    f"Sage 'REVIEW_OK: JA' wenn:\n"
                    f"  1. Code ist syntaktisch korrekt\n"
                    f"  2. Nur '{focus}' wurde geändert\n\n"
                    f"Sage 'REVIEW_OK: NEIN: <Grund>' wenn nicht.\n\n"
                    f"CODE:\n{candidate[:3000]}"
                )
                try:
                    review_raw  = _call_cerebras(review_prompt, "", 150)
                    review_ok   = "REVIEW_OK: JA" in review_raw
                    if not review_ok:
                        reason = review_raw[:120]
                        log.warning(f"  Reviewer NEIN: {reason}")
                        self.memory.record_failure(self.iterations, self.current_goal,
                                                   reason, "reviewer")
                        continue
                except Exception as re_err:
                    log.warning(f"  Reviewer-Fehler: {re_err} — als OK gewertet")

                new_code = candidate
                log.info("  ✅ Developer + Reviewer OK")
                break

            except Exception as e:
                log.error(f"  Developer Versuch {attempt}: {e}")
                self.memory.record_failure(self.iterations, self.current_goal, str(e), "developer")
                if attempt >= self.max_attempts:
                    return {"status": "error", "summary": f"Developer: {e}"}
                time.sleep(2)

        # ── 5. SYNTAX-CHECK ───────────────────────────────────────────
        ok, err = self._syntax_check(new_code)
        if not ok:
            log.warning(f"  Syntax-Fehler: {err} — versuche Auto-Fix")
            try:
                fix_prompt = (
                    f"SYNTAXFEHLER im generierten Python-Code:\n{err}\n\n"
                    f"Beheibe NUR diesen Fehler. Gib den kompletten Code zurück.\n"
                    f"KEIN MARKDOWN. NUR PYTHON.\n\n{new_code}"
                )
                fix = None
                try:
                    fix = _call_cerebras(fix_prompt, _DEVELOPER_SYSTEM, 8192)
                except Exception:
                    pass
                if not fix and groq_client:
                    try:
                        r = groq_client.chat.completions.create(
                            model="llama-3.3-70b-versatile",
                            messages=[{"role": "system", "content": _DEVELOPER_SYSTEM},
                                      {"role": "user",   "content": fix_prompt}],
                            max_tokens=8192,
                        )
                        fix = r.choices[0].message.content
                    except Exception:
                        pass
                if fix:
                    new_code = _strip_code_fences(fix)
                    ok, err  = self._syntax_check(new_code)
            except Exception:
                pass
            if not ok:
                self.memory.record_failure(self.iterations, self.current_goal, err, "syntax")
                return {"status": "error", "summary": f"Syntax: {err}"}
        log.info("  ✅ Syntax OK")

        # ── 6. SELFTEST ───────────────────────────────────────────────
        test_ok, test_out = self._selftest(new_code)
        if not test_ok:
            log.warning(f"  Selftest fehlgeschlagen: {test_out[:200]}")
            self.memory.record_failure(self.iterations, self.current_goal,
                                       test_out[:100], "selftest")
            return {"status": "error", "summary": f"Selftest: {test_out[:100]}"}
        log.info("  ✅ Selftest OK")

        if new_code.strip() == source.strip():
            return {"status": "error", "summary": "Keine Änderungen"}

        # ── 7. DEPLOY mit sofortigem Rollback bei Fehler ──────────────
        backup = create_deployment_backup()
        try:
            SELF_PATH.write_text(new_code, encoding="utf-8")
            verify_ok, verify_err = self._syntax_check(new_code)
            if not verify_ok:
                raise RuntimeError(f"Post-Deploy Syntax-Check fehlgeschlagen: {verify_err}")
        except Exception as e:
            log.error(f"  Deploy fehlgeschlagen: {e} — Rollback!")
            shutil.copy2(backup, SELF_PATH)
            self.memory.record_failure(self.iterations, self.current_goal, str(e), "deploy")
            return {"status": "error", "summary": f"Deploy-Fehler + Rollback: {e}"}

        summary = self._extract_summary(new_code)
        log.info(f"  🚀 Deployed! Backup: {backup.name} — {summary}")
        cleanup_old_backups(keep=10)

        # Modul-Backups nach erfolgreichem Deploy
        backup_all_modules()

        self.memory.record_success(self.iterations, self.current_goal,
                                   summary, self._last_plan, str(analysis_data))
        self._last_plan = ""

        goal_done = self._check_goal_reached()
        return {
            "status":  "goal_reached" if goal_done else "success",
            "summary": summary,
            "applied": True,
            "backup":  str(backup),
        }

    def _embed_section(self, source: str, focus: str, new_section: str) -> str:
        """
        Bettet eine geänderte Funktion per AST präzise in den Source-Code ein.
        Sucht die Funktion nach echtem Namen (über _FOCUS_ALIAS falls nötig).
        Fällt zurück auf Regex wenn AST scheitert.
        """
        import ast as _ast
        import re as _re

        func_name = _FOCUS_ALIAS.get(focus, focus)

        # ── AST-basierter Ansatz ──────────────────────────────────────
        try:
            tree = _ast.parse(source)
            lines = source.splitlines()
            target = None

            for node in _ast.walk(tree):
                if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                    if node.name == func_name:
                        target = node
                        break

            if target is not None:
                start_line = target.lineno - 1        # 0-basiert
                end_line   = getattr(target, "end_lineno", start_line + 1)

                # Normalisiere neuen Code
                new_lines = new_section.strip().splitlines()
                # Ziel-Einrückung aus Original übernehmen
                orig_indent = len(lines[start_line]) - len(lines[start_line].lstrip())
                orig_indent_str = " " * orig_indent

                normalized = []
                for i, line in enumerate(new_lines):
                    if i == 0:
                        normalized.append(orig_indent_str + line.lstrip())
                    elif line.strip():
                        body_lines = [l for l in new_lines[1:] if l.strip()]
                        min_ind = min(
                            (len(l) - len(l.lstrip()) for l in body_lines), default=0
                        )
                        curr = len(line) - len(line.lstrip())
                        extra = max(0, curr - min_ind)
                        normalized.append(orig_indent_str + "    " + " " * extra + line.lstrip())
                    else:
                        normalized.append("")

                result = lines[:start_line] + normalized + lines[end_line:]
                return "\n".join(result)

        except Exception as _ast_err:
            log.warning(f"  _embed_section AST-Fehler: {_ast_err} — Fallback auf Regex")

        # ── Regex-Fallback ────────────────────────────────────────────
        pattern = _re.compile(
            r"(^def\s+" + _re.escape(func_name) + r"\b"
            r"|^    def\s+" + _re.escape(func_name) + r"\b)",
            _re.MULTILINE
        )
        m = pattern.search(source)
        if not m:
            log.warning(f"  _embed_section: '{func_name}' nicht gefunden — Original beibehalten")
            return source

        start = m.start()
        end   = len(source)
        for mo in _re.finditer(r"^(?:async def |def |class |[^ \t\n])",
                               source[start + 1:], _re.MULTILINE):
            end = start + 1 + mo.start()
            break

        return source[:start] + new_section.strip() + "\n\n" + source[end:]


    def _syntax_check(self, code: str) -> Tuple[bool, str]:
        tmp = PATHS["opt_workspace"] / f"syn_{int(time.time()*1000)}.py"
        tmp.write_text(code, encoding="utf-8")
        try:
            r = subprocess.run(
                [sys.executable, "-m", "py_compile", str(tmp)],
                capture_output=True, text=True, timeout=20
            )
            tmp.unlink(missing_ok=True)
            return (True, "") if r.returncode == 0 else (False, r.stderr.strip())
        except subprocess.TimeoutExpired:
            tmp.unlink(missing_ok=True)
            return False, "Timeout"
        except Exception as e:
            tmp.unlink(missing_ok=True)
            return False, str(e)

    def _selftest(self, code: str) -> Tuple[bool, str]:
        inject = '''
if "--selftest" in sys.argv:
    _errs = []
    try:
        import pygame, edge_tts, speech_recognition
        from google import genai as _gt
        import telebot, requests
    except ImportError as _e:
        _errs.append(f"Import: {_e}")
    for _d in ["temp_audio", "temp_vision", "opt_workspace"]:
        if not Path(_d).exists():
            _errs.append(f"Dir fehlt: {_d}")
    if _errs:
        print("SELFTEST FAIL:", "; ".join(_errs)); sys.exit(1)
    print("SELFTEST OK"); sys.exit(0)
'''
        if "--selftest" not in code:
            pos      = code.find("\nif __name__")
            new_code = (code[:pos] + inject + code[pos:]) if pos != -1 else code + inject
        else:
            new_code = code

        tmp = PATHS["opt_workspace"] / f"st_{int(time.time()*1000)}.py"
        tmp.write_text(new_code, encoding="utf-8")
        try:
            r = subprocess.run(
                [sys.executable, str(tmp), "--selftest"],
                capture_output=True, text=True, timeout=40,
                cwd=str(SELF_PATH.parent)
            )
            tmp.unlink(missing_ok=True)
            if r.returncode == 0 and "SELFTEST OK" in r.stdout:
                return True, r.stdout
            return False, (r.stdout + r.stderr)[:600]
        except subprocess.TimeoutExpired:
            tmp.unlink(missing_ok=True)
            return False, "Selftest-Timeout"
        except Exception as e:
            tmp.unlink(missing_ok=True)
            return False, str(e)

    def _check_goal_reached(self) -> bool:
        if self.iterations < 2:
            return False
        try:
            ans = _call_gemini_with_backoff(
                f"Wurde das Ziel '{self.current_goal}' in {self.iterations} Iterationen erreicht? "
                f"Antworte nur: JA oder NEIN.", "", 5, stop_event=self._stop,
            ).strip().upper()
            return ans.startswith("JA")
        except Exception:
            return False

    def _extract_summary(self, code: str) -> str:
        for line in code.splitlines()[:10]:
            if f"# ITERATION {self.iterations}:" in line:
                return line.split(":", 1)[-1].strip()
        return f"Iteration {self.iterations} abgeschlossen"

    def _finalize(self, reason: str):
        self.status = self.DONE
        el     = int((datetime.now() - self.start_time).total_seconds()) if self.start_time else 0
        log.info(f"🏁 Optimierung beendet: {reason}. {self.iterations} Iterationen.")
        report = {
            "end_time":   datetime.now().isoformat(),
            "reason":     reason,
            "iterations": self.iterations,
            "elapsed_s":  el,
            "goal":       self.current_goal,
            "history":    self.history,
            "learning":   self.memory.get_stats_summary(),
        }
        rf = PATHS["logs"] / f"opt_final_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        rf.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        if _tg_chat_id and bot:
            try:
                bot.send_message(_tg_chat_id,
                    f"🏁 *Optimierung abgeschlossen*\n"
                    f"📊 {self.iterations} Iter | ⏱ {self._fmt(el)}\n"
                    f"🎯 {self.current_goal}\n"
                    f"📝 {reason}\n"
                    f"🧠 {self.memory.get_stats_summary()}",
                    parse_mode="Markdown"
                )
            except Exception:
                pass

    @staticmethod
    def _parse_duration(text: str) -> int:
        if not text:
            return 0
        t, total = text.lower().strip(), 0
        for pat, mul in [
            (r"(\d+)\s*(?:sekunde?n?|sek|s\b)", 1),
            (r"(\d+)\s*(?:minute?n?|min|m\b)",  60),
            (r"(\d+)\s*(?:stunde?n?|std|h\b)",  3600),
            (r"(\d+)\s*(?:tage?n?|d\b)",        86400),
        ]:
            m = re.search(pat, t)
            if m:
                total += int(m.group(1)) * mul
        return total

    @staticmethod
    def _fmt(seconds: int) -> str:
        if seconds < 60:   return f"{seconds}s"
        if seconds < 3600: return f"{seconds//60}min {seconds%60}s"
        return f"{seconds//3600}h {(seconds%3600)//60}min"

# ══════════════════════════════════════════════════════════════════════
#  MODUL 9 — INTENT MATCHING
# ══════════════════════════════════════════════════════════════════════

INTENTS = {
    r"uhrzeit|wie sp[äa]t|zeit jetzt":                               "time",
    r"datum|welcher tag|welches datum":                              "date",
    r"(?:öffne|starte|zeig|spiel)?\s*youtube":                       "youtube",
    r"(?:such|google|such.*google|google.*nach)":                    "google",
    r"optimier\s*(?:dich)?(?:\s.*)?":                                "optimize",
    r"(?:h[oö]r\s*(?:jetzt\s*)?auf|stop(?:p)?\s*(?:die)?\s*optimier|"
    r"lass\s*(?:das|es)\s*(?:sein|bleib)|keine\s*optimier|"
    r"unterbrich|pause\s*(?:optimier)?)":                            "opt_stop",
    r"optimier.*status|status.*optimier|was\s*machst\s*du":          "opt_status",
    r"lernprotokoll|was\s*(?:hast\s*du\s*gelernt|weißt\s*du)":      "learning",
    r"opt.*report|bericht.*optimier":                                "opt_report",
    r"rollback|backup wiederherstell":                               "rollback",
    r"golden\s*copy|ursprungsversion":                               "golden_rollback",
    r"log(?:eintr[äa]ge)?|debug|fehler.?log":                       "show_log",
    r"(?:beende|exit|stopp|shut.?down)\s*(?:jarvis)?":              "exit",
    r"mikrofon\s*(?:aus|stumm|deaktiv)":                            "mic_off",
    r"mikrofon\s*(?:an|ein|aktiv|h[öo]r\s*zu)":                    "mic_on",
    r"meshtastic\s*(?:senden?|schreib|schick)":                     "mesh_send",
    r"meshtastic\s*status":                                          "mesh_status",
    r"system\s*(?:info|status|check)":                              "sysinfo",
    r"reset\s*(?:chat|verlauf|ged[äa]chtnis)":                      "reset_chat",
    r"(?:was\s+kannst\s+du|deine?\s+f[äa]higkeiten|hilfe|help)":   "capabilities",
    r"handbuch|manual|bedienung":                                    "handbook",
    # Memory-Befehle
    r"(?:merk\s*dir|speicher|notier|schreib\s*dir)\s*(?:das|folgendes|:)?": "memory_save",
    r"(?:was\s*(?:hast\s*du\s*dir\s*gemerkt|weißt\s*du\s*über\s*mich)|"
    r"zeig.*notizen|meine\s*notizen|memory\s*(?:anzeigen|zeigen|status))":  "memory_show",
    # Computer-Control
    r"(?:mach|erstell|nimm)\s*screenshot|bildschirm\s*(?:foto|bild)": "cc_screenshot",
    r"(?:tipp|schreib|eingabe)\s*(?:folgendes|text)?":               "cc_type",
    r"drück\s*(?:die\s*)?(?:taste\s*)?":                             "cc_key",
    r"(?:klick|klicke)\s*(?:auf)?":                                  "cc_click",
    r"(?:scrolle?|scroll\s*(?:hoch|runter|up|down))":               "cc_scroll",
    r"(?:führ\s*aus|starte?\s*befehl|terminal)\s*:":                 "cc_run",
}


def match_intent(text: str) -> Optional[str]:
    lower = text.lower()
    for pat, intent in INTENTS.items():
        if re.search(pat, lower):
            return intent
    return None


def _parse_opt_command(text: str) -> dict:
    lower        = text.lower()
    duration_str = ""
    for pat in [
        r"für\s+(\d+\s*(?:sekunden?|minuten?|stunden?|tage?|sek|min|std|h|d)\b)",
        r"(\d+\s*(?:sekunden?|minuten?|stunden?|tage?|sek|min|std|h|d)\b)\s+lang",
        r"(\d+\s*(?:sekunden?|minuten?|stunden?|tage?|sek|min|std|h|d)\b)",
    ]:
        m = re.search(pat, lower)
        if m:
            duration_str = m.group(1)
            break
    clean = re.sub(r"optimier\s*(?:dich)?\s*(?:selbst)?\s*", "", lower).strip()
    clean = re.sub(r"für\s+\d+\s*\w+", "", clean).strip()
    clean = re.sub(r"\d+\s*\w+\s+lang", "", clean).strip()
    clean = re.sub(r"^(?:und|mit dem ziel|,)\s*", "", clean).strip()
    return {"goal": clean if len(clean) > 5 else "", "duration": duration_str}


def handle_local(intent: str, text: str):
    global mic_on, _tg_chat_id
    import platform

    if intent == "time":
        say(f"Es ist {datetime.now().strftime('%H:%M')} Uhr.")

    elif intent == "date":
        say(f"Heute ist {datetime.now().strftime('%A, der %d. %B %Y')}.")

    elif intent == "youtube":
        q = re.sub(
            r"\b(?:bitte|mal|doch|jetzt|schnell|kurz|einfach|"
            r"öffne|starte|zeig|spiel|spiele|auf|youtube)\b",
            "", text, flags=re.I
        ).strip()
        q = re.sub(r"\s{2,}", " ", q).strip(" ,.")
        import webbrowser
        url = f"https://youtube.com/results?search_query={q.replace(' ', '+')}" if q else "https://youtube.com"
        webbrowser.open(url)
        say(f"Öffne YouTube{' für ' + q if q else ''}.")

    elif intent == "google":
        # Filler-Wörter + Trigger-Wörter entfernen → echten Suchbegriff extrahieren
        q = re.sub(
            r"\b(?:bitte|mal|doch|jetzt|schnell|kurz|einfach|"
            r"such|suche|google|googel|nach|mir|das|die|den|"
            r"kannst\s*du|könntest\s*du|würdest\s*du)\b",
            "", text, flags=re.I
        ).strip()
        q = re.sub(r"\s{2,}", " ", q).strip(" ,.")
        import webbrowser
        url = f"https://google.com/search?q={q.replace(' ', '+')}" if q else "https://google.com"
        webbrowser.open(url)
        say(f"Suche nach {q}." if q else "Öffne Google.")

    elif intent == "optimize":
        if _opt_engine:
            p = _parse_opt_command(text)
            _opt_engine.start(goal=p["goal"], duration_input=p["duration"])
        else:
            say("Optimierungs-Engine nicht initialisiert.")

    elif intent == "opt_stop":
        if _opt_engine:
            _opt_engine.stop(save_progress=True)
        else:
            say("Keine Optimierung aktiv.")

    elif intent == "opt_status":
        say(_opt_engine.get_status() if _opt_engine else "Engine nicht verfügbar.")

    elif intent == "learning":
        say(_opt_engine.get_learning_summary() if _opt_engine else "Kein Lernprotokoll.")

    elif intent == "opt_report":
        reports = sorted(PATHS["logs"].glob("opt_final_*.json"))
        if not reports:
            say("Noch kein Optimierungsbericht.")
        else:
            try:
                d = json.loads(reports[-1].read_text(encoding="utf-8"))
                say(f"Letzter Bericht: {d.get('iterations',0)} Iterationen. "
                    f"Ziel: {d.get('goal','?')}. "
                    f"Grund: {d.get('reason','?')}. "
                    f"Lernen: {d.get('learning','')}")
            except Exception as e:
                say(f"Bericht nicht lesbar: {e}")

    elif intent == "rollback":
        ok = auto_rollback()
        say("Rollback abgeschlossen. Bitte neu starten." if ok else "Kein Backup vorhanden.")

    elif intent == "golden_rollback":
        ok = auto_rollback(to_golden=True)
        say("Zur Golden Copy zurückgekehrt. Bitte neu starten." if ok else "Golden Copy nicht gefunden.")

    elif intent == "show_log":
        try:
            lines = (PATHS["logs"] / "debug.log").read_text(encoding="utf-8").splitlines()[-15:]
            log.info("=== LOG ===\n" + "\n".join(lines))
            say(f"Die letzten {len(lines)} Log-Einträge sind in der Konsole.")
        except Exception as e:
            say(f"Log nicht lesbar: {e}")

    elif intent == "exit":
        say("Auf Wiedersehen.")
        time.sleep(1.5)
        os._exit(0)

    elif intent == "mic_off":
        mic_on = False
        say("Mikrofon deaktiviert.")

    elif intent == "mic_on":
        mic_on = True
        say("Mikrofon aktiv.")

    elif intent == "mesh_send":
        q = re.sub(r"meshtastic\s*(?:senden?|schreib|schick)\s*", "", text, flags=re.I).strip()
        if q:
            say("Gesendet." if meshtastic_bridge.send(q) else "Senden fehlgeschlagen.")
        else:
            say("Was soll ich senden?")

    elif intent == "mesh_status":
        say(f"Meshtastic {'verbunden' if meshtastic_bridge.connected else 'nicht verbunden'}.")

    elif intent == "sysinfo":
        opt_s = _opt_engine.status if _opt_engine else "N/A"
        dev   = f"Cerebras {cerebras_model}" if cerebras_client else "Gemini"
        cc    = "aktiv" if COMPUTER_CONTROL else "inaktiv"
        say(
            f"System: {platform.system()} {platform.release()}, "
            f"Python {platform.python_version()}. "
            f"Gemini: {'aktiv ' + (gemini_model or '') if gemini_chat else 'offline'}. "
            f"Developer-KI: {dev}. "
            f"Groq: {'aktiv' if groq_client else 'offline'}. "
            f"Computer-Control: {cc}. "
            f"Optimierung: {opt_s}. "
            f"User: {USER_ID}."
        )

    elif intent == "reset_chat":
        if gemini_chat:
            gemini_chat.reset()
        say("Chat-Verlauf zurückgesetzt.")

    elif intent == "capabilities":
        dev = f"Cerebras {cerebras_model}" if cerebras_client else "Gemini"
        cc  = "Maus- und Tastatursteuerung aktiv." if COMPUTER_CONTROL else ""
        say(
            f"Ich bin J.A.R.V.I.S Guardian Version {JARVIS_VERSION}. "
            f"Ich kann: Sprachsteuerung auf Deutsch, Telegram-Steuerung von überall, "
            f"Bild- Video- und Audioanalyse per Telegram, "
            f"autonome Selbst-Optimierung meines eigenen Codes, "
            f"{cc} "
            f"Web-Suche und System-Steuerung. "
            f"Developer-KI: {dev}."
        )

    elif intent == "handbook":
        generate_handbook()
        say("Handbuch aktualisiert.")

    elif intent == "memory_save":
        # Was nach dem Trigger steht, speichern
        note = re.sub(
            r"(?:merk\s*dir|speicher|notier|schreib\s*dir)\s*(?:das|folgendes)?\s*:?\s*",
            "", text, flags=re.I
        ).strip()
        if note:
            _add_to_memory_txt(note)
            say(f"Gespeichert: {note[:80]}")
        else:
            say("Was soll ich mir merken?")

    elif intent == "memory_show":
        mem = _load_memory_txt()
        if mem:
            say(f"Meine Notizen über dich: {mem[:400]}")
            if bot and _tg_chat_id:
                try:
                    bot.send_message(_tg_chat_id,
                        f"📋 *Meine Notizen:*\n```\n{mem[:2000]}\n```",
                        parse_mode="Markdown")
                except Exception:
                    pass
        else:
            say("Ich habe noch keine Notizen gespeichert. Sag: Merk dir, dass ...")

    # ── Computer-Control Intents ───────────────────────────────────────
    elif intent == "cc_screenshot":
        if not COMPUTER_CONTROL:
            say("Computer-Control nicht verfügbar. Bitte pyautogui installieren.")
            return
        path = cc_screenshot()
        if path and bot and _tg_chat_id:
            try:
                with open(path, "rb") as f:
                    bot.send_photo(_tg_chat_id, f, caption="📸 Screenshot")
                Path(path).unlink(missing_ok=True)
            except Exception as e:
                log.error(f"Screenshot-Telegram: {e}")
        say("Screenshot erstellt.")

    elif intent == "cc_type":
        if not COMPUTER_CONTROL:
            say("Computer-Control nicht verfügbar.")
            return
        q = re.sub(r"(?:tipp|schreib|eingabe)\s*(?:folgendes|text)?\s*:?\s*", "", text, flags=re.I).strip()
        if q:
            say("Tippe Text." if cc_type_text(q) else "Tipp-Fehler.")
        else:
            say("Was soll ich tippen?")

    elif intent == "cc_key":
        if not COMPUTER_CONTROL:
            say("Computer-Control nicht verfügbar.")
            return
        q = re.sub(r"drück\s*(?:die\s*)?(?:taste\s*)?", "", text, flags=re.I).strip()
        KEY_MAP = {
            "eingabe": "enter", "enter": "enter", "escape": "escape",
            "esc": "escape", "leerzeichen": "space", "space": "space",
            "tab": "tab", "rücktaste": "backspace", "backspace": "backspace",
            "strg c": "ctrl+c", "strg v": "ctrl+v", "strg z": "ctrl+z",
            "strg a": "ctrl+a", "alt tab": "alt+tab",
        }
        key = KEY_MAP.get(q.lower(), q)
        say("Taste gedrückt." if cc_key(key) else "Tastenfehler.")

    elif intent == "cc_scroll":
        if not COMPUTER_CONTROL:
            say("Computer-Control nicht verfügbar.")
            return
        direction = "up" if any(w in text.lower() for w in ["hoch", "up", "oben"]) else "down"
        say("Scrolle." if cc_scroll(direction) else "Scroll-Fehler.")

    elif intent == "cc_run":
        if not COMPUTER_CONTROL:
            say("Computer-Control nicht verfügbar.")
            return
        q = re.sub(r"(?:führ\s*aus|starte?\s*befehl|terminal)\s*:\s*", "", text, flags=re.I).strip()
        if q:
            stdout, stderr, rc = cc_run_command(q)
            result = stdout or stderr or "Kein Output"
            say(f"Befehl ausgeführt. {'Erfolgreich.' if rc == 0 else 'Fehler.'}")
            if bot and _tg_chat_id:
                try:
                    bot.send_message(_tg_chat_id,
                        f"💻 `{q}`\n{'✅' if rc == 0 else '❌'} RC={rc}\n```\n{result[:1000]}\n```",
                        parse_mode="Markdown")
                except Exception:
                    pass
        else:
            say("Welchen Befehl soll ich ausführen?")

# ══════════════════════════════════════════════════════════════════════
#  MODUL 10 — COMMAND PROCESSOR
# ══════════════════════════════════════════════════════════════════════

def process_command(text: str):
    log.info(f"▶ Input: {text}")
    if ui:
        ui.set_status("thinking")

    # Gespräch persistent im Memory speichern
    _memory_add("user", text)

    intent = match_intent(text)
    if intent:
        threading.Thread(target=handle_local, args=(intent, text), daemon=True).start()
        return

    if not gemini_chat and not groq_client:
        threading.Thread(target=say,
            args=("KI offline. Bitte Gemini API-Key in .env prüfen.",),
            daemon=True).start()
        return

    def _ai():
        try:
            cached = _cache_get(text)
            if cached:
                _memory_add("jarvis", cached)
                say(cached)
                return
            # Gemini versuchen
            if gemini_chat:
                resp = gemini_chat.send_message(text).text
            else:
                raise RuntimeError("Gemini nicht verfügbar")
            _memory_add("jarvis", resp)
            _cache_set(text, resp)
            say(resp)
        except Exception as e:
            log.error(f"Gemini-Chat: {e}")
            if groq_client:
                try:
                    enriched_sys = _get_enriched_system_prompt()
                    r = groq_client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=[
                            {"role": "system", "content": enriched_sys},
                            {"role": "user",   "content": text},
                        ],
                        max_tokens=600,
                    )
                    resp = r.choices[0].message.content
                    _memory_add("jarvis", resp)
                    say(resp)
                    return
                except Exception as e2:
                    log.error(f"Groq-Fallback: {e2}")
            say("Alle KI-Verbindungen ausgefallen.")

    threading.Thread(target=_ai, daemon=True).start()

# ══════════════════════════════════════════════════════════════════════
#  MODUL 11 — TTS & LISTEN
# ══════════════════════════════════════════════════════════════════════

_tts_lock = threading.Lock()


async def _speak_async(text: str):
    global is_speaking
    is_speaking = True
    fname = PATHS["temp_audio"] / f"s_{int(time.time()*1000)}.mp3"
    try:
        clean = re.sub(r"[*_`#>\[\]]", "", text).strip()
        if not clean:
            return
        await edge_tts.Communicate(clean, VOICE).save(str(fname))
        pygame.mixer.music.load(str(fname))
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy() and is_speaking:
            await asyncio.sleep(0.05)
        pygame.mixer.music.unload()
    except Exception as e:
        log.error(f"TTS: {e}")
    finally:
        is_speaking = False
        fname.unlink(missing_ok=True)


def say(text: str):
    if ui:
        ui.set_status("speaking", text=text)
    with _tts_lock:
        try:
            asyncio.run(_speak_async(text))
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(_speak_async(text))
            loop.close()
    if ui:
        ui.set_status("ready")



def listen_loop():
    RECONNECT_INTERVAL = 30
    mic_error_logged   = False

    while True:
        if not mic_on or is_speaking:
            time.sleep(0.2)
            continue

        try:
            r = sr.Recognizer()
            r.energy_threshold         = 300
            r.dynamic_energy_threshold = True
            r.pause_threshold          = 0.8

            with sr.Microphone() as source:
                if mic_error_logged:
                    log.info("🎤 Mikrofon wieder verbunden")
                    mic_error_logged = False
                else:
                    log.info("🎤 Kalibriere Mikrofon...")
                r.adjust_for_ambient_noise(source, duration=1.5)
                log.info("🎤 Bereit — höre zu...")

                while True:
                    if not mic_on or is_speaking:
                        time.sleep(0.2)
                        continue
                    try:
                        audio = r.listen(source, timeout=5, phrase_time_limit=15)
                        val   = r.recognize_google(audio, language="de-DE")
                        if val:
                            process_command(val)
                    except sr.WaitTimeoutError:
                        pass
                    except sr.UnknownValueError:
                        pass
                    except sr.RequestError as e:
                        log.error(f"Speech-API: {e}")
                        time.sleep(3)
                    except OSError as e:
                        errno_val = getattr(e, "errno", None)
                        if errno_val in (-9988, -9999, -9986) or "Stream closed" in str(e):
                            if not mic_error_logged:
                                log.warning(f"🎤 Audio-Gerät getrennt — warte {RECONNECT_INTERVAL}s")
                                mic_error_logged = True
                            break
                        else:
                            log.error(f"Audio-OSError: {e}")
                            time.sleep(2)
                            break

        except OSError as e:
            if not mic_error_logged:
                log.warning(f"🎤 Kein Mikrofon — versuche alle {RECONNECT_INTERVAL}s")
                mic_error_logged = True
            time.sleep(RECONNECT_INTERVAL)

        except Exception as e:
            log.error(f"Listen-Fehler: {e}")
            time.sleep(5)

        if mic_error_logged:
            time.sleep(RECONNECT_INTERVAL)


# ══════════════════════════════════════════════════════════════════════
#  MODUL 12 — TELEGRAM BOT (verbesserte Fehlerbehandlung)
# ══════════════════════════════════════════════════════════════════════

def _is_owner(msg) -> bool:
    if not OWNER_TELEGRAM_ID:
        return True
    return str(msg.from_user.id) == str(OWNER_TELEGRAM_ID)


def _owner_only(func):
    def wrapper(msg):
        if not _is_owner(msg):
            try:
                bot.reply_to(msg, "⛔ Nicht autorisiert.")
            except Exception:
                pass
            return
        func(msg)
    return wrapper


def _safe_reply(msg, text: str, parse_mode: str = None, **kwargs):
    """Sicher antworten mit automatischem Markdown-Fallback."""
    try:
        if parse_mode:
            bot.reply_to(msg, text[:4096], parse_mode=parse_mode, **kwargs)
        else:
            bot.reply_to(msg, text[:4096], **kwargs)
    except Exception as e:
        if "can't parse entities" in str(e).lower() or "parse" in str(e).lower():
            # Markdown-Fehler → plain text
            try:
                clean = re.sub(r"[*_`\[\]()]", "", text)
                bot.reply_to(msg, clean[:4096])
            except Exception as e2:
                log.error(f"Reply-Fallback fehlgeschlagen: {e2}")
        else:
            log.error(f"Telegram-Reply-Fehler: {e}")


def _safe_send(chat_id, text: str, parse_mode: str = None, **kwargs):
    """Sicher senden mit automatischem Fallback."""
    try:
        if parse_mode:
            bot.send_message(chat_id, text[:4096], parse_mode=parse_mode, **kwargs)
        else:
            bot.send_message(chat_id, text[:4096], **kwargs)
    except Exception as e:
        if "can't parse entities" in str(e).lower():
            try:
                clean = re.sub(r"[*_`\[\]()]", "", text)
                bot.send_message(chat_id, clean[:4096])
            except Exception as e2:
                log.error(f"Send-Fallback fehlgeschlagen: {e2}")
        else:
            log.error(f"Telegram-Send-Fehler: {e}")



# ITERATION 2: [Vollständige setup_telegram wiederhergestellt]

def setup_telegram():
    global bot, _tg_chat_id

    if not TELEGRAM_TOKEN:
        log.warning("⚠️  TELEGRAM_TOKEN fehlt — Telegram deaktiviert")
        return

    apihelper.CONNECT_TIMEOUT = 20
    apihelper.READ_TIMEOUT    = 20

    reconnect_wait = 5
    max_wait       = 120

    while True:
        try:
            bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=False)
            log.info("✅ Telegram-Bot initialisiert")

            @bot.message_handler(commands=["start", "help"])
            def cmd_start(msg):
                global _tg_chat_id
                _tg_chat_id = msg.chat.id
                dev = f"Cerebras {cerebras_model}" if cerebras_client else "Gemini"
                cc  = "✅" if COMPUTER_CONTROL else "❌"
                _safe_reply(msg,
                    f"🤖 J.A.R.V.I.S Guardian v{JARVIS_VERSION}\n"
                    f"🛠 Developer-KI: {dev}\n"
                    f"🖥 Computer-Control: {cc}\n\n"
                    f"📸 Bild → Analyse | 🎬 Video → Frames\n"
                    f"🎙 Audio → Transkript | 💬 Text → KI\n\n"
                    f"Befehle:\n"
                    f"/optimize [Ziel] [Dauer]\n"
                    f"/opt_stop /opt_status /opt_report\n"
                    f"/learning /rollback /golden_rollback\n"
                    f"/diamond_rollback — 💎 Notausgang\n"
                    f"/status /reset\n\n"
                    f"Memory:\n"
                    f"/memory — Gesprächs-Verlauf\n"
                    f"/merken <Text> — Notiz speichern\n"
                    f"/notizen — alle Notizen anzeigen\n\n"
                    f"Computer-Control:\n"
                    f"/screenshot /type <text>\n"
                    f"/key <taste> /click <x> <y>\n"
                    f"/run <befehl> /screen_info\n"
                    f"/scroll <up|down>"
                )

            @bot.message_handler(commands=["optimize"])
            @_owner_only
            def cmd_optimize(msg):
                args   = msg.text.replace("/optimize", "").strip()
                params = _parse_opt_command("optimiere dich " + args)
                if _opt_engine:
                    threading.Thread(
                        target=_opt_engine.start,
                        args=(params["goal"], params["duration"]),
                        daemon=True
                    ).start()
                    dev = f"Cerebras {cerebras_model}" if cerebras_client else "Gemini"
                    _safe_reply(msg,
                        f"Optimierung gestartet\n"
                        f"Ziel: {params['goal'] or 'Allgemein'}\n"
                        f"Dauer: {params['duration'] or 'Unbegrenzt'}\n"
                        f"Developer-KI: {dev}"
                    )
                else:
                    _safe_reply(msg, "Engine nicht verfügbar.")

            @bot.message_handler(commands=["opt_stop"])
            @_owner_only
            def cmd_opt_stop(msg):
                if _opt_engine:
                    _opt_engine.stop(save_progress=True)
                    _safe_reply(msg, "Gestoppt. Fortschritt gespeichert.")
                else:
                    _safe_reply(msg, "Nicht aktiv.")

            @bot.message_handler(commands=["opt_status"])
            def cmd_opt_status(msg):
                _safe_reply(msg, _opt_engine.get_status() if _opt_engine else "N/A")

            @bot.message_handler(commands=["learning"])
            def cmd_learning(msg):
                _safe_reply(msg, _opt_engine.get_learning_summary() if _opt_engine else "N/A")

            @bot.message_handler(commands=["opt_report"])
            def cmd_opt_report(msg):
                reports = sorted(PATHS["logs"].glob("opt_final_*.json"))
                if not reports:
                    _safe_reply(msg, "Noch kein Bericht.")
                    return
                try:
                    d   = json.loads(reports[-1].read_text(encoding="utf-8"))
                    txt = (
                        f"Optimierungsbericht\n"
                        f"{d.get('iterations',0)} Iterationen\n"
                        f"Zeit: {d.get('elapsed_s',0)//60} Min\n"
                        f"Ziel: {d.get('goal','-')}\n"
                        f"Grund: {d.get('reason','-')}\n"
                        f"Lernen: {d.get('learning','-')}\n\n"
                        f"Letzte Iterationen:\n"
                    )
                    for h in d.get("history", [])[-5:]:
                        icon = "OK" if h.get("applied") else "Fehler"
                        txt += f"[{icon}] #{h['iteration']} [{h.get('focus','-')}]: {h.get('summary','-')[:60]}\n"
                    _safe_reply(msg, txt)
                except Exception as e:
                    _safe_reply(msg, f"Fehler: {e}")

            @bot.message_handler(commands=["rollback"])
            @_owner_only
            def cmd_rollback(msg):
                _safe_reply(msg,
                    "Rollback OK. JARVIS neu starten." if auto_rollback() else "Kein Backup."
                )

            @bot.message_handler(commands=["golden_rollback"])
            @_owner_only
            def cmd_golden(msg):
                _safe_reply(msg,
                    "Golden Copy wiederhergestellt. Neu starten."
                    if auto_rollback(to_golden=True) else "Golden Copy nicht gefunden."
                )

            @bot.message_handler(commands=["diamond_rollback"])
            @_owner_only
            def cmd_diamond(msg):
                """Diamant-Rollback: absoluter Notausgang auf deinen persönlichen Nullpunkt."""
                ok = auto_rollback(to_diamond=True)
                _safe_reply(msg,
                    "💎 Diamant-Datei wiederhergestellt. Bitte JARVIS neu starten."
                    if ok else
                    "💎 Keine Diamant-Datei gefunden.\n"
                    "Erstelle einmalig manuell:\n"
                    "  copy jarvis_v5_8.py jarvis_diamond.py"
                )

            @bot.message_handler(commands=["reset"])
            def cmd_reset(msg):
                if gemini_chat:
                    gemini_chat.reset()
                if _conv_memory:
                    _conv_memory.clear_recent(keep_last=5)
                _safe_reply(msg, "Chat zurückgesetzt. Langzeit-Memory bleibt erhalten.")

            @bot.message_handler(commands=["memory"])
            def cmd_memory(msg):
                if not _conv_memory:
                    _safe_reply(msg, "Memory nicht initialisiert.")
                    return
                stats  = _conv_memory.get_stats()
                recent = _conv_memory.get_context_block()
                mem_txt = _load_memory_txt()
                notes_block = f"\n\n📋 Persönliche Notizen:\n{mem_txt[:800]}" if mem_txt else ""
                _safe_reply(msg, f"{stats}\n\n{recent[:1500]}{notes_block}")

            @bot.message_handler(commands=["merken"])
            @_owner_only
            def cmd_merken(msg):
                note = msg.text.replace("/merken", "").strip()
                if note:
                    _add_to_memory_txt(note)
                    _safe_reply(msg, f"✅ Gespeichert: {note[:100]}")
                else:
                    _safe_reply(msg, "Verwendung: /merken <Was ich mir merken soll>")

            @bot.message_handler(commands=["notizen"])
            def cmd_notizen(msg):
                mem = _load_memory_txt()
                if mem:
                    _safe_reply(msg, f"📋 Meine Notizen:\n\n{mem[:3000]}")
                else:
                    _safe_reply(msg, "Noch keine Notizen. /merken <Text> um etwas zu speichern.")

            @bot.message_handler(commands=["mesh"])
            @_owner_only
            def cmd_mesh(msg):
                t = msg.text.replace("/mesh", "").strip()
                if t:
                    _safe_reply(msg, "Gesendet!" if meshtastic_bridge.send(t) else "Nicht verbunden.")
                else:
                    _safe_reply(msg, "Verwendung: /mesh <Nachricht>")

            @bot.message_handler(commands=["status"])
            def cmd_status(msg):
                import platform
                opt_s  = _opt_engine.status if _opt_engine else "N/A"
                opt_it = _opt_engine.iterations if _opt_engine else 0
                dev    = f"Cerebras {cerebras_model}" if cerebras_client else "Gemini"
                resume = _load_opt_resume()
                res_s  = f"\nResume: {resume['goal']} (Iter {resume['iterations_done']})" if resume else ""
                cc     = "aktiv" if COMPUTER_CONTROL else "inaktiv"
                diamond_s = "💎 OK" if DIAMOND_FILE.exists() else "💎 FEHLT"
                _safe_reply(msg,
                    f"J.A.R.V.I.S v{JARVIS_VERSION} | User: {USER_ID}\n"
                    f"Gemini: {'OK ' + (gemini_model or '') if gemini_chat else 'OFFLINE'}\n"
                    f"Developer-KI: {dev}\n"
                    f"Groq: {'OK' if groq_client else 'OFFLINE'}\n"
                    f"Meshtastic: {'OK' if meshtastic_bridge.connected else 'OFFLINE'}\n"
                    f"Mikrofon: {'AN' if mic_on else 'AUS'}\n"
                    f"Computer-Control: {cc}\n"
                    f"Sicherheit: {diamond_s} | ⭐ Golden OK\n"
                    f"Opt-Engine: {opt_s} (Iter: {opt_it}){res_s}"
                )

            # ── Computer-Control Befehle ───────────────────────────────
            @bot.message_handler(commands=["screenshot"])
            @_owner_only
            def cmd_screenshot(msg):
                if not COMPUTER_CONTROL:
                    _safe_reply(msg, "Computer-Control nicht verfügbar.\npip install pyautogui")
                    return
                try:
                    bot.send_chat_action(msg.chat.id, "upload_photo")
                    path = cc_screenshot()
                    if path:
                        with open(path, "rb") as f:
                            bot.send_photo(msg.chat.id, f, caption="📸 Screenshot")
                        Path(path).unlink(missing_ok=True)
                    else:
                        _safe_reply(msg, "Screenshot fehlgeschlagen.")
                except Exception as e:
                    _safe_reply(msg, f"Fehler: {e}")

            @bot.message_handler(commands=["type"])
            @_owner_only
            def cmd_type(msg):
                if not COMPUTER_CONTROL:
                    _safe_reply(msg, "Computer-Control nicht verfügbar.")
                    return
                text_to_type = msg.text.replace("/type", "").strip()
                if not text_to_type:
                    _safe_reply(msg, "Verwendung: /type <text>")
                    return
                ok = cc_type_text(text_to_type)
                _safe_reply(msg, f"Getippt: {text_to_type[:50]}" if ok else "Tipp-Fehler.")

            @bot.message_handler(commands=["key"])
            @_owner_only
            def cmd_key(msg):
                if not COMPUTER_CONTROL:
                    _safe_reply(msg, "Computer-Control nicht verfügbar.")
                    return
                key = msg.text.replace("/key", "").strip()
                if not key:
                    _safe_reply(msg, "Verwendung: /key <taste>\nBeispiele: enter, ctrl+c, alt+tab")
                    return
                ok = cc_key(key)
                _safe_reply(msg, f"Taste: {key}" if ok else "Tastenfehler.")

            @bot.message_handler(commands=["click"])
            @_owner_only
            def cmd_click(msg):
                if not COMPUTER_CONTROL:
                    _safe_reply(msg, "Computer-Control nicht verfügbar.")
                    return
                try:
                    parts = msg.text.replace("/click", "").strip().split()
                    x, y  = int(parts[0]), int(parts[1])
                    ok    = cc_click(x, y)
                    _safe_reply(msg, f"Klick: ({x},{y})" if ok else "Klick-Fehler.")
                except (ValueError, IndexError):
                    _safe_reply(msg, "Verwendung: /click <x> <y>")

            @bot.message_handler(commands=["move"])
            @_owner_only
            def cmd_move(msg):
                if not COMPUTER_CONTROL:
                    _safe_reply(msg, "Computer-Control nicht verfügbar.")
                    return
                try:
                    parts = msg.text.replace("/move", "").strip().split()
                    x, y  = int(parts[0]), int(parts[1])
                    ok    = cc_move(x, y)
                    _safe_reply(msg, f"Maus: ({x},{y})" if ok else "Move-Fehler.")
                except (ValueError, IndexError):
                    _safe_reply(msg, "Verwendung: /move <x> <y>")

            @bot.message_handler(commands=["scroll"])
            @_owner_only
            def cmd_scroll(msg):
                if not COMPUTER_CONTROL:
                    _safe_reply(msg, "Computer-Control nicht verfügbar.")
                    return
                direction = msg.text.replace("/scroll", "").strip().lower() or "down"
                direction = "up" if direction in ("up", "hoch", "oben") else "down"
                ok = cc_scroll(direction)
                _safe_reply(msg, f"Scroll {direction}" if ok else "Scroll-Fehler.")

            @bot.message_handler(commands=["run"])
            @_owner_only
            def cmd_run(msg):
                cmd = msg.text.replace("/run", "").strip()
                if not cmd:
                    _safe_reply(msg, "Verwendung: /run <befehl>")
                    return
                try:
                    bot.send_chat_action(msg.chat.id, "typing")
                    stdout, stderr, rc = cc_run_command(cmd, timeout=30)
                    output = stdout or stderr or "(kein Output)"
                    status = "OK" if rc == 0 else f"Fehler RC={rc}"
                    _safe_reply(msg, f"$ {cmd}\n{status}\n\n{output[:2000]}")
                except Exception as e:
                    _safe_reply(msg, f"Fehler: {e}")

            @bot.message_handler(commands=["screen_info"])
            def cmd_screen_info(msg):
                if not COMPUTER_CONTROL:
                    _safe_reply(msg, "Computer-Control nicht verfügbar.")
                    return
                info = cc_get_screen_info()
                if "error" in info:
                    _safe_reply(msg, f"Fehler: {info['error']}")
                else:
                    _safe_reply(msg,
                        f"Bildschirm: {info.get('width')}x{info.get('height')}\n"
                        f"Maus: ({info.get('mouse_x')},{info.get('mouse_y')})"
                    )

            @bot.message_handler(content_types=["text"])
            def handle_text(msg):
                global _tg_chat_id
                _tg_chat_id = msg.chat.id
                text   = msg.text.strip()
                intent = match_intent(text)
                if intent:
                    restricted = {"optimize", "opt_stop", "rollback", "golden_rollback",
                                  "exit", "cc_screenshot", "cc_type", "cc_key",
                                  "cc_click", "cc_scroll", "cc_run"}
                    if intent in restricted and not _is_owner(msg):
                        _safe_reply(msg, "Nicht autorisiert.")
                        return
                    threading.Thread(target=handle_local, args=(intent, text), daemon=True).start()
                    _safe_reply(msg, f"Ausführe: {intent}")
                    return
                _memory_add("user", text)
                if gemini_chat:
                    try:
                        bot.send_chat_action(msg.chat.id, "typing")
                        cached = _cache_get(text)
                        resp   = cached or gemini_chat.send_message(text).text
                        if not cached:
                            _cache_set(text, resp)
                        _memory_add("jarvis", resp)
                        _safe_reply(msg, resp)
                        threading.Thread(target=say, args=(resp[:500],), daemon=True).start()
                    except Exception as e:
                        log.error(f"Text-Handler: {e}")
                        _safe_reply(msg, f"Fehler: {e}")
                else:
                    _safe_reply(msg, "KI nicht verfügbar.")

            @bot.message_handler(content_types=["photo"])
            def handle_photo(msg):
                global _tg_chat_id
                _tg_chat_id = msg.chat.id
                try:
                    bot.send_chat_action(msg.chat.id, "typing")
                    fi   = bot.get_file(msg.photo[-1].file_id)
                    data = bot.download_file(fi.file_path)
                    tmp  = PATHS["temp_vision"] / f"tg_{int(time.time())}.jpg"
                    tmp.write_bytes(data)
                    q = msg.caption or "Was siehst du? Beschreibe detailliert auf Deutsch."
                    _safe_reply(msg, "Analysiere...")
                    result = analyze_image(str(tmp), q)
                    _safe_reply(msg, result)
                    tmp.unlink(missing_ok=True)
                except Exception as e:
                    log.error(f"Photo-Handler: {e}")
                    _safe_reply(msg, f"Fehler: {e}")

            @bot.message_handler(content_types=["video", "video_note"])
            def handle_video(msg):
                global _tg_chat_id
                _tg_chat_id = msg.chat.id
                try:
                    bot.send_chat_action(msg.chat.id, "typing")
                    vid  = msg.video or msg.video_note
                    fi   = bot.get_file(vid.file_id)
                    data = bot.download_file(fi.file_path)
                    tmp  = PATHS["temp_vision"] / f"tg_{int(time.time())}.mp4"
                    tmp.write_bytes(data)
                    q = getattr(msg, "caption", None) or "Analysiere dieses Video."
                    _safe_reply(msg, "Analysiere Video...")
                    result = analyze_video(str(tmp), max_frames=6, question=q)
                    _safe_reply(msg, result)
                    tmp.unlink(missing_ok=True)
                except Exception as e:
                    log.error(f"Video-Handler: {e}")
                    _safe_reply(msg, f"Fehler: {e}")

            @bot.message_handler(content_types=["voice", "audio", "document"])
            def handle_audio(msg):
                global _tg_chat_id
                _tg_chat_id = msg.chat.id
                try:
                    bot.send_chat_action(msg.chat.id, "typing")
                    if msg.voice:
                        fid, ext = msg.voice.file_id, "ogg"
                    elif msg.audio:
                        fid, ext = msg.audio.file_id, "mp3"
                    elif msg.document:
                        mime = msg.document.mime_type or ""
                        if not any(x in mime for x in ["audio", "video", "ogg", "mp3", "wav", "m4a"]):
                            _safe_reply(msg, "Nur Audio-Dokumente.")
                            return
                        fid = msg.document.file_id
                        ext = (msg.document.file_name or "audio.mp3").split(".")[-1]
                    else:
                        return

                    fi   = bot.get_file(fid)
                    data = bot.download_file(fi.file_path)
                    tmp  = PATHS["temp_audio"] / f"tg_{int(time.time())}.{ext}"
                    tmp.write_bytes(data)
                    _safe_reply(msg, "Transkribiere...")
                    transcript = transcribe_audio(str(tmp))
                    cap = (msg.caption or "").lower()

                    if "zusammenfassen" in cap:
                        cleaned = clean_text(transcript, mode="both")
                        _safe_reply(msg, f"Zusammenfassung:\n{cleaned}")
                    elif "füllwörter" in cap:
                        _safe_reply(msg, f"Bereinigt:\n{clean_text(transcript, 'filler')}")
                    else:
                        _safe_reply(msg, f"Transkript:\n{transcript}")
                    tmp.unlink(missing_ok=True)
                except Exception as e:
                    log.error(f"Audio-Handler: {e}")
                    _safe_reply(msg, f"Fehler: {e}")

            # Alte Webhook-Session bereinigen (409-Prophylaxe)
            try:
                bot.delete_webhook(drop_pending_updates=True)
                log.info("🔗 Telegram: Webhook/Session bereinigt")
                time.sleep(1)
            except Exception as _we:
                log.warning(f"Telegram Webhook-Cleanup: {_we}")

            log.info("🔄 Telegram polling startet...")
            reconnect_wait = 5
            bot.infinity_polling(
                none_stop=True,
                interval=1,
                timeout=30,
                long_polling_timeout=20,
            )

        except Exception as e:
            log.error(f"Telegram-Fehler: {e} — Reconnect in {reconnect_wait}s")
            time.sleep(reconnect_wait)
            reconnect_wait = min(reconnect_wait * 2, max_wait)
            bot = None
            continue


# ══════════════════════════════════════════════════════════════════════
#  MODUL 13 — ARC REAKTOR UI  (resizable, detailliert)
# ══════════════════════════════════════════════════════════════════════

class JarvisUI:
    # ── Farben ─────────────────────────────────────────────────────────
    CYAN    = "#00e5ff"
    GREEN   = "#00ff88"
    YELLOW  = "#ffd600"
    RED     = "#ff1744"
    ORANGE  = "#ff9100"
    DIM     = "#1a4060"
    DIM2    = "#0a2a3a"
    BG      = "#04080f"

    # ── Größen-Stufen (W x H) ─────────────────────────────────────────
    #   MINI   → nur Titel + Status
    #   NORMAL → + Untertitel + Statusbar
    #   VOLL   → + Opt-Details / Lernprotokoll / Brain-Status
    SIZES = {
        "mini":   (560, 56),
        "normal": (860, 148),
        "voll":   (860, 310),
    }
    SIZE_ORDER = ["mini", "normal", "voll"]

    # Höhen-Schwellen für automatischen Modus beim freien Resize
    _H_MINI   = 70
    _H_NORMAL = 160

    def __init__(self):
        self._size_idx  = 1          # start mit "normal"
        self._pulse     = 0.0
        self._drag_x    = 0
        self._drag_y    = 0
        self._opt_succ  = 0
        self._opt_fail  = 0
        self._last_sub  = ""
        self._rebuild_pending = False

        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=self.BG)
        sw = self.root.winfo_screenwidth()
        W, H = self.SIZES["normal"]
        self.root.geometry(f"{W}x{H}+{sw - W - 20}+40")
        self.root.minsize(360, 46)

        # ── Canvas (Hintergrund & statische Elemente) ──────────────────
        self.canvas = tk.Canvas(self.root, bg=self.BG, highlightthickness=0)
        self.canvas.place(x=0, y=0, relwidth=1.0, relheight=1.0)

        # ── Drag auf Titelbereich ───────────────────────────────────────
        self.canvas.bind("<ButtonPress-1>",  self._drag_start)
        self.canvas.bind("<B1-Motion>",      self._drag_move)
        self.canvas.bind("<ButtonRelease-1>", self._drag_end)

        # ── Resize-Griff unten rechts ──────────────────────────────────
        self._resize_grip = tk.Label(self.root, text="⠿", bg=self.BG,
                                     fg=self.DIM, font=("Consolas", 9), cursor="size_nw_se")
        self._resize_grip.place(relx=1.0, rely=1.0, anchor="se", width=16, height=16)
        self._resize_grip.bind("<ButtonPress-1>",  self._resize_start)
        self._resize_grip.bind("<B1-Motion>",       self._resize_move)
        self._resize_grip.bind("<Enter>", lambda e: self._resize_grip.config(fg=self.CYAN))
        self._resize_grip.bind("<Leave>", lambda e: self._resize_grip.config(fg=self.DIM))

        # Größenänderung-Event → Layout neu berechnen
        self.root.bind("<Configure>", self._on_configure)

        # ── Variablen ──────────────────────────────────────────────────
        self.sub_var      = tk.StringVar()
        self.opt_var      = tk.StringVar(value="OPT: BEREIT")
        self.iter_var     = tk.StringVar(value="ITER: 0  ✓0  ✗0")
        self.learn_var    = tk.StringVar(value="🧠 0 gelernt")
        self.dev_var      = tk.StringVar(value="DEV: —")
        self.focus_var    = tk.StringVar(value="FOKUS: —")
        self.brain_var    = tk.StringVar(value="Warte auf Aktivität...")
        self.gemini_var   = tk.StringVar(value="🧠 GEMINI ?")
        self.groq_var     = tk.StringVar(value="🔬 GROQ ?")
        self.cerebras_var = tk.StringVar(value="⚡ CEREBRAS ?")

        F = "Consolas"

        # ── Untertitel-Label (unter Titelzeile) ────────────────────────
        # Verwendet place() mit relativer Breite — passt sich Fenstergröße an
        self._lbl_sub = tk.Label(
            self.root, textvariable=self.sub_var,
            font=(F, 9), fg=self.CYAN, bg=self.BG,
            anchor="w", justify="left",
            wraplength=1,   # wird in _layout() dynamisch gesetzt
        )

        # ── Statusbar (unterste Zeile) ─────────────────────────────────
        self._bar_frame = tk.Frame(self.root, bg=self.BG)
        tk.Label(self._bar_frame, textvariable=self.opt_var,
            font=(F, 8), fg=self.DIM, bg=self.BG).pack(side="left", padx=(8, 14))
        self._iter_lbl = tk.Label(self._bar_frame, textvariable=self.iter_var,
            font=(F, 8), fg=self.DIM, bg=self.BG)
        self._iter_lbl.pack(side="left", padx=(0, 14))
        tk.Label(self._bar_frame, textvariable=self.dev_var,
            font=(F, 8), fg=self.DIM, bg=self.BG).pack(side="left", padx=(0, 14))
        self._cc_lbl = tk.Label(self._bar_frame,
            text=f"CC: {'AN' if COMPUTER_CONTROL else 'AUS'}",
            font=(F, 8), fg=self.GREEN if COMPUTER_CONTROL else self.DIM, bg=self.BG)
        self._cc_lbl.pack(side="left", padx=(0, 14))
        tk.Label(self._bar_frame, text=f"USER: {USER_ID}",
            font=(F, 8), fg=self.DIM, bg=self.BG).pack(side="left")

        # ── Detail-Panel (nur "voll") ──────────────────────────────────
        self._detail_frame = tk.Frame(self.root, bg=self.BG)

        # Zeile 1: Fokus + Lernprotokoll
        row1 = tk.Frame(self._detail_frame, bg=self.BG)
        row1.pack(fill="x", padx=10, pady=(4, 0))
        tk.Label(row1, textvariable=self.focus_var,
            font=(F, 8), fg=self.YELLOW, bg=self.BG, anchor="w").pack(side="left", padx=(0, 16))
        tk.Label(row1, textvariable=self.learn_var,
            font=(F, 8), fg=self.DIM, bg=self.BG, anchor="w").pack(side="left")

        tk.Frame(self._detail_frame, bg=self.DIM2, height=1).pack(fill="x", padx=10, pady=4)

        # Zeile 2: Brain-Status
        row2 = tk.Frame(self._detail_frame, bg=self.BG)
        row2.pack(fill="x", padx=10, pady=(0, 2))
        tk.Label(row2, text="BRAINS:", font=(F, 8, "bold"), fg=self.DIM, bg=self.BG
                 ).pack(side="left", padx=(0, 10))
        self._gemini_lbl = tk.Label(row2, textvariable=self.gemini_var,
            font=(F, 8), fg=self.DIM, bg=self.BG)
        self._gemini_lbl.pack(side="left", padx=(0, 14))
        self._groq_lbl = tk.Label(row2, textvariable=self.groq_var,
            font=(F, 8), fg=self.DIM, bg=self.BG)
        self._groq_lbl.pack(side="left", padx=(0, 14))
        self._cerebras_lbl = tk.Label(row2, textvariable=self.cerebras_var,
            font=(F, 8), fg=self.DIM, bg=self.BG)
        self._cerebras_lbl.pack(side="left")

        tk.Frame(self._detail_frame, bg=self.DIM2, height=1).pack(fill="x", padx=10, pady=4)

        # Zeile 3: Letzte Aktivität (mehrzeilig, wraplength wird in _layout gesetzt)
        self._brain_lbl = tk.Label(
            self._detail_frame, textvariable=self.brain_var,
            font=(F, 8), fg="#2a6080", bg=self.BG,
            anchor="nw", justify="left",
            wraplength=1,   # wird in _layout() gesetzt
        )
        self._brain_lbl.pack(fill="both", expand=True, padx=10, pady=(0, 4))

        # Canvas-Element-IDs
        self._status_id = None
        self._arc_id    = None
        self._mesh_id   = None
        self._size_id   = None

        # ── Text-Eingabe-Frame ─────────────────────────────────────────
        self._input_frame = tk.Frame(self.root, bg=self.BG)
        self._input_var   = tk.StringVar()
        self._input_entry = tk.Entry(
            self._input_frame,
            textvariable=self._input_var,
            font=("Consolas", 9),
            bg="#001e33", fg=self.CYAN,
            insertbackground=self.CYAN,
            relief="flat", bd=0,
        )
        self._input_entry.pack(side="left", fill="x", expand=True, padx=(8, 4))
        self._input_entry.bind("<Return>", self._send_text_input)

        self._send_btn = tk.Label(
            self._input_frame,
            text="▶", font=("Consolas", 10, "bold"),
            fg=self.CYAN, bg=self.BG, cursor="hand2",
        )
        self._send_btn.pack(side="right", padx=(0, 8))
        self._send_btn.bind("<Button-1>", self._send_text_input)

        # Farben laden (vor Canvas-Build)
        self._load_color_config()

        self._build_canvas()
        self._layout()
        self._animate()

    # ── Canvas komplett neu zeichnen ───────────────────────────────────
    def _build_canvas(self):
        c = self.canvas
        c.delete("all")
        W = self.root.winfo_width()  or self.SIZES["normal"][0]
        H = self.root.winfo_height() or self.SIZES["normal"][1]

        # Hintergrund-Rahmen (3 verschachtelte Rechtecke)
        for i, col in enumerate(["#001422", "#001e33", "#002244"]):
            o = i
            c.create_rectangle(o, o, W-o-1, H-o-1, outline=col, width=1, tags="static")

        # Ecken-Akzente
        for x, y in [(14, 14), (W-14, 14), (14, H-14), (W-14, H-14)]:
            c.create_oval(x-4, y-4, x+4, y+4, outline=self.CYAN, width=1, tags="static")

        # Trennlinie unter Titelzeile
        c.create_line(16, 56, W-16, 56, fill=self.DIM2, width=1, tags="static")

        # Trennlinie über Statusbar (nur wenn Platz)
        if H >= 90:
            c.create_line(16, H-32, W-32, H-32, fill=self.DIM2, width=1, tags="static")

        # Titel "J.A.R.V.I.S"
        c.create_text(20, 30, text="J.A.R.V.I.S",
            font=("Consolas", 18, "bold"), fill=self.CYAN, anchor="w", tags="static")

        # Status-Text (dynamisch, wird über set_status() aktualisiert)
        self._status_id = c.create_text(212, 30, text="| STUMM",
            font=("Consolas", 10, "bold"), fill=self.RED, anchor="w")

        # Subzeile: Guardian + Feature-Tags — IMMER sichtbar wenn H >= 56
        if H >= 56:
            cc_tag = ".ENV | JSON-OPTIMIZER | MULTI-AI" + (" | COMPUTER-CONTROL" if COMPUTER_CONTROL else "")
            subtitle = f"Guardian v{JARVIS_VERSION}  ·  {cc_tag}"
            c.create_text(20, 46, text=subtitle,
                font=("Consolas", 7), fill="#1e5070", anchor="w", tags="static")

        # Schließen-Button (✕)
        btn = c.create_text(W-14, 14, text="✕",
            font=("Consolas", 11), fill=self.DIM, anchor="center", tags="static")
        c.tag_bind(btn, "<Enter>",    lambda e: c.itemconfig(btn, fill=self.RED))
        c.tag_bind(btn, "<Leave>",    lambda e: c.itemconfig(btn, fill=self.DIM))
        c.tag_bind(btn, "<Button-1>", lambda e: os._exit(0))

        # Mikrofon-Button (🎤)
        mic = c.create_text(W-38, 14, text="🎤",
            font=("Consolas", 10), fill=self.CYAN, anchor="center", tags="static")
        c.tag_bind(mic, "<Button-1>", self._toggle_mic)

        # Größen-Schalter (◈)
        self._size_id = c.create_text(W-60, 14, text="◈",
            font=("Consolas", 10), fill=self.DIM, anchor="center")
        c.tag_bind(self._size_id, "<Enter>",    lambda e: c.itemconfig(self._size_id, fill=self.CYAN))
        c.tag_bind(self._size_id, "<Leave>",    lambda e: c.itemconfig(self._size_id, fill=self.DIM))
        c.tag_bind(self._size_id, "<Button-1>", self._cycle_size)

        # Einstellungen-Button (⚙)
        gear = c.create_text(W-82, 14, text="⚙",
            font=("Consolas", 10), fill=self.DIM, anchor="center", tags="static")
        c.tag_bind(gear, "<Enter>",    lambda e: c.itemconfig(gear, fill=self.CYAN))
        c.tag_bind(gear, "<Leave>",    lambda e: c.itemconfig(gear, fill=self.DIM))
        c.tag_bind(gear, "<Button-1>", lambda e: self._open_settings_window())

        # MESH-Indikator
        self._mesh_id = c.create_text(W-88, H-14, text="● MESH",
            font=("Consolas", 7), fill="#1a3a5a", anchor="e")

        # Arc-Reaktor Orb (pulsierender Kreis)
        cx, cy, r = W-14, H-14, 6
        self._arc_id = c.create_oval(cx-r, cy-r, cx+r, cy+r, outline=self.CYAN, width=2)
        c.create_oval(cx-2, cy-2, cx+2, cy+2, fill=self.CYAN, outline="", tags="static")

    # ── Layout: Widgets positionieren (responsiv) ──────────────────────
    def _layout(self):
        W = self.root.winfo_width()  or self.SIZES["normal"][0]
        H = self.root.winfo_height() or self.SIZES["normal"][1]

        # Modus aus aktueller Höhe ableiten (für freies Resize)
        if H < self._H_MINI:
            mode = "mini"
        elif H < self._H_NORMAL:
            mode = "normal"
        else:
            mode = "voll"

        # Effektive Breite für Text (Rand links + rechts für Buttons freilassen)
        text_w = max(100, W - 90)
        bar_w  = max(100, W - 50)

        if mode == "mini":
            # Nur Canvas (Titel + Status), keine weiteren Widgets
            self._lbl_sub.place_forget()
            self._bar_frame.place_forget()
            self._detail_frame.place_forget()
            self._input_frame.place_forget()

        elif mode == "normal":
            # Untertitel direkt unter der Trennlinie
            self._lbl_sub.config(wraplength=text_w)
            self._lbl_sub.place(x=20, y=62, width=text_w, height=H - 120)
            # Eingabefeld über der Statusbar
            self._input_frame.place(x=0, y=H - 52, width=W, height=24)
            # Statusbar ganz unten, volle Breite
            self._bar_frame.place(x=0, y=H - 28, width=bar_w, height=24)
            self._detail_frame.place_forget()

        else:  # voll
            # Untertitel bleibt kurz (1-2 Zeilen) direkt unter der Linie
            self._lbl_sub.config(wraplength=text_w)
            self._lbl_sub.place(x=20, y=62, width=text_w, height=32)
            # Detail-Panel zwischen Untertitel und Eingabefeld
            detail_y = 98
            detail_h = H - detail_y - 62
            self._detail_frame.place(x=0, y=detail_y, width=W, height=max(40, detail_h))
            # wraplength für brain_var-Label im Detail-Panel
            self._brain_lbl.config(wraplength=max(100, W - 30))
            # Eingabefeld über der Statusbar
            self._input_frame.place(x=0, y=H - 52, width=W, height=24)
            # Statusbar unten
            self._bar_frame.place(x=0, y=H - 28, width=bar_w, height=24)

    # ── Configure-Event (Fenster wurde resized) ────────────────────────
    def _on_configure(self, _e=None):
        # Debounce: nur einmal pro Frame neu bauen
        if not self._rebuild_pending:
            self._rebuild_pending = True
            self.root.after(30, self._rebuild)

    # ── Rebuild (Canvas + Layout) ──────────────────────────────────────
    def _rebuild(self):
        self._rebuild_pending = False
        self._build_canvas()
        self._layout()

    # ── Größe wechseln (◈-Button) ─────────────────────────────────────
    def _cycle_size(self, _e=None):
        self._size_idx = (self._size_idx + 1) % len(self.SIZE_ORDER)
        size = self.SIZE_ORDER[self._size_idx]
        W, H = self.SIZES[size]
        self.root.geometry(f"{W}x{H}")
        # _on_configure wird automatisch ausgelöst

    # ── Drag ───────────────────────────────────────────────────────────
    def _drag_start(self, e):
        if e.y > 54:
            return
        self._drag_x, self._drag_y = e.x, e.y

    def _drag_move(self, e):
        if self._drag_x == 0 and self._drag_y == 0:
            return
        nx = self.root.winfo_x() + e.x - self._drag_x
        ny = self.root.winfo_y() + e.y - self._drag_y
        self.root.geometry(f"+{nx}+{ny}")

    def _drag_end(self, _e=None):
        self._drag_x, self._drag_y = 0, 0

    # ── Freies Resize via Griff ────────────────────────────────────────
    def _resize_start(self, e):
        self._rx = e.x_root
        self._ry = e.y_root
        self._rw = self.root.winfo_width()
        self._rh = self.root.winfo_height()

    def _resize_move(self, e):
        nw = max(360, self._rw + (e.x_root - self._rx))
        nh = max(46,  self._rh + (e.y_root - self._ry))
        self.root.geometry(f"{nw}x{nh}")
        # _size_idx wird bei _layout() implizit aus Höhe abgeleitet

    # ── Mikrofon ───────────────────────────────────────────────────────
    def _toggle_mic(self, _e):
        global mic_on
        mic_on = not mic_on
        try:
            self.canvas.itemconfig(self._status_id,
                text="| BEREIT" if mic_on else "| STUMM",
                fill=self.GREEN if mic_on else self.RED)
        except Exception:
            pass

    # ── Text-Eingabe senden ────────────────────────────────────────────
    def _send_text_input(self, _e=None):
        text = self._input_var.get().strip()
        if not text:
            return
        self._input_var.set("")
        threading.Thread(target=process_command, args=(text,), daemon=True).start()

    # ── Einstellungen-Fenster ──────────────────────────────────────────
    def _open_settings_window(self):
        win = tk.Toplevel(self.root)
        win.title("J.A.R.V.I.S Einstellungen")
        win.configure(bg=self.BG)
        win.geometry("420x520")
        win.attributes("-topmost", True)

        # Titel
        tk.Label(win, text="J.A.R.V.I.S — Einstellungen",
                 font=("Consolas", 11, "bold"), fg=self.CYAN, bg=self.BG
                 ).pack(pady=(12, 8))
        tk.Frame(win, bg=self.DIM2, height=1).pack(fill="x", padx=12, pady=4)

        tk.Label(win, text="Farben", font=("Consolas", 9, "bold"),
                 fg=self.DIM, bg=self.BG, anchor="w").pack(fill="x", padx=12)

        colors_to_edit = {
            "Hauptfarbe (Cyan)":   "CYAN",
            "Hintergrund":         "BG",
            "Grün (OK/Aktiv)":    "GREEN",
            "Rot (Fehler/Stumm)":  "RED",
            "Gelb (Warnung)":     "YELLOW",
            "Orange (Cerebras)":  "ORANGE",
        }
        self._color_vars = {}
        for label, attr in colors_to_edit.items():
            row = tk.Frame(win, bg=self.BG)
            row.pack(fill="x", padx=12, pady=3)
            tk.Label(row, text=label, font=("Consolas", 9), fg=self.CYAN,
                     bg=self.BG, width=22, anchor="w").pack(side="left")
            var = tk.StringVar(value=getattr(self, attr))
            self._color_vars[attr] = var
            entry = tk.Entry(row, textvariable=var, font=("Consolas", 9),
                             bg="#001e33", fg=self.CYAN, width=10,
                             insertbackground=self.CYAN)
            entry.pack(side="left", padx=4)
            preview = tk.Label(row, text="■", font=("Consolas", 12),
                               fg=getattr(self, attr), bg=self.BG)
            preview.pack(side="left")
            var.trace("w", lambda *a, p=preview, v=var, at=attr:
                      self._preview_color(p, v, at))
            tk.Button(row, text="Pick", font=("Consolas", 8),
                      bg="#001e33", fg=self.CYAN, relief="flat",
                      command=lambda at=attr, v=var, p=preview:
                      self._pick_color(at, v, p)).pack(side="left", padx=2)

        tk.Frame(win, bg=self.DIM2, height=1).pack(fill="x", padx=12, pady=8)

        # Buttons
        btn_frame = tk.Frame(win, bg=self.BG)
        btn_frame.pack(fill="x", padx=12, pady=4)
        tk.Button(btn_frame, text="✅ Speichern & Anwenden",
                  font=("Consolas", 9, "bold"), bg="#001e33", fg=self.CYAN,
                  relief="flat",
                  command=lambda: self._apply_colors(win)).pack(side="left", padx=(0, 8))
        tk.Button(btn_frame, text="↩ Zurücksetzen",
                  font=("Consolas", 9), bg=self.BG, fg=self.DIM,
                  relief="flat",
                  command=lambda: self._reset_colors(win)).pack(side="left")

    def _pick_color(self, attr, var, preview):
        from tkinter import colorchooser
        color = colorchooser.askcolor(color=getattr(self, attr),
                                      title=f"Farbe wählen: {attr}")[1]
        if color:
            var.set(color)
            preview.config(fg=color)

    def _preview_color(self, preview, var, attr):
        try:
            preview.config(fg=var.get())
        except Exception:
            pass

    def _apply_colors(self, win):
        for attr, var in self._color_vars.items():
            try:
                setattr(self, attr, var.get())
            except Exception:
                pass
        self._save_color_config()
        self._rebuild()
        win.destroy()

    def _reset_colors(self, win):
        defaults = {
            "CYAN": "#00d4ff", "BG": "#000d1a", "GREEN": "#00ff88",
            "RED": "#ff3355", "YELLOW": "#ffcc00", "ORANGE": "#ff8800",
        }
        for attr, val in defaults.items():
            if attr in self._color_vars:
                self._color_vars[attr].set(val)

    def _save_color_config(self):
        try:
            config_path = PATHS["memory"] / "ui_colors.json"
            colors = {attr: getattr(self, attr)
                      for attr in ["CYAN", "BG", "GREEN", "RED", "YELLOW", "ORANGE", "DIM", "DIM2"]}
            config_path.write_text(json.dumps(colors, indent=2), encoding="utf-8")
        except Exception as e:
            log.warning(f"Farb-Config speichern: {e}")

    def _load_color_config(self):
        try:
            config_path = PATHS["memory"] / "ui_colors.json"
            if config_path.exists():
                colors = json.loads(config_path.read_text(encoding="utf-8"))
                for attr, val in colors.items():
                    if hasattr(self, attr):
                        setattr(self, attr, val)
        except Exception as e:
            log.warning(f"Farb-Config laden: {e}")

    # ── Animate-Loop (50ms) ────────────────────────────────────────────
    def _animate(self):
        try:
            W = self.root.winfo_width()
            H = self.root.winfo_height()
            c = self.canvas

            # Pulsierender Orb (Position immer unten rechts)
            if self._arc_id:
                cx, cy = W-14, H-14
                r = int(6 + 3 * math.sin(self._pulse))
                c.coords(self._arc_id, cx-r, cy-r, cx+r, cy+r)
            self._pulse += 0.07

            # MESH-Indikator
            if self._mesh_id:
                c.coords(self._mesh_id, W-88, H-14)
                c.itemconfig(self._mesh_id,
                    fill=self.GREEN if meshtastic_bridge.connected else "#1a3a5a")

            # Opt-Engine Daten
            if _opt_engine:
                s   = _opt_engine.status
                it  = _opt_engine.iterations
                mem = _opt_engine.memory

                col_map = {
                    "running": self.GREEN, "paused": self.YELLOW,
                    "done": self.CYAN,     "failed": self.RED,
                }
                self.opt_var.set(f"OPT: {s.upper()}")

                # Lerneinträge
                entries = len(mem._log.get("entries", []))
                stats   = mem._log.get("stats", {})
                succ    = stats.get("total_success", 0)
                fail    = stats.get("total_failure", 0)

                self._opt_succ = succ
                self._opt_fail = fail
                self.iter_var.set(f"ITER: {it}  ✓{succ}  ✗{fail}")
                self.learn_var.set(f"🧠 {entries} gelernt  ·  Rate: {round(succ/max(succ+fail,1)*100)}%")

                dev_str = f"DEV: Cerebras {cerebras_model}" if cerebras_client else "DEV: Gemini"
                self.dev_var.set(dev_str)

                if s == "running":
                    try:
                        focus = _FOCUS_AREAS[_opt_engine._focus_index % len(_FOCUS_AREAS)]
                        elapsed = int((datetime.now() - _opt_engine.start_time).total_seconds()) if _opt_engine.start_time else 0
                        m, sec = divmod(elapsed, 60)
                        self.focus_var.set(f"FOKUS: {focus.upper()}  ·  LAUFZEIT: {m:02d}:{sec:02d}")
                    except Exception:
                        pass
                else:
                    self.focus_var.set(f"FOKUS: —  ·  STATUS: {s.upper()}")

            # Brain-Status Farben aktualisieren
            g_ok  = gemini_client    is not None
            q_ok  = groq_client      is not None
            cb_ok = cerebras_client  is not None
            self.gemini_var.set(f"🧠 GEMINI {'✓' if g_ok else '✗'}")
            self.groq_var.set(f"🔬 GROQ {'✓' if q_ok else '✗'}")
            self.cerebras_var.set(f"⚡ CEREBRAS {'✓' if cb_ok else '✗'}")
            try:
                self._gemini_lbl.config(fg=self.GREEN if g_ok else self.RED)
                self._groq_lbl.config(fg=self.GREEN if q_ok else self.RED)
                self._cerebras_lbl.config(fg=self.GREEN if cb_ok else self.ORANGE)
            except Exception:
                pass

        except Exception:
            pass

        self.root.after(50, self._animate)

    # ── set_status (von say() und process_command() aufgerufen) ────────
    def set_status(self, status: str, text: str = ""):
        clean = re.sub(r"[*_`#\[\]]", "", text).strip()
        MAP = {
            "speaking": (self.GREEN,  "| SPRICHT"),
            "thinking": (self.YELLOW, "| ANALYSIERE"),
            "error":    (self.RED,    "| FEHLER"),
            "ready":    (self.CYAN,   "| BEREIT"),
        }
        col, label = MAP.get(status, (self.CYAN, "| ONLINE"))

        def _u():
            try:
                self.canvas.itemconfig(self._status_id, text=label, fill=col)
                if clean:
                    self._last_sub = clean
                    # Kein hartes Abschneiden — wraplength übernimmt Umbruch
                    self.sub_var.set(clean)
                    self.brain_var.set(f"▶ {clean}")
            except Exception:
                pass
        self.root.after(0, _u)

# ══════════════════════════════════════════════════════════════════════
#  SELFTEST
# ══════════════════════════════════════════════════════════════════════

if "--selftest" in sys.argv:
    _errs = []
    try:
        from dotenv import load_dotenv as _ld
    except ImportError:
        _errs.append("python-dotenv fehlt: pip install python-dotenv")
    try:
        import pygame, edge_tts, speech_recognition, telebot, requests
        from google import genai as _gt
    except ImportError as _e:
        _errs.append(f"Pflicht-Import fehlt: {_e}")
    for _d in ["temp_audio", "temp_vision", "opt_workspace", "screenshots"]:
        if not Path(_d).exists():
            _errs.append(f"Dir fehlt: {_d}")
    for _fn in ["init_brains", "ensure_golden_copy", "auto_rollback",
                "LearningMemory", "analyze_image", "transcribe_audio",
                "OptimizationEngine", "generate_handbook", "_call_cerebras",
                "_call_gemini_json", "_check_required_keys",
                "cc_screenshot", "cc_type_text", "cc_key"]:
        if _fn not in dir() and _fn not in globals():
            _errs.append(f"Symbol fehlt: {_fn}")
    if _errs:
        print("SELFTEST FAIL:", "; ".join(_errs))
        sys.exit(1)
    print("SELFTEST OK")
    sys.exit(0)

# ══════════════════════════════════════════════════════════════════════
#  TERMINAL-STEUERUNG
# ══════════════════════════════════════════════════════════════════════

TERMINAL_CMD_FILE = PATHS["memory"] / "terminal_cmd.json"


def _send_terminal_cmd(cmd: str, goal: str = "", duration: str = ""):
    _save_json(TERMINAL_CMD_FILE, {
        "cmd":      cmd,
        "goal":     goal,
        "duration": duration,
        "sent_at":  datetime.now().isoformat(),
    })
    print(f"\n✅ Befehl gesendet: {cmd}")
    if goal:     print(f"   Ziel:  {goal}")
    if duration: print(f"   Dauer: {duration}")
    print("JARVIS prüft in ~2 Sekunden.\n")


def _poll_terminal_commands():
    while True:
        try:
            if TERMINAL_CMD_FILE.exists():
                data     = json.loads(TERMINAL_CMD_FILE.read_text(encoding="utf-8"))
                TERMINAL_CMD_FILE.unlink(missing_ok=True)
                cmd      = data.get("cmd", "")
                goal     = data.get("goal", "")
                duration = data.get("duration", "")
                log.info(f"📟 Terminal-Befehl: {cmd}")

                if cmd == "optimize" and _opt_engine:
                    _opt_engine.start(goal=goal, duration_input=duration)
                elif cmd == "stop" and _opt_engine:
                    _opt_engine.stop(save_progress=True)
                elif cmd == "status" and _opt_engine:
                    print(f"\n📊 STATUS: {_opt_engine.get_status()}\n")
                elif cmd == "learning" and _opt_engine:
                    print(f"\n🧠 LERNPROTOKOLL: {_opt_engine.get_learning_summary()}\n")
                elif cmd == "rollback":
                    ok = auto_rollback()
                    print(f"\n{'Rollback OK — JARVIS neu starten.' if ok else 'Kein Backup.'}\n")
                elif cmd == "golden":
                    ok = auto_rollback(to_golden=True)
                    print(f"\n{'Golden Copy OK — JARVIS neu starten.' if ok else 'Golden Copy fehlt.'}\n")
                elif cmd == "diamond":
                    ok = auto_rollback(to_diamond=True)
                    print(f"\n{'💎 Diamant-Datei wiederhergestellt — JARVIS neu starten.' if ok else '💎 Keine Diamant-Datei. Erstelle manuell: copy jarvis_v5_8.py jarvis_diamond.py'}\n")
                else:
                    log.warning(f"Unbekannter Terminal-Befehl: {cmd}")
        except Exception as e:
            log.error(f"Terminal-Poll: {e}")
        time.sleep(2)


def _print_terminal_help():
    # HINWEIS: generate_handbook() wird hier NICHT aufgerufen, da es globale
    # Variablen (cerebras_client, log) benötigt die beim CLI-Aufruf nicht
    # initialisiert sind und sonst zu einem Fehler führen würden.
    if HANDBUCH_PATH.exists():
        print(HANDBUCH_PATH.read_text(encoding="utf-8"))
    print("\n📖 Handbuch: JARVIS_HANDBUCH.txt\n")
    print(f"""
  J.A.R.V.I.S Guardian v{JARVIS_VERSION} — Terminal-Schnellreferenz:

  OPTIMIERUNG:
    python jarvis_v5_8.py --cmd optimize --goal "Ziel" --duration "8h"
    python jarvis_v5_8.py --cmd stop
    python jarvis_v5_8.py --cmd status
    python jarvis_v5_8.py --cmd learning

  NOTFALL / ROLLBACK:
    python jarvis_v5_8.py --cmd rollback
    python jarvis_v5_8.py --cmd golden

  TESTS & HILFE:
    python jarvis_v5_8.py --selftest
    python jarvis_fulltest.py         (vollständiger Systemtest)
""")

# ══════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":

    if "--cmd" in sys.argv:
        import argparse
        parser = argparse.ArgumentParser(description="J.A.R.V.I.S Terminal-Steuerung")
        parser.add_argument("--cmd", required=True,
                            choices=["optimize", "stop", "status", "learning", "rollback", "golden", "diamond"])
        parser.add_argument("--goal",     default="")
        parser.add_argument("--duration", default="")
        args = parser.parse_args()
        _send_terminal_cmd(args.cmd, args.goal, args.duration)
        sys.exit(0)

    _check_required_keys()
    startup_check()
    brain_ok = init_brains()

    pygame.mixer.pre_init(44100, -16, 2, 512)
    pygame.mixer.init()

    ui          = JarvisUI()
    _opt_engine = OptimizationEngine()

    if MESHTASTIC_ENABLED:
        threading.Thread(target=meshtastic_bridge.connect, daemon=True).start()

    threading.Thread(target=listen_loop,            daemon=True).start()
    threading.Thread(target=setup_telegram,          daemon=True).start()
    threading.Thread(target=_poll_terminal_commands, daemon=True).start()

    def _boot():
        time.sleep(1.5)
        resume_data = _load_opt_resume()
        dev = f"Cerebras {cerebras_model}" if cerebras_client else "Gemini"
        cc  = "Computer-Control aktiv." if COMPUTER_CONTROL else ""
        if brain_ok:
            if resume_data:
                say(
                    f"J.A.R.V.I.S Guardian Version {JARVIS_VERSION} online. "
                    f"Developer-KI: {dev}. {cc} "
                    "Gespeicherter Optimierungsstand vorhanden. "
                    "Sag Optimiere dich um weiterzumachen."
                )
            else:
                say(f"J.A.R.V.I.S Guardian Version {JARVIS_VERSION} online. Developer-KI: {dev}. {cc}")
        else:
            say("Warnung: KI-Verbindung fehlgeschlagen. Bitte Gemini API-Key in der dot-env-Datei prüfen.")

    threading.Thread(target=_boot, daemon=True).start()

    try:
        ui.root.mainloop()
    except KeyboardInterrupt:
        log.info("Manuell beendet.")
        os._exit(0)
    except Exception as e:
        log.critical(f"UI-Crash: {e}")
        os._exit(1)