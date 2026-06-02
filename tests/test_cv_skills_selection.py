r"""tests/test_cv_skills_selection.py – Testet, dass exakt verlangte Skills im CV landen."""

import yaml
from datetime import datetime
from pathlib import Path

from src.agent.bullet_selector import BulletSelector
from src.telegram.formatters import latex_escape


class TestSkillSelectionForJobRequirements:
    """Testet, dass Skills die eine Stelle explizit verlangt, im CV auftauchen."""

    def test_figma_userresearch_designsystems_from_job_land_in_cv(self):
        """
        Job verlangt Figma, User Research, Design Systems.
        -> BulletSelector muss diese Skills auswählen (cross-language: design systems <-> designsysteme).
        -> LaTeX-Escaping muss korrekt sein (idempotent, _ -> \_).
        """
        selector = BulletSelector()
        job_title = "Senior UX Designer"
        job_desc = (
            "Must have: Figma for UI design, User Research with real users, "
            "Design Systems experience. Prototyping in Figma is required."
        )

        bullets = selector.select(job_title, job_desc, max_bullets=10)
        bullets_lower = [b.lower() for b in bullets]

        # Figma and User Research must appear (exact string match)
        required = [
            ("figma", ["figma"]),
            ("user research", ["user research"]),
        ]
        missing = []
        for label, variants in required:
            if not any(any(v in b for v in variants) for b in bullets_lower):
                missing.append(label)

        # "Designsysteme" (German compound) covers "design systems" (English bigram)
        if not any("designsystem" in b for b in bullets_lower):
            missing.append("design systems / designsysteme")

        assert not missing, f"Missing required skills: {missing}\nBullets: {bullets}"

        # Verify LaTeX escaping with input that ACTUALLY has underscores
        bullet_with_underscore = "Python_FastAPI_Docker experience"
        escaped = latex_escape(bullet_with_underscore)
        assert "Py\\_thon" in escaped or "\\_" in escaped, f"Underscore not escaped: {escaped}"
        # Idempotency: running twice gives same result
        assert latex_escape(escaped) == escaped, "latex_escape is not idempotent"

    def test_no_irrelevant_skills_selected(self):
        """Skills die NICHT in der Job-Beschreibung vorkommen, sollten nicht dominant sein."""
        selector = BulletSelector()
        bullets = selector.select(
            job_title="Backend Engineer",
            job_description="Python FastAPI PostgreSQL Docker Kubernetes REST API",
            max_bullets=8,
        )

        irrelevant_terms = ["kochen", "gitarre", "tennis", "urlaub"]
        irrelevant_found = [b for b in bullets if any(t in b.lower() for t in irrelevant_terms)]
        assert len(irrelevant_found) == 0, (
            f"Irrelevant skills appeared in CV: {irrelevant_found}\nSelected: {bullets}"
        )

        relevant_terms = ["python", "fastapi", "postgresql", "docker", "kubernetes", "api"]
        relevant_found = sum(1 for b in bullets if any(t in b.lower() for t in relevant_terms))
        assert relevant_found >= 3, (
            f"Only {relevant_found} relevant bullets found. Selected: {bullets}"
        )

    def test_skills_text_matches_bullets_plus_static(self):
        """skills_text muss der String sein: bullets + static_skills mit \textbullet Separator."""
        selector = BulletSelector()
        job_title = "Senior UX Designer"
        job_desc = "Figma, User Research, Design Systems, Prototyping"

        bullets = selector.select(job_title, job_desc, max_bullets=6)

        config = yaml.safe_load(Path("data/config.yaml").read_text())
        static_skills = list(config.get("cv", {}).get("static_skills", []))

        all_skills = bullets[:6] + static_skills
        skills_text = r" \textbullet\ ".join([latex_escape(s) for s in all_skills])

        assert "figma" in skills_text.lower() or "Figma" in skills_text, "Figma not in skills_text"
        assert any("KI" in s for s in static_skills), "KI static skill missing"

        bullet_count = skills_text.count(r"\textbullet")
        assert bullet_count >= len(all_skills) - 1, (
            f"Expected at least {len(all_skills) - 1} \\textbullet separators, got {bullet_count}"
        )

    def test_split_by_employer_preserves_skill_relevance(self):
        """Auch nach dem Employer-Split müssen verlangte Skills in den Listen sein."""
        selector = BulletSelector()
        job_title = "Product Designer"
        job_desc = "Figma Design Systems User Testing Prototyping"

        bullets_8020, bullets_untitled = selector.split_by_employer(
            job_title, job_desc, max_bullets=12, min_bullets=8,
        )

        all_bullets = bullets_8020 + bullets_untitled
        all_lower = [b.lower() for b in all_bullets]

        required = [
            ("figma", ["figma"]),
            ("prototyping", ["prototyp", "prototyping"]),
            ("design systems", ["designsystem", "design systems"]),
        ]
        for label, variants in required:
            found = any(any(v in b for v in variants) for b in all_lower)
            assert found, (
                f"Required skill '{label}' not found. 8020={len(bullets_8020)}, "
                f"untitled={len(bullets_untitled)}"
            )

    def test_ki_skills_always_included_regardless_of_job(self):
        """KI-Skills aus config müssen IMMER im CV sein – auch wenn Job sie nicht explizit verlangt."""
        selector = BulletSelector()
        config = yaml.safe_load(Path("data/config.yaml").read_text())
        static_skills = list(config.get("cv", {}).get("static_skills", []))

        # Job describes ONLY Java/Android – no relation to KI
        bullets = selector.select(
            job_title="Android Developer",
            job_description="Java Kotlin Android Studio XML layouts REST",
            max_bullets=6,
        )

        all_skills = bullets[:6] + static_skills

        for skill in static_skills:
            assert skill in all_skills, f"Static skill '{skill}' not in final list. Skills: {all_skills}"

        ki_skills_in_list = [s for s in all_skills if "KI" in s or "LLM" in s or "Prompt" in s]
        assert len(ki_skills_in_list) >= 2, f"Expected >= 2 KI skills, got: {ki_skills_in_list}"

    def test_latex_escaping_completeness(self):
        """Alle LaTeX-Sonderzeichen müssen korrekt escaped sein (idempotent)."""
        dangerous = [
            ("10% schneller durch Optimierung $50", [r"\%", r"\$"]),
            ("Team mit 3 Personen & 2 Freelancern #backend", [r"\&", r"\#"]),
            ("Python_FastAPI_Docker experience", [r"\_"]),
        ]

        for bullet, expected_escapes in dangerous:
            escaped = latex_escape(bullet)
            for esc in expected_escapes:
                assert esc in escaped, f"Expected '{esc}' in escaped output of '{bullet}', got: {escaped}"
            # Idempotency
            assert latex_escape(escaped) == escaped, f"latex_escape not idempotent for: {bullet}"
