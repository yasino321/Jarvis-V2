# Changelog — J.A.R.V.I.S

Alle wichtigen Änderungen werden hier dokumentiert.

---

## [v5.8 / Guardian v3.2] — 2026-05

### 🐛 Bugfixes
- **`create_deployment_backup` NameError behoben** — Funktion fehlte als eigenständige `def`, verwaiste Code-Zeilen in `backup_all_modules()` entfernt. Der Optimizer crashte beim Deploy.

### ✨ Neue Features
- **Mikrofon startet standardmäßig STUMM** — `mic_on = False` als Standard; Status in der Titelzeile immer sichtbar (`| STUMM` rot / `| BEREIT` grün)
- **Text-Eingabefeld in der UI** — Direktes Tippen ohne Sprache; Enter oder `▶`-Button zum Senden; in `normal`- und `voll`-Modus sichtbar
- **Color-Picker / Settings-Fenster** — `⚙`-Button öffnet Einstellungen; Live-Preview für alle UI-Farben; Reset auf Standardfarben; Farben in `memory/ui_colors.json` gespeichert

### ⚡ Verbesserungen
- **Optimizer schneller** — Developer-Retry-Sleep: 5s → 2s; Erfolgs-Sleep: 8s → 2s; Fehler-Sleep: 12s → 6s
- **Reviewer-Tokens** — 200 → 150 (kaum Qualitätsverlust, spürbar schneller)
- **Syntax-Fix robuster** — Cerebras Token-Limit 32000 → 8192; Groq als automatischer Fallback bei Cerebras-400-Fehler

---

## [v5.8 / Guardian v3.1] — Vorgänger

### Features
- Computer-Control: Maus, Tastatur, Screenshots (pyautogui)
- Telegram: Robustere Fehlerbehandlung, Auto-Reconnect
- Telegram: `/screenshot`, `/type`, `/click`, `/run` Befehle
- Optimizer: Besseres Prompt-Engineering, höhere Erfolgsrate
- Optimizer: Rollback bei Syntaxfehler sofort automatisch
- Startup-Check: Fehlende Pakete werden klar gemeldet

---

## Frühere Versionen

- **v5.7** — OpenClaw Ordner-Management eingeführt
- **v5.6** — Multi-Brain System (Gemini + Groq + Cerebras)
- **v5.5** — Self-Optimizer v2.0 (Patch-basiert, nicht mehr Full-Rewrite)
- **v5.0** — Google Services Integration
- **v4.x** — Telegram-Integration
- **v3.x** — Spracherkennung + Edge-TTS
- **v2.x** — Erste Gemini-Integration
- **v1.x** — Basis-Assistent
