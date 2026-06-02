"""tests/test_bullet_selector.py – Tests für den BulletSelector."""

import pytest
from pathlib import Path
import tempfile
import yaml

from src.agent.bullet_selector import BulletSelector


@pytest.fixture
def sample_pool() -> Path:
    """Erstellt einen temporären Mini-Bullet-Pool."""
    data = {
        "categories": {
            "ux_ui": [
                "Konzeption und Gestaltung von Webtools für Audi mit Figma.",
                "Usability-Tests geplant und durchgeführt, Ergebnisse in Design-Iterationen umgesetzt.",
                "Designsysteme mit modularen Komponenten in Figma aufgebaut.",
            ],
            "tech_ki": [
                "Lokale LLM-Integration mit Ollama und Docker aufgebaut.",
                "ERP-Migration auf FastAPI/React/SQL-Basis geleitet.",
                "Eigenen KI-Bewerbungs-Agenten entwickelt mit Python 3.12 und async.",
            ],
            "product": [
                "Product Owner für Audi-internes Webtool mit 500 Nutzer:innen.",
                "Scrum Master für crossfunktionales Team von 8 Personen.",
                "Requirements Engineering komplexer Fachprozesse.",
            ],
        },
        "config": {
            "max_in_cv": 12,
            "min_in_cv": 8,
        },
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(data, f)
        return Path(f.name)


class TestBulletSelectorInit:
    def test_loads_pool(self, sample_pool):
        selector = BulletSelector(pool_path=sample_pool)
        assert selector.bullet_count == 9
        assert "ux_ui" in selector.pool
        assert len(selector.pool["ux_ui"]) == 3

    def test_missing_pool_graceful(self):
        selector = BulletSelector(pool_path=Path("/nonexistent/pool.yaml"))
        assert selector.bullet_count == 0
        assert selector.select("Test", "Description") == []


class TestBulletSelection:
    def test_select_returns_correct_count(self, sample_pool):
        selector = BulletSelector(pool_path=sample_pool)
        result = selector.select(
            job_title="UX Designer",
            job_description="Wir suchen einen UX Designer mit Figma Erfahrung.",
            max_bullets=5,
            min_bullets=3,
        )
        assert 3 <= len(result) <= 5

    def test_ux_job_prioritizes_ux_bullets(self, sample_pool):
        selector = BulletSelector(pool_path=sample_pool)
        result = selector.select(
            job_title="Senior UX Designer",
            job_description="Figma, Design Systems, Usability Testing, User Research, Prototyping.",
            max_bullets=3,
            min_bullets=3,
        )
        # UX-bezogene Bullets sollten in den Top 3 sein
        assert any("Figma" in b or "Usability" in b for b in result)

    def test_tech_job_prioritizes_tech_bullets(self, sample_pool):
        selector = BulletSelector(pool_path=sample_pool)
        result = selector.select(
            job_title="Full-Stack Developer",
            job_description="Python, FastAPI, Docker, React, KI-Integration, LLM, Ollama.",
            max_bullets=3,
            min_bullets=3,
        )
        assert any("Python" in b or "Ollama" in b or "LLM" in b for b in result)

    def test_product_job_prioritizes_po_bullets(self, sample_pool):
        selector = BulletSelector(pool_path=sample_pool)
        result = selector.select(
            job_title="Product Owner",
            job_description="Scrum, Backlog, Product Roadmap, Stakeholder Management.",
            max_bullets=3,
            min_bullets=3,
        )
        assert any("Product Owner" in b or "Scrum" in b for b in result)

    def test_select_by_category(self, sample_pool):
        selector = BulletSelector(pool_path=sample_pool)
        result = selector.select_by_category(
            job_title="UX Designer",
            job_description="Figma, Design Systems, Usability Testing.",
            bullets_per_category=2,
        )
        assert len(result) == 3  # 3 categories
        assert len(result["ux_ui"]) == 2
        assert len(result["tech_ki"]) == 2
        assert len(result["product"]) == 2

    def test_max_bullets_limit(self, sample_pool):
        selector = BulletSelector(pool_path=sample_pool)
        result = selector.select(
            job_title="Generic",
            job_description="Some job.",
            max_bullets=4,
            min_bullets=2,
        )
        assert len(result) <= 4


class TestKeywordExtraction:
    def test_extracts_german_keywords(self, sample_pool):
        selector = BulletSelector(pool_path=sample_pool)
        keywords = selector._extract_keywords(
            "Wir suchen einen Senior UX Designer mit Figma und User Research Erfahrung."
        )
        assert "figma" in keywords
        assert "sucht" not in keywords  # stopword-ish
        assert "user research" in keywords

    def test_extracts_english_keywords(self, sample_pool):
        selector = BulletSelector(pool_path=sample_pool)
        keywords = selector._extract_keywords(
            "Looking for a Product Designer with Figma experience and design systems."
        )
        assert "figma" in keywords
        assert "product designer" in keywords
        assert "design systems" in keywords
        assert "looking" not in keywords  # stopword
