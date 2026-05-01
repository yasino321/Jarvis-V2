"""
╔══════════════════════════════════════════════════════════════════════╗
║   J.A.R.V.I.S — GOOGLE SERVICES MODULE                             ║
║   Kalender · Notizen (Keep) · Wecker · Gmail · Tasks               ║
║   Wird von jarvis_v5_8.py importiert                                ║
╚══════════════════════════════════════════════════════════════════════╝

SETUP (einmalig):
  1. Google Cloud Console: https://console.cloud.google.com
  2. Neues Projekt erstellen (z.B. "JARVIS")
  3. APIs aktivieren:
       - Google Calendar API
       - Google Tasks API
       - Gmail API
       - Google Keep API (optional, über Keep Notes)
  4. OAuth 2.0 Credentials erstellen (Typ: Desktop App)
  5. credentials.json herunterladen → in Jarvis-Ordner legen
  6. Beim ersten Start: Browser öffnet sich → Google-Konto auswählen
  7. token.json wird automatisch gespeichert (kein Passwort mehr nötig)

PRIVATSPHÄRE:
  - credentials.json  → NIEMALS auf GitHub hochladen!
  - token.json        → NIEMALS auf GitHub hochladen!
  - Beide sind in .gitignore eingetragen.
"""

from __future__ import annotations
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, List

log = logging.getLogger("JARVIS.Google")

# ── Diese werden von jarvis_v5_8.py nach dem Import gesetzt ──────────
PATHS = {}
OWNER_TELEGRAM_ID = ""

# ── Konstanten ────────────────────────────────────────────────────────
CREDENTIALS_FILE = Path("credentials.json")
TOKEN_FILE       = Path("token.json")

# Google API Scopes (was JARVIS darf)
SCOPES = [
    "https://www.googleapis.com/auth/calendar",          # Kalender lesen+schreiben
    "https://www.googleapis.com/auth/tasks",             # Tasks lesen+schreiben
    "https://www.googleapis.com/auth/gmail.send",        # E-Mail senden
    "https://www.googleapis.com/auth/gmail.readonly",    # E-Mails lesen
]

# ── Globale Service-Objekte ────────────────────────────────────────────
_calendar_service = None
_tasks_service    = None
_gmail_service    = None
_auth_ok          = False

# ─────────────────────────────────────────────────────────────────────
#  AUTHENTIFIZIERUNG
# ─────────────────────────────────────────────────────────────────────

def init_google() -> bool:
    """
    Initialisiert alle Google-Dienste über OAuth2.
    Beim ersten Mal öffnet sich ein Browser-Fenster.
    Danach läuft alles automatisch über token.json.
    """
    global _calendar_service, _tasks_service, _gmail_service, _auth_ok

    if not CREDENTIALS_FILE.exists():
        log.warning(
            "⚠️  Google: credentials.json fehlt.\n"
            "   → https://console.cloud.google.com → APIs → OAuth Credentials\n"
            "   → Desktop App → Download → als 'credentials.json' speichern"
        )
        return False

    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        creds = None

        # Gespeichertes Token laden
        if TOKEN_FILE.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
            except Exception as e:
                log.warning(f"Google Token ungültig: {e} — neu authentifizieren")
                TOKEN_FILE.unlink(missing_ok=True)
                creds = None

        # Token abgelaufen → automatisch erneuern
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                log.info("🔄 Google Token erneuert")
            except Exception as e:
                log.warning(f"Token-Refresh fehlgeschlagen: {e} — neu authentifizieren")
                TOKEN_FILE.unlink(missing_ok=True)
                creds = None

        # Kein gültiges Token → Browser-Login
        if not creds or not creds.valid:
            log.info("🌐 Google: Browser-Authentifizierung startet...")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_FILE), SCOPES
            )
            creds = flow.run_local_server(port=0, open_browser=True)
            TOKEN_FILE.write_text(creds.to_json())
            log.info("✅ Google: Token gespeichert → token.json")

        # Services aufbauen
        _calendar_service = build("calendar", "v3", credentials=creds)
        _tasks_service    = build("tasks",    "v1", credentials=creds)
        _gmail_service    = build("gmail",    "v1", credentials=creds)
        _auth_ok = True
        log.info("✅ Google Services initialisiert: Kalender · Tasks · Gmail")
        return True

    except ImportError:
        log.error(
            "❌ Google-Pakete fehlen:\n"
            "   pip install google-auth google-auth-oauthlib "
            "google-auth-httplib2 google-api-python-client"
        )
        return False
    except Exception as e:
        log.error(f"❌ Google Init-Fehler: {e}")
        return False


def google_status() -> str:
    if not _auth_ok:
        if not CREDENTIALS_FILE.exists():
            return "❌ Google nicht verbunden — credentials.json fehlt"
        return "❌ Google nicht verbunden — init_google() fehlgeschlagen"
    svc = []
    if _calendar_service: svc.append("📅 Kalender")
    if _tasks_service:    svc.append("✅ Tasks")
    if _gmail_service:    svc.append("📧 Gmail")
    return "✅ Google verbunden: " + " · ".join(svc)


# ─────────────────────────────────────────────────────────────────────
#  KALENDER
# ─────────────────────────────────────────────────────────────────────

def calendar_list_events(days_ahead: int = 7, max_results: int = 10) -> str:
    """Zeigt anstehende Kalender-Ereignisse."""
    if not _calendar_service:
        return "Google Kalender nicht verbunden."
    try:
        now    = datetime.now(timezone.utc)
        end    = now + timedelta(days=days_ahead)
        result = _calendar_service.events().list(
            calendarId="primary",
            timeMin=now.isoformat(),
            timeMax=end.isoformat(),
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        events = result.get("items", [])
        if not events:
            return f"Keine Termine in den nächsten {days_ahead} Tagen."

        lines = [f"📅 Deine nächsten {len(events)} Termine:"]
        for ev in events:
            start_raw = ev["start"].get("dateTime", ev["start"].get("date", ""))
            try:
                if "T" in start_raw:
                    dt = datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
                    dt_local = dt.astimezone()
                    time_str = dt_local.strftime("%d.%m. %H:%M")
                else:
                    time_str = start_raw
            except Exception:
                time_str = start_raw
            title    = ev.get("summary", "(kein Titel)")
            location = ev.get("location", "")
            loc_str  = f" 📍 {location}" if location else ""
            lines.append(f"  • {time_str} — {title}{loc_str}")
        return "\n".join(lines)

    except Exception as e:
        log.error(f"Kalender-Liste: {e}")
        return f"Kalender-Fehler: {e}"


def calendar_create_event(
    title: str,
    start_dt: datetime,
    end_dt: datetime = None,
    description: str = "",
    location: str = "",
) -> str:
    """Erstellt einen neuen Kalender-Eintrag."""
    if not _calendar_service:
        return "Google Kalender nicht verbunden."
    try:
        if end_dt is None:
            end_dt = start_dt + timedelta(hours=1)

        tz_name = datetime.now().astimezone().tzname() or "Europe/Berlin"
        body = {
            "summary":     title,
            "description": description,
            "location":    location,
            "start": {
                "dateTime": start_dt.isoformat(),
                "timeZone": "Europe/Berlin",
            },
            "end": {
                "dateTime": end_dt.isoformat(),
                "timeZone": "Europe/Berlin",
            },
        }
        ev = _calendar_service.events().insert(calendarId="primary", body=body).execute()
        link = ev.get("htmlLink", "")
        log.info(f"📅 Termin erstellt: {title} am {start_dt.strftime('%d.%m. %H:%M')}")
        return (
            f"✅ Termin erstellt: '{title}'\n"
            f"   📅 {start_dt.strftime('%d.%m.%Y %H:%M')} – "
            f"{end_dt.strftime('%H:%M')}"
        )
    except Exception as e:
        log.error(f"Kalender-Create: {e}")
        return f"Termin-Fehler: {e}"


def calendar_delete_event(title_keyword: str) -> str:
    """Löscht den nächsten Termin der den Suchbegriff enthält."""
    if not _calendar_service:
        return "Google Kalender nicht verbunden."
    try:
        now    = datetime.now(timezone.utc)
        result = _calendar_service.events().list(
            calendarId="primary",
            timeMin=now.isoformat(),
            q=title_keyword,
            maxResults=5,
            singleEvents=True,
            orderBy="startTime",
        ).execute()
        events = result.get("items", [])
        if not events:
            return f"Kein Termin mit '{title_keyword}' gefunden."
        ev = events[0]
        _calendar_service.events().delete(
            calendarId="primary", eventId=ev["id"]
        ).execute()
        return f"🗑️ Termin gelöscht: '{ev.get('summary', title_keyword)}'"
    except Exception as e:
        log.error(f"Kalender-Delete: {e}")
        return f"Lösch-Fehler: {e}"


# ─────────────────────────────────────────────────────────────────────
#  TASKS / AUFGABEN
# ─────────────────────────────────────────────────────────────────────

def _get_default_tasklist() -> Optional[str]:
    """Gibt die ID der Standard-Aufgabenliste zurück."""
    if not _tasks_service:
        return None
    try:
        lists = _tasks_service.tasklists().list(maxResults=1).execute()
        items = lists.get("items", [])
        return items[0]["id"] if items else "@default"
    except Exception:
        return "@default"


def tasks_list(max_results: int = 10, show_completed: bool = False) -> str:
    """Zeigt offene Aufgaben."""
    if not _tasks_service:
        return "Google Tasks nicht verbunden."
    try:
        list_id = _get_default_tasklist() or "@default"
        result  = _tasks_service.tasks().list(
            tasklist=list_id,
            maxResults=max_results,
            showCompleted=show_completed,
            showHidden=False,
        ).execute()
        items = result.get("items", [])
        if not items:
            return "✅ Keine offenen Aufgaben."
        lines = [f"✅ Deine Aufgaben ({len(items)}):"]
        for t in items:
            due = ""
            if t.get("due"):
                try:
                    d   = datetime.fromisoformat(t["due"].replace("Z", "+00:00"))
                    due = f" (fällig: {d.strftime('%d.%m.')})"
                except Exception:
                    pass
            status = "☑" if t.get("status") == "completed" else "☐"
            lines.append(f"  {status} {t.get('title', '?')}{due}")
        return "\n".join(lines)
    except Exception as e:
        log.error(f"Tasks-Liste: {e}")
        return f"Tasks-Fehler: {e}"


def tasks_create(title: str, due: datetime = None, notes: str = "") -> str:
    """Erstellt eine neue Aufgabe."""
    if not _tasks_service:
        return "Google Tasks nicht verbunden."
    try:
        list_id = _get_default_tasklist() or "@default"
        body: dict = {"title": title, "notes": notes, "status": "needsAction"}
        if due:
            body["due"] = due.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        _tasks_service.tasks().insert(tasklist=list_id, body=body).execute()
        due_str = f" (fällig: {due.strftime('%d.%m.%Y')})" if due else ""
        log.info(f"✅ Aufgabe erstellt: {title}")
        return f"✅ Aufgabe erstellt: '{title}'{due_str}"
    except Exception as e:
        log.error(f"Task-Create: {e}")
        return f"Aufgaben-Fehler: {e}"


def tasks_complete(title_keyword: str) -> str:
    """Markiert eine Aufgabe als erledigt."""
    if not _tasks_service:
        return "Google Tasks nicht verbunden."
    try:
        list_id = _get_default_tasklist() or "@default"
        result  = _tasks_service.tasks().list(
            tasklist=list_id, maxResults=20, showCompleted=False
        ).execute()
        items = result.get("items", [])
        match = next(
            (t for t in items if title_keyword.lower() in t.get("title", "").lower()),
            None
        )
        if not match:
            return f"Keine Aufgabe mit '{title_keyword}' gefunden."
        match["status"] = "completed"
        _tasks_service.tasks().update(
            tasklist=list_id, task=match["id"], body=match
        ).execute()
        return f"☑ Aufgabe erledigt: '{match['title']}'"
    except Exception as e:
        log.error(f"Task-Complete: {e}")
        return f"Tasks-Fehler: {e}"


# ─────────────────────────────────────────────────────────────────────
#  GMAIL
# ─────────────────────────────────────────────────────────────────────

def gmail_send(to: str, subject: str, body: str) -> str:
    """Sendet eine E-Mail."""
    if not _gmail_service:
        return "Gmail nicht verbunden."
    try:
        import base64
        from email.mime.text import MIMEText
        msg           = MIMEText(body, "plain", "utf-8")
        msg["to"]     = to
        msg["subject"] = subject
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        _gmail_service.users().messages().send(
            userId="me", body={"raw": raw}
        ).execute()
        log.info(f"📧 E-Mail gesendet an {to}: {subject}")
        return f"📧 E-Mail gesendet an {to}"
    except Exception as e:
        log.error(f"Gmail-Send: {e}")
        return f"E-Mail-Fehler: {e}"


def gmail_list_unread(max_results: int = 5) -> str:
    """Zeigt ungelesene E-Mails."""
    if not _gmail_service:
        return "Gmail nicht verbunden."
    try:
        result  = _gmail_service.users().messages().list(
            userId="me", q="is:unread", maxResults=max_results
        ).execute()
        msgs = result.get("messages", [])
        if not msgs:
            return "📧 Keine ungelesenen E-Mails."
        lines = [f"📧 {len(msgs)} ungelesene E-Mail(s):"]
        for m in msgs:
            detail = _gmail_service.users().messages().get(
                userId="me", id=m["id"], format="metadata",
                metadataHeaders=["From", "Subject", "Date"]
            ).execute()
            headers = {h["name"]: h["value"] for h in detail.get("payload", {}).get("headers", [])}
            sender  = headers.get("From",    "?")[:40]
            subject = headers.get("Subject", "(kein Betreff)")[:60]
            lines.append(f"  • Von: {sender}\n    Betreff: {subject}")
        return "\n".join(lines)
    except Exception as e:
        log.error(f"Gmail-List: {e}")
        return f"Gmail-Fehler: {e}"


# ─────────────────────────────────────────────────────────────────────
#  SOFTWARE-WECKER (ohne Google — läuft lokal)
# ─────────────────────────────────────────────────────────────────────

import threading
import time

_alarms: List[dict] = []
_alarm_lock         = threading.Lock()
_alarm_thread       = None
_say_callback       = None   # wird von jarvis_v5_8.py gesetzt
_bot_callback       = None   # (bot, chat_id) für Telegram-Benachrichtigung
_alarm_storage_file = None   # wird nach PATHS-Init gesetzt


def _alarm_storage() -> Path:
    if PATHS and "memory" in PATHS:
        return PATHS["memory"] / "alarms.json"
    return Path("alarms.json")


def _load_alarms():
    global _alarms
    p = _alarm_storage()
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            now  = datetime.now().timestamp()
            # Nur zukünftige Wecker laden
            _alarms = [a for a in data if a.get("ts", 0) > now]
            log.info(f"⏰ {len(_alarms)} Wecker geladen")
        except Exception as e:
            log.warning(f"Wecker laden: {e}")
            _alarms = []


def _save_alarms():
    p = _alarm_storage()
    try:
        p.write_text(json.dumps(_alarms, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        log.warning(f"Wecker speichern: {e}")


def _alarm_loop():
    while True:
        time.sleep(10)
        now = datetime.now().timestamp()
        fired = []
        with _alarm_lock:
            for alarm in list(_alarms):
                if alarm["ts"] <= now:
                    fired.append(alarm)
                    _alarms.remove(alarm)
            if fired:
                _save_alarms()

        for alarm in fired:
            msg = f"⏰ Wecker: {alarm.get('label', 'Zeit!')}"
            log.info(msg)
            if _say_callback:
                try:
                    _say_callback(msg)
                except Exception:
                    pass
            if _bot_callback:
                bot, chat_id = _bot_callback
                if bot and chat_id:
                    try:
                        bot.send_message(chat_id, f"⏰ *Wecker!*\n{alarm.get('label', 'Zeit!')}", parse_mode="Markdown")
                    except Exception:
                        pass


def start_alarm_thread():
    global _alarm_thread
    _load_alarms()
    _alarm_thread = threading.Thread(target=_alarm_loop, daemon=True)
    _alarm_thread.start()
    log.info("⏰ Wecker-Thread gestartet")


def alarm_set(label: str, alarm_dt: datetime) -> str:
    """Setzt einen Wecker."""
    ts = alarm_dt.timestamp()
    if ts <= datetime.now().timestamp():
        return "❌ Wecker-Zeit liegt in der Vergangenheit."
    with _alarm_lock:
        _alarms.append({"ts": ts, "label": label, "set_at": datetime.now().isoformat()})
        _save_alarms()
    time_str = alarm_dt.strftime("%d.%m.%Y %H:%M")
    log.info(f"⏰ Wecker gesetzt: '{label}' um {time_str}")
    return f"⏰ Wecker gesetzt: '{label}' um {time_str}"


def alarm_list() -> str:
    """Zeigt alle gesetzten Wecker."""
    if not _alarms:
        return "⏰ Keine aktiven Wecker."
    lines = [f"⏰ Aktive Wecker ({len(_alarms)}):"]
    for a in sorted(_alarms, key=lambda x: x["ts"]):
        dt = datetime.fromtimestamp(a["ts"])
        lines.append(f"  • {dt.strftime('%d.%m.%Y %H:%M')} — {a.get('label', '?')}")
    return "\n".join(lines)


def alarm_delete(label_keyword: str) -> str:
    """Löscht einen Wecker anhand des Namens."""
    with _alarm_lock:
        before = len(_alarms)
        remaining = [a for a in _alarms if label_keyword.lower() not in a.get("label", "").lower()]
        removed = before - len(remaining)
        _alarms.clear()
        _alarms.extend(remaining)
        if removed:
            _save_alarms()
    if removed:
        return f"🗑️ {removed} Wecker gelöscht."
    return f"Kein Wecker mit '{label_keyword}' gefunden."


# ─────────────────────────────────────────────────────────────────────
#  NATÜRLICHE SPRACHE → DATETIME-PARSER
# ─────────────────────────────────────────────────────────────────────

def parse_datetime_german(text: str) -> Optional[datetime]:
    """
    Parst deutsche Zeitangaben:
    "morgen um 9 Uhr", "in 30 Minuten", "übermorgen 14:30",
    "nächsten Freitag um 18 Uhr", "Montag 10:00"
    """
    now   = datetime.now()
    lower = text.lower().strip()

    # ── Relative Zeiten ───────────────────────────────────────────────
    m = re.search(r"in\s+(\d+)\s*(minuten?|min|stunden?|std|h\b|sekunden?|sek)", lower)
    if m:
        val, unit = int(m.group(1)), m.group(2)
        if "min" in unit:
            return now + timedelta(minutes=val)
        if "stund" in unit or unit in ("std", "h"):
            return now + timedelta(hours=val)
        if "sek" in unit:
            return now + timedelta(seconds=val)

    # ── Tagesangaben ──────────────────────────────────────────────────
    base = now.date()
    if "übermorgen" in lower:
        base = now.date() + timedelta(days=2)
    elif "morgen" in lower:
        base = now.date() + timedelta(days=1)
    elif "heute" in lower:
        base = now.date()
    else:
        # Wochentage
        WDAYS = {
            "montag": 0, "dienstag": 1, "mittwoch": 2, "donnerstag": 3,
            "freitag": 4, "samstag": 5, "sonntag": 6
        }
        for name, wd in WDAYS.items():
            if name in lower:
                days_ahead = (wd - now.weekday()) % 7
                if days_ahead == 0:
                    days_ahead = 7  # Nächste Woche wenn heute
                base = now.date() + timedelta(days=days_ahead)
                break

    # ── Uhrzeit extrahieren ───────────────────────────────────────────
    time_match = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(?:uhr|h\b)?", lower)
    if time_match:
        hour   = int(time_match.group(1))
        minute = int(time_match.group(2)) if time_match.group(2) else 0
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            result = datetime(base.year, base.month, base.day, hour, minute)
            if result < now and base == now.date():
                result += timedelta(days=1)
            return result

    return None


# ─────────────────────────────────────────────────────────────────────
#  INTENT-HANDLER für jarvis_v5_8.py
# ─────────────────────────────────────────────────────────────────────

GOOGLE_INTENTS = {
    r"(?:zeig|nächste[rn]?|meine?)\s*(?:termin|kalender|events?)(?:\s.*)?|was\s*(?:hab|habe)\s*ich\s*(?:heute|morgen|nächste|diese\s*woche)?": "google_calendar_list",
    r"(?:erstell|trag ein|neuer?|neuen?|füg hinzu)\s*(?:termin|event|treffen|meeting)(?:\s.*)?":                                                "google_calendar_create",
    r"(?:lösch|entfern)\s*(?:termin|event)(?:\s.*)?":                                                                                           "google_calendar_delete",
    r"(?:zeig|meine?)\s*(?:aufgaben?|todos?|tasks?)(?:\s.*)?":                                                                                  "google_tasks_list",
    r"(?:erstell|neue?[rn]?|füg hinzu)\s*(?:aufgabe?|todo|task)(?:\s.*)?":                                                                      "google_tasks_create",
    r"(?:erledigt|fertig|abhaken)\s*(?:aufgabe?|task)?(?:\s.*)?":                                                                               "google_tasks_complete",
    r"(?:ungelesene?|neue?)\s*(?:mails?|e-?mails?)(?:\s.*)?|(?:zeig|check)\s*(?:gmail|postfach|mails?)":                                       "google_gmail_list",
    r"(?:schick|sende?|schreib)\s*(?:mail|e-?mail)(?:\s.*)?":                                                                                   "google_gmail_send",
    r"(?:stell|setz|neuer?)\s*(?:wecker|alarm)(?:\s.*)?":                                                                                       "google_alarm_set",
    r"(?:zeig|meine?|aktive?)\s*(?:wecker|alarme?)(?:\s.*)?":                                                                                   "google_alarm_list",
    r"(?:lösch|stopp|entfern)\s*(?:wecker|alarm)(?:\s.*)?":                                                                                     "google_alarm_delete",
    r"google\s*status|google\s*verbindung":                                                                                                      "google_status",
}


def match_google_intent(text: str) -> Optional[str]:
    lower = text.lower()
    for pat, intent in GOOGLE_INTENTS.items():
        if re.search(pat, lower):
            return intent
    return None


def handle_google_intent(intent: str, text: str, say_fn=None) -> str:
    """
    Haupteinsprungpunkt für JARVIS.
    Wird in handle_local() von jarvis_v5_8.py aufgerufen.
    """
    say = say_fn or (lambda t: print(f"JARVIS: {t}"))
    lower = text.lower()

    # ── Wecker ────────────────────────────────────────────────────────
    if intent == "google_alarm_set":
        dt = parse_datetime_german(text)
        if not dt:
            result = "Ich habe die Uhrzeit nicht verstanden. Beispiel: Stell einen Wecker für morgen um 8 Uhr."
        else:
            label = re.sub(
                r"(?:stell|setz|neuen?|wecker|alarm|für|um|uhr|\d+:\d+|\d+\s*uhr)", "", lower
            ).strip() or "Wecker"
            result = alarm_set(label.capitalize(), dt)
        say(result)
        return result

    if intent == "google_alarm_list":
        result = alarm_list()
        say(result)
        return result

    if intent == "google_alarm_delete":
        # Keyword aus Text extrahieren
        kw = re.sub(r"(?:lösch|stopp|entfern|wecker|alarm)", "", lower).strip()
        result = alarm_delete(kw or "")
        say(result)
        return result

    # ── Kalender ──────────────────────────────────────────────────────
    if intent == "google_calendar_list":
        days = 1 if "heute" in lower else 7 if "woche" in lower else 3 if "morgen" in lower else 7
        result = calendar_list_events(days_ahead=days)
        say(result)
        return result

    if intent == "google_calendar_create":
        dt = parse_datetime_german(text)
        if not dt:
            result = "Wann soll der Termin sein? Beispiel: Erstelle Termin Zahnarzt morgen um 14 Uhr."
        else:
            title = re.sub(
                r"(?:erstell|trag ein|neuen?|neuer?|füg hinzu|termin|event|treffen|meeting|am|für|um|uhr|morgen|heute|montag|dienstag|mittwoch|donnerstag|freitag|samstag|sonntag|\d+:\d+|\d+\s*uhr)",
                "", lower
            ).strip().capitalize() or "Termin"
            result = calendar_create_event(title, dt)
        say(result)
        return result

    if intent == "google_calendar_delete":
        kw = re.sub(r"(?:lösch|entfern|termin|event)", "", lower).strip()
        result = calendar_delete_event(kw or "")
        say(result)
        return result

    # ── Tasks ─────────────────────────────────────────────────────────
    if intent == "google_tasks_list":
        result = tasks_list()
        say(result)
        return result

    if intent == "google_tasks_create":
        dt    = parse_datetime_german(text)
        title = re.sub(
            r"(?:erstell|neue?[rn]?|füg hinzu|aufgabe?|todo|task|bis|am|um|fällig)", "", lower
        ).strip().capitalize() or "Neue Aufgabe"
        result = tasks_create(title, due=dt)
        say(result)
        return result

    if intent == "google_tasks_complete":
        kw = re.sub(r"(?:erledigt|fertig|abhaken|aufgabe?|task)", "", lower).strip()
        result = tasks_complete(kw or "")
        say(result)
        return result

    # ── Gmail ─────────────────────────────────────────────────────────
    if intent == "google_gmail_list":
        result = gmail_list_unread()
        say(result)
        return result

    if intent == "google_gmail_send":
        # Einfaches Parsing: "schick mail an test@mail.com Betreff: Hallo Inhalt: ..."
        to_match      = re.search(r"an\s+([\w.@+-]+)", lower)
        subject_match = re.search(r"betreff:?\s*(.+?)(?:inhalt:|text:|$)", text, re.IGNORECASE)
        body_match    = re.search(r"(?:inhalt|text):?\s*(.+)$", text, re.IGNORECASE | re.DOTALL)
        if not to_match:
            result = "Bitte gib eine E-Mail-Adresse an. Beispiel: Schick Mail an beispiel@gmail.com Betreff: Hallo Inhalt: ..."
        else:
            result = gmail_send(
                to      = to_match.group(1),
                subject = subject_match.group(1).strip() if subject_match else "Nachricht von JARVIS",
                body    = body_match.group(1).strip() if body_match else "",
            )
        say(result)
        return result

    # ── Status ────────────────────────────────────────────────────────
    if intent == "google_status":
        result = google_status()
        say(result)
        return result

    return ""
