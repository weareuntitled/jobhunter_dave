# JobHunter Dave Bot

> Autonomer KI-Bewerbungs-Agent für Job-Suche, CV-Generierung und Bewerbungs-Automation.
> Built by Daniel Peters, betrieben via Telegram.

![Stack](https://img.shields.io/badge/Python-3.12-blue)
![Stack](https://img.shields.io/badge/aiogram-3.x-0099CC)
![Stack](https://img.shields.io/badge/LaTeX-tectonic-008080)
![License](https://img.shields.io/badge/license-Proprietary-red)

---

## Was macht der Bot?

**JobHunter Dave** scraped automatisch Jobs (LinkedIn, Stepstone, Indeed), matcht sie gegen Daniels Profil, generiert massgeschneiderte CVs + Anschreiben und versendet Bewerbungen per E-Mail. Komplett autonom, vom Scan bis zum PDF im Postfach.

### Pipeline

```
Job Scraping → Filter & Ranking → Bullet-Selektion (Keyword-Match)
  → CV-Generierung (LaTeX) → Anschreiben (LLM) → PDF-Compile (tectonic)
  → E-Mail-Versand (SMTP)
```

### Features

- **Telegram-Interface**: komplette Steuerung via Bot, keine CLI
- **Bullet-Pool-Selection**: 43 kuratierte Bullet Points, gewichtet per Keyword-Matching auf die Stelle
- **CV-Generierung**: 8 LaTeX-Varianten + dynamische Skill-Selektion
- **Anschreiben-Generierung**: LLM- oder Template-basiert (offline-fähig), mit Firmenbezug und Gehaltsvorstellung
- **PDF-Kompilierung**: tectonic, saubere Übergänge, keine Layout-Warnungen
- **Multi-Source-Scraping**: LinkedIn, Stepstone, Indeed mit Deduplication
- **JobHunter Dave Bot**: sich selbst als erstes Bullet in der UNTITLED UX Section, damit klar ist dass die Bewerbung mit dem Bot geschrieben wurde

---

## Stack

| Layer       | Tech                                             |
|-------------|--------------------------------------------------|
| Bot         | `aiogram` 3.x (async Telegram)                   |
| HTTP        | `httpx` (async, http2)                           |
| Database    | `aiosqlite` (jobs, applications)                 |
| Scheduling  | `rocketry` (cron-like jobs)                      |
| E-Mail      | `aiosmtplib` (async SMTP + SSL)                  |
| Templates   | `jinja2` (CV/cover letter)                       |
| PDF         | `tectonic` (LaTeX → PDF)                         |
| LLM         | OpenRouter / DeepSeek / OpenAI / Anthropic       |
| Config      | YAML + pydantic                                  |
| Tests       | `pytest` (89+ Tests, davon 15 PDF-Compile-Tests) |

---

## Setup

### Voraussetzungen

- Python 3.12+
- [tectonic](https://tectonic-typesetting.github.io/) (LaTeX-Compiler)
- Telegram Bot Token (via @BotFather)
- SMTP-Credentials (z.B. mailbox.org, Gmail mit App-Password)

### Installation

```bash
git clone git@github.com:weareuntitled/jobhunter_dave.git
cd jobhunter_dave
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Konfiguration

```bash
cp .env.example .env
# .env mit echten Werten füllen:
# - TELEGRAM_BOT_TOKEN
# - TELEGRAM_CHAT_ID
# - SMTP_HOST, SMTP_USER, SMTP_PASSWORD
# - Optional: OPENROUTER_API_KEY, DEEPSEEK_API_KEY
```

**Wichtig:** `.env` ist in `.gitignore` und wird niemals committed.

### Start

```bash
PYTHONPATH=. python -m src.main
```

Bot ist live, antwortet auf `/start` in Telegram.

### Docker

```bash
docker compose up -d
```

---

## Projektstruktur

```
src/
├── main.py                    # Entry Point
├── agent/
│   ├── bullet_selector.py    # Keyword-Match gegen Bullet-Pool
│   ├── llm_client.py          # OpenRouter / DeepSeek / OpenAI / Anthropic
│   └── cover_letter.py        # Anschreiben-Generierung
├── telegram/
│   ├── bot.py                 # aiogram Bot Setup
│   ├── routers/
│   │   └── hunt.py            # /hunt, /generate, /send Commands
│   └── formatters.py          # LaTeX escaping + Telegram Markdown
├── latex/
│   ├── compiler.py            # tectonic wrapper
│   └── templates/             # .tex Vorlagen
├── scraper/                   # LinkedIn, Stepstone, Indeed
├── database/                  # aiosqlite models + queries
├── sender/                    # SMTP + cover letter bundling
└── scheduler/                 # rocketry jobs

data/
├── bullet_pool.yaml           # 43 kuratierte Bullet Points (6 Kategorien)
├── config.yaml                # Static Skills, Gehaltsvorstellung, etc.
├── cv/                        # 8 LaTeX CV-Varianten
├── samples/                   # Cover-Letter-Beispiele
└── master_profile.md          # Daniels vollständiger Werdegang

tests/
├── test_cv_*.py               # 60+ CV-Tests (Layout, Skills, Bullets)
├── test_cover_letter.py       # 23 Anschreiben-Tests
└── test_cv_pdf_compile.py     # 15 PDF-Compile-Tests mit tectonic
```

---

## Entwicklung

### Tests

```bash
# Alle Tests
PYTHONPATH=. pytest tests/ -v

# Nur PDF-Compile-Tests (brauchen tectonic)
PYTHONPATH=. pytest tests/test_cv_pdf_compile.py -v

# Nur CV-Layout-Tests
PYTHONPATH=. pytest tests/test_cv_layout.py -v
```

**89+ Tests** inkl. Layout-Validierung, Bullet-Selektion, Anschreiben-Templates, PDF-Kompilierung mit Warning-Checks.

### Linting

```bash
ruff check src/ tests/
mypy src/
```

### Bullet-Pool erweitern

Neue Bullets in `data/bullet_pool.yaml` ergänzen, mit `employer: "8020"` oder `"untitled"` oder `"both"`:

```yaml
ux_ui_design:
  - employer: "8020"
    text: "Neuer Bullet -- von Was bis Impact, Harvard-Style."
```

Selektion passiert automatisch per Keyword-Match auf den Job-Title und -Description.

---

## Sicherheit

- **Niemals** echte Secrets in `.env.example` committen
- **Immer** `.env` lokal halten und in `.gitignore` belassen
- Bei versehentlichem Leak: Token sofort beim Provider revoked/regenerieren, dann `git commit --amend` + `git push --force`
- Siehe `CONTEXT.md` für die Domain-Sprache und Architektur-Entscheidungen

---

## Lizenz

Proprietär. © 2026 UNTITLED UX. Alle Rechte vorbehalten.

Kein öffentlicher Use ohne explizite Erlaubnis. Issue-Tracker und Diskussionen sind trotzdem willkommen.

---

## Autor

**Daniel Peters** — UX/UI Designer, AI Product Specialist, [untitled-ux.de](https://untitled-ux.de)

Entwickelt JobHunter Dave als autonomen Sidekick für die eigene Job-Suche. Die Bullets im CV sind alle echt, die Pipeline ist real, der Bot ist im produktiven Einsatz.
