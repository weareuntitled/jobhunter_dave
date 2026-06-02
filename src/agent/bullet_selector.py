"""src/agent/bullet_selector.py – Keyword-basierte Bullet-Selektion mit Employer-Tags."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import NamedTuple

import yaml

logger = logging.getLogger("job-hunter")

POOL_PATH = Path("data/bullet_pool.yaml")


class ScoredBullet(NamedTuple):
    score: float
    category: str
    employer: str
    text: str


class BulletSelector:
    def __init__(self, pool_path: Path | None = None) -> None:
        self.pool_path = pool_path or POOL_PATH
        self.pool: dict[str, list[dict[str, str]]] = {}
        self._load_pool()

    def _load_pool(self) -> None:
        if not self.pool_path.exists():
            logger.warning(f"Bullet pool not found at {self.pool_path}")
            return
        with open(self.pool_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self.pool = data.get("categories", {})
        total = sum(len(b) for b in self.pool.values())
        logger.debug(f"Loaded {total} bullets in {len(self.pool)} categories")

    def select(
        self,
        job_title: str,
        job_description: str,
        max_bullets: int = 12,
        min_bullets: int = 8,
    ) -> list[str]:
        """Wählt Bullet-Texte per Keyword-Matching aus (ohne Employer-Tag)."""
        if not self.pool:
            return []
        job_text = f"{job_title} {job_description}".lower()
        keywords = self._extract_keywords(job_text)
        scored = []
        for category, bullets in self.pool.items():
            for entry in bullets:
                text = entry.get("text", entry) if isinstance(entry, dict) else entry
                score = self._score_bullet(text.lower(), keywords, job_text)
                scored.append((score, text))
        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:max_bullets]
        if len(top) < min_bullets:
            top = scored[:min_bullets]
        return [text for _, text in top]

    def select_scored(self, job_title: str, job_description: str, max_bullets: int = 12, min_bullets: int = 8) -> list[ScoredBullet]:
        """Wählt Bullets mit Employer-Tag aus."""
        if not self.pool:
            return []
        job_text = f"{job_title} {job_description}".lower()
        keywords = self._extract_keywords(job_text)
        scored: list[ScoredBullet] = []
        for category, bullets in self.pool.items():
            for entry in bullets:
                if isinstance(entry, dict):
                    text = entry.get("text", "")
                    employer = entry.get("employer", "untitled")
                else:
                    text = str(entry)
                    employer = "untitled"
                score = self._score_bullet(text.lower(), keywords, job_text)
                scored.append(ScoredBullet(score, category, employer, text))
        scored.sort(key=lambda x: x.score, reverse=True)
        top = scored[:max_bullets]
        if len(top) < min_bullets:
            top = scored[:min_bullets]
        return top

    def split_by_employer(self, job_title: str, job_description: str, max_bullets: int = 12, min_bullets: int = 8) -> tuple[list[str], list[str]]:
        """Split selektierte Bullets in 8020 und untitled-ux."""
        scored = self.select_scored(job_title, job_description, max_bullets, min_bullets)
        bullets_8020 = [sb.text for sb in scored if sb.employer == "8020"]
        bullets_untitled = [sb.text for sb in scored if sb.employer == "untitled"]
        return bullets_8020, bullets_untitled

    def select_by_category(
        self, job_title: str, job_description: str, bullets_per_category: int = 2,
    ) -> dict[str, list[str]]:
        if not self.pool:
            return {}
        job_text = f"{job_title} {job_description}".lower()
        keywords = self._extract_keywords(job_text)
        result: dict[str, list[str]] = {}
        for category, bullets in self.pool.items():
            entries = []
            for entry in bullets:
                text = entry.get("text", entry) if isinstance(entry, dict) else entry
                entries.append((self._score_bullet(text.lower(), keywords, job_text), text))
            entries.sort(key=lambda x: x[0], reverse=True)
            result[category] = [t for _, t in entries[:bullets_per_category]]
        return result

    def _extract_keywords(self, text: str) -> set[str]:
        stopwords = {
            "der", "die", "das", "und", "für", "mit", "bei", "von", "den",
            "the", "and", "for", "with", "you", "are", "our", "your", "we",
            "ist", "ein", "eine", "auf", "aus", "auch", "wird", "werden",
            "zu", "zur", "zum", "im", "in", "an", "als", "wie", "sich",
            "oder", "nach", "über", "durch", "nicht", "kein", "kann",
            "sowie", "des", "dem", "hat", "haben", "sein", "sind",
            "looking", "this", "that", "have", "has", "been", "will",
            "would", "should", "could", "about", "into", "more",
        }
        words = text.replace(",", " ").replace(".", " ").replace("(", " ").replace(")", " ").split()
        keywords = set()
        for w in words:
            w = w.strip().lower()
            if len(w) > 3 and w not in stopwords:
                keywords.add(w)
        words_clean = [w.strip().lower() for w in words if w.strip().lower() not in stopwords]
        for i in range(len(words_clean) - 1):
            bigram = f"{words_clean[i]} {words_clean[i+1]}"
            if len(bigram) > 5:
                keywords.add(bigram)
        return keywords

    def _score_bullet(self, bullet_lower: str, keywords: set[str], job_text: str) -> float:
        score = 0.0
        for kw in keywords:
            if kw in bullet_lower:
                score += 1.0
        return score

    @property
    def bullet_count(self) -> int:
        return sum(len(b) for b in self.pool.values())
