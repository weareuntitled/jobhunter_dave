"""src/crawler/filters.py – Pre-Filterung für Jobs."""

from __future__ import annotations

import logging

from src.agent.schemas import JobListing

logger = logging.getLogger("job-hunter")

AUGSBURG_RADIUS = {
    "augsburg", "königsbrunn", "neusäß", "friedberg", "stadtbergen", "gersthofen",
    "landsberg", "landsberg am lech", "aichach", "donauwörth", "dillingen",
    "dillingen an der donau", "günzburg", "nördlingen", "neuburg", "neuburg an der kammer",
    "schrobenhausen", "wertingen", "zell", "merching", "aken", "kissing", "mering",
    "dinkelscherben", "zusmarshausen", "grossaitingen", "kleinaitingen", "wehringen",
    "oberottmarshausen",
}
MUNICH_RADIUS = {
    "münchen", "munich", "freising", "fürstenfeldbruck", "dachau", "starnberg",
    "germering", "garching", "unterhaching", "ottobrunn", "haar", "martinsried",
    "rosenheim", "wolfratshausen", "erding", "neufahrn", "waldkraiburg",
    "kirchheim", "heimstetten", "poing", "grasbrunn", "brunnthal",
    "unterföhring", "oberhaching", "pullach", "gräfelfing", "planegg", "gilching",
}
REMOTE_ONLY_KEYWORDS = {
    "remote", "homeoffice", "home office", "deutschlandweit", "workation",
    "mobiles arbeiten",
}
ONSITE_KEYWORDS = {"on-site", "on site", "onsite", "vor ort", " onsite", "office required", "büro"}
ALL_RADIUS = AUGSBURG_RADIUS | MUNICH_RADIUS


class JobFilter:
    def __init__(self, config: dict) -> None:
        self.config = config
        self.exclude_portal_only = config.get("exclude_portal_only", True)
        self.min_salary = config.get("min_salary_threshold", 0)
        self.remote_preference = config.get("remote_preference", "remote_first")
        self.excluded_companies = [c.lower() for c in config.get("excluded_companies", [])]
        self.keywords = [k.lower() for k in config.get("keywords", [])]
        self.allowed_locations = [l.lower() for l in config.get("allowed_locations", [])]

    def _full_text(self, job: JobListing) -> str:
        return f"{job.title} {job.description} {job.location}".lower()

    def _location_in_radius(self, location_text: str) -> bool:
        normalized = set(location_text.lower().replace("/", " ").replace("-", " ").replace(",", " ").split())
        return bool(normalized & ALL_RADIUS)

    def _is_remote(self, job: JobListing, full_text: str) -> bool:
        if job.remote_type and job.remote_type.value == "remote":
            return True
        if any(w in full_text for w in REMOTE_ONLY_KEYWORDS):
            return True
        return False

    def _is_onsite_in_description(self, job: JobListing) -> bool:
        desc = job.description.lower()
        title_loc = f"{job.title} {job.location}".lower()
        if any(w in desc for w in ONSITE_KEYWORDS):
            return True
        if "office" in desc and "hybrid" not in title_loc:
            return True
        return False

    def should_include(self, job: JobListing) -> bool:
        full_text = self._full_text(job)

        is_remote = self._is_remote(job, full_text)
        in_radius = self._location_in_radius(job.location)
        is_onsite = self._is_onsite_in_description(job)

        if is_onsite:
            is_remote = False

        if not (is_remote or in_radius):
            if self.remote_preference == "remote_only":
                logger.debug(f"   Filtered (not remote): {job.title}")
            else:
                logger.debug(f"   Filtered (location outside radius): {job.title} @ {job.location}")
            return False

        if job.company.lower() in self.excluded_companies:
            logger.debug(f"   Filtered (excluded company): {job.company}")
            return False

        full_text_norm = full_text.replace("/", " ").replace("-", " ").replace("_", " ").lower()
        job_words = set(full_text_norm.split())
        def keyword_matches(kw: str) -> bool:
            kw_words = kw.lower().split()
            return all(w in job_words for w in kw_words)
        if not any(keyword_matches(kw) for kw in self.keywords):
            logger.debug(f"   Filtered (no keyword match): {job.title}")
            return False

        return True
