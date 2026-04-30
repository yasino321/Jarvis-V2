# 🤖 J.A.R.V.I.S — Guardian v3.2

**J**ust **A** **R**ather **V**ery **I**ntelligent **S**ystem

Ein selbst-optimierender KI-Assistent für Windows/Mac/Linux — mit Sprachsteuerung, Telegram-Fernsteuerung, Computer-Control und autonomem Code-Optimizer.

---

## ✨ Features

| Feature | Beschreibung |
|---|---|
| 🧠 **Multi-Brain KI** | Gemini + Groq + Cerebras — automatisches Fallback |
| 🎙️ **Spracherkennung** | Deutsch (de-DE), Mikrofon-Toggle, startet standardmäßig STUMM |
| 💬 **Text-Eingabe** | Direkt in der UI tippen ohne Sprache |
| 📱 **Telegram** | Vollständige Fernsteuerung via eigenem Bot |
| 🖥️ **Computer-Control** | Maus, Tastatur, Screenshots per Sprachbefehl oder Telegram |
| 🔁 **Self-Optimizer** | JARVIS verbessert seinen eigenen Code automatisch (Patch-basiert) |
| 🦅 **OpenClaw** | KI-gestütztes autonomes Ordner-Management |
| 📅 **Google Services** | Kalender, Gmail, Tasks, Keep |
| 🎨 **Anpassbare UI** | Color-Picker, 3 Größenstufen (mini/normal/voll), immer im Vordergrund |
| 💾 **Auto-Backup** | Vor jedem Optimizer-Deploy automatisch gesichert |
| ⚡ **Sofort-Rollback** | Automatischer Rollback bei Fehler, manuell per Befehl |

---

## 📁 Dateistruktur

```
jarvis/
├── jarvis_v5_8.py         ← Hauptdatei — hier starten
├── jarvis_brains.py       ← KI-Backends (Gemini / Groq / Cerebras)
├── jarvis_optimizer.py    ← Self-Optimierungs-Engine
├── jarvis_openclaw.py     ← Autonomes Ordner-Management
├── jarvis_google.py       ← Google-Integration (Kalender etc.)
├── jarvis_fulltest.py     ← Vollständiger Systemtest
├── requirements.txt       ← Alle Python-Abhängigkeiten
├── _env.exemple           ← Konfigurations-Vorlage → zu _env kopieren
├── setup.py               ← Einmal-Setup-Skript
└── README.md
```

> Zur Laufzeit erstellt JARVIS automatisch: `users/default/memory/`, `users/default/backups/`, `users/default/logs/`, `temp_audio/`, `screenshots/`

---

## 🚀 Installation

### 1. Repository klonen

```bash
git clone https://github.com/yasino321/Jarvis-V2
cd Jarvis-V2
cd Jarvis
```

### 2. Automatisches Setup

```bash
python setup.py
```

Das Setup-Skript prüft Python, installiert alle Pakete und erstellt die `_env`-Datei.

> **Alternativ manuell:**
> ```bash
> pip install -r requirements.txt
> (Alternativ: pip install -r requirements.txt --break-system-packages)
> cp _env.exemple _env   # Windows: copy _env.exemple _env
> ```

### 3. API-Keys eintragen

Die Datei `_env` im Texteditor öffnen und mindestens diese drei Keys eintragen:

```env
GEMINI_API_KEY=dein-key
TELEGRAM_TOKEN=dein-bot-token
OWNER_TELEGRAM_ID=deine-telegram-id
```

### 4. Testen & Starten

```bash
# Alles prüfen (empfohlen beim ersten Start)
python jarvis_fulltest.py

# JARVIS starten
python jarvis_v5_8.py
```

---

## 🔑 API-Keys beschaffen

| Service | Wo holen | Pflicht? |
|---|---|---|
| **Google Gemini** | https://aistudio.google.com/apikey | ✅ Ja |
| **Telegram Bot-Token** | Telegram → @BotFather → `/newbot` | ✅ Ja |
| **Telegram User-ID** | Telegram → @userinfobot → `/start` | ✅ Ja |
| Groq | https://console.groq.com/keys | Empfohlen |
| Cerebras | https://cloud.cerebras.ai/ | Empfohlen |

> **Tipp Doppel-Quota:** Ein zweiter Gemini-Key (`GEMINI_API_KEY_2`) mit einem zweiten Google-Account verdoppelt dein tägliches Anfrage-Limit. Bei Rate-Limit wechselt JARVIS automatisch auf KEY_2.

---

## 🖥️ Bedienung

### Terminal-Befehle

```bash
python jarvis_v5_8.py                                          # Normal starten
python jarvis_v5_8.py --selftest                               # Komponenten-Schnelltest
python jarvis_fulltest.py                                      # Vollständiger Systemtest
python jarvis_v5_8.py --help-terminal                          # Alle Befehle anzeigen

# Optimizer direkt aus dem Terminal steuern:
python jarvis_v5_8.py --cmd optimize --goal "Ziel" --duration "2h"
python jarvis_v5_8.py --cmd stop
python jarvis_v5_8.py --cmd status
python jarvis_v5_8.py --cmd rollback
python jarvis_v5_8.py --cmd golden     # Rollback auf Golden Copy
```

### UI-Elemente

| Element | Funktion |
|---|---|
| `🎤` (Button) | Mikrofon ein/aus — startet standardmäßig **STUMM** |
| `⚙` (Button) | Einstellungen: Farben (Color-Picker), Reset |
| `◈` (Button) | Fenstergröße wechseln: mini → normal → voll |
| `✕` (Button) | JARVIS beenden |
| **Eingabefeld** | Text direkt eingeben, Enter oder `▶` zum Senden |
| Titelzeile ziehen | Fenster frei verschieben |
| Ecke rechts unten | Fenstergröße frei anpassen |

### Sprachbefehle (Beispiele)

```
"Optimiere dich für zwei Stunden"
"Stopp"
"Status"
"Screenshot"
"Öffne YouTube und suche nach ..."
"Kalender heute"
"Erinnerung morgen 9 Uhr Meeting"
"Ordner aufräumen"
"Rollback"
"Mikrofon aus"
```

### Telegram-Befehle

```
/status              — Aktueller System-Status
/optimize            — Optimizer starten
/stop                — Optimizer stoppen
/screenshot          — Screenshot an Telegram senden
/rollback            — Letztes Backup einspielen
/golden_rollback     — Auf Golden Copy zurücksetzen
/learning            — Lernprotokoll anzeigen
/reset               — Chat-Memory zurücksetzen
/cmd <befehl>        — Terminal-Befehl ausführen
/run <python-code>   — Python-Code ausführen
/type <text>         — Text am Computer eingeben (Computer-Control)
/click <x> <y>       — Mausklick ausführen
/move <x> <y>        — Maus bewegen
/scroll <n>          — Scrollen (positiv = hoch)
/screen_info         — Bildschirmgröße und Mausposition
/claw                — OpenClaw Ordner-Status
/claw scan           — Ordner KI-analysieren
/confirm_cleanup     — Aufräumen nach Scan bestätigen
```

---

## 🧠 Multi-Brain System

```
┌─────────────────────────────────────────────────────────┐
│  Anfrage / Aufgabe                                      │
└────────────────┬────────────────────────────────────────┘
                 │
         ┌───────▼───────┐
         │  Gemini 2.5   │  ← Haupt-Brain: Konversation,
         │  (Planer)     │    Planung, Bildanalyse
         └───────┬───────┘
           429 / Fehler
                 │
         ┌───────▼───────┐
         │  Groq Llama   │  ← Kritiker: Code-Review,
         │  3.3 70B      │    Fallback-Chat, Whisper-STT
         └───────┬───────┘
           429 / Fehler
                 │
         ┌───────▼───────┐
         │  Cerebras     │  ← Coder: schnelle Code-
         │  llama3.1     │    Generierung im Optimizer
         └───────────────┘
```

Wenn ein Brain ausfällt oder das Tageslimit erreicht, wechselt JARVIS automatisch auf das nächste. Das System läuft auch mit nur einem aktiven Brain.

---

## 🔁 Self-Optimizer

Der Optimizer verbessert JARVIS iterativ und sicher:

1. **Planer** (Gemini) — analysiert Code, wählt konkreten Verbesserungsbereich
2. **Developer** (Cerebras) — generiert chirurgischen Patch (nur die betroffene Funktion)
3. **Reviewer** (Groq) — prüft den Patch vor dem Deploy
4. **Syntax-Check** — automatischer Python-Parse-Test
5. **Deploy + Backup** — Patch eingespielt, bei Fehler: sofortiger Auto-Rollback

```bash
# 2 Stunden optimieren
python jarvis_v5_8.py --cmd optimize --goal "Performance verbessern" --duration "2h"

# Status prüfen (aus anderem Terminal)
python jarvis_v5_8.py --cmd status

# Stoppen
python jarvis_v5_8.py --cmd stop
```

---

## 🦅 OpenClaw — Ordner-Management

OpenClaw hält deinen JARVIS-Ordner automatisch sauber:

- KI analysiert alle Dateien (Gemini → Groq → Cerebras Fallback)
- Whitelist schützt wichtige Dateien (jarvis_*.py, _env, etc.)
- Temp-Dateien, alte Outputs → `Müll/` (wiederherstellbar per `/restore`)
- Bestätigung vor destruktiven Aktionen konfigurierbar

```
# Via Telegram:
/claw            → Status anzeigen
/claw scan       → Ordner analysieren und Vorschlag zeigen
/confirm_cleanup → Analyse ausführen
```

---

## 📅 Google Services einrichten (optional)

Für Kalender, Gmail, Tasks:

1. [Google Cloud Console](https://console.cloud.google.com) → Neues Projekt
2. APIs aktivieren: **Calendar API**, **Tasks API**, **Gmail API**
3. OAuth 2.0 Credentials (Typ: Desktop App) erstellen
4. `credentials.json` herunterladen → in den JARVIS-Ordner legen
5. Beim ersten Start öffnet sich der Browser → Google-Konto auswählen
6. `token.json` wird automatisch gespeichert (kein Passwort mehr nötig)

---

## 🎨 UI anpassen

Klick auf `⚙` öffnet das Einstellungs-Fenster:

- Farben für alle UI-Elemente (Hauptfarbe, Hintergrund, Grün, Rot, Gelb, Orange)
- Live-Preview beim Tippen, Color-Picker-Dialog per „Pick"-Button
- Reset-Button für Standard-Farben (Iron-Man-Blau)
- Einstellungen werden in `users/default/memory/ui_colors.json` gespeichert

---

## ⚙️ Vollständige Konfiguration (`_env`)

```env
# ── PFLICHT ───────────────────────────────────────────────────
GEMINI_API_KEY=
GEMINI_API_KEY_2=          # Optionaler 2. Key → doppeltes Tageslimit
TELEGRAM_TOKEN=
OWNER_TELEGRAM_ID=

# ── KI-BACKENDS ───────────────────────────────────────────────
GROQ_API_KEY=
CEREBRAS_API_KEY=

# ── COMPUTER-CONTROL ──────────────────────────────────────────
ACE_FAILSAFE=true           # Maus in Ecke oben-links = Notfall-Stop
ACE_PAUSE=0.05              # Pause zwischen pyautogui-Aktionen

# ── OPENCLAW ──────────────────────────────────────────────────
OPENCLAW_MANAGED_DIR=.      # Welcher Ordner verwaltet wird
OPENCLAW_TRASH_DIR=Müll     # Wohin archiviert wird
OPENCLAW_AUTO_CLEANUP=true
OPENCLAW_CONFIRM_DESTRUCTIVE=true

# ── OPTIMIZER ─────────────────────────────────────────────────
OPT_MAX_LINES=3500
OPT_ITERATION_PAUSE=8       # Sekunden zwischen Iterationen

# ── SONSTIGES ─────────────────────────────────────────────────
JARVIS_VOICE=de-DE-ConradNeural
USER_ID=default
MESHTASTIC_ENABLED=false
```

---

## 🆘 Fehlerbehebung

### JARVIS startet nicht

```bash
python jarvis_v5_8.py --selftest
# oder vollständig:
python jarvis_fulltest.py
```

### Mikrofon funktioniert nicht

JARVIS startet standardmäßig **STUMM** — auf `🎤` klicken oder sagen „Mikrofon an".

```bash
# Bei echten Mikrofon-Problemen:
pip install pyaudio
# Linux: sudo apt-get install python3-pyaudio portaudio19-dev
# Mac: brew install portaudio && pip install pyaudio
```

### tkinter fehlt (Linux)

```bash
sudo apt-get install python3-tk
```

### Optimizer macht Fehler → Rollback

```bash
python jarvis_v5_8.py --cmd rollback
# oder via Telegram: /rollback
```

### Gemini-Tageslimit erreicht

Kein manueller Eingriff nötig — JARVIS wechselt automatisch auf Groq/Cerebras.
Nach 24h wird Gemini automatisch wieder aktiviert.

---

## 🏗️ Architektur

```
jarvis_v5_8.py  (Hauptdatei)
│   UI, Intent-Router, Telegram, Spracherkennung, TTS,
│   Computer-Control, Selftest, Rollback-Logik
│
├── import jarvis_brains     → KI-Calls, Blackout-Guard, Smart-Router
├── import jarvis_optimizer  → Self-Optimierungs-Engine (Patch-basiert)
├── import jarvis_openclaw   → KI-Ordner-Management
└── import jarvis_google     → Google Kalender / Gmail / Tasks
```

Alle Module erhalten ihre Konfiguration (API-Clients, PATHS, etc.) nach dem Import aus der Hauptdatei gesetzt — kein zirkulärer Import, kein globaler State außerhalb der Hauptdatei.

---

## 📜 Changelog

### v5.8 / Guardian v3.2
- **Bugfix:** `create_deployment_backup` NameError behoben (Optimizer-Crash beim Deploy)
- **Neu:** Mikrofon startet standardmäßig STUMM, Status immer in Titelzeile sichtbar
- **Neu:** Text-Eingabefeld direkt in der UI (kein Mikrofon nötig)
- **Neu:** Color-Picker / Settings-Fenster (`⚙`-Button)
- **Schneller:** Optimizer-Delays reduziert (2s statt 8s nach Erfolg)
- **Robuster:** Syntax-Fix mit Groq-Fallback wenn Cerebras Token-Limit erreicht

### v5.8 / Guardian v3.1
- Computer-Control via pyautogui
- Telegram: `/screenshot`, `/type`, `/click`, `/run`
- Optimizer: Patch-basiert (nicht mehr Full-Rewrite)
- Auto-Rollback bei Syntaxfehler

---

*JARVIS Guardian v3.2 — Python 3.10+*
