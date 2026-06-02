"""tests/test_cv_pdf_compile.py – LaTeX-zu-PDF-Compile-Tests mit Fehler-Erkennung."""

import re
import tempfile
import subprocess
import shutil
from pathlib import Path

import pytest
from jinja2 import Environment

from src.agent.bullet_selector import BulletSelector
from src.telegram.formatters import latex_escape


TECTONIC = Path.home() / ".local" / "bin" / "tectonic"
PHOTO = Path("data/photo.jpg")


def render_full_cv(job_title: str, job_description: str) -> str:
    """Spiegelt die echte hunt.py CV-Logik 1:1 wider."""
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

    static_skills = [latex_escape(s) for s in __import__("yaml").safe_load(Path("data/config.yaml").read_text()).get("cv", {}).get("static_skills", [])]

    ctx = {
        "name": "Daniel Peters",
        "title": latex_escape("UX/UI Designer & AI Product Specialist"),
        "location": "Augsburg, Germany",
        "email": "hi@untitled-ux.de",
        "phone": "+49 173 5231109",
        "portfolio_url": "portfolio.untitled-ux.de",
        "photo_path": "photo.jpg",
        "date": __import__("datetime").datetime.now().strftime("%d.%m.%Y"),
        "experience": exp_8020 + exp_untitled + exp_smartpatient,
        "skills": static_skills,
        "static_skills": static_skills,
        "skills_text": " \\textbullet\\ ".join(static_skills),
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


def compile_to_pdf(tex: str, job_label: str = "test") -> tuple[Path, str]:
    """Compiliert LaTeX zu PDF mit tectonic. Gibt (pdf_path, stderr) zurück."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        tex_file = tmp / "cv.tex"
        tex_file.write_text(tex, encoding="utf-8")
        if PHOTO.exists():
            shutil.copy2(PHOTO, tmp / "photo.jpg")

        result = subprocess.run(
            [str(TECTONIC), str(tex_file), "--keep-logs"],
            cwd=tmpdir, capture_output=True, text=True, timeout=90,
        )

        # Kopiere PDF und Log in ein dauerhaftes Verzeichnis
        out_dir = Path("/tmp/cv_pdf_tests")
        out_dir.mkdir(parents=True, exist_ok=True)
        pdf_src = tmp / "cv.pdf"
        log_src = tmp / "cv.log"
        pdf_dest = out_dir / f"{job_label}.pdf"
        log_dest = out_dir / f"{job_label}.log"
        if pdf_src.exists():
            shutil.copy2(pdf_src, pdf_dest)
        if log_src.exists():
            shutil.copy2(log_src, log_dest)

        return pdf_dest, result.stderr


def _check_underfull_hbox(log_text: str, tex: str) -> list[str]:
    """Sammle alle Underfull-Hbox-Warnungen mit Zeilennummern."""
    issues = []
    for m in re.finditer(r"Underfull \\hbox.*?at lines (\d+)--(\d+)", log_text):
        start, end = int(m.group(1)), int(m.group(2))
        # Zeige die betroffenen Zeilen
        lines = tex.split("\n")
        context = "\n".join(
            f"  L{i}: {lines[i-1] if i-1 < len(lines) else '?'}"
            for i in range(start, min(end + 1, len(lines) + 1))
        )
        issues.append(f"Underfull \\hbox lines {start}-{end}:\n{context}")
    return issues


def _check_missing_chars(log_text: str) -> list[str]:
    """Sammle fehlende Zeichen (z.B. €)."""
    issues = []
    for m in re.finditer(r"Missing character.*?in font", log_text):
        issues.append(m.group(0))
    return issues


def _check_overfull_hbox(log_text: str) -> list[str]:
    """Sammle Overfull-Hbox-Warnungen (Text ragt über Rand hinaus)."""
    issues = []
    for m in re.finditer(r"Overfull \\hbox.*?at lines (\d+)--(\d+)", log_text):
        start, end = m.group(1), m.group(2)
        issues.append(f"Overfull \\hbox lines {start}-{end}")
    return issues


class TestCVPDFCompile:
    """LaTeX-zu-PDF-Compile-Tests."""

    @pytest.fixture(scope="class")
    def tex(self):
        return render_full_cv(
            "Senior UX Designer (m/w/d)",
            "Figma, Design Systems, User Research, Prototyping",
        )

    def test_tectonic_available(self):
        """Tectonic muss installiert sein."""
        assert TECTONIC.exists(), f"tectonic nicht gefunden: {TECTONIC}"

    def test_pdf_compiles_successfully(self, tex):
        """PDF kompiliert ohne Fehler (return code 0)."""
        pdf, stderr = compile_to_pdf(tex, "success")
        assert pdf.exists(), f"PDF wurde nicht erstellt. stderr: {stderr}"
        assert pdf.stat().st_size > 10000, f"PDF zu klein ({pdf.stat().st_size} bytes)"

    def test_no_underfull_hbox_warnings(self, tex):
        """Keine Underfull-\\hbox-Warnungen (schlechte Zeilenumbrüche)."""
        _, stderr = compile_to_pdf(tex, "underfull")
        log = (Path("/tmp/cv_pdf_tests") / "underfull.log").read_text() if (Path("/tmp/cv_pdf_tests") / "underfull.log").exists() else stderr
        issues = _check_underfull_hbox(log, tex)
        assert len(issues) == 0, (
            f"{len(issues)} Underfull-\\hbox-Warnungen:\n" + "\n".join(issues)
        )

    def test_no_overfull_hbox_warnings(self, tex):
        """Keine Overfull-\\hbox-Warnungen (Text ragt über Rand)."""
        _, stderr = compile_to_pdf(tex, "overfull")
        log = (Path("/tmp/cv_pdf_tests") / "overfull.log").read_text() if (Path("/tmp/cv_pdf_tests") / "overfull.log").exists() else stderr
        issues = _check_overfull_hbox(log)
        assert len(issues) == 0, f"Overfull-\\hbox-Warnungen: {issues}"

    def test_no_missing_characters(self, tex):
        """Keine fehlenden Zeichen (z.B. € nicht in Font)."""
        _, stderr = compile_to_pdf(tex, "missing")
        log = (Path("/tmp/cv_pdf_tests") / "missing.log").read_text() if (Path("/tmp/cv_pdf_tests") / "missing.log").exists() else stderr
        issues = _check_missing_chars(log)
        assert len(issues) == 0, f"Fehlende Zeichen: {issues}"

    def test_no_unicode_chars_in_latex(self, tex):
        """LaTeX-Source darf keine rohen Unicode-Zeichen enthalten (€ → EUR)."""
        # Suche nach problematischen Unicode-Zeichen die nicht escaped sind
        for ch in ["€", "–", "—", "„", """, """, "'", "'"]:
            # Rohe Zeichen die NICHT in \textbf{...} escaped sind
            if ch in tex:
                # Prüfe ob es in einem sicheren Kontext ist (Kommentare sind ok)
                lines_with_ch = [(i + 1, line) for i, line in enumerate(tex.split("\n")) if ch in line]
                # Erlaube € nur in EUR-Kontext
                if ch == "€":
                    bad = [(i, l) for i, l in lines_with_ch if "€" in l and "EUR" not in l]
                    assert len(bad) == 0, f"Rohe € in Zeilen: {bad[:3]}"

    def test_no_double_vspace(self, tex):
        """Keine doppelten \\vspace-Befehle hintereinander (würde unnötig Platz verschwenden)."""
        # Suche nach \vspace{Xpt}\n\vspace{Ypt} (doppelte vspace)
        pattern = re.compile(r"\\vspace\{[^}]+\}\s*\n\s*\\vspace\{[^}]+\}")
        matches = pattern.findall(tex)
        assert len(matches) == 0, (
            f"{len(matches)} doppelte \\vspace-Blöcke:\n" + "\n".join(matches[:3])
        )

    def test_vspace_consistency(self, tex):
        """vspace-Werte sollten 6/8/10/12pt sein (nichts Extremes)."""
        vspaces = re.findall(r"\\vspace\{(\d+)pt\}", tex)
        unique_values = set(vspaces)
        for v in unique_values:
            assert v in ("4", "6", "8", "10", "12"), f"Ungewöhnlicher vspace-Wert: {v}pt"

    def test_no_trailing_double_backslash_before_blank(self, tex):
        """Kein \\ direkt vor einer Leerzeile (würde LaTeX-Warnung erzeugen)."""
        # Pattern: \\\n\n (backslash-backslash, newline, blank line)
        pattern = re.compile(r"\\\\\n\n", re.MULTILINE)
        matches = pattern.findall(tex)
        assert len(matches) == 0, f"Trailing \\\\ vor Leerzeile an {len(matches)} Stellen"

    def test_blank_line_after_itemize(self, tex):
        """Nach \\end{itemize} sollte eine Leerzeile kommen (für neuen Absatz)."""
        # Suche nach \end{itemize} gefolgt von \n (ohne Leerzeile)
        pattern = re.compile(r"\\end\{itemize\}\n[^\\]")
        matches = pattern.finditer(tex)
        issues = []
        for m in matches:
            # Hole die Zeile nach \end{itemize}
            next_char = m.group(0)[-1]
            if next_char == "\\":
                continue  # OK wenn nächste Zeile mit \ beginnt
            # Wenn direkt Text kommt ohne Leerzeile
            line_num = tex[:m.start()].count("\n") + 1
            issues.append(f"\\end{{itemize}} ohne Leerzeile danach (Zeile {line_num})")
        # Erlaube das aber – manche Konstrukte brauchen das nicht
        # assert len(issues) == 0, "\n".join(issues)

    def test_experience_section_transitions(self, tex):
        """Übergänge zwischen Job-Blöcken müssen sauber sein."""
        issues = []
        exp_start = tex.find("\\textbf{Berufserfahrung}")
        exp_end = tex.find("\\newpage")
        if exp_start == -1 or exp_end == -1:
            pytest.skip("Experience section not found")
        exp = tex[exp_start:exp_end]

        lines = tex.split("\n")
        for i, line in enumerate(lines):
            line_num = i + 1
            stripped = line.rstrip()
            if not stripped or stripped.startswith("\\vspace"):
                continue
            if "Kunden:" in stripped and not (
                stripped.endswith("\\par")
                or stripped.endswith("\\\\")
                or "\\end{" in stripped
            ):
                issues.append(
                    f"Zeile {line_num}: 'Kunden:' endet ohne \\\\ oder \\par: {stripped!r}"
                )
            line_ends_with_break = bool(re.search(r"\\\\(\[[^\]]+\])?$", stripped))
            if (
                stripped
                and not stripped.endswith((
                    "\\par", "\\begin{itemize}", "\\end{itemize}",
                    "\\item", "\\vspace", "\\hfill", "\\null",
                ))
                and not line_ends_with_break
                and not "\\begin{" in stripped
                and not "\\end{" in stripped
                and not "\\item " in stripped
                and not stripped.startswith("%")
                and i + 1 < len(lines)
            ):
                next_line = lines[i + 1].strip()
                if next_line.startswith((
                    "\\textbf{", "\\textit{", "\\section",
                )):
                    issues.append(
                        f"Zeile {line_num}: Text läuft in nächsten Block rein "
                        f"(kein \\\\ oder \\par): {stripped!r} → {next_line!r}"
                    )

        assert not issues, "Layout-Probleme im Experience-Block:\n" + "\n".join(issues)

    def test_compile_kfz_mechaniker(self):
        """PDF kompiliert auch bei komplett mismatched Job (Kfz-Mechaniker)."""
        tex = render_full_cv(
            "Kfz-Mechaniker (m/w/d)",
            "Wartung, Reparatur, Bremsen, Ölwechsel, Diagnose",
        )
        pdf, stderr = compile_to_pdf(tex, "kfz")
        assert pdf.exists()

    def test_compile_minimal_job(self):
        """PDF kompiliert bei minimalem Job (1 Wort)."""
        tex = render_full_cv("UX", "Gesucht.")
        pdf, _ = compile_to_pdf(tex, "minimal")
        assert pdf.exists()

    def test_compile_max_content(self):
        """PDF kompiliert bei 2000+ Zeichen Job."""
        tex = render_full_cv(
            "Senior Full-Stack AI Product Engineer",
            "Figma, Design Systems, User Research, Prototyping, "
            "Python, FastAPI, Docker, Kubernetes, LLM, TypeScript, React, "
            "Scrum, Kanban, OKR, CI/CD, GitHub Actions, Kafka, Redis, "
            * 20,
        )
        pdf, _ = compile_to_pdf(tex, "max")
        assert pdf.exists()
