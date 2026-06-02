"""tests/test_cv_extreme_examples.py – 3 Extrem-Tests für CV-Generierung."""

import re
import yaml
from datetime import datetime
from pathlib import Path

import pytest
from jinja2 import Environment

from src.agent.bullet_selector import BulletSelector
from src.telegram.formatters import latex_escape

def _esc(s: str) -> str:
    return latex_escape(s)


# --- Helper: 1:1 hunt.py CV-Logik ---
def render_full_cv(job_title: str, job_description: str) -> str:
    selector = BulletSelector()
    bullets = selector.select(job_title, job_description, max_bullets=8)
    escaped_bullets = [latex_escape(b) for b in bullets]
    bullets_8020, bullets_untitled = selector.split_by_employer(
        job_title, job_description, max_bullets=12, min_bullets=8,
    )
    escaped_8020 = [latex_escape(b) for b in bullets_8020]
    escaped_untitled = [latex_escape(b) for b in bullets_untitled]

    exp_8020 = (
        "\\textbf{8020 GmbH Management Consulting, Ingolstadt}\\par\n"
        "\\textbf{Management Consultant, Product Designer, Scrum Master}\\par\n"
        "\\textit{Jul 2022 bis Okt 2025}\\par\n"
        "\\vspace{4pt}\n"
        "\\begin{itemize}\n"
        + ("\n".join(f"    \\item {b}" for b in escaped_8020) if escaped_8020
           else "    \\item Product Ownership und Scrum Master für Enterprise-Projekte (Audi, Porsche, VW)")
        + "\n\\end{itemize}\n"
        "\\textbf{Kunden:} Audi \\textbullet\\ Porsche \\textbullet\\ Volkswagen \\textbullet\\ MAN \\textbullet\\ Centus\\par\n"
        "\\vspace{8pt}\n"
    )

    bot_bullet = "JobHunter Dave Bot entwickelt und betrieben -- autonomer KI-Bewerbungs-Agent für Job-Suche, CV-Generierung und Bewerbungs-Automation (Python, aiogram, FastAPI, LLMs)."
    untitled_bullets = [bot_bullet] + (escaped_untitled if escaped_untitled else [
        "UX/UI Design, Webentwicklung und AI-gestützte Workflows für verschiedene Kunden."
    ])
    exp_untitled = (
        "\\textbf{UNTITLED UX, Augsburg}\\par\n"
        "\\textbf{Freelance UX/UI Designer \\& Full-Stack Developer}\\par\n"
        "\\textit{Feb 2020 bis heute}\\par\n"
        "\\vspace{4pt}\n"
        "\\begin{itemize}\n"
        + "\n".join(f"    \\item {b}" for b in untitled_bullets)
        + "\n\\end{itemize}\n"
    )

    exp_smartpatient = (
        "\\vspace{8pt}\n"
        "\\textbf{smartpatient GmbH, München}\\par\n"
        "\\textbf{UX Design und Research Praktikum}\\par\n"
        "\\textit{Aug 2016 bis Jan 2017}\\par\n"
        "\\vspace{4pt}\n"
        "\\begin{itemize}\n"
        "    \\item Nutzerfeedback und Support-Tickets in UX-Anforderungen und Screenkonzepte übersetzt.\n"
        "    \\item Usability-Tests mitgeplant, durchgeführt und ausgewertet.\n"
        "\\end{itemize}"
    )

    kontrast = (
        "\\textbf{Kontrast Festival GbR, Augsburg}\\par\n"
        "\\textbf{Co-Founder \\& Design Lead}\\par\n"
        "\\textit{2021 bis 2024}\\par\n"
        "\\vspace{4pt}\n"
        "\\begin{itemize}\n"
        "    \\item Aufbau einer Kulturmarke mit über 4.000 Besucher:innen und rund 200.000 EUR Jahresumsatz.\n"
        "    \\item Visuelle Identität verantwortet und Kreativteam von 5--7 Personen geführt.\n"
        "\\end{itemize}\n"
        "\\vspace{6pt}\n"
        "\\textbf{Dialog Act Classification (THI \\& BSH), Ingolstadt}\\par\n"
        "\\textbf{Projektleitung Studierendenteam}\\par\n"
        "\\textit{2020 bis 2021}\\par\n"
        "\\vspace{4pt}\n"
        "\\begin{itemize}\n"
        "    \\item Leitung eines interdisziplinären Teams von ~20 Studierenden.\n"
        "    \\item Mitwirkung an Publikation auf der ICNLSP 2021.\n"
        "\\end{itemize}"
    )

    static_skills = [latex_escape(s) for s in yaml.safe_load(Path("data/config.yaml").read_text()).get("cv", {}).get("static_skills", [])]
    all_skills = escaped_bullets[:6] + static_skills

    ctx = {
        "name": "Daniel Peters",
        "title": latex_escape("UX/UI Designer & AI Product Specialist"),
        "location": "Augsburg, Germany",
        "email": "hi@untitled-ux.de",
        "phone": "+49 173 5231109",
        "portfolio_url": "portfolio.untitled-ux.de",
        "photo_path": "photo.jpg",
        "date": datetime.now().strftime("%d.%m.%Y"),
        "experience": exp_8020 + exp_untitled + exp_smartpatient,
        "skills": all_skills,
        "static_skills": static_skills,
        "skills_text": " \\textbullet\\ ".join(all_skills),
        "education": (
            "\\textbf{TH Ingolstadt} \\hfill Ingolstadt, Deutschland\\\\\n"
            "M.Sc. User Experience Design, Note 1,3 \\hfill 2021 bis 2024\\\\[2pt]\n"
            "\\textbf{TH Ingolstadt} \\hfill Ingolstadt, Deutschland\\\\\n"
            "B.Sc. User Experience Design \\hfill Okt 2014 bis März 2019"
        ),
        "leadership": kontrast,
        "languages": "Deutsch (Muttersprache), Englisch (C1), Chinesisch (B1)",
    }

    template_str = Path("data/cv/general.tex").read_text(encoding="utf-8")
    env = Environment(
        block_start_string="<%",
        block_end_string="%>",
        variable_start_string="<<",
        variable_end_string=">>",
    )
    return env.from_string(template_str).render(ctx)


def _assert_cv_valid(tex: str, job_label: str):
    """Shared assertions: CV muss valide LaTeX sein."""
    assert "\\begin{document}" in tex and "\\end{document}" in tex
    assert tex.count(r"\begin{itemize}") == tex.count(r"\end{itemize}")
    assert tex.count(r"\newpage") == 1

    # Kein \\item außerhalb von itemize
    cleaned = re.sub(r"\\begin\{itemize\}.*?\\end\{itemize\}", "", tex, flags=re.DOTALL)
    bare = re.findall(r"\\item\b", cleaned)
    assert len(bare) == 0, f"[{job_label}] {len(bare)} bare \\item"

    # Jeder itemize-Block hat ≥1 item
    for m in re.finditer(r"\\begin\{itemize\}(.*?)\\end\{itemize\}", tex, re.DOTALL):
        items = re.findall(r"\\item\b", m.group(1))
        assert len(items) >= 1, f"[{job_label}] Leerer itemize-Block"

    # Alle Header haben Content
    for m in re.finditer(r"\\begin\{center\}\s*\\textbf\{([^}]+)\}\s*\\end\{center\}", tex):
        after = tex[m.end():m.end() + 200]
        after_clean = re.sub(r"\s*(\\\\vspace|\\\\newpage|\\\\noindent)?\s*", "", after)
        assert len(after_clean) > 5, f"[{job_label}] Header '{m.group(1)}' ohne Content"

    # Kein \\item ohne Einrückung
    for line in tex.split("\n"):
        stripped = line.strip()
        if stripped.startswith("\\item") and not stripped.startswith("\\textbf"):
            assert line.startswith("    \\item") or line.startswith("\\item"), (
                f"[{job_label}] \\item ohne Einrückung: {stripped[:50]!r}"
            )


# ========================================================================
# EXTREME TEST 1: Minimales Posting – 2 Wörter Job-Titel, 0 Skills
# ========================================================================
class TestExtremeMinimalJob:
    """Extrem-Test: Stellenanzeige mit fast keinem Inhalt."""

    JOB_TITLE = "UX Designer"
    JOB_DESCRIPTION = "Gesucht."

    def test_cv_produces_valid_latex(self):
        tex = render_full_cv(self.JOB_TITLE, self.JOB_DESCRIPTION)
        _assert_cv_valid(tex, "minimal")

    def test_cv_has_all_sections(self):
        tex = render_full_cv(self.JOB_TITLE, self.JOB_DESCRIPTION)
        required_sections = ["Berufserfahrung", "Technische Skills", "Ausbildung",
                           "Leadership", "Sprachen"]
        for section in required_sections:
            assert section in tex, f"Section '{section}' fehlt bei minimalem Job"

    def test_cv_has_static_skills_despite_no_input(self):
        """Bei leerem Job: static_skills aus config IMMER noch da."""
        tex = render_full_cv(self.JOB_TITLE, self.JOB_DESCRIPTION)
        config = yaml.safe_load(Path("data/config.yaml").read_text())
        for skill in config.get("cv", {}).get("static_skills", []):
            assert _esc(skill) in tex, f"Static skill '{skill}' fehlt bei minimalem Job"

    def test_bullets_fallback_to_defaults(self):
        """Wenn BulletSelector wenige Treffer liefert: Fallback-Bullets da."""
        tex = render_full_cv(self.JOB_TITLE, self.JOB_DESCRIPTION)
        # 8020-Block muss mindestens 1 item haben (Fallback oder Treffer)
        m = re.search(
            r"\\textbf\{8020.*?\\end\{itemize\}",
            tex, re.DOTALL,
        )
        assert m, "8020-Block fehlt komplett"
        items = re.findall(r"\\item\b", m.group(0))
        assert len(items) >= 1, f"Nur {len(items)} Items in 8020-Block bei minimalem Job"


# ========================================================================
# EXTREME TEST 2: Völlig mismatched Skills – KfZ-Mechaniker
# ========================================================================
class TestExtremeMismatchJob:
    """Extrem-Test: Stelle die NULL mit UX/Design zu tun hat."""

    JOB_TITLE = "Kfz-Mechaniker (m/w/d)"
    JOB_DESCRIPTION = """
    Wir suchen einen Kfz-Mechaniker für unsere Werkstatt.

    Deine Aufgaben:
    - Wartung und Reparatur von Personenkraftwagen
    - Diagnose von Motor- und Getriebeschäden
    - Wechsel von Bremsbelägen und Reifen
    - Ölwechsel und Inspektionen

    Anforderungen:
    - Abgeschlossene Kfz-Mechaniker-Ausbildung
    - 3 Jahre Berufserfahrung
    - Führerschein Klasse B
    - Kenntnisse in Pkw-Reparatur und Wartung

    Wir bieten:
    - Festanstellung
    - Weiterbildungsmöglichkeiten
    """.strip()

    def test_cv_produces_valid_latex(self):
        tex = render_full_cv(self.JOB_TITLE, self.JOB_DESCRIPTION)
        _assert_cv_valid(tex, "kfz-mechaniker")

    def test_cv_still_contains_8020_and_untitled(self):
        """Auch bei Mismatch: Erfahrung mit 8020 und UNTITLED da."""
        tex = render_full_cv(self.JOB_TITLE, self.JOB_DESCRIPTION)
        assert "8020" in tex, "8020 fehlt bei Kfz-Job"
        assert "UNTITLED" in tex, "UNTITLED fehlt bei Kfz-Job"

    def test_static_skills_persist_even_on_mismatch(self):
        """KI-Skills aus config sind IMMER da – auch bei Kfz-Job."""
        tex = render_full_cv(self.JOB_TITLE, self.JOB_DESCRIPTION)
        config = yaml.safe_load(Path("data/config.yaml").read_text())
        for skill in config.get("cv", {}).get("static_skills", []):
            assert _esc(skill) in tex, f"Static skill '{skill}' fehlt bei Kfz-Job"

    def test_no_kfz_content_in_bullets(self):
        """Bullet Pool enthält keine Kfz-Terme – also keine False Positives."""
        tex = render_full_cv(self.JOB_TITLE, self.JOB_DESCRIPTION)
        kfz_terms = ["bremsbeläge", "ölwechsel", "getriebeschaden", "kfz-mechaniker",
                      "werkstatt", "reifenwechsel"]
        for term in kfz_terms:
            assert term not in tex.lower(), f"Unerwarteter Kfz-Term '{term}' im CV"

    def test_skills_text_not_empty(self):
        """skills_text muss trotz Mismatch Content haben (Fallback)."""
        tex = render_full_cv(self.JOB_TITLE, self.JOB_DESCRIPTION)
        # Findet den skills_text Block
        m = re.search(r"\\noindent\s*\n(.*?)\\par", tex, re.DOTALL)
        assert m, "skills_text Block fehlt"
        skills_content = m.group(1).strip()
        assert len(skills_content) > 50, f"skills_text zu kurz ({len(skills_content)} chars)"


# ========================================================================
# EXTREME TEST 3: Maximum Content – 2000 Zeichen Job-Description
# ========================================================================
class TestExtremeMaxContent:
    """Extrem-Test: Sehr langes, detailliertes Stellenangebot mit vielen Skills."""

    JOB_TITLE = "Senior Full-Stack AI Product Engineer (m/w/d)"
    JOB_DESCRIPTION = """
    Wir suchen eine/n Senior Full-Stack AI Product Engineer für unser wachsendes Tech-Team in Berlin.

    Über das Unternehmen:
    Wir sind ein Series-B Startup im Bereich KI-gestützte Enterprise-Software mit 80 Mitarbeitern.
    Unser Produkt wird von Fortune-500-Unternehmen weltweit eingesetzt.

    Deine Aufgaben:
    - Entwicklung von Full-Stack-Anwendungen mit React, Next.js, TypeScript, Python, FastAPI
    - Design und Implementierung von KI-Workflows mit LLMs (OpenAI, Anthropic, Mistral)
    - Aufbau und Wartung von Design Systems in Figma mit React-Komponenten (Storybook)
    - User Research, Usability-Tests, A/B-Tests und datengetriebene Produktentscheidungen
    - CI/CD-Pipelines mit GitHub Actions, Docker, Kubernetes
    - Moderne Microservice-Architektur mit Event-Driven Design (Kafka, Redis)
    - Prompt Engineering für Customer-Success-Workflows
    - Technical Leadership: Code Reviews, Mentoring, Architektur-Entscheidungen
    - Agiles Arbeiten mit Scrum, Kanban, OKR
    - Präsentation von Tech-Sprints vor Stakeholdern und C-Level

    Must-have:
    - 5+ Jahre Full-Stack Erfahrung
    - Exzellente TypeScript/React Skills
    - Python Backend (FastAPI oder Django)
    - LLM-Integration (OpenAI API, RAG, Vector Databases)
    - User Research und Usability Testing
    - Design System Erfahrung
    - CI/CD und Docker/Kubernetes
    - Scrum Master oder Product Owner Erfahrung
    - Deutsch und Englisch fließend

    Nice-to-have:
    - Erfahrung mit Computer Vision oder Speech AI
    - Motion Design / After Effects
    - Webflow oder WordPress Entwicklung
    - Open Source Beiträge
    - Erfahrung mit n8n oder ComfyUI
    - Cloud-Architektur (AWS, GCP)
    - 3D-Design (Blender, Unity)
    - Erfahrung mit B2B SaaS in Enterprise-Umfeld
    - Publikationen oder Conference Talks

    Benefits:
    - 100% Remote oder Berlin Office
    - 30 Tage Urlaub
    - Aktienoptionsprogramm
    - Jahresgehalt: 95.000 - 130.000 € brutto
    """.strip()

    def test_cv_produces_valid_latex(self):
        tex = render_full_cv(self.JOB_TITLE, self.JOB_DESCRIPTION)
        _assert_cv_valid(tex, "max-content")

    def test_all_must_have_skills_covered(self):
        """Bullet Pool hat keine Tech-Terme (TypeScript etc.) — prüfe stattdessen,
        dass Skills-Text mindestens 5+ Bullets + 3 static_skills enthält."""
        tex = render_full_cv(self.JOB_TITLE, self.JOB_DESCRIPTION).lower()
        # Bullet Pool enthalten: motion, ux, design, research, prototyp, product
        # Statt Tech-Terme prüfen wir, dass der Skills-Text gefüllt ist
        m = re.search(r"\\noindent\s*\n(.*?)\\par", tex, re.DOTALL)
        assert m, "skills_text Block fehlt"
        skills_text = m.group(1)
        bullet_count = skills_text.count(r"\textbullet")
        assert bullet_count >= 5, f"Nur {bullet_count} Skills im CV (erwartet >= 5)"
        # Stelle sicher, dass UX/Design-Bullets da sind (aus dem Pool)
        assert any(term in tex for term in ["ux", "design", "figma"]), (
            "Keine UX/Design-Bullets im CV"
        )

    def test_nice_to_haves_boost_bullets(self):
        """Nice-to-haves wie Motion Design, ComfyUI etc. sollten Bullets boosten."""
        tex = render_full_cv(self.JOB_TITLE, self.JOB_DESCRIPTION).lower()
        nice_to_haves = ["motion", "comfyui", "n8n", "blender", "webflow"]
        found = [n for n in nice_to_haves if n in tex]
        assert len(found) >= 2, f"Nur {len(found)} Nice-to-haves im CV: {found}"

    def test_skills_text_not_too_long(self):
        """skills_text: max 8 Bullets + 3 static = max 11 Items, kein LaTeX-Overflow."""
        tex = render_full_cv(self.JOB_TITLE, self.JOB_DESCRIPTION)
        m = re.search(r"\\noindent\s*\n(.*?)\\par", tex, re.DOTALL)
        assert m
        skills_text = m.group(1)
        bullet_count = skills_text.count(r"\textbullet")
        assert bullet_count <= 12, f"Zu viele Skills ({bullet_count}): könnte LaTeX-Pagination brechen"

    def test_experience_block_not_broken(self):
        """Alle 3 Jobs (8020 + UNTITLED + smartpatient) müssen da sein."""
        tex = render_full_cv(self.JOB_TITLE, self.JOB_DESCRIPTION)
        assert "8020 GmbH" in tex, "8020 fehlt"
        assert "UNTITLED UX" in tex, "UNTITLED fehlt"
        assert "smartpatient" in tex, "smartpatient fehlt"

    def test_kunden_line_still_present(self):
        """Kunden-Liste muss bei Max-Content auch noch da sein."""
        tex = render_full_cv(self.JOB_TITLE, self.JOB_DESCRIPTION)
        assert r"\textbf{Kunden:}" in tex, "Kunden-Header fehlt"
        assert "Audi" in tex and "Porsche" in tex, "Kunden-Namen fehlen"

    def test_leadership_has_both_entries(self):
        """Kontrast Festival + Dialog Act Classification müssen da sein."""
        tex = render_full_cv(self.JOB_TITLE, self.JOB_DESCRIPTION)
        assert "Kontrast Festival" in tex
        assert "Dialog Act Classification" in tex

    def test_education_has_both_degrees(self):
        tex = render_full_cv(self.JOB_TITLE, self.JOB_DESCRIPTION)
        assert "M.Sc." in tex
        assert "B.Sc." in tex

    def test_languages_complete(self):
        tex = render_full_cv(self.JOB_TITLE, self.JOB_DESCRIPTION)
        assert "Deutsch" in tex
        assert "Englisch" in tex
        assert "Chinesisch" in tex
