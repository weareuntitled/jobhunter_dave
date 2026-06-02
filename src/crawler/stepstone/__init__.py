"""src/crawler/stepstone/__init__.py – Stepstone.de scraper (requests + BS4)."""

from __future__ import annotations

import hashlib
import logging
import re
import time
from typing import Any
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup, Tag

logger = logging.getLogger("job-hunter")

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

STEPSTONE_DOMAIN = "www.stepstone.de"

KNOWN_CITIES = {
    "augsburg", "berlin", "hamburg", "münchen", "munich", "köln", "cologne",
    "frankfurt", "stuttgart", "düsseldorf", "dortmund", "essen", "leipzig",
    "bremen", "dresden", "hannover", "nürnberg", "duisburg", "bochum",
    "wuppertal", "bielefeld", "bonn", "mannheim", "karlsruhe", "augsburg",
    "freiburg", "kiel", "rostock", "erfurt", "mainz", "saarbrücken",
    "potsdam", "regensburg", "würzburg", "ingolstadt", "heidelberg",
    "paderborn", "osnabrück", "cottbus", "braunschweig", "halle", "krefeld",
    "magdeburg", "passau", "ludwigshafen", "oldenburg", "lemgo", "gelsenkirchen",
    "mönchengladbach", "bielefeld", "gießen", "siegen", "witten",
    "göttingen", "chemnitz", "hagen", "kassel", "hamm", "ulan",
    "neuss", "ingolstadt", "offenbach", "fulda", "darmstadt",
}


def _build_search_url(query: str, location: str, radius: int = 50, page: int = 1) -> str:
    query_slug = query.lower().replace(" ", "-").replace("/", "-")
    base = f"https://{STEPSTONE_DOMAIN}/jobs/{query_slug}/in-{location}"
    params: dict[str, Any] = {"radius": radius}
    if page > 1:
        params["page"] = page
    qs = urlencode(params)
    return f"{base}?{qs}"


def _fetch_html(url: str, timeout: int = 15) -> str:
    headers = {"User-Agent": DEFAULT_UA, "Accept-Language": "de-DE,de;q=0.9,en;q=0.8"}
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        if resp.ok:
            return resp.text
    except Exception as e:
        logger.warning(f"Stepstone fetch error: {e}")
    return ""


def _clean_location(loc: str) -> str:
    """Entfernt UI-Text wie 'Gehalt anzeigen' aus der Location."""
    if not loc:
        return loc
    # Remove known UI fragments
    remove_patterns = [
        "Gehalt anzeigen", "Schnelle Bewerbung", "Teilweise Home-Office",
        "Home-Office-Optionen", "Anschreiben nicht erforderlich",
        "Vollzeit", "Teilzeit", "Minijob",
    ]
    for pat in remove_patterns:
        loc = loc.replace(pat, "")
    # Clean up trailing commas and whitespace
    loc = loc.strip().rstrip(",").strip()
    return loc or "Remote"


def _extract_company_location(text_after_title: str) -> tuple[str, str]:
    text = text_after_title.strip()

    # Heuristic: known city names indicate where location starts
    words = text.split()
    for i, word in enumerate(words):
        clean = re.sub(r"[^a-zA-ZäöüÄÖÜß-]", "", word.lower())
        if clean in KNOWN_CITIES:
            company = " ".join(words[:i]).strip(" ,.")
            location = " ".join(words[i:]).strip(" ,.")
            return company, location

    # Fallback: first word group = company, rest = location
    if len(words) > 3:
        mid = len(words) // 2
        return " ".join(words[:mid]), " ".join(words[mid:])

    return text, ""


def _parse_jobs_from_html(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    jobs: list[dict[str, Any]] = []

    job_items = soup.select('[data-testid="job-item"]')
    if not job_items:
        job_items = soup.select("article")

    for item in job_items:
        title_el = item.select_one('[data-testid="job-item-title"]')
        if not title_el:
            title_el = item.select_one("h2, h3")
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        if not title:
            continue

        # URL
        link_el = item.select_one('a[href*="/stellenangebote"]')
        if not link_el:
            link_el = item.select_one("a[href*='/jobs/']")
        if not link_el:
            link_el = title_el.find_parent("a") or title_el.select_one("a")
        job_url = ""
        if link_el and link_el.get("href"):
            href = link_el["href"]
            job_url = href if href.startswith("http") else f"https://{STEPSTONE_DOMAIN}{href}"

        # Company + Location from the div after title
        company = ""
        location = ""
        content_el = item.select_one('[data-testid="job-card-content"]')
        if content_el:
            # Get all text after the title
            full_text = content_el.get_text(separator=" ", strip=True)
            # Remove the title from the beginning
            if full_text.startswith(title):
                after_title = full_text[len(title):].strip()
            else:
                after_title = full_text
            company, location = _extract_company_location(after_title)
            location = _clean_location(location)

        # Description - find the div after job-card-content (skip <style> siblings)
        description = ""
        card = item.select_one('[data-testid="job-card-content"]')
        if card:
            sib = card.find_next_sibling()
            while sib and sib.name == "style":
                sib = sib.find_next_sibling()
            if sib and sib.name == "div":
                text = sib.get_text(strip=True)
                if len(text) > 30:
                    # Remove UI prefixes
                    for prefix in ["Schnelle Bewerbung", "Anschreiben nicht erforderlich", "Gehalt anzeigen"]:
                        if text.startswith(prefix):
                            text = text[len(prefix):].strip()
                    description = text[:1000]

        # Salary — dedicated element + regex fallback
        salary = ""
        salary_el = item.select_one('[data-testid="job-item-salary"]')
        if salary_el:
            salary = salary_el.get_text(strip=True)

        if not salary:
            full_card_text = item.get_text(separator=" ", strip=True)
            m = re.search(
                r"(\d{2}\.?\d{3}\s*[€\-–]\s*\d{2}\.?\d{3}[€\s]*)",
                full_card_text,
            )
            if m:
                salary = m.group(1).strip().replace("\xa0", " ")

        job_id = hashlib.sha256(f"{title}{company}{job_url}".encode()).hexdigest()[:16]

        jobs.append({
            "jobTitle": title,
            "companyName": company,
            "location": location,
            "jobUrl": job_url,
            "jobDescription": description,
            "salary": salary,
            "employmentType": "",
            "datePosted": "",
            "category": "",
            "experienceLevel": "",
            "source": STEPSTONE_DOMAIN,
            "id": job_id,
        })

    return jobs


def scrape_stepstone(
    query: str,
    location: str = "augsburg",
    radius: int = 50,
    max_pages: int = 2,
    throttle: float = 1.5,
) -> list[dict[str, Any]]:
    all_jobs: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for page in range(1, max_pages + 1):
        url = _build_search_url(query, location, radius, page)
        logger.info(f"Stepstone: fetching page {page} → {url}")
        html = _fetch_html(url)
        if not html:
            break

        jobs = _parse_jobs_from_html(html)
        if not jobs:
            break

        for job in jobs:
            if job["jobUrl"] and job["jobUrl"] not in seen_urls:
                seen_urls.add(job["jobUrl"])
                all_jobs.append(job)

        if page < max_pages:
            time.sleep(throttle)

    logger.info(f"Stepstone: {len(all_jobs)} unique jobs found")
    return all_jobs
