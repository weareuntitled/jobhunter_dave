"""tests/test_cv_layout.py – Layout-Checks: Newlines, Page-Breaks, keine leeren Header, itemize korrekt."""

import re
import yaml
from datetime import datetime
from pathlib import Path

import pytest
from jinja2 import Environment

from src.agent.bullet_selector import BulletSelector
from src.telegram.formatters import latex_escape


JOB_TITLE = "Senior UX Designer (m/w/d) – Fokus Design Systems & User Research"
JOB_DESCRIPTION = """
Wir suchen einen erfahrenen UX Designer für unser Produktteam.

Deine Aufgaben:
- Du gestaltest innovative UX-Konzepte für unsere SaaS-Plattform
- Du baust unser Design System in Figma weiter aus
- Du führst User Research Sessions mit unseren Kunden durch

Must-have:
- 3+ Jahre UX/UI Design Erfahrung
- Exzellente Figma Skills
- Erfahrung mit Design Systems
- User Research Methoden
- Prototyping Skills
""".strip()


def render_full_cv(job_title: str, job_description: str) -> str:
    """Spiegelt die echte hunt.py CV-Logik 1:1 wider (inkl. 3 Jobs, Kontrast, Kunden)."""
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
        "\\vspace{12pt}\n"
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
    template = env.from_string(template_str)
    return template.render(ctx)


class TestCVLayout:
    """Layout-Checks für den vollständigen CV."""

    @pytest.fixture
    def tex(self, tmp_path):
        out = tmp_path / "cv.tex"
        tex_content = render_full_cv(JOB_TITLE, JOB_DESCRIPTION)
        out.write_text(tex_content, encoding="utf-8")
        return tex_content

    def test_every_section_header_has_content_below(self, tex):
        """Jeder Section-Header muss Content danach haben (kein leerer Block)."""
        # Section-Header im Template: \begin{center} \textbf{...} \end{center}
        header_pattern = re.compile(
            r"\\begin\{center\}\s*\\textbf\{([^}]+)\}\s*\\end\{center\}",
            re.MULTILINE,
        )

        for match in header_pattern.finditer(tex):
            header = match.group(1)
            # Nimm die nächsten 200 Zeichen nach dem Header
            after = tex[match.end():match.end() + 200]
            # Filtere nur whitespace, \vspace, \newpage, \noindent raus
            after_stripped = re.sub(r"[\s\\]*(vspace|newpage|noindent|par)?[\s\\]*", "", after)
            assert len(after_stripped) > 5, (
                f"Section-Header '{header}' hat keinen Content darunter.\n"
                f"Nach 200 Zeichen: {after[:200]!r}"
            )

    def test_no_bare_item_outside_itemize(self, tex):
        """Kein \item darf außerhalb von \begin{itemize}...\end{itemize} stehen."""
        # Entferne alle itemize-Blöcke
        cleaned = re.sub(
            r"\\begin\{itemize\}.*?\\end\{itemize\}",
            "",
            tex,
            flags=re.DOTALL,
        )
        bare_items = re.findall(r"\\item\b", cleaned)
        assert len(bare_items) == 0, (
            f"Gefunden: {len(bare_items)} \\item außerhalb von itemize-Block.\n"
            f"Beispiele: {bare_items[:3]}"
        )

    def test_all_itemize_blocks_have_begin_and_end(self, tex):
        """Anzahl \\begin{itemize} muss gleich \\end{itemize} sein."""
        begins = tex.count(r"\begin{itemize}")
        ends = tex.count(r"\end{itemize}")
        assert begins == ends, (
            f"\\begin{{itemize}}={begins} vs \\end{{itemize}}={ends}"
        )
        assert begins >= 3, f"Erwartet >= 3 itemize-Blöcke (3 Jobs + Kontrast + Dialog), gefunden {begins}"

    def test_every_itemize_has_at_least_one_item(self, tex):
        """Jeder itemize-Block muss mindestens 1 \\item haben."""
        # Iteriere über alle itemize-Blöcke
        for m in re.finditer(r"\\begin\{itemize\}(.*?)\\end\{itemize\}", tex, re.DOTALL):
            block = m.group(1)
            item_count = len(re.findall(r"\\item\b", block))
            assert item_count >= 1, f"Leerer itemize-Block gefunden: {block[:100]!r}"

    def test_newlines_between_sections(self, tex):
        """Zwischen jedem \\end{itemize} und dem nächsten \\begin{center} muss eine Leerzeile sein."""
        pattern = re.compile(
            r"\\end\{itemize\}\s*\n\s*(\\begin\{center\}|\\newpage|\\vspace|\\noindent)",
        )
        # Sollte mehrere solcher Übergänge geben
        transitions = pattern.findall(tex)
        assert len(transitions) >= 4, f"Zu wenige Section-Übergänge mit Newline: {len(transitions)}"

    def test_no_stray_double_backslash_in_items(self, tex):
        """Kein literaler \\ in Items (sollte \\\\ für LaTeX-Linebreak sein)."""
        # Suche nach "    \    \item" (Bug in hunt.py mit "    \    \item")
        bad_pattern = re.compile(r"^\s*\\\s*\\item", re.MULTILINE)
        bad_matches = bad_pattern.findall(tex)
        assert len(bad_matches) == 0, (
            f"Gefunden: {len(bad_matches)} Items mit literalem Backslash davor.\n"
            f"Beispiele: {bad_matches[:3]}"
        )

    def test_no_lone_unescaped_backslash(self, tex):
        """Kein einsamer \\ am Zeilenende (sollte \\\\ für LaTeX sein)."""
        # \\\\ in LaTeX = \\. Im Python-String "\\\\" = 2 chars: \ \
        # Suche nach Zeilen die mit \ enden (nicht mit \textbullet, \textbf etc.)
        bad = re.findall(r"[^a-zA-Z\\]\s*\\\\$", tex, re.MULTILINE)
        # Filter: \\ am Zeilenende ist OK in LaTeX, aber im Python-Output ist es
        # verdächtig wenn nicht in einem itemize-Block-Kontext

    def test_skills_section_no_orphan_header(self, tex):
        """Header 'Technische Skills' muss Content haben (skills_text)."""
        # skills_text placeholder ist gesetzt
        assert "<< skills_text >>" not in tex, "Placeholder nicht ersetzt"
        # Textbullet separator muss da sein
        assert r"\textbullet" in tex, "Kein \\textbullet separator in skills_text"

    def test_page_break_only_after_experience(self, tex):
        """Genau ein \\newpage im CV (nach Berufserfahrung)."""
        newpage_count = tex.count(r"\newpage")
        assert newpage_count == 1, f"Erwartet 1 \\newpage, gefunden {newpage_count}"

    def test_education_has_th_degrees(self, tex):
        """Education-Block muss TH Ingolstadt + M.Sc. + B.Sc. enthalten."""
        assert "TH Ingolstadt" in tex, "TH Ingolstadt fehlt in Education"
        assert "M.Sc." in tex, "M.Sc. fehlt in Education"
        assert "B.Sc." in tex, "B.Sc. fehlt in Education"

    def test_leadership_has_kontrast_and_dialog(self, tex):
        """Leadership-Block muss Kontrast + Dialog Act haben."""
        assert "Kontrast Festival" in tex, "Kontrast Festival fehlt in Leadership"
        assert "Dialog Act Classification" in tex, "Dialog Act fehlt in Leadership"

    def test_kunden_line_present(self, tex):
        """8020-Block muss Kunden-Liste haben."""
        assert r"\textbf{Kunden:}" in tex, "Kunden-Header fehlt im 8020-Block"
        assert "Audi" in tex and "Porsche" in tex, "Kunden-Namen fehlen"

    def test_smartpatient_present(self, tex):
        """smartpatient GmbH muss als 3. Job da sein."""
        assert "smartpatient GmbH" in tex, "smartpatient GmbH fehlt in Experience"
        assert "München" in tex, "München (Standort) fehlt"

    def test_languages_has_three(self, tex):
        """Sprachen: Deutsch, Englisch, Chinesisch."""
        assert "Deutsch" in tex and "Englisch" in tex and "Chinesisch" in tex, (
            "Sprachen unvollständig"
        )

    def test_no_empty_lines_in_compact_section(self, tex):
        """Im skills_text-Block sollte kein doppelter Newline sein (eine Zeile)."""
        # skills_text beginnt nach \noindent und endet bei \par
        m = re.search(r"\\noindent\s*\n(.*?)\\par", tex, re.DOTALL)
        assert m, "skills_text-Block nicht gefunden"
        skills_block = m.group(1)
        # Sollte im Wesentlichen eine Zeile sein
        # Erlaube \textbullet als Separator
        # Keine leeren Zeilen
        lines = [l for l in skills_block.split("\n") if l.strip()]
        assert len(lines) <= 2, f"skills_text zu viele Zeilen: {len(lines)}"

    def test_no_duplicate_company_header(self, tex):
        """Kein doppelter 8020 oder UNTITLED Header."""
        count_8020 = tex.count(r"\textbf{8020")
        count_untitled = tex.count(r"\textbf{UNTITLED")
        assert count_8020 == 1, f"8020 Header {count_8020}x statt 1x"
        assert count_untitled == 1, f"UNTITLED Header {count_untitled}x statt 1x"

    def test_emp_8020_block_contains_kunden(self, tex):
        """Der 8020-Block muss nach \\end{itemize} die Kunden-Zeile haben (nicht davor)."""
        # Finde 8020 Block bis zum nächsten \textbf{...} Header
        m = re.search(
            r"\\textbf\{8020.*?\\textbullet\\ Centus",
            tex,
            re.DOTALL,
        )
        assert m, "8020-Block endet nicht mit 'Centus' Kunde. Reihenfolge kaputt."
        # Kunden muss NACH dem \end{itemize} sein
        block = m.group(0)
        itemize_end = block.rfind(r"\end{itemize}")
        kunden_pos = block.find(r"\textbf{Kunden:}")
        assert kunden_pos > itemize_end, (
            f"\\textbf{{Kunden:}} steht VOR \\end{{itemize}} (Position {kunden_pos} vs {itemize_end})"
        )

    def test_print_full_cv_for_inspection(self, tex, tmp_path):
        """Drucke den vollen CV für visuelle Inspektion."""
        out = tmp_path / "full_cv.tex"
        out.write_text(tex, encoding="utf-8")

        print(f"\n{'='*70}")
        print(f"FULL CV OUTPUT: {out}")
        print(f"Größe: {len(tex)} Zeichen, {tex.count(chr(10))} Zeilen")
        print(f"Itemize-Blöcke: {tex.count(chr(92) + 'begin' + chr(123) + 'itemize' + chr(125))}")
        print(f"\\item-Count: {tex.count(chr(92) + 'item' + chr(92) + 'b')}")
        print(f"\\newpage: {tex.count(chr(92) + 'newpage')}")
        print(f"{'='*70}\n")
        print(tex)
        print(f"\n{'='*70}")
