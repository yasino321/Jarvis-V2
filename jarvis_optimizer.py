"""
╔══════════════════════════════════════════════════════════════════════╗
║   J.A.R.V.I.S — OPTIMIZER MODULE v2.0                              ║
║   Diff-basiertes Patch-System | Multi-Brain Konsens                ║
║   Cerebras schreibt PATCHES, nicht kompletten Code neu             ║
║   Wird von jarvis_v5_8.py importiert                               ║
╚══════════════════════════════════════════════════════════════════════╝

KERN-PHILOSOPHIE v2.0:
  - Cerebras erhält EINE Funktion → liefert NUR den geänderten Body
  - Gemini plant KONKRETE Patches (welche Funktion, was genau)
  - Groq prüft den Patch BEVOR er angewendet wird
  - Fehler werden chirurgisch gefixt, nicht der Code neu geschrieben
  - GodMode: alle 3 Brains einigen sich auf den besten Patch
"""

from __future__ import annotations
import ast
import json
import logging
import re
import shutil
import subprocess
import sys
import textwrap
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

log = logging.getLogger("JARVIS")

# ── Diese werden von jarvis_v5_8.py nach dem Import gesetzt ──────────
SELF_PATH        = None
PATHS            = {}
BrainStatus      = None
SYSTEM_PROMPT    = ""
MAX_LINES        = 2500
_OPT_MAX_DRY_RUN = 2
_OPT_MAX_CODE_ATT = 4
_OPT_ITER_PAUSE  = 10

# Brain-Funktionen (aus jarvis_brains)
_call_gemini_raw          = None
_call_gemini_json         = None
_call_gemini_with_backoff = None
_call_cerebras            = None
_call_groq_critic         = None
_strip_code_fences        = None
_is_rate_limit            = None
_godmode_konsens          = None
_godmode_query_parallel   = None

# Clients
gemini_client    = None
gemini_model     = None
groq_client      = None
cerebras_client  = None
cerebras_model   = None

# JSON helpers
_save_json       = None
_load_json       = None

# Backup helpers
_create_deployment_backup = None
_cleanup_old_backups      = None
_archive_dead_code        = None
_say                      = None

# Resume file
OPT_RESUME_FILE  = None

# ──────────────────────────────────────────────────────────────────────
#  GLOBALER RATE-LIMIT GUARD
# ──────────────────────────────────────────────────────────────────────

_global_rate_limit_until: float = 0.0
_rate_limit_lock = threading.Lock()


def _set_global_rate_limit_pause(err_msg: str):
    global _global_rate_limit_until
    wait = 60
    m = re.search(r"retry.?after[:\s]+(\d+)", err_msg, re.IGNORECASE)
    if m:
        wait = int(m.group(1))
    elif "429" in err_msg:
        wait = 90
    with _rate_limit_lock:
        _global_rate_limit_until = time.time() + wait
    log.warning(f"⏳ Rate-Limit Guard: {wait}s Pause")


def _wait_for_rate_limit(stop_event: threading.Event = None):
    with _rate_limit_lock:
        until = _global_rate_limit_until
    remaining = until - time.time()
    if remaining <= 0:
        return
    log.info(f"⏳ Rate-Limit Guard aktiv — warte {remaining:.0f}s ...")
    while remaining > 0:
        if stop_event and stop_event.is_set():
            return
        time.sleep(min(2.0, remaining))
        remaining = until - time.time()


# ──────────────────────────────────────────────────────────────────────
#  CONSTANTS
# ──────────────────────────────────────────────────────────────────────

_FOCUS_AREAS = [
    "error_handling",
    "ai_routing",
    "listen_loop",
    "telegram_handlers",
    "optimization_engine",
    "computer_control",
    "vision_analysis",
    "audio_processing",
    "openclaw_management",
]

_PLANNER_SYSTEM = """Du bist Gemini, der strategische Planer im JARVIS Multi-Brain System.
Deine Aufgabe: Identifiziere EINE konkrete, kleine Verbesserung in EINER Funktion.

WICHTIGE REGELN:
- Nenne die EXAKTE Funktion (z.B. "def _call_cerebras" oder "class OptimizationEngine")
- Beschreibe NUR kleine, isolierte Änderungen (max. 20 Zeilen)
- KEINE neuen Imports ohne Prüfung
- Antworte AUSSCHLIESSLICH mit gültigem JSON"""

_CODER_SYSTEM = """Du bist Cerebras, der Hochgeschwindigkeits-Patcher im JARVIS System.
Du erhältst EINE Python-Funktion und einen Verbesserungsplan.

ABSOLUT KRITISCHE REGELN:
1. Gib NUR den neuen Funktions-Body zurück — KEINE Backticks, KEIN Markdown
2. Behalte die EXAKTE Signatur (def-Zeile unverändert)
3. KEINE anderen Funktionen verändern
4. Syntaktisch korrekt Python
5. Minimale, gezielte Änderung"""

_CRITIC_SYSTEM = """Du bist Groq, der kritische Sicherheitsprüfer im JARVIS System.
Prüfe ob der neue Funktions-Code sicher und korrekt ist.
Sei STRENG: besser kein Patch als ein fehlerhafter."""

_FIX_SYSTEM = """Du bist Cerebras im Repair-Modus.
Du erhältst Python-Code mit einem konkreten Fehler.
Behebe NUR diesen einen Fehler. Ändere nichts anderes.
Gib NUR Python zurück. KEINE Backticks. KEIN Markdown."""


# ──────────────────────────────────────────────────────────────────────
#  CODE-ANALYSE WERKZEUGE
# ──────────────────────────────────────────────────────────────────────

class CodeAnalyzer:
    """Extrahiert und manipuliert Funktionen/Klassen per AST."""

    @staticmethod
    def get_all_functions(source: str) -> Dict[str, dict]:
        """Gibt alle top-level und class-Funktionen zurück: {name: {lines, source, indent}}"""
        functions = {}
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return {}

        lines = source.splitlines()

        def extract_node(node, class_prefix=""):
            if not hasattr(node, 'lineno'):
                return
            start = node.lineno - 1
            end   = getattr(node, 'end_lineno', start + 1)
            name  = f"{class_prefix}{node.name}" if hasattr(node, 'name') else ""
            if not name:
                return
            func_lines = lines[start:end]
            indent = len(func_lines[0]) - len(func_lines[0].lstrip()) if func_lines else 0
            functions[name] = {
                "start":  start,
                "end":    end,
                "source": "\n".join(func_lines),
                "indent": indent,
                "lines":  len(func_lines),
            }

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                extract_node(node)
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        extract_node(item, class_prefix=f"{node.name}.")
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Nur top-level
                if not any(
                    isinstance(p, ast.ClassDef)
                    for p in ast.walk(tree)
                    if hasattr(p, 'body') and node in getattr(p, 'body', [])
                ):
                    extract_node(node)

        return functions

    @staticmethod
    def replace_function(source: str, func_name: str, new_body: str) -> str:
        """
        Ersetzt den Body einer Funktion mit neuem Code.
        func_name kann "method" oder "Class.method" sein.
        """
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return source

        lines = source.splitlines()
        target_node = None

        # Suche den Knoten
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        full = f"{node.name}.{item.name}"
                        if full == func_name or item.name == func_name:
                            target_node = item
                            break
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == func_name or node.name == func_name.split(".")[-1]:
                    target_node = node
                    break

        if target_node is None:
            log.warning(f"  replace_function: '{func_name}' nicht gefunden")
            return source

        start = target_node.lineno - 1
        end   = getattr(target_node, 'end_lineno', start + 1)

        # Normalisiere Einrückung des neuen Codes
        new_lines = new_body.splitlines()
        # Entferne komplett leere Zeilen am Anfang/Ende
        while new_lines and not new_lines[0].strip():
            new_lines.pop(0)
        while new_lines and not new_lines[-1].strip():
            new_lines.pop()

        # Berechne Ziel-Einrückung aus dem Original
        orig_line  = lines[start] if start < len(lines) else ""
        orig_indent = len(orig_line) - len(orig_line.lstrip())
        orig_indent_str = " " * orig_indent

        # Normalisiere neue Zeilen
        if new_lines:
            # Finde minimale Einrückung im neuen Code (außer def-Zeile)
            body_lines = [l for l in new_lines[1:] if l.strip()]
            if body_lines:
                min_indent = min(len(l) - len(l.lstrip()) for l in body_lines)
            else:
                min_indent = 0

            normalized = []
            for i, line in enumerate(new_lines):
                if i == 0:
                    # def-Zeile: Ziel-Einrückung
                    normalized.append(orig_indent_str + line.lstrip())
                elif line.strip():
                    # Body: relative Einrückung beibehalten
                    curr = len(line) - len(line.lstrip())
                    extra = max(0, curr - min_indent)
                    normalized.append(orig_indent_str + "    " + " " * extra + line.lstrip())
                else:
                    normalized.append("")

            result = lines[:start] + normalized + lines[end:]
        else:
            result = lines[:start] + lines[end:]

        return "\n".join(result)

    @staticmethod
    def find_best_target(source: str, focus: str) -> Optional[Tuple[str, str]]:
        """
        Findet die beste Funktion für einen Fokus-Bereich.
        Gibt (func_name, func_source) zurück.
        """
        focus_map = {
            "listen_loop":         ["listen_loop", "_listen", "_audio_loop"],
            "telegram_handlers":   ["setup_telegram", "cmd_", "_handle_msg"],
            "optimization_engine": ["_run_iteration", "_run_loop", "_syntax_check"],
            "ai_routing":          ["_call_cerebras", "_smart_chat", "_godmode"],
            "error_handling":      ["startup_check", "_count_recent", "_handle_error"],
            "computer_control":    ["cc_click", "cc_type", "cc_screenshot"],
            "vision_analysis":     ["analyze_image", "analyze_video", "_vision"],
            "audio_processing":    ["transcribe_audio", "_speak", "say"],
            "openclaw_management": ["scan_folder", "_ai_classify", "execute_cleanup"],
        }
        keywords = focus_map.get(focus, [focus.split("_")])

        functions = CodeAnalyzer.get_all_functions(source)
        if not functions:
            return None

        # Suche nach Keyword-Match
        for kw in keywords:
            for fname, fdata in functions.items():
                if kw.lower() in fname.lower():
                    # Bevorzuge nicht zu große Funktionen (Cerebras-Limit)
                    if fdata["lines"] <= 80:
                        return fname, fdata["source"]

        # Fallback: kleinste passende Funktion
        for fname, fdata in sorted(functions.items(), key=lambda x: x[1]["lines"]):
            if fdata["lines"] >= 5 and fdata["lines"] <= 60:
                return fname, fdata["source"]

        return None


# ──────────────────────────────────────────────────────────────────────
#  PATCH ENGINE
# ──────────────────────────────────────────────────────────────────────

class PatchEngine:
    """
    Kernlogik: Patch eine einzelne Funktion.
    Cerebras bekommt immer nur die eine Funktion, nicht den ganzen Code.
    """

    @staticmethod
    def _call_coder(func_source: str, plan: dict, func_name: str,
                    iteration: int) -> Optional[str]:
        """Cerebras schreibt den neuen Funktions-Code. Gemini als Fallback."""
        problem  = plan.get("problem",  "Verbesserung")
        solution = plan.get("solution", "Robustheit erhöhen")

        prompt = (
            f"VERBESSERUNGSAUFTRAG:\n"
            f"  Problem:  {problem}\n"
            f"  Lösung:   {solution}\n"
            f"  Funktion: {func_name}\n\n"
            f"WICHTIG: Gib NUR den verbesserten Funktions-Code zurück.\n"
            f"Füge am Anfang ein: # PATCH {iteration}: {solution[:50]}\n"
            f"KEINE Backticks. KEIN Markdown. Nur Python.\n\n"
            f"ZU VERBESSERNDE FUNKTION:\n{func_source}"
        )

        # Versuch 1: Cerebras (primär — schnell und gut für Code)
        if cerebras_client and _call_cerebras:
            try:
                BrainStatus.set("coder", "working", "Cerebras patcht...")
                raw = _call_cerebras(prompt, _CODER_SYSTEM, max_tokens=4096)
                code = _strip_code_fences(raw) if _strip_code_fences else raw
                if code and len(code) > 20:
                    log.info(f"  ⚡ Cerebras Patch: {len(code)} Zeichen")
                    return code
            except Exception as e:
                log.warning(f"  Cerebras Coder: {e}")
                if _is_rate_limit and _is_rate_limit(str(e)):
                    _set_global_rate_limit_pause(str(e))

        # Versuch 2: Gemini (Fallback)
        if gemini_client and _call_gemini_raw:
            try:
                BrainStatus.set("coder", "working", "Gemini patcht...")
                raw = _call_gemini_raw(prompt, _CODER_SYSTEM, max_tokens=4096)
                code = _strip_code_fences(raw) if _strip_code_fences else raw
                if code and len(code) > 20:
                    log.info(f"  🧠 Gemini Patch: {len(code)} Zeichen")
                    return code
            except Exception as e:
                log.warning(f"  Gemini Coder: {e}")
                if _is_rate_limit and _is_rate_limit(str(e)):
                    _set_global_rate_limit_pause(str(e))

        # Versuch 3: Groq (Not-Fallback)
        if groq_client:
            try:
                BrainStatus.set("coder", "working", "Groq patcht...")
                r = groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {"role": "system", "content": _CODER_SYSTEM},
                        {"role": "user",   "content": prompt},
                    ],
                    max_tokens=4096,
                )
                raw = r.choices[0].message.content
                code = _strip_code_fences(raw) if _strip_code_fences else raw
                if code and len(code) > 20:
                    log.info(f"  🔬 Groq Patch: {len(code)} Zeichen")
                    return code
            except Exception as e:
                log.warning(f"  Groq Coder: {e}")

        return None

    @staticmethod
    def _fix_syntax(bad_code: str, error: str) -> Optional[str]:
        """
        Gezielte Syntax-Reparatur.
        Wichtig: Sendet den VOLLSTÄNDIGEN bad_code, nicht nur einen Ausschnitt.
        """
        prompt = (
            f"SYNTAXFEHLER im folgenden Python-Code:\n"
            f"FEHLER: {error}\n\n"
            f"Behebe NUR diesen Fehler. Ändere NICHTS ANDERES.\n"
            f"Gib den VOLLSTÄNDIGEN reparierten Code zurück. NUR Python.\n\n"
            f"{bad_code}"
        )

        # Cerebras zuerst
        if cerebras_client and _call_cerebras:
            try:
                raw = _call_cerebras(prompt, _FIX_SYSTEM, max_tokens=4096)
                return _strip_code_fences(raw) if _strip_code_fences else raw
            except Exception as e:
                log.warning(f"  Fix Cerebras: {e}")

        # Gemini als Fallback
        if gemini_client and _call_gemini_raw:
            try:
                raw = _call_gemini_raw(prompt, _FIX_SYSTEM, max_tokens=4096)
                return _strip_code_fences(raw) if _strip_code_fences else raw
            except Exception as e:
                log.warning(f"  Fix Gemini: {e}")

        return None

    @staticmethod
    def _critic_approve(func_source: str, new_func: str, plan: dict) -> Tuple[bool, str]:
        """
        Groq prüft ob der Patch sicher und korrekt ist.
        Gibt (ok, reason) zurück.
        """
        if not groq_client or not _call_groq_critic:
            # Kein Kritiker verfügbar: einfache Syntax-Prüfung
            return True, "Kein Kritiker verfügbar — auto-approve"

        prompt = (
            f"Vergleiche ORIGINAL und PATCH einer Python-Funktion:\n\n"
            f"PLAN:\n  Problem: {plan.get('problem','?')}\n"
            f"  Lösung:  {plan.get('solution','?')}\n\n"
            f"ORIGINAL ({len(func_source.splitlines())} Zeilen):\n{func_source}\n\n"
            f"PATCH ({len(new_func.splitlines())} Zeilen):\n{new_func}\n\n"
            f"Antworte NUR mit:\n"
            f"APPROVE: JA  — wenn der Patch sicher, korrekt und sinnvoll ist\n"
            f"APPROVE: NEIN: <kurzer Grund>  — wenn Fehler oder Risiko"
        )
        try:
            resp = _call_groq_critic(prompt, _CRITIC_SYSTEM, max_tokens=200)
            if resp.startswith("CRITIC_"):
                return True, "Kritiker nicht verfügbar"
            if "APPROVE: NEIN" in resp.upper():
                reason = resp.split("NEIN:", 1)[-1].strip()[:120] if "NEIN:" in resp else resp[:80]
                return False, reason
            return True, "Kritiker genehmigt"
        except Exception as e:
            log.warning(f"  Kritiker-Fehler: {e}")
            return True, f"Kritiker-Fehler: {e}"

    @staticmethod
    def _godmode_plan(func_source: str, func_name: str, focus: str,
                      goal: str, learn_ctx: str) -> Optional[dict]:
        """
        GodMode: Alle 3 Brains planen parallel, Groq synthetisiert den besten Plan.
        Wird genutzt wenn Gemini-Planung fehlschlägt oder als Boost.
        """
        if not _godmode_query_parallel:
            return None

        prompt = (
            f"OPTIMIERUNGSZIEL: {goal}\n"
            f"FOKUS: {focus}\n"
            f"FUNKTION: {func_name}\n\n"
            f"{learn_ctx}\n\n"
            f"Schlage EINE kleine, sichere Verbesserung vor.\n"
            f"JSON: {{\"problem\": \"...\", \"solution\": \"...\", \"risk\": \"low\"}}\n\n"
            f"FUNKTION:\n{func_source[:3000]}"
        )
        try:
            answers = _godmode_query_parallel(prompt, _PLANNER_SYSTEM)
            if not answers:
                return None

            # Groq synthetisiert, oder nehme erste Antwort
            synth_prompt = (
                f"Wähle den BESTEN und SICHERSTEN Verbesserungsplan aus diesen Vorschlägen:\n\n"
            )
            for brain, ans in answers.items():
                synth_prompt += f"=== {brain} ===\n{ans[:600]}\n\n"
            synth_prompt += (
                f"Antworte NUR mit JSON:\n"
                f'{{\"problem\": \"...\", \"solution\": \"...\", \"risk\": \"low\"}}'
            )

            if groq_client:
                try:
                    r = groq_client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=[
                            {"role": "system",
                             "content": "Synthetisiere den besten Plan. NUR JSON."},
                            {"role": "user", "content": synth_prompt},
                        ],
                        max_tokens=300,
                    )
                    raw = r.choices[0].message.content
                    raw = re.sub(r"^```json\s*", "", raw.strip(), flags=re.MULTILINE)
                    raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE)
                    return json.loads(raw)
                except Exception as e:
                    log.warning(f"  GodMode-Synthese: {e}")

            # Fallback: parse erste JSON-Antwort
            for ans in answers.values():
                try:
                    raw = re.sub(r"^```json\s*", "", ans.strip(), flags=re.MULTILINE)
                    raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE)
                    s = raw.find('{'); e = raw.rfind('}')
                    if s != -1 and e != -1:
                        return json.loads(raw[s:e+1])
                except Exception:
                    continue
        except Exception as e:
            log.warning(f"  GodMode Plan: {e}")
        return None


# ──────────────────────────────────────────────────────────────────────
#  LEARNING MEMORY
# ──────────────────────────────────────────────────────────────────────

class LearningMemory:
    def __init__(self):
        mem = PATHS.get("memory", Path("users/default/memory"))
        self._log_path = mem / "learning_log.json"
        self._err_path = mem / "error_patterns.json"
        self._kb_path  = mem / "knowledge_base.json"

        self._log    = _load_json(self._log_path,  {"entries": [], "stats": {}})
        self._errors = _load_json(self._err_path,  {"patterns": {}})
        self._kb     = _load_json(self._kb_path,   {
            "successful_patches":  [],
            "failed_patches":      [],
            "key_insights":        [],
            "patch_history":       [],
        })
        log.info(f"🧠 Lernprotokoll: {len(self._log['entries'])} Einträge")

    def record_success(self, iteration: int, goal: str, func_name: str,
                       summary: str, plan: dict):
        entry = {
            "type":      "success",
            "timestamp": datetime.now().isoformat(),
            "iteration": iteration,
            "goal":      goal,
            "func":      func_name,
            "summary":   summary,
            "plan":      plan,
        }
        self._log["entries"].append(entry)
        self._log.setdefault("stats", {})
        self._log["stats"]["total_success"] = \
            self._log["stats"].get("total_success", 0) + 1
        _save_json(self._log_path, self._log)

        patch_entry = f"[{func_name}] {summary[:80]}"
        patches = self._kb.setdefault("successful_patches", [])
        if patch_entry not in patches:
            patches.append(patch_entry)
        if len(patches) > 30:
            patches.pop(0)

        history = self._kb.setdefault("patch_history", [])
        history.append({"func": func_name, "plan": plan, "ts": entry["timestamp"]})
        if len(history) > 50:
            history.pop(0)
        _save_json(self._kb_path, self._kb)

        self._save_training_sample(iteration, goal, func_name, plan, summary)
        log.info(f"🧠 Erfolg: [{func_name}] {summary[:60]}")

    def record_failure(self, iteration: int, goal: str, reason: str,
                       stage: str, func_name: str = "",
                       is_rate_limit: bool = False):
        if is_rate_limit:
            log.info(f"⏳ Rate-Limit [{stage}]")
            return
        self._log["entries"].append({
            "type":      "failure",
            "timestamp": datetime.now().isoformat(),
            "iteration": iteration,
            "goal":      goal,
            "reason":    reason[:200],
            "stage":     stage,
            "func":      func_name,
        })
        self._log.setdefault("stats", {})
        self._log["stats"]["total_failure"] = \
            self._log["stats"].get("total_failure", 0) + 1
        key = f"{stage}:{func_name}:{reason[:50]}"
        self._errors["patterns"][key] = \
            self._errors["patterns"].get(key, 0) + 1
        _save_json(self._log_path,  self._log)
        _save_json(self._err_path, self._errors)

        fail = self._kb.setdefault("failed_patches", [])
        entry = f"[{stage}/{func_name}] {reason[:80]}"
        if entry not in fail:
            fail.append(entry)
        if len(fail) > 30:
            fail.pop(0)
        _save_json(self._kb_path, self._kb)

    def get_context_for_prompt(self) -> str:
        succ  = self._kb.get("successful_patches", [])[-5:]
        fail  = self._kb.get("failed_patches",     [])[-5:]
        ins   = self._kb.get("key_insights",        [])[-3:]
        stats = self._log.get("stats", {})
        s, f  = stats.get("total_success", 0), stats.get("total_failure", 0)
        lines = [f"=== LERNPROTOKOLL (Erfolge: {s}, Fehler: {f}) ==="]
        if succ:
            lines.append("✅ Was funktioniert hat:")
            for item in succ:
                lines.append(f"  + {item}")
        if fail:
            lines.append("❌ Was scheitert (VERMEIDEN):")
            for item in fail:
                lines.append(f"  - {item}")
        if ins:
            lines.append("💡 Erkenntnisse:")
            for item in ins:
                lines.append(f"  → {item}")
        top_err = sorted(self._errors["patterns"].items(),
                         key=lambda x: -x[1])[:3]
        if top_err:
            lines.append("🔁 Häufigste Fehler:")
            for k, v in top_err:
                lines.append(f"  [{v}x] {k.split(':',1)[-1][:80]}")
        return "\n".join(lines)

    def get_stats_summary(self) -> str:
        stats = self._log.get("stats", {})
        s     = stats.get("total_success", 0)
        f     = stats.get("total_failure", 0)
        rate  = round(s / max(s + f, 1) * 100)
        total = len(self._log.get("entries", []))
        ins   = len(self._kb.get("key_insights", []))
        return (f"{total} Iterationen. Erfolgsrate: {rate}% "
                f"({s} Erfolge, {f} Fehler). {ins} Erkenntnisse.")

    def add_insight(self, insight: str):
        ins = self._kb.setdefault("key_insights", [])
        if insight not in ins:
            ins.append(insight)
        if len(ins) > 20:
            ins.pop(0)
        _save_json(self._kb_path, self._kb)

    def _save_training_sample(self, iteration, goal, func_name, plan, summary):
        sample = {
            "instruction": f"Patch Funktion '{func_name}'. Ziel: {goal}",
            "input":       json.dumps(plan, ensure_ascii=False),
            "output":      summary,
            "metadata":    {"iteration": iteration,
                            "timestamp": datetime.now().isoformat()},
        }
        dataset = PATHS.get("training", Path("users/default/training_data")) \
                  / "successful_iterations.jsonl"
        try:
            dataset.parent.mkdir(parents=True, exist_ok=True)
            with open(dataset, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(sample, ensure_ascii=False) + "\n")
        except Exception as e:
            log.warning(f"Training-Save: {e}")


# ──────────────────────────────────────────────────────────────────────
#  OPTIMIZATION ENGINE
# ──────────────────────────────────────────────────────────────────────

class OptimizationEngine:

    IDLE    = "idle"
    RUNNING = "running"
    PAUSED  = "paused"
    DONE    = "done"
    FAILED  = "failed"

    def __init__(self):
        self.status               = self.IDLE
        self.thread               = None
        self._stop                = threading.Event()
        self.current_goal         = ""
        self.duration_sec         = 0
        self.start_time           = None
        self.iterations           = 0
        self.max_iterations       = 30
        self.max_code_attempts    = _OPT_MAX_CODE_ATT
        self.history: List[Dict]  = []
        self._last_plan           = ""
        self._resumed             = False
        self.memory               = LearningMemory()
        self._focus_index         = 0
        self._consecutive_fails   = 0
        self._load_history()

    def _load_history(self):
        rp = PATHS.get("logs", Path("users/default/logs")) / "opt_report.json"
        if rp and rp.exists():
            try:
                self.history = json.loads(rp.read_text(encoding="utf-8"))
            except Exception:
                self.history = []

    def _save_history(self):
        rp = PATHS.get("logs", Path("users/default/logs")) / "opt_report.json"
        try:
            rp.write_text(json.dumps(self.history, ensure_ascii=False, indent=2),
                          encoding="utf-8")
        except Exception as e:
            log.error(f"History-Save: {e}")

    def start(self, goal: str = "", duration_input: str = ""):
        if self.status == self.RUNNING:
            if _say:
                _say("Optimierung läuft bereits.")
            return

        resume = _load_json(OPT_RESUME_FILE, None) \
            if OPT_RESUME_FILE and OPT_RESUME_FILE.exists() else None

        if resume and not goal:
            self.current_goal = resume["goal"]
            self.duration_sec = resume.get("duration_sec", 0)
            self.iterations   = resume.get("iterations_done", 0)
            self._last_plan   = resume.get("planned_changes", "")
            self._resumed     = True
        else:
            self.current_goal = goal or \
                "Robustheit, Fehlerbehandlung und Code-Qualität verbessern"
            self.duration_sec = self._parse_duration(duration_input)
            self.iterations   = 0
            self._last_plan   = ""
            self._resumed     = False
            if OPT_RESUME_FILE:
                OPT_RESUME_FILE.unlink(missing_ok=True)

        self._consecutive_fails = 0
        self.start_time = datetime.now()
        self._stop.clear()
        self.status = self.RUNNING
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

        dur = self._fmt(self.duration_sec) if self.duration_sec else "unbegrenzt"
        dev = f"Cerebras {cerebras_model}" if cerebras_client else "Gemini"
        if _say:
            if self._resumed:
                _say(f"Weiter bei Iteration {self.iterations}. Diff-Patch-System aktiv.")
            else:
                _say(f"Selbst-Optimierung gestartet. Zeitrahmen: {dur}. "
                     f"Brains: Gemini + {dev} + Groq. Patch-Modus.")

    def stop(self, save_progress: bool = True):
        if self.status != self.RUNNING:
            if _say:
                _say("Keine Optimierung aktiv.")
            return
        self._stop.set()
        self.status = self.PAUSED
        if save_progress and OPT_RESUME_FILE:
            _save_json(OPT_RESUME_FILE, {
                "goal":            self.current_goal,
                "duration_sec":    self.duration_sec,
                "iterations_done": self.iterations,
                "planned_changes": self._last_plan,
                "paused_at":       datetime.now().isoformat(),
            })
            if _say:
                _say("Gestoppt. Fortschritt gespeichert.")
        else:
            if OPT_RESUME_FILE:
                OPT_RESUME_FILE.unlink(missing_ok=True)
            if _say:
                _say("Optimierung gestoppt.")

    def get_status(self) -> str:
        dev = f"Cerebras {cerebras_model}" if cerebras_client else "Gemini"
        if self.status == self.IDLE:
            return f"Bereit. Brains: Gemini + {dev} + Groq. Patch-Modus v2."
        if self.status == self.RUNNING:
            el   = int((datetime.now() - self.start_time).total_seconds())
            focus = _FOCUS_AREAS[self._focus_index % len(_FOCUS_AREAS)]
            rem  = ""
            if self.duration_sec:
                rem = f" Verbleibend: {self._fmt(max(0, self.duration_sec-el))}."
            stats = self.memory.get_stats_summary()
            return (f"Läuft — Iter {self.iterations}, Fokus: {focus}. "
                    f"Laufzeit: {self._fmt(el)}.{rem} | {stats}")
        if self.status == self.PAUSED:
            return f"Pausiert nach Iter {self.iterations}. {self.memory.get_stats_summary()}"
        if self.status == self.DONE:
            return f"Abgeschlossen nach {self.iterations} Iter. {self.memory.get_stats_summary()}"
        return f"Status: {self.status}"

    def get_learning_summary(self) -> str:
        return self.memory.get_stats_summary()

    # ── RUN LOOP ───────────────────────────────────────────────────────

    def _run_loop(self):
        log.info("🧠 Patch-Optimizer v2 gestartet")
        if SELF_PATH and _archive_dead_code:
            try:
                lines = len(SELF_PATH.read_text(encoding="utf-8").splitlines())
                if lines > MAX_LINES:
                    log.info(f"🧹 {lines} Zeilen > {MAX_LINES} — Cleanup")
                    _archive_dead_code()
            except Exception as e:
                log.warning(f"Cleanup-Check: {e}")

        while not self._stop.is_set():
            _wait_for_rate_limit(stop_event=self._stop)
            if self._stop.is_set():
                break

            # Zeitlimit prüfen
            if self.duration_sec and self.start_time:
                elapsed = (datetime.now() - self.start_time).total_seconds()
                if elapsed >= self.duration_sec:
                    self._finalize("Zeitlimit erreicht")
                    return

            # Max-Iterationen prüfen
            if self.iterations >= self.max_iterations:
                self._finalize("Max Iterationen erreicht")
                return

            # Zu viele aufeinanderfolgende Fehler: kurze Pause
            if self._consecutive_fails >= 5:
                log.warning(f"⚠ {self._consecutive_fails} Fehler in Folge — 60s Pause")
                self._consecutive_fails = 0
                for _ in range(60):
                    if self._stop.is_set():
                        return
                    time.sleep(1)

            self.iterations += 1
            focus = _FOCUS_AREAS[self._focus_index % len(_FOCUS_AREAS)]
            self._focus_index += 1
            log.info(f"\n{'='*60}\n🔄 ITER {self.iterations} | Fokus: {focus}\n{'='*60}")

            result = self._run_iteration(focus)
            self.history.append({
                "iteration": self.iterations,
                "timestamp": datetime.now().isoformat(),
                "goal":      self.current_goal,
                "focus":     focus,
                "status":    result["status"],
                "summary":   result.get("summary", ""),
                "applied":   result.get("applied", False),
                "func":      result.get("func", ""),
            })
            self._save_history()

            status = result["status"]
            if status == "goal_reached":
                if OPT_RESUME_FILE:
                    OPT_RESUME_FILE.unlink(missing_ok=True)
                if _say:
                    _say(f"Ziel nach {self.iterations} Iterationen erreicht.")
                self._finalize("Ziel erreicht")
                return
            elif status == "success":
                self._consecutive_fails = 0
                log.info(f"✅ Iter {self.iterations}: {result.get('summary','')}")
                time.sleep(_OPT_ITER_PAUSE)
            elif status == "rate_limited":
                log.info("⏳ Rate-Limit — warte ...")
                self.iterations -= 1
                time.sleep(5)
            elif status == "stopped":
                return
            elif status == "no_change":
                # Kein Fehler, aber auch keine Änderung — nächste Iteration
                log.info(f"  → Keine Änderung bei '{result.get('func','')}' — weiter")
                time.sleep(3)
            else:
                self._consecutive_fails += 1
                log.warning(f"⚠ Iter {self.iterations}: {result.get('summary','')}")
                time.sleep(8)

        self._finalize("Manuell gestoppt")

    # ── SINGLE ITERATION (PATCH-BASIERT) ──────────────────────────────

    def _run_iteration(self, focus: str) -> dict:
        """
        Neue Patch-Strategie:
        1. Wähle EINE Funktion aus dem Ziel-Code
        2. Gemini/GodMode plant EINE kleine Verbesserung
        3. Cerebras patcht NUR diese Funktion
        4. Groq prüft den Patch
        5. Patch wird chirurgisch in den Code eingebettet
        6. Syntax-Check → Deploy
        """
        if not SELF_PATH or not SELF_PATH.exists():
            return {"status": "error", "summary": "SELF_PATH nicht verfügbar"}

        source    = SELF_PATH.read_text(encoding="utf-8")
        learn_ctx = self.memory.get_context_for_prompt()

        # ── SCHRITT 1: Funktion wählen ─────────────────────────────────
        BrainStatus.set("planner", "working", "Wählt Funktion...")
        target = CodeAnalyzer.find_best_target(source, focus)
        if not target:
            return {"status": "error",
                    "summary": f"Keine passende Funktion für '{focus}'"}
        func_name, func_source = target
        log.info(f"🎯 Ziel-Funktion: {func_name} ({len(func_source.splitlines())} Zeilen)")

        # ── SCHRITT 2: Plan erstellen ──────────────────────────────────
        BrainStatus.set("planner", "working", f"Plane {func_name}...")
        plan = self._create_plan(func_name, func_source, focus, learn_ctx)
        if not plan:
            return {"status": "error", "summary": "Kein Plan erstellt",
                    "func": func_name}

        log.info(f"📋 Plan: {plan.get('solution','?')[:60]}")
        BrainStatus.set("planner", "done", plan.get("solution", "?")[:40])

        if self._stop.is_set():
            return {"status": "stopped", "summary": "Gestoppt"}

        # ── SCHRITT 3: Code patchen ────────────────────────────────────
        new_func = None
        for attempt in range(1, self.max_code_attempts + 1):
            if self._stop.is_set():
                return {"status": "stopped", "summary": "Gestoppt"}

            BrainStatus.set("coder", "working",
                            f"Patch {attempt}/{self.max_code_attempts}")
            raw = PatchEngine._call_coder(
                func_source, plan, func_name, self.iterations
            )
            if not raw:
                self.memory.record_failure(self.iterations, self.current_goal,
                                           "Kein Code generiert", "coder",
                                           func_name)
                if attempt < self.max_code_attempts:
                    time.sleep(3)
                continue

            # Stripped und Syntax-geprüft
            candidate = _strip_code_fences(raw) if _strip_code_fences else raw

            # Grundprüfung: muss mit def/async def/class beginnen
            stripped = candidate.lstrip()
            if not (stripped.startswith("def ") or
                    stripped.startswith("async def ") or
                    stripped.startswith("class ") or
                    "# PATCH" in candidate):
                log.warning(f"  Ungültiger Patch-Anfang: {candidate[:60]}")
                # Versuche zu retten: suche def-Zeile
                for line in candidate.splitlines():
                    if line.lstrip().startswith(("def ", "async def ", "class ")):
                        idx = candidate.find(line)
                        candidate = candidate[idx:]
                        break

            # ── SCHRITT 4: Kritiker prüft ─────────────────────────────
            critic_ok, critic_reason = PatchEngine._critic_approve(
                func_source, candidate, plan
            )
            if not critic_ok:
                log.warning(f"  Kritiker NEIN: {critic_reason}")
                self.memory.record_failure(self.iterations, self.current_goal,
                                           critic_reason, "critic", func_name)
                if attempt < self.max_code_attempts:
                    # Kritiker-Feedback in nächsten Versuch einbauen
                    plan["critic_feedback"] = critic_reason
                    time.sleep(2)
                continue

            new_func = candidate
            log.info(f"  ✅ Patch akzeptiert (Versuch {attempt})")
            break

        if not new_func:
            self.memory.record_failure(self.iterations, self.current_goal,
                                       "Alle Patch-Versuche fehlgeschlagen",
                                       "coder", func_name)
            return {"status": "error",
                    "summary": f"Patch fehlgeschlagen nach {self.max_code_attempts} Versuchen",
                    "func": func_name}

        # ── SCHRITT 5: Patch einbetten ─────────────────────────────────
        BrainStatus.set("coder", "working", "Bettet Patch ein...")
        try:
            new_source = CodeAnalyzer.replace_function(source, func_name, new_func)
        except Exception as e:
            log.error(f"  Embed-Fehler: {e}")
            self.memory.record_failure(self.iterations, self.current_goal,
                                       str(e), "embed", func_name)
            return {"status": "error", "summary": f"Embed: {e}", "func": func_name}

        # Keine Änderung?
        if new_source.strip() == source.strip():
            log.info(f"  → Patch war identisch — keine Änderung")
            return {"status": "no_change",
                    "summary": "Patch identisch mit Original",
                    "func": func_name}

        # ── SCHRITT 6: Syntax-Check ────────────────────────────────────
        ok, err = self._syntax_check(new_source)
        if not ok:
            log.warning(f"  Syntax-Fehler nach Embed: {err}")
            BrainStatus.set("coder", "working", "Behebt Syntax...")
            # Gezielter Fix: ganzen neuen Source übergeben
            fixed = PatchEngine._fix_syntax(new_source, err)
            if fixed:
                new_source = fixed
                ok, err = self._syntax_check(new_source)
            if not ok:
                log.error(f"  Syntax nicht heilbar: {err}")
                self.memory.record_failure(self.iterations, self.current_goal,
                                           err, "syntax", func_name)
                return {"status": "error",
                        "summary": f"Syntax: {err[:100]}", "func": func_name}

        log.info("  ✅ Syntax OK")
        BrainStatus.set("coder", "done", "Syntax OK")

        # ── SCHRITT 7: Deploy ──────────────────────────────────────────
        backup = _create_deployment_backup() if _create_deployment_backup else None
        try:
            SELF_PATH.write_text(new_source, encoding="utf-8")
            # Post-Deploy Syntax-Bestätigung
            ok, err = self._syntax_check(new_source)
            if not ok:
                raise RuntimeError(f"Post-Deploy Syntax: {err}")
        except Exception as e:
            log.error(f"  Deploy failed — Rollback! {e}")
            if backup and SELF_PATH:
                shutil.copy2(backup, SELF_PATH)
                BrainStatus.set("planner", "error", "Rollback")
            self.memory.record_failure(self.iterations, self.current_goal,
                                       str(e), "deploy", func_name)
            return {"status": "error",
                    "summary": f"Deploy+Rollback: {e}", "func": func_name}

        summary = f"[{func_name}] {plan.get('solution','')[:60]}"
        log.info(f"  🚀 Patch deployed: {summary}")
        if _cleanup_old_backups:
            _cleanup_old_backups(keep=10)

        self.memory.record_success(self.iterations, self.current_goal,
                                   func_name, summary, plan)

        # Ziel erreicht?
        goal_done = self._check_goal_reached()
        return {
            "status":  "goal_reached" if goal_done else "success",
            "summary": summary,
            "applied": True,
            "backup":  str(backup) if backup else "",
            "func":    func_name,
        }

    def _create_plan(self, func_name: str, func_source: str,
                     focus: str, learn_ctx: str) -> Optional[dict]:
        """
        Erstellt einen Verbesserungsplan per Gemini (primär) oder GodMode.
        """
        prompt = (
            f"OPTIMIERUNGSZIEL: {self.current_goal}\n"
            f"FOKUS: {focus}\n"
            f"ITERATION: {self.iterations}\n\n"
            f"{learn_ctx}\n\n"
            f"Analysiere diese Funktion und schlage EINE kleine, sichere Verbesserung vor.\n"
            f"FUNKTION: {func_name}\n\n"
            f"Antworte NUR mit JSON:\n"
            f'{{"problem": "was konkret verbessert wird", '
            f'"solution": "wie konkret", "risk": "low"}}\n\n'
            f"CODE:\n{func_source[:3000]}"
        )

        # Versuch 1: Gemini
        if gemini_client and _call_gemini_json:
            try:
                result = _call_gemini_json(prompt, _PLANNER_SYSTEM)
                if result and isinstance(result, dict) and "problem" in result:
                    return result
                # Manchmal gibt Gemini eine Liste zurück
                if isinstance(result, list) and result:
                    item = result[0]
                    if isinstance(item, dict) and "problem" in item:
                        return item
            except Exception as e:
                if _is_rate_limit and _is_rate_limit(str(e)):
                    log.warning("⚡ Planer Gemini 429 — GodMode")
                    _set_global_rate_limit_pause(str(e))
                else:
                    log.warning(f"Planer Gemini: {e}")

        # Versuch 2: GodMode (alle 3 Brains parallel)
        if _godmode_query_parallel:
            plan = PatchEngine._godmode_plan(
                func_source, func_name, focus,
                self.current_goal, learn_ctx
            )
            if plan:
                log.info("  ✅ GodMode-Plan erfolgreich")
                return plan

        # Versuch 3: Groq-Fallback
        if groq_client:
            try:
                r = groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {"role": "system", "content": _PLANNER_SYSTEM},
                        {"role": "user",   "content": prompt},
                    ],
                    max_tokens=500,
                )
                raw = r.choices[0].message.content
                raw = re.sub(r"^```json\s*", "", raw.strip(), flags=re.MULTILINE)
                raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE)
                s = raw.find('{'); e = raw.rfind('}')
                if s != -1 and e != -1:
                    result = json.loads(raw[s:e+1])
                    if "problem" in result:
                        log.info("  ✅ Groq-Plan erfolgreich")
                        return result
            except Exception as e:
                if _is_rate_limit and _is_rate_limit(str(e)):
                    _set_global_rate_limit_pause(str(e))
                log.warning(f"Planer Groq: {e}")

        # Minimal-Fallback
        return {
            "problem":  f"Verbesserung der Funktion {func_name}",
            "solution": "Fehlerbehandlung robuster machen",
            "risk":     "low",
        }

    # ── SYNTAX CHECK ──────────────────────────────────────────────────

    def _syntax_check(self, code: str) -> Tuple[bool, str]:
        """Syntaxprüfung via py_compile. Temporäre Datei im opt_workspace."""
        ws  = PATHS.get("opt_workspace", Path("opt_workspace"))
        ws.mkdir(parents=True, exist_ok=True)
        tmp = ws / f"syn_{int(time.time()*1000)}.py"
        try:
            tmp.write_text(code, encoding="utf-8")
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

    # ── GOAL CHECK ────────────────────────────────────────────────────

    def _check_goal_reached(self) -> bool:
        if self.iterations < 3 or not _call_gemini_with_backoff:
            return False
        try:
            ans = _call_gemini_with_backoff(
                f"Wurde '{self.current_goal}' nach {self.iterations} "
                f"Patch-Iterationen erreicht? NUR: JA oder NEIN.",
                "", 5, stop_event=self._stop
            ).strip().upper()
            return ans.startswith("JA")
        except Exception:
            return False

    # ── FINALIZE ──────────────────────────────────────────────────────

    def _finalize(self, reason: str):
        self.status = self.DONE
        el = int((datetime.now() - self.start_time).total_seconds()) \
             if self.start_time else 0
        log.info(f"🏁 Optimierung beendet: {reason}. {self.iterations} Iter.")
        if _say:
            stats = self.memory.get_stats_summary()
            _say(f"Optimierung abgeschlossen: {reason}. {stats}")
        report = {
            "end_time":   datetime.now().isoformat(),
            "reason":     reason,
            "iterations": self.iterations,
            "elapsed_s":  el,
            "goal":       self.current_goal,
            "history":    self.history,
            "learning":   self.memory.get_stats_summary(),
        }
        rp = PATHS.get("logs", Path("users/default/logs")) \
             / f"opt_final_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            rp.parent.mkdir(parents=True, exist_ok=True)
            rp.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                          encoding="utf-8")
        except Exception as e:
            log.warning(f"Finalize-Save: {e}")

    # ── UTILITY ───────────────────────────────────────────────────────

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
        if seconds < 60:
            return f"{seconds}s"
        if seconds < 3600:
            return f"{seconds//60}min {seconds%60}s"
        return f"{seconds//3600}h {(seconds%3600)//60}min"
