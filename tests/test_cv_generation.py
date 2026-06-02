"""tests/test_cv_generation.py – Testet CV-Template-Rendering mit echten Daten."""

import yaml
from datetime import datetime
from pathlib import Path

from src.agent.bullet_selector import BulletSelector


def _latex_escape(text: str) -> str:
    return text.replace("&", "\\&").replace("%", "\\%").replace("$", "\\$").replace("#", "\\#").replace("_", "\\_").replace("{", "\\{").replace("}", "\\}")


class TestCVTemplateRendering:
    """Testet, dass das general.tex-Template korrekt gerendert wird."""

    def test_skills_text_rendered_in_output(self):
        """skills_text muss im gerenderten CV auftauchen."""
        from jinja2 import Environment

        bullets = [
            "UX/UI Design für Enterprise-Kunden (Audi, Porsche)",
            "Design Systems mit Figma aufgebaut",
            "User Research mit 20+ Teilnehmern",
        ]
        static_skills = [
            "KI-gestützte Produktentwicklung",
            "Prompt Engineering",
            "LLM-Integration",
        ]
        all_skills = bullets + static_skills

        env = Environment(
            block_start_string="<%",
            block_end_string="%>",
            variable_start_string="<<",
            variable_end_string=">>",
        )
        template = env.from_string(
            Path("data/cv/general.tex").read_text(encoding="utf-8")
        )

        ctx = {
            "name": "Test User",
            "title": "Test Title",
            "location": "Test City",
            "email": "test@test.de",
            "phone": "+49 123",
            "portfolio_url": "test.de",
            "photo_path": "photo.jpg",
            "date": datetime.now().strftime("%d.%m.%Y"),
            "experience": r"\item Test-Erfahrung",
            "skills": [_latex_escape(s) for s in all_skills],
            "static_skills": static_skills,
            "skills_text": r" \textbullet\ ".join([_latex_escape(s) for s in all_skills]),
            "education": r"Test Education",
            "leadership": r"Test Leadership",
            "languages": "Deutsch, Englisch",
        }

        tex_output = template.render(ctx)

        # skills_text must be present
        assert "UX/UI Design" in tex_output, "skills_text not in CV"
        assert "KI-gestützte" in tex_output, "static_skills not in CV"
        assert "Test-Erfahrung" in tex_output, "experience not in CV"

    def test_bullet_selector_returns_relevant_bullets(self):
        """BulletSelector liefert passende Bullets zur Job-Beschreibung."""
        selector = BulletSelector()
        bullets = selector.select(
            job_title="Senior UX Designer",
            job_description="We are looking for a UX Designer with Figma, User Research, and Design Systems experience. Must know prototyping.",
            max_bullets=6,
        )
        assert len(bullets) > 0, "No bullets returned"
        ux_terms = ["ux", "design", "figma", "research", "prototyp", "user"]
        has_relevant = any(
            any(term in b.lower() for term in ux_terms)
            for b in bullets
        )
        assert has_relevant, f"No UX-relevant bullets: {bullets[:3]}"

    def test_split_by_employer_returns_both(self):
        """split_by_employer teilt 8020 und untitled korrekt."""
        selector = BulletSelector()
        bullets_8020, bullets_untitled = selector.split_by_employer(
            job_title="Senior UX Designer",
            job_description="We need a UX Designer with Figma skills.",
            max_bullets=12,
            min_bullets=8,
        )
        total = len(bullets_8020) + len(bullets_untitled)
        assert total >= 4, f"Too few bullets: {total}"
        assert len(bullets_8020) > 0, "No 8020 bullets"
        assert len(bullets_untitled) > 0, "No untitled bullets"

    def test_config_static_skills_loaded(self):
        """static_skills aus config.yaml sind vorhanden und nicht leer."""
        config = yaml.safe_load(Path("data/config.yaml").read_text())
        static_skills = config.get("cv", {}).get("static_skills", [])
        assert len(static_skills) == 3, f"Expected 3 static_skills, got {len(static_skills)}"
        assert any("KI" in s for s in static_skills), "No KI skill in static_skills"

    def test_general_tex_uses_skills_text(self):
        """general.tex enthält << skills_text >> (nicht leere Section)."""
        tex = Path("data/cv/general.tex").read_text(encoding="utf-8")
        assert "<< skills_text >>" in tex, "general.tex missing skills_text placeholder"
        assert "Technische Skills" in tex, "Skills section header missing"

    def test_full_cv_rendering_for_fluid_design(self):
        """E2E: Rendere CV für FLUID Design Senior UX Designer Stelle."""
        from jinja2 import Environment

        selector = BulletSelector()
        job_title = "Senior UX Designer"
        job_desc = (
            "Du gestaltest innovative UX-Konzepte für digitale Produkte. "
            "Figma, User Research, Design Systems, Prototyping, "
            "Interaction Design, Usability Testing. "
            "Agile Entwicklung mit Scrum. Zusammenarbeit mit Product Ownern."
        )

        bullets = selector.select(job_title, job_desc, max_bullets=6)
        bullets_8020, bullets_untitled = selector.split_by_employer(
            job_title, job_desc, max_bullets=12, min_bullets=8,
        )

        config = yaml.safe_load(Path("data/config.yaml").read_text())
        static_skills = [s for s in config.get("cv", {}).get("static_skills", [])]

        all_skills = bullets[:6] + static_skills

        esc = _latex_escape
        env = Environment("<%", "%>", "<<", ">>")
        template = env.from_string(Path("data/cv/general.tex").read_text(encoding="utf-8"))

        # Build experience like hunt.py does
        exp_8020 = (
            r"\textbf{8020 GmbH} \\ "
            + ("\n".join(f"  \\item {esc(b)}" for b in bullets_8020) if bullets_8020
               else r"  \item Default 8020 bullet")
        )
        exp_untitled = (
            r"\textbf{UNTITLED UX} \\ "
            + ("\n".join(f"  \\item {esc(b)}" for b in bullets_untitled) if bullets_untitled
               else r"  \item Default untitled bullet")
        )

        ctx = {
            "name": "Daniel Peters",
            "title": esc("UX/UI Designer & AI Product Specialist"),
            "location": "Augsburg, Germany",
            "email": "hi@untitled-ux.de",
            "phone": "+49 173 5231109",
            "portfolio_url": "portfolio.untitled-ux.de",
            "photo_path": "photo.jpg",
            "date": datetime.now().strftime("%d.%m.%Y"),
            "experience": exp_8020 + "\n" + exp_untitled,
            "skills": [esc(s) for s in all_skills],
            "static_skills": static_skills,
            "skills_text": r" \textbullet\ ".join([esc(s) for s in all_skills]),
            "education": r"\textbf{TH Ingolstadt} \\ M.Sc. UX Design",
            "leadership": r"\textbf{Kontrast Festival} \\ Co-Founder",
            "languages": "Deutsch (Muttersprache), Englisch (C1)",
        }

        tex_output = template.render(ctx)

        checks = [
            ("Daniel Peters", "Name missing"),
            ("UNTITLED UX", "UNTITLED UX section missing"),
            ("8020", "8020 section missing"),
            ("KI-gestützt", "static_skills not rendered"),
            ("Kontrast", "Leadership section missing"),
            ("TH Ingolstadt", "Education section missing"),
            ("Deutsch", "Languages section missing"),
        ]
        for text, msg in checks:
            assert text in tex_output, f"CV missing: {msg}"

        assert len(bullets) >= 3, f"Too few bullets: {len(bullets)}"
        for b in bullets[:2]:
            escaped = esc(b[:20])
            assert escaped in tex_output, f"Bullet '{b[:40]}' not found in CV output"
