"""tests/test_crawler.py – Tests für Job-Filterung."""

import pytest
from src.crawler.filters import JobFilter
from src.agent.schemas import JobListing, JobSource


class TestJobFilter:
    def test_basic_keyword_match(self):
        config = {
            "exclude_portal_only": False,
            "keywords": ["UX", "Designer"],
            "excluded_companies": [],
        }
        filter_obj = JobFilter(config)

        job = JobListing(
            id="1", title="UX Designer", company="Corp",
            url="https://corp.de", source=JobSource.LINKEDIN,
            description="We need a UX Designer.",
            has_email_contact=True,
        )
        assert filter_obj.should_include(job) is True

    def test_portal_only_filter_disabled(self):
        config = {
            "exclude_portal_only": True,
            "keywords": ["UX"],
            "excluded_companies": [],
        }
        filter_obj = JobFilter(config)

        job = JobListing(
            id="2", title="UX Designer", company="Corp",
            url="https://corp.de", source=JobSource.STEPSTONE,
            description="Apply via portal only.",
            has_email_contact=False,
        )
        assert filter_obj.should_include(job) is True

    def test_excluded_company(self):
        config = {
            "exclude_portal_only": False,
            "keywords": ["UX"],
            "excluded_companies": ["BadCorp"],
        }
        filter_obj = JobFilter(config)

        job = JobListing(
            id="3", title="UX Designer", company="BadCorp",
            url="https://bad.de", source=JobSource.INDEED,
            description="Great job at BadCorp.",
            has_email_contact=True,
        )
        assert filter_obj.should_include(job) is False

    def test_no_keyword_match(self):
        config = {
            "exclude_portal_only": False,
            "keywords": ["Python", "Backend"],
            "excluded_companies": [],
        }
        filter_obj = JobFilter(config)

        job = JobListing(
            id="4", title="Nurse", company="Hospital",
            url="https://hospital.de", source=JobSource.LINKEDIN,
            description="Medical staff needed for nursing positions.",
            has_email_contact=True,
        )
        assert filter_obj.should_include(job) is False

    def test_remote_only_filter(self):
        config = {
            "exclude_portal_only": False,
            "keywords": ["UX"],
            "excluded_companies": [],
            "remote_preference": "remote_only",
        }
        filter_obj = JobFilter(config)

        job_remote = JobListing(
            id="5", title="UX Designer", company="RemoteCo",
            url="https://remote.co", source=JobSource.LINKEDIN,
            description="Fully remote position available now.",
            has_email_contact=True,
        )
        assert filter_obj.should_include(job_remote) is True

        job_onsite = JobListing(
            id="6", title="UX Designer", company="OfficeCo",
            url="https://office.co", source=JobSource.INDEED,
            description="On-site in Berlin office required.",
            has_email_contact=True,
        )
        assert filter_obj.should_include(job_onsite) is False

    def test_case_insensitive_company_filter(self):
        config = {
            "exclude_portal_only": False,
            "keywords": ["UX"],
            "excluded_companies": ["badcorp"],
        }
        filter_obj = JobFilter(config)

        job = JobListing(
            id="7", title="UX", company="BadCorp",
            url="https://bad.de", source=JobSource.LINKEDIN,
            description="This company is BadCorp and not a good fit.",
            has_email_contact=True,
        )
        assert filter_obj.should_include(job) is False
