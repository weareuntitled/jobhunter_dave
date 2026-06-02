"""src/crawler/scraper.py – JobSpy Async-Wrapper + Stepstone mit Progress-Callback."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import logging
import random
from collections.abc import Callable, Awaitable
from datetime import datetime

from jobspy import scrape_jobs, Site as JobSpySite

from src.agent.schemas import JobListing, JobSource, WorkMode
from src.crawler.filters import JobFilter

STEPSTONE_SITES = {"stepstone"}

SITE_MAP: dict[str, JobSpySite] = {
    "linkedin": JobSpySite.LINKEDIN,
    "indeed": JobSpySite.INDEED,
    "glassdoor": JobSpySite.GLASSDOOR,
    "google": JobSpySite.GOOGLE,
}

logger = logging.getLogger("job-hunter")

ProgressCallback = Callable[[str], Awaitable[None] | None]


async def _call_progress(cb: ProgressCallback | None, msg: str) -> None:
    """Ruft Progress-Callback auf (sync oder async)."""
    if cb is None:
        return
    result = cb(msg)
    if inspect.isawaitable(result):
        await result


class JobScraper:
    def __init__(self, config: dict) -> None:
        self.config = config
        self.filter = JobFilter(config)

    async def fetch_jobs(self, on_progress: ProgressCallback | None = None) -> list[JobListing]:
        """Scrapes jobs from configured sources. Optional progress callback."""
        all_jobs = []

        for site in self.config["sites"]:
            await _call_progress(on_progress, f"🔍 Scrape {site}...")

            try:
                if site in STEPSTONE_SITES:
                    jobs = await self._scrape_stepstone(site, on_progress)
                else:
                    jobs = await self._scrape_jobspy(site, on_progress)

                all_jobs.extend(jobs)

                if on_progress and jobs:
                    await _call_progress(on_progress, f"✅ {site}: {len(jobs)} Jobs gefunden")

                delay = random.uniform(2, 5)
                await asyncio.sleep(delay)

            except Exception as e:
                logger.warning(f"Scraping {site} failed: {e}")
                continue

        if on_progress:
            await _call_progress(on_progress, f"📊 Gesamt: {len(all_jobs)} Jobs nach Filterung")
        return all_jobs

    async def _scrape_stepstone(
        self, site: str, on_progress: ProgressCallback | None = None,
    ) -> list[JobListing]:
        from src.crawler.stepstone import _build_search_url, _fetch_html, _parse_jobs_from_html
        from src.crawler.keyword_tracker import get_next, advance, set_current

        stepstone_cfg = self.config.get("stepstone", {})
        radius = stepstone_cfg.get("radius", 50)
        max_pages = stepstone_cfg.get("max_pages", 5)
        target = stepstone_cfg.get("target_results", 15)

        all_jobs = []
        seen_urls: set[str] = set()
        scraped_pages = 0
        max_scrapes = 40  # 48 keywords × 5 pages = viel, aber begrenzt

        while len(all_jobs) < target and scraped_pages < max_scrapes:
            tasks = get_next(self.config["keywords"], max_pages=max_pages)
            if not tasks:
                break

            keyword, page = tasks[0]
            set_current(keyword)

            if on_progress:
                await _call_progress(on_progress,
                    f"📄 Stepstone: '{keyword}' Seite {page} "
                    f"({len(all_jobs)}/{target} Jobs)"
                )

            url = _build_search_url(
                keyword,
                self.config.get("location", "augsburg").lower().replace(" ", "-"),
                radius, page,
            )
            html = await asyncio.to_thread(_fetch_html, url)
            advance()
            scraped_pages += 1

            if not html:
                continue

            raw = _parse_jobs_from_html(html)
            for row in raw:
                job_url = row.get("jobUrl", "")
                if job_url and job_url not in seen_urls:
                    seen_urls.add(job_url)
                    job = self._stepstone_row_to_job(row, site)
                    if self.filter.should_include(job):
                        all_jobs.append(job)
                        if len(all_jobs) >= target:
                            break

        return all_jobs

    async def _scrape_jobspy(
        self, site: str, on_progress: ProgressCallback | None = None,
    ) -> list[JobListing]:
        jobspy_site = SITE_MAP.get(site)
        if not jobspy_site:
            return []

        location = self.config.get("location", "Augsburg, Germany")
        search_terms = self.config.get("keywords", [])[:5]
        search_term = " OR ".join(search_terms[:3])

        if on_progress:
            await _call_progress(on_progress, f"🔍 JobSpy ({site}): '{search_term[:50]}...'")

        try:
            result = await asyncio.to_thread(
                scrape_jobs,
                site=[jobspy_site],
                search_term=search_term,
                location=location,
                results_wanted=50,
                hours_old=168,
                country_de=True,
            )
        except Exception as e:
            logger.warning(f"JobSpy {site} scrape failed: {e}")
            return []

        jobs = []
        for row in result.jobs:
            job = JobListing(
                id=row.id or hashlib.md5(f"{row.title}{row.company}".encode()).hexdigest()[:12],
                title=row.title or "Unknown",
                company=row.company or "Unknown",
                location=row.location or "",
                url=row.url or "",
                description=row.description or "",
                source=JobSource.JOBSPY,
                work_mode=None,
                posted_at=row.date_posted,
                salary=None,
            )
            if self.filter.should_include(job):
                jobs.append(job)

        if on_progress:
            await _call_progress(on_progress, f"✅ JobSpy ({site}): {len(jobs)} Jobs nach Filter")
        return jobs

    def _stepstone_row_to_job(self, row: dict, site: str) -> JobListing:
        job_url = row.get("jobUrl", "")
        job_id = hashlib.md5(job_url.encode()).hexdigest()[:12] if job_url else "unknown"

        title = row.get("jobTitle") or row.get("title", "Unknown")
        company = row.get("companyName") or row.get("company", "Unknown")
        location = row.get("location", "")
        description = row.get("jobDescription") or row.get("description", "") or f"{title} at {company}"

        title_lower = title.lower()
        desc_lower = description.lower()
        combined = f"{title_lower} {desc_lower}"

        remote_keywords = ["remote", "homeoffice", "home office", "deutschlandweit", "workation"]
        onsite_keywords = ["vor-ort", "vor ort", "büro", "office"]
        hybrid_keywords = ["hybrid", "mischform"]

        work_mode = None
        if any(kw in combined for kw in remote_keywords):
            work_mode = WorkMode.REMOTE
        elif any(kw in combined for kw in onsite_keywords):
            work_mode = WorkMode.ONSITE
        elif any(kw in combined for kw in hybrid_keywords):
            work_mode = WorkMode.HYBRID

        salary = row.get("salary", "") or None
        if not salary:
            # Fallback: suche nach Gehaltsangabe in Title/Desc
            import re
            title_desc = f"{title} {description}"
            m = re.search(r"(\d{2}\.?\d{3}[\s]*[–\-]\s*\d{2}\.?\d{3})", title_desc)
            if m:
                salary = m.group(1)

        return JobListing(
            id=job_id,
            title=title,
            company=company,
            location=location,
            url=job_url,
            description=description,
            source=JobSource.STEPSTONE,
            work_mode=work_mode,
            posted_at=None,
            salary_range=salary,
        )
