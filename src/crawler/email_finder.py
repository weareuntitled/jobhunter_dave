"""src/crawler/email_finder.py – Findet Kontakt-E-Mails von Unternehmens-Websites."""

from __future__ import annotations

import logging
import re
from urllib.parse import urljoin, urlparse

import httpx

logger = logging.getLogger("job-hunter")

EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

CAREER_PATHS = ["/karriere", "/careers", "/jobs", "/career", "/about", "/impressum", "/contact"]


class EmailFinder:
    def __init__(self, timeout: int = 10) -> None:
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; JobHunter/1.0)"},
        )

    async def find(self, company_name: str, company_url: str | None = None) -> str | None:
        """Findet eine E-Mail-Adresse für ein Unternehmen."""
        urls_to_try: list[str] = []

        if company_url:
            domain = self._extract_domain(company_url)
            if domain:
                urls_to_try.append(f"https://{domain}")
                for path in CAREER_PATHS:
                    urls_to_try.append(f"https://{domain}{path}")

        # Fallback: Google-like Suche über die Domain
        if not urls_to_try:
            name_slug = company_name.lower().replace(" ", "").replace("gmbh", "").replace("ag", "")
            urls_to_try = [f"https://{name_slug}.de", f"https://www.{name_slug}.de"]

        for url in urls_to_try[:5]:  # max 5 Versuche
            try:
                email = await self._scrape_email(url)
                if email:
                    return email
            except Exception:
                continue

        return None

    async def _scrape_email(self, url: str) -> str | None:
        """Scraped eine Seite nach E-Mail-Adressen."""
        try:
            response = await self.client.get(url)
            response.raise_for_status()
            text = response.text.lower()

            # Priorität: bekannte Karriere-Patterns
            career_emails = [
                f"jobs@{self._extract_domain(url)}",
                f"karriere@{self._extract_domain(url)}",
                f"bewerbung@{self._extract_domain(url)}",
                f"career@{self._extract_domain(url)}",
            ]
            for email in career_emails:
                if email in text:
                    return email

            # Fallback: erste gefundene E-Mail
            emails = EMAIL_PATTERN.findall(response.text)
            if emails:
                # Filter unerwünschte
                for email in emails:
                    skip = any(x in email.lower() for x in ["example", "test", "noreply", "no-reply", "@linkedin", "@indeed", "@stepstone", "@xing", "privacy", "datenschutz"])
                    if not skip:
                        return email.lower()
        except Exception:
            pass
        return None

    def _extract_domain(self, url: str) -> str | None:
        try:
            parsed = urlparse(url)
            if parsed.netloc:
                return parsed.netloc.replace("www.", "").split("/")[0]
        except Exception:
            pass
        return None

    async def close(self) -> None:
        await self.client.aclose()
