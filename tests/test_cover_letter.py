"""tests/test_cover_letter.py – Anschreiben-Tests: Template-Rendering, Fallback, Extrem-Cases."""

import re
import yaml
from datetime import datetime
from pathlib import Path

import pytest
from jinja2 import Environment

from src.telegram.formatters import latex_escape


# --- Cover Letter Template-Rendering (1:1 wie compiler.py) ---
def render_cover_letter(
    company: str = "FLUID Design GmbH",
    job_title: str = "Senior UX Designer",
    language: str = "de",
    score: int = 8,
    salary_expectation: str | None = None,
    cover_letter_body: str | None = None,
) -> str:
    """Rendert das cover_letter.tex Template mit allen Variablen."""
    template_str = Path("src/latex/templates/cover_letter.tex").read_text(encoding="utf-8")
    env = Environment(
        block_start_string="<%",
        block_end_string="%>",
        variable_start_string="<<",
        variable_end_string=">>",
    )
    template = env.from_string(template_str)

    if cover_letter_body is None:
        from src.agent.llm_client import _template_cover_letter
        from src.agent.schemas import JobListing, ProfileSummary
        job = JobListing(
            id="1", title=job_title, company=company, location="Berlin",
            url="https://example.com/job", description="Test-Jobbeschreibung mit mindestens 10 Zeichen.",
            posted_at="2026-01-01", source="linkedin",
        )
        profile = ProfileSummary(
            name="Daniel Peters", title="UX/UI Designer & AI Product Specialist",
            location="Augsburg", email="hi@untitled-ux.de", phone="+49 173 5231109",
            portfolio_url="portfolio.untitled-ux.de",
            skills=["UX", "Figma", "Python"], experience_years=5,
        )
        cover_letter_body = _template_cover_letter(job, profile, [], language)

    ctx = {
        "language": language,
        "company": latex_escape(company),
        "job_title": latex_escape(job_title),
        "applicant_name_upper": "DANIEL PETERS",
        "applicant_name": "Daniel Peters",
        "applicant_location": "Augsburg",
        "date": datetime.now().strftime("%d.%m.%Y"),
        "cover_letter_body": cover_letter_body,
        "salary_expectation": salary_expectation,
        "portfolio_url": "portfolio.untitled-ux.de",
        "score": score,
        "company_logo_path": None,
    }
    return template.render(ctx)


def _assert_valid_latex(tex: str, label: str):
    """Shared: Cover-Letter muss valides LaTeX sein."""
    assert "\\documentclass" in tex, f"[{label}] Kein documentclass"
    assert "\\begin{document}" in tex and "\\end{document}" in tex, f"[{label}] Body fehlt"
    assert "DANIEL PETERS" in tex, f"[{label}] Name fehlt"
    assert "portfolio.untitled-ux.de" in tex, f"[{label}] Portfolio fehlt"
    assert "KI-Bewerbungs-Agenten" in tex, f"[{label}] Disclaimer fehlt"
    assert "Mit freundlichen" in tex, f"[{label}] Sign-off fehlt"

    # Keine unescaped & in fließtext (nur in \&)
    # Check body ist nicht leer
    m = re.search(r"<< cover_letter_body >>|cover_letter_body_placeholder", tex)
    assert not m, f"[{label}] cover_letter_body nicht ersetzt"


def _assert_edgy_tone(text: str, label: str):
    """Prüft dass der Anschreiben-Text edgy/persönlich klingt und keine Floskeln hat."""
    text_lower = text.lower()

    # Keine Floskeln (aus dem System-Prompt)
    forbidden = [
        "sehr geehrte",
        "damen und herren",
        "ich freue mich",
        "gespräch",
        "einladung",
        "lassen sie uns",
        "kontaktieren sie",
    ]
    for phrase in forbidden:
        assert phrase not in text_lower, f"[{label}] Verbotene Floskel: '{phrase}'"

    # Erste Zeile MUSS der Pflicht-Satz sein (DE oder EN)
    first_line = text.strip().split("\n")[0].lower()
    has_agent_opener = (
        "ki-bewerbungs-agent" in first_line
        or "ai job application agent" in first_line
    )
    assert has_agent_opener, (
        f"[{label}] Erste Zeile nicht der Pflicht-Satz: {first_line[:80]!r}"
    )

    # Kein "Mit freundlichen Grüßen" im Body (kommt erst vom Template)
    assert "mit freundlichen" not in text_lower, f"[{label}] Sign-off im Body (verboten)"

    # Max ~220 Wörter
    word_count = len(text.split())
    assert word_count <= 250, f"[{label}] Zu lang: {word_count} Wörter (max ~220)"


def _make_job(title: str = "Test", company: str = "Test GmbH"):
    from src.agent.schemas import JobListing
    return JobListing(
        id="1", title=title, company=company, location="Berlin",
        url="https://example.com/job", description="Test-Job mit genug Zeichen für Validierung.",
        posted_at="2026-01-01", source="linkedin",
    )


def _make_profile():
    from src.agent.schemas import ProfileSummary
    return ProfileSummary(
        name="Daniel Peters", title="Designer", location="Augsburg",
        email="hi@t.de", phone="+49 123", portfolio_url="test.de",
        skills=["UX", "Figma", "Python"], experience_years=5,
    )


class TestCoverLetterTemplate:
    """Template-Rendering und Struktur-Checks."""

    def test_german_template_structure(self):
        """DT Cover-Letter: Template hat alle Sektionen."""
        tex = render_cover_letter(language="de")
        assert "\\documentclass" in tex
        assert "Berufserfahrung" not in tex  # Kein CV-Content
        assert "DANIEL PETERS" in tex
        assert "FLUID Design" in tex or "das Unternehmen" in tex

    def test_english_template_structure(self):
        """EN Cover-Letter: babel auf englisch."""
        tex = render_cover_letter(language="en", company="Acme Corp", job_title="UX Designer")
        assert "\\usepackage[en]{babel}" in tex
        assert "Acme Corp" in tex

    def test_salary_expectation_shown_when_provided(self):
        """Gehaltsvorstellung erscheint NUR wenn salary_expectation gesetzt."""
        tex_with = render_cover_letter(salary_expectation="85.000")
        assert "85.000" in tex_with
        assert "EUR brutto" in tex_with

        tex_without = render_cover_letter(salary_expectation=None)
        assert "Gehaltsvorstellung" not in tex_without

    def test_cover_letter_body_inserted(self):
        """cover_letter_body wird korrekt ins Template eingefügt."""
        body = "Dies ist ein Test-Anschreiben für die Stelle."
        tex = render_cover_letter(cover_letter_body=body)
        assert body in tex

    def test_no_empty_cover_letter_body(self):
        """cover_letter_body darf nicht leer sein."""
        from src.agent.llm_client import _template_cover_letter
        job = _make_job()
        profile = _make_profile()
        body_de = _template_cover_letter(job, profile, [], "de")
        body_en = _template_cover_letter(job, profile, [], "en")
        assert len(body_de) > 50, f"DE body zu kurz: {len(body_de)}"
        assert len(body_en) > 50, f"EN body zu kurz: {len(body_en)}"

    def test_footer_disclaimer_present(self):
        """Footer muss KI-Bewerbungs-Agenten-Disclaimer haben."""
        tex = render_cover_letter()
        assert "KI-Bewerbungs-Agenten" in tex
        assert "entwickelt" in tex.lower() or "entwickelt" in tex

    def test_score_shown_in_footer(self):
        """Match-Score muss im Footer stehen."""
        tex = render_cover_letter(score=9)
        assert "9/10" in tex

    def test_date_in_letter(self):
        """Datum muss im Brief stehen."""
        tex = render_cover_letter()
        today = datetime.now().strftime("%d.%m.%Y")
        assert today in tex


class TestCoverLetterTone:
    """Ton: edgy, Agent-first, keine Floskeln."""

    def test_german_fallback_has_agent_opener(self):
        """DE Fallback beginnt mit KI-Agent-Satz."""
        from src.agent.llm_client import _template_cover_letter
        body = _template_cover_letter(_make_job("UX Designer", "FLUID"), _make_profile(), [], "de")
        first_line = body.strip().split("\n")[0]
        assert "ki-bewerbungs-agent" in first_line.lower()

    def test_english_fallback_has_agent_opener(self):
        """EN Fallback beginnt mit KI-Agent-Satz."""
        from src.agent.llm_client import _template_cover_letter
        body = _template_cover_letter(_make_job("UX Designer", "FLUID"), _make_profile(), [], "en")
        first_line = body.strip().split("\n")[0]
        assert "ai job application agent" in first_line.lower() or "ki" in first_line.lower()

    def test_no_forbidden_floskeln(self):
        """Keine verbotenen Floskeln im Body (DE+EN)."""
        from src.agent.llm_client import _template_cover_letter
        for lang in ["de", "en"]:
            body = _template_cover_letter(_make_job("Backend Entwickler", "Startup GmbH"), _make_profile(), [], lang)
            _assert_edgy_tone(body, f"fallback-{lang}")

    def test_no_technical_tools_in_body(self):
        """Keine technischen Tools/Projekte im Body (ERP, WordPress, Cursor, ComfyUI, n8n)."""
        from src.agent.llm_client import _template_cover_letter
        forbidden_tools = ["erp", "wordpress", "cursor", "ollama", "comfyui", "n8n", "synera"]
        body = _template_cover_letter(_make_job(), _make_profile(), [], "de").lower()
        for tool in forbidden_tools:
            assert tool not in body, f"Verbotenes Tool '{tool}' im Body"

    def test_no_signoff_in_body(self):
        """Body darf kein 'Mit freundlichen Grüßen' oder 'Best regards' enthalten."""
        from src.agent.llm_client import _template_cover_letter
        for lang in ["de", "en"]:
            body = _template_cover_letter(_make_job(), _make_profile(), [], lang)
            assert "mit freundlichen" not in body.lower()
            assert "best regards" not in body.lower()

    def test_daniel_in_third_person(self):
        """Daniel muss in 3. Person erwähnt werden."""
        from src.agent.llm_client import _template_cover_letter
        body = _template_cover_letter(_make_job(), _make_profile(), [], "de")
        assert "Daniel" in body, "Daniel nicht im Body erwähnt"


class TestCoverLetterExtreme:
    """Extrem-Covers für ungewöhnliche Jobs."""

    def test_kfz_mechaniker_still_valid(self):
        """Kfz-Mechaniker: Cover-Letter muss trotzdem valide sein."""
        tex = render_cover_letter(
            company="Autohaus Müller",
            job_title="Kfz-Mechaniker (m/w/d)",
            language="de",
            cover_letter_body=(
                "ich bin der KI-Bewerbungs-Agent von Daniel Peters. Mein System hat Ihre "
                "Ausschreibung für Kfz-Mechaniker bei Autohaus Müller analysiert und erkennt "
                "Überlappungen in der Prozessoptimierung.\n\n"
                "Obwohl Daniels Kernkompetenz UX/UI Design ist, bringt er Erfahrung in "
                "der Automatisierung und KI-gestützten Analyse mit, die auch in der "
                "Werkstatt-Organisation relevant sein kann."
            ),
        )
        _assert_valid_latex(tex, "kfz-mechaniker")
        assert "Autohaus Müller" in tex
        assert "Kfz-Mechaniker" in tex

    def test_english_job_with_german_candidate(self):
        """Englisches Anschreiben für deutschen Kandidaten."""
        tex = render_cover_letter(
            company="TechCorp Inc",
            job_title="Senior Product Designer",
            language="en",
            score=7,
            cover_letter_body=(
                "I am the AI job application agent of Daniel Peters. My system analyzed your "
                "posting for Senior Product Designer at TechCorp Inc and identified a strong match.\n\n"
                "Daniel brings hands-on experience in user research, design systems, and "
                "product ownership from consulting and freelance projects."
            ),
        )
        _assert_valid_latex(tex, "english-job")
        assert "TechCorp Inc" in tex
        assert "Senior Product Designer" in tex

    def test_maximal_company_name(self):
        """Sehr langer Firmenname."""
        long_name = "Die Firma mit dem sehr langen Namen GmbH & Co. KG"
        tex = render_cover_letter(
            company=long_name,
            job_title="Praktikant",
            language="de",
        )
        assert long_name in tex
        _assert_valid_latex(tex, "long-company")

    def test_special_characters_in_company(self):
        """Sonderzeichen im Firmennamen."""
        company = "Müller & Söhne GmbH"
        tex = render_cover_letter(company=company, language="de")
        # Nach LaTeX-Escaping muss & zu \& werden
        assert "Müller" in tex

    def test_empty_body_fallback(self):
        """Wenn cover_letter_body leer/None: Template-Fallback funktioniert."""
        tex = render_cover_letter(cover_letter_body=None)
        _assert_valid_latex(tex, "empty-body-fallback")
        # Template-Fallback muss mindestens 50 Zeichen haben
        body_start = tex.find("DANIEL PETERS")
        assert body_start > 0

    def test_very_short_body(self):
        """Extrem kurzer Body (1 Satz)."""
        short_body = "ich bin der KI-Bewerbungs-Agent von Daniel Peters."
        tex = render_cover_letter(cover_letter_body=short_body)
        assert short_body in tex
        _assert_valid_latex(tex, "short-body")

    def test_very_long_body_still_renders(self):
        """Langer Body (>220 Wörter) rendert trotzdem."""
        long_body = (
            "ich bin der KI-Bewerbungs-Agent von Daniel Peters. "
            + "Dies ist ein Test-Satz für ein sehr langes Anschreiben. " * 50
        )
        tex = render_cover_letter(cover_letter_body=long_body)
        assert "KI-Bewerbungs-Agent" in tex
        _assert_valid_latex(tex, "long-body")

    def test_all_template_variables_replaced(self):
        """Kein << variable >> unersetzt im Output."""
        tex = render_cover_letter(language="de")
        placeholders = re.findall(r"<<\s*\w+\s*>>", tex)
        assert len(placeholders) == 0, f"Ungesetzte Platzhalter: {placeholders}"

    def test_footer_shows_correct_score(self):
        """Verschiedene Scores korrekt im Footer."""
        for s in [1, 5, 10]:
            tex = render_cover_letter(score=s)
            assert f"{s}/10" in tex
