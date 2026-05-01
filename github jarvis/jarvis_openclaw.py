"""
╔══════════════════════════════════════════════════════════════════════╗
║   J.A.R.V.I.S — OPENCLAW MODULE                                    ║
║   Autonomes Ordner-Management mit KI-Smart-Router                  ║
║   Wird von jarvis_v5_8.py importiert                                ║
╚══════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations
import json
import logging
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional

log = logging.getLogger("JARVIS")

# ── Diese werden von jarvis_v5_8.py nach dem Import gesetzt ──────────
BrainStatus            = None
OPENCLAW_MANAGED_DIR   = "."
OPENCLAW_TRASH_DIR     = "Müll"
OPENCLAW_KEEP_EXTENSIONS = {".py", ".json", ".txt", ".md", ".env", ".log", ".sha256"}
OPENCLAW_CONFIRM_DESTRUCTIVE = True
OPENCLAW_AUTO_CLEANUP  = False
PATHS                  = {}
gemini_client          = None
groq_client            = None
cerebras_client        = None

# Wird aus jarvis_brains importiert (nach dem Setzen der globals)
_call_gemini_json      = None
_call_cerebras         = None
_load_json             = None
_save_json             = None

# Dateien die NIEMALS verschoben werden
_KEEP_FILES = {
    "jarvis_v5_8.py", "_env", ".env", "JARVIS_HANDBUCH.txt",
    "jarvis_brains.py", "jarvis_openclaw.py", "jarvis_optimizer.py",
    "jarvis_claw.py",
}


# ──────────────────────────────────────────────────────────────────────

class OpenClawManager:
    """
    Autonomes Ordner-Management für den JARVIS-Ordner.
    KI entscheidet per Smart-Router welche Dateien behalten/archiviert werden.
    """

    def __init__(self):
        self.managed_dir       = Path(OPENCLAW_MANAGED_DIR)
        self.trash_dir         = Path(OPENCLAW_TRASH_DIR)
        self._history_file     = None   # wird nach PATHS-Init gesetzt
        self._pending_actions: List[dict] = []

    def _history_path(self) -> Path:
        if PATHS and "memory" in PATHS:
            return PATHS["memory"] / "openclaw_history.json"
        return Path("openclaw_history.json")

    def scan_folder(self) -> dict:
        """Scannt den verwalteten Ordner und klassifiziert per KI."""
        # Ordner aktualisieren (falls _env sich geändert hat)
        self.managed_dir = Path(OPENCLAW_MANAGED_DIR)
        self.trash_dir   = Path(OPENCLAW_TRASH_DIR)

        if not self.managed_dir.exists():
            return {"error": f"Ordner '{self.managed_dir}' existiert nicht.\n"
                             f"Tipp: Setze OPENCLAW_MANAGED_DIR=. in deiner _env"}

        BrainStatus.set("openclaw", "working", f"Scanne '{self.managed_dir}'...")
        all_files = []
        for f in self.managed_dir.rglob("*"):
            if f.is_file():
                try:
                    all_files.append({
                        "path":     str(f.relative_to(self.managed_dir)),
                        "name":     f.name,
                        "ext":      f.suffix.lower(),
                        "size_kb":  round(f.stat().st_size / 1024, 1),
                        "modified": datetime.fromtimestamp(
                            f.stat().st_mtime).strftime("%Y-%m-%d"),
                    })
                except Exception:
                    pass

        if not all_files:
            BrainStatus.set("openclaw", "done", "Ordner leer")
            return {"files": [], "summary": "Ordner ist leer",
                    "total": 0, "keep": 0, "trash": 0}

        log.info(f"🦅 OpenClaw: {len(all_files)} Dateien in '{self.managed_dir}'")
        BrainStatus.set("openclaw", "working", "KI analysiert...")
        analysis = self._ai_classify_files(all_files)
        BrainStatus.set("openclaw", "done", f"{len(all_files)} analysiert")

        return {
            "files":    all_files,
            "analysis": analysis,
            "total":    len(all_files),
            "keep":     len([x for x in analysis if x.get("action") == "keep"]),
            "trash":    len([x for x in analysis if x.get("action") == "trash"]),
        }

    def _ai_classify_files(self, files: List[dict]) -> List[dict]:
        """KI-Klassifizierung per Smart-Router (Gemini→Groq→Cerebras)."""
        quick = []
        needs_ai = []

        for f in files:
            name = f["name"].lower()
            ext  = f["ext"]
            # Pflichtdateien immer behalten
            if f["name"] in _KEEP_FILES or name in {k.lower() for k in _KEEP_FILES}:
                quick.append({"name": f["name"], "action": "keep",
                               "reason": "Pflichtdatei"})
                continue
            # Wichtige Endungen: immer behalten
            if ext in {".py", ".json", ".env", ".md", ".sha256", ".txt"}:
                quick.append({"name": f["name"], "action": "keep",
                               "reason": f"Wichtige Endung {ext}"})
                continue
            # Eindeutige Trash-Endungen
            if ext in {".tmp", ".bak", ".pyc", ".pyo", ".cache"} \
               or name.startswith("temp_") or name.startswith("dr_"):
                quick.append({"name": f["name"], "action": "trash",
                               "reason": f"Temp-Datei {ext}"})
                continue
            needs_ai.append(f)

        if not needs_ai:
            return quick

        file_list = "\n".join(
            f"  - {f['name']} ({f['ext']}, {f['size_kb']}KB, {f['modified']})"
            for f in needs_ai[:80]
        )
        prompt = (
            f"Du verwaltest den JARVIS-Ordner. Entscheide für jede Datei:\n"
            f"'keep' = wichtig | 'trash' = ins Archiv\n\n"
            f"Behalte: Skripte, Konfigs, Backups, Logs, Handbücher\n"
            f"Archiviere: Duplikate, alte Outputs, Binaries, leere Dateien\n\n"
            f"DATEIEN:\n{file_list}\n\n"
            f'Antworte NUR als JSON-Array: '
            f'[{{"name":"datei","action":"keep","reason":"Grund"}},...]'
        )
        system = "Du bist ein Datei-Verwaltungs-Experte. Antworte NUR mit JSON."
        ai_results = None

        # Versuch 1: Gemini
        if gemini_client and _call_gemini_json:
            try:
                ai_results = _call_gemini_json(prompt, system)
                if isinstance(ai_results, list) and ai_results:
                    log.info(f"🦅 OpenClaw (Gemini): {len(ai_results)} Entscheidungen")
            except Exception as e:
                log.warning(f"OpenClaw Gemini: {e}")
                ai_results = None

        # Versuch 2: Groq
        if not ai_results and groq_client:
            try:
                r = groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "system", "content": system},
                               {"role": "user",   "content": prompt}],
                    max_tokens=2000,
                )
                raw = r.choices[0].message.content
                raw = re.sub(r"^```json\s*", "", raw.strip(), flags=re.MULTILINE)
                raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE)
                ai_results = json.loads(raw)
                if isinstance(ai_results, list) and ai_results:
                    log.info(f"🦅 OpenClaw (Groq): {len(ai_results)} Entscheidungen")
            except Exception as e:
                log.warning(f"OpenClaw Groq: {e}")
                ai_results = None

        # Versuch 3: Cerebras
        if not ai_results and cerebras_client and _call_cerebras:
            try:
                raw = _call_cerebras(prompt, system, max_tokens=2000)
                raw = re.sub(r"^```json\s*", "", raw.strip(), flags=re.MULTILINE)
                raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE)
                s = raw.find('['); e = raw.rfind(']')
                if s != -1 and e != -1:
                    ai_results = json.loads(raw[s:e+1])
                    log.info(f"🦅 OpenClaw (Cerebras): {len(ai_results)} Entscheidungen")
            except Exception as e:
                log.warning(f"OpenClaw Cerebras: {e}")
                ai_results = None

        # Fallback: nach Endung entscheiden
        if not ai_results:
            log.warning("🦅 OpenClaw: Kein Brain — Endungs-Fallback")
            ai_results = [
                {"name": f["name"],
                 "action": "keep" if f["ext"] in OPENCLAW_KEEP_EXTENSIONS else "trash",
                 "reason": f"Endung {f['ext']}"}
                for f in needs_ai
            ]

        if isinstance(ai_results, dict):
            for v in ai_results.values():
                if isinstance(v, list):
                    ai_results = v
                    break

        return quick + (ai_results if isinstance(ai_results, list) else [])

    def execute_cleanup(self, analysis: List[dict], dry_run: bool = False,
                        confirm_callback=None) -> dict:
        if not analysis:
            return {"moved": 0, "kept": 0, "errors": []}
        to_trash = [a for a in analysis if a.get("action") == "trash"]
        to_keep  = [a for a in analysis if a.get("action") == "keep"]

        if dry_run:
            return {"dry_run": True,
                    "to_trash": [a["name"] for a in to_trash],
                    "to_keep":  [a["name"] for a in to_keep],
                    "moved": 0, "kept": len(to_keep)}

        if OPENCLAW_CONFIRM_DESTRUCTIVE and to_trash and confirm_callback:
            names = ", ".join(a["name"] for a in to_trash[:10])
            if len(to_trash) > 10:
                names += f" ... und {len(to_trash)-10} weitere"
            confirm_callback(
                f"🦅 OpenClaw: {len(to_trash)} Dateien verschieben?\n"
                f"{names}\n\nSende /confirm_cleanup zum Bestätigen."
            )
            self._pending_actions = to_trash
            return {"pending": True, "count": len(to_trash)}

        return self._do_move_to_trash(to_trash)

    def confirm_cleanup(self) -> dict:
        if not self._pending_actions:
            return {"error": "Keine ausstehenden Aktionen"}
        result = self._do_move_to_trash(self._pending_actions)
        self._pending_actions = []
        return result

    def _do_move_to_trash(self, to_trash: List[dict]) -> dict:
        moved  = 0
        errors = []
        ts     = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.trash_dir.mkdir(parents=True, exist_ok=True)
        trash_session = self.trash_dir / f"cleanup_{ts}"
        trash_session.mkdir(parents=True, exist_ok=True)
        BrainStatus.set("openclaw", "working", f"Verschiebe {len(to_trash)} ...")

        for item in to_trash:
            name = item.get("name", "")
            src  = self.managed_dir / name
            if not src.exists():
                continue
            dest = trash_session / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                dest = trash_session / f"{src.stem}_{ts}{src.suffix}"
            try:
                shutil.move(str(src), str(dest))
                log.info(f"🗑️  '{name}' → cleanup_{ts}/")
                moved += 1
            except Exception as e:
                errors.append(f"{name}: {e}")
                log.error(f"OpenClaw Move: {name} → {e}")

        self._save_history(to_trash, trash_session, moved)
        BrainStatus.set("openclaw", "done", f"{moved} verschoben")
        return {"moved": moved, "trash_dir": str(trash_session), "errors": errors}

    def restore_from_trash(self, filename: str) -> bool:
        if not self.trash_dir.exists():
            return False
        for session in sorted(self.trash_dir.iterdir(), reverse=True):
            if session.is_dir():
                for f in session.rglob(filename):
                    try:
                        shutil.move(str(f), str(self.managed_dir / f.name))
                        log.info(f"♻️  '{filename}' wiederhergestellt")
                        return True
                    except Exception as e:
                        log.error(f"Restore: {e}")
                        return False
        return False

    def get_folder_status(self) -> str:
        self.managed_dir = Path(OPENCLAW_MANAGED_DIR)
        self.trash_dir   = Path(OPENCLAW_TRASH_DIR)
        if not self.managed_dir.exists():
            return f"Ordner '{self.managed_dir}' nicht gefunden"
        files      = [f for f in self.managed_dir.rglob("*") if f.is_file()]
        total_size = sum(f.stat().st_size for f in files) / (1024 * 1024)
        trash_n    = sum(1 for f in self.trash_dir.rglob("*")
                         if f.is_file()) if self.trash_dir.exists() else 0
        return (f"📁 '{self.managed_dir}': {len(files)} Dateien "
                f"({total_size:.1f} MB)\n"
                f"🗑️  '{self.trash_dir}': {trash_n} Dateien im Archiv\n"
                f"🔧 Auto-Cleanup: {'AN' if OPENCLAW_AUTO_CLEANUP else 'AUS'}")

    def _save_history(self, moved: List[dict], trash_session: Path, count: int):
        if not _load_json or not _save_json:
            return
        hp = self._history_path()
        history = _load_json(hp, {"sessions": []})
        history["sessions"].append({
            "timestamp":   datetime.now().isoformat(),
            "session_dir": str(trash_session),
            "moved_count": count,
            "files":       [a.get("name") for a in moved],
        })
        if len(history["sessions"]) > 50:
            history["sessions"] = history["sessions"][-50:]
        _save_json(hp, history)