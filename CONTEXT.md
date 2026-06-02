# Job Hunter Agent – Domain Language

> Glossar der Fachbegriffe. Keine Implementierungsdetails.
> Erstellt: 2026-06-01 – grill-with-docs Session

---

## Bullet Point

Eine kompakte, ergebnisorientierte Aussage über eine berufliche Leistung. Struktur gemischt – entweder _Ergebnis → Methode → Kontext_ oder _Aktion → Ergebnis → Technologie_, je nachdem was für die Zielstelle stärker wirkt.

**Nicht zu verwechseln mit:** Aufzählungspunkt in UI-Listen (Itemize-Item).

## Bullet Pool

Eine kuratierte Sammlung von 43 Bullet Points, organisiert in 6 Kompetenz-Kategorien. Der Pool ist die einzige Quelle für CV-Inhalte. Der Agent wählt daraus per Keyword-Matching aus, generiert keine neuen Bullets.

## Kompetenz-Kategorie

Eine von sechs thematischen Gruppen im Bullet Pool:
1. **UX/UI Design & Research** – Designsysteme, Prototyping, Usability-Tests, IA
2. **Product Ownership & Agile** – Scrum, Backlog, Requirements, Teamführung
3. **Tech & KI-Entwicklung** – FastAPI, Docker, LLMs, Full-Stack
4. **Motion Design & Video** – After Effects, Explainer, AI-Video
5. **Web & CMS** – WordPress, Webflow, SEO, Landingpages
6. **KI/ML & Automation** – Prompt Engineering, ComfyUI, AI-Agent, n8n

## Keyword-Matching (Bullet-Selektion)

Verfahren, mit dem der Agent aus dem Bullet Pool die 8-12 relevantesten Bullets für eine Stelle auswählt. Keywords aus der Job-Beschreibung werden gegen den Bullet-Text gematcht. Höhere Übereinstimmung = höhere Priorität im CV.

## Anschreiben (Cover Letter)

Ein personalisiertes Bewerbungsschreiben mit folgender Struktur:
1. Absender-Block (Name, Kontakt, Portfolio)
2. Empfänger (Firma, Ort)
3. Betreff + Datum
4. Einleitung (persönlich, kein Agent-Bezug)
5. 8020-Ergebnisse (2-3 Bullets aus dem Pool)
6. Warum dieses Unternehmen (1-2 Sätze)
7. Gehaltsvorstellung (fest, nicht variabel)
8. Signatur
9. Footer: "Erstellt mit meinem eigenen KI-Bewerbungs-Agenten"

## Firmenbezug

1-2 Sätze im Anschreiben, die spezifisch auf das Zielunternehmen eingehen. Nicht tiefer recherchiert – entspricht dem Stil der existierenden Templates (peerigon.tex, makandra.tex etc.).

## Agent-Disclaimer

Hinweis im Footer des Anschreibens und CVs: "Erstellt mit meinem eigenen KI-Bewerbungs-Agenten – entwickelt und betrieben von Daniel Peters." Erscheint NUR im Footer, nicht im Fließtext.

## CV-Variante

Eine von 8 LaTeX-Vorlagen (`data/cv/*.tex`). Alle Varianten teilen dieselbe Struktur (Header, Erfahrung, Skills, Ausbildung, Sprachen, Footer) und unterscheiden sich nur durch die per Keyword-Matching ausgewählten Bullet Points. Die Varianten-Namen (backend, frontend, etc.) sind historisch – in der aktuellen Version sind alle CVs strukturell identisch.

## Sprach-Erkennung

Heuristik: >50% deutsche Wörter in der Job-Beschreibung → deutsches Anschreiben. >50% englische Wörter → englisches Anschreiben. 50/50 → Deutsch (Default).

## Job-Profil

Die vom Go-API-Endpoint `/api/v1/evaluate` zurückgegebene Bewertung einer Stelle. Enthält: Match-Score (0-10), Begründung, ausgewählte CV-Variante, Sprache, generiertes Anschreiben.

## 8020 Consulting

Das Unternehmen, bei dem Daniel Peters von Oktober 2022 bis November 2025 als Management Consultant, Product Designer und Scrum Master gearbeitet hat. Die Bullet Points zu 8020 sind der Kern des CVs.

## KI-Bewerbungs-Agent

Ein von Daniel Peters selbst entwickeltes, vollautonomes System zum Job-Hunting. Tech-Stack: Python 3.12, async/await, httpx, aiogram, aiosqlite, rocketry, aiosmtplib, jinja2. Der Agent scraped Jobs, matcht Profile, generiert Anschreiben und CVs, kompiliert PDFs und versendet E-Mails.
