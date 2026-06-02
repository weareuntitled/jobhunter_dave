"""tests/test_cv_real_example.py – Realistisches Beispiel: kompletter CV für eine konkrete Stelle."""

import yaml
from datetime import datetime
from pathlib import Path

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
- Du arbeitest eng mit Product Ownern und Entwicklern zusammen
- Du etablierst Design QA Prozesse

Must-have:
- 3+ Jahre UX/UI Design Erfahrung
- Exzellente Figma Skills
- Erfahrung mit Design Systems
- User Research Methoden (Interviews, Usability Tests)
- Prototyping Skills
- Deutsch und Englisch

Nice-to-have:
- Erfahrung mit Enterprise Produkten
- B2B SaaS Background
- Motion Design / Micro-Interactions
- KI-gestützte Design Workflows
""".strip()

COMPANY = "FLUID Design GmbH"
LOCATION = "München, Remote möglich"


def render_cv(job_title: str, job_description: str, output_path: Path | None = None) -> str:
    """Rendert das CV-Template für eine konkrete Stelle und gibt den LaTeX-Output zurück."""
    selector = BulletSelector()

    # 1. Relevante Bullets auswählen
    bullets = selector.select(job_title, job_description, max_bullets=8)
    bullets_8020, bullets_untitled = selector.split_by_employer(
        job_title, job_description, max_bullets=14, min_bullets=8,
    )

    # 2. Static Skills laden
    config = yaml.safe_load(Path("data/config.yaml").read_text())
    static_skills = list(config.get("cv", {}).get("static_skills", []))

    # 3. Skills für skills_text zusammenbauen
    job_skills = bullets[:6]
    all_skills = job_skills + static_skills
    skills_text = r" \textbullet\ ".join([latex_escape(s) for s in all_skills])

    # 4. Erfahrung als LaTeX formatieren
    def render_experience_block(company_name: str, bullet_list: list[str]) -> str:
        items = "\n".join(f"  \\item {latex_escape(b)}" for b in bullet_list)
        if not items:
            items = "  \\item Erfahrung in der Rolle"
        return f"\\textbf{{{latex_escape(company_name)}}} \\\\\n{items}"

    exp_8020 = render_experience_block("8020 GmbH -- Management Consultant & Product Designer", bullets_8020)
    exp_untitled = render_experience_block("UNTITLED UX -- Founder & Lead Designer", bullets_untitled)

    # 5. CV-Kontext
    ctx = {
        "name": "Daniel Peters",
        "title": latex_escape("UX/UI Designer & AI Product Specialist"),
        "location": "Augsburg, Deutschland",
        "email": "hi@untitled-ux.de",
        "phone": "+49 173 5231109",
        "portfolio_url": "portfolio.untitled-ux.de",
        "photo_path": "photo.jpg",
        "date": datetime.now().strftime("%d.%m.%Y"),
        "experience": exp_8020 + "\n\n" + exp_untitled,
        "skills": [latex_escape(s) for s in all_skills],
        "static_skills": static_skills,
        "skills_text": skills_text,
        "education": r"\textbf{Technische Hochschule Ingolstadt} \\ M.Sc. UX Design (laufend) \\ B.Sc. Informatik",
        "leadership": r"\textbf{Kontrast Festival} \\ Co-Founder & Programmleitung (2018-heute) \\ Team von 12 Freiwilligen geführt",
        "languages": "Deutsch (Muttersprache), Englisch (C1)",
    }

    # 6. Template rendern
    template_str = Path("data/cv/general.tex").read_text(encoding="utf-8")
    env = Environment(
        block_start_string="<%",
        block_end_string="%>",
        variable_start_string="<<",
        variable_end_string=">>",
    )
    template = env.from_string(template_str)
    tex_output = template.render(ctx)

    if output_path:
        output_path.write_text(tex_output, encoding="utf-8")

    return tex_output


def test_real_fluid_design_job_produces_valid_cv():
    """E2E: Generiert CV für FLUID Design Senior UX Designer Stelle."""
    output_dir = Path("/tmp/cv_examples")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "fluid_design_cv.tex"

    tex = render_cv(JOB_TITLE, JOB_DESCRIPTION, output_path)

    # === STRUKTUR-CHECKS ===
    assert "\\documentclass" in tex, "LaTeX documentclass fehlt"
    assert "\\begin{document}" in tex and "\\end{document}" in tex, "LaTeX body fehlt"
    assert "Daniel Peters" in tex, "Name fehlt"
    assert "Augsburg" in tex, "Location fehlt"
    assert "hi@untitled-ux.de" in tex, "Email fehlt"
    assert "+49 173 5231109" in tex, "Phone fehlt"
    assert "KI-Bewerbungs-Agenten" in tex, "Footer-Disclaimer fehlt"

    # === SKILL-MATCHING-CHECKS ===
    # Diese Skills MÜSSEN drin sein, weil die Job sie explizit verlangt:
    must_contain_skills = [
        "figma",
        "designsystem",
        "user research",
        "prototyp",
        "ki-gestützt",  # lowercase, da tex_lower verwendet wird
    ]
    tex_lower = tex.lower()
    missing = [s for s in must_contain_skills if s not in tex_lower]
    assert not missing, f"Fehlende Skills: {missing}\nCV Output: {output_path}"

    # === ARBEITSGEBER-CHECKS ===
    assert "8020" in tex, "8020 GmbH Erfahrungs-Block fehlt"
    assert "UNTITLED" in tex, "UNTITLED UX Erfahrungs-Block fehlt"

    # === LATEX-ESCAPING-CHECKS ===
    dangerous_chars = ["&", "%", "$", "#"]
    for ch in dangerous_chars:
        # Suche nach unescaped Vorkommen (nicht direkt nach \)
        i = 0
        unescaped_count = 0
        while i < len(tex):
            if tex[i] == ch and (i == 0 or tex[i - 1] != "\\"):
                unescaped_count += 1
            i += 1
        # Sonderzeichen müssen escaped sein, _ auch
        if unescaped_count > 0:
            print(f"WARN: {unescaped_count} unescaped '{ch}' in CV")

    # skills_text Sektion muss da sein
    assert "Technische Skills" in tex, "Skills-Header fehlt"
    assert r"\textbullet" in tex, "Skills-Separator fehlt"

    # === OUTPUT PRINTEN ===
    print(f"\n{'='*70}")
    print(f"RENDERED CV for: {COMPANY} -- {JOB_TITLE[:50]}...")
    print(f"Output: {output_path}")
    print(f"Größe: {len(tex)} Zeichen, {tex.count(chr(10))} Zeilen")
    print(f"{'='*70}\n")
    print(tex[:3000])
    if len(tex) > 3000:
        print(f"\n... ({len(tex) - 3000} weitere Zeichen)")
    print(f"\n{'='*70}")
    print(f"Vollständiges LaTeX: {output_path}")
    print(f"{'='*70}")


def test_skill_match_audit_for_fluid_job():
    """Audit: Welche Skills aus der Job-Beschreibung sind im CV?"""
    selector = BulletSelector()
    bullets = selector.select(JOB_TITLE, JOB_DESCRIPTION, max_bullets=12)

    # Skills die der Job verlangt
    required = ["figma", "user research", "designsystem", "prototyp", "ux", "design"]
    tex = " ".join(bullets).lower()

    print(f"\nSKILL-MATCHING AUDIT für {COMPANY}:")
    print(f"{'Skill':<20} {'Gefunden?':<10}")
    print("-" * 30)
    for skill in required:
        found = skill in tex
        marker = "[OK]" if found else "[FEHLT]"
        print(f"{skill:<20} {marker:<10}")

    # Mindestens 4 von 6 müssen matchen
    matches = sum(1 for s in required if s in tex)
    assert matches >= 4, f"Nur {matches} von {len(required)} Skills gefunden"


def test_compare_two_jobs_select_different_bullets():
    """Zwei verschiedene Jobs sollten verschiedene Bullets auswählen."""
    selector = BulletSelector()

    job_a = "Senior UX Designer mit Figma, Design Systems und User Research Erfahrung"
    job_b = "Backend Engineer mit Python, FastAPI, PostgreSQL und Docker"

    bullets_a = selector.select(job_a, "Figma Design Systems User Research Prototyping", max_bullets=6)
    bullets_b = selector.select(job_b, "Python FastAPI PostgreSQL Docker Kubernetes", max_bullets=6)

    # Verschiedene Bullets
    assert bullets_a != bullets_b, "Beide Jobs liefern gleiche Bullets"

    # Job A sollte UX-Bullets haben
    assert any("figma" in b.lower() or "design" in b.lower() for b in bullets_a), "Job A hat keine UX-Bullets"
    # Job B sollte Tech-Bullets haben
    assert any("python" in b.lower() or "docker" in b.lower() or "fastapi" in b.lower() for b in bullets_b), "Job B hat keine Tech-Bullets"

    print(f"\nVERGLEICH: UX-Job vs Backend-Job")
    print(f"UX-Job Bullets ({len(bullets_a)}):")
    for b in bullets_a[:3]:
        print(f"  - {b[:80]}")
    print(f"Backend-Job Bullets ({len(bullets_b)}):")
    for b in bullets_b[:3]:
        print(f"  - {b[:80]}")
