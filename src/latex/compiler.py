"""src/latex/compiler.py – Tectonic-Compiler für Anschreiben-PDFs."""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from pathlib import Path

from jinja2 import Environment

from src.agent.schemas import EvaluateResponse, JobListing
from src.telegram.formatters import latex_escape

logger = logging.getLogger("job-hunter")

# Jinja2 mit alternativen Delimitern für LaTeX-Kompatibilität
latex_env = Environment(
    block_start_string="<%",
    block_end_string="%>",
    variable_start_string="<<",
    variable_end_string=">>",
    comment_start_string="<#",
    comment_end_string="#>",
)


def _format_name_upper(name: str) -> str:
    """Formatiert Namen als 'NACHNAME,\\VORNAME' für das Grid-Layout."""
    parts = name.rsplit(" ", 1)
    if len(parts) == 2:
        return f"{parts[1].upper()},\\\\{parts[0].upper()}"
    return name.upper()


def _find_tectonic() -> str:
    """Findet das tectonic Binary an verschiedenen Pfaden."""
    import shutil
    candidates = [
        os.path.expanduser("~/.local/bin/tectonic"),
        "tectonic",
        "/usr/local/bin/tectonic",
    ]
    for candidate in candidates:
        if shutil.which(candidate):
            return candidate
    return "tectonic"


class LaTeXCompiler:
    def __init__(self, config: dict) -> None:
        self.output_dir = Path(config["output_dir"])
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.template_dir = Path(config.get("template_dir", "./src/latex/templates"))
        self.portfolio_url = config["portfolio_url"]

    async def compile(
        self,
        evaluation: EvaluateResponse,
        job: JobListing,
        profile_data: dict,
    ) -> str:
        """Kompiliert das Anschreiben zu PDF und gibt den Pfad zurück."""

        # Template laden
        template_path = self.template_dir / "cover_letter.tex"
        template_text = template_path.read_text(encoding="utf-8")
        template = latex_env.from_string(template_text)

        # Template-Variablen
        name = profile_data.get("name", "Daniel Peters")
        lang = profile_data.get("application_language", "de")

        context = {
            "applicant_name": latex_escape(name),
            "applicant_name_upper": _format_name_upper(name),
            "applicant_title": latex_escape(profile_data.get("title", "UX/UI Designer")),
            "applicant_location": latex_escape(profile_data.get("location", "Augsburg")),
            "applicant_email": latex_escape(profile_data.get("email", "hi@untitled-ux.de")),
            "applicant_phone": latex_escape(profile_data.get("phone", "+49 173 5231109")),
            "portfolio_url": self.portfolio_url,
            "linkedin_url": profile_data.get("linkedin_url", ""),
            "job_title": latex_escape(job.title),
            "company": latex_escape(job.company),
            "job_location": latex_escape(job.location),
            "job_url": str(job.url),
            "cover_letter_body": latex_escape(evaluation.adapted_cover_letter),
            "score": evaluation.score,
            "date": profile_data.get("date", "\\today"),
            "include_photo": profile_data.get("include_photo", False),
            "photo_path": profile_data.get("photo_path", ""),
            "salary_expectation": profile_data.get("salary_expectation", ""),
            "salary_min": profile_data.get("salary_min", 56000),
            "salary_max": profile_data.get("salary_max", 70000),
            "availability": profile_data.get("availability", "nach Absprache"),
            "application_language": lang,
            "language": "ngerman" if lang == "de" else "english",
            "company_logo_path": profile_data.get("company_logo_path", ""),
        }

        # Temporäres Verzeichnis für Kompilierung
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            tex_file = tmp_path / "cover_letter.tex"
            tex_file.write_text(template.render(context), encoding="utf-8")

            # Photo kopieren falls vorhanden
            photo_src = Path(profile_data.get("photo_path", ""))
            if profile_data.get("include_photo", False) and photo_src.exists():
                photo_dst = tmp_path / "photo.jpg"
                photo_dst.write_bytes(photo_src.read_bytes())

            # Tectonic ausführen
            try:
                tectonic_bin = _find_tectonic()
                proc = await asyncio.create_subprocess_exec(
                    tectonic_bin,
                    str(tex_file),
                    cwd=str(tmp_path),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

                if proc.returncode != 0:
                    logger.error(f"Tectonic failed: {stderr.decode()}")
                    raise RuntimeError(f"LaTeX compilation failed: {stderr.decode()[:500]}")

                # PDF verschieben
                pdf_src = tmp_path / "cover_letter.pdf"
                safe_company = "".join(c for c in job.company if c.isalnum() or c in " -_").rstrip()
                safe_title = "".join(c for c in job.title[:30] if c.isalnum() or c in " -_").rstrip()
                pdf_name = f"{safe_company}_{safe_title}_{job.id[:8]}.pdf"
                pdf_dst = self.output_dir / pdf_name

                pdf_dst.write_bytes(pdf_src.read_bytes())
                logger.info(f"PDF compiled: {pdf_dst}")
                return str(pdf_dst)

            except asyncio.TimeoutError:
                logger.error("Tectonic compilation timed out after 120s")
                raise

    async def compile_cv(
        self,
        cv_variant: str,
        bullets: list[str],
        profile_data: dict,
    ) -> str:
        """Kompiliert CV-Variante mit selektierten Bullets."""
        # Find Tectonic binary
        tectonic_bin = _find_tectonic()
        
        # Load CV template
        template_path = Path(f"data/cv/{cv_variant}.tex")
        template_text = template_path.read_text(encoding="utf-8")
        
        # Render with Jinja2
        env = Environment(
            block_start_string="<%",
            block_end_string="%>",
            variable_start_string="<<",
            variable_end_string=">>",
        )
        template = env.from_string(template_text)
        
        # Build experience section from bullets
        experience = "\n".join(f"\\item {b}" for b in bullets)
        
        rendered = template.render(
            experience=experience,
            **profile_data,
        )
        
        # Write to temp file
        with tempfile.TemporaryDirectory() as tmpdir:
            tex_path = Path(tmpdir) / "cv.tex"
            tex_path.write_text(rendered, encoding="utf-8")
            
            # Compile with Tectonic
            proc = await asyncio.create_subprocess_exec(
                tectonic_bin,
                str(tex_path),
                cwd=tmpdir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

            if proc.returncode != 0:
                raise RuntimeError(f"CV compilation failed: {stderr.decode()[:500]}")

            pdf_src = Path(tmpdir) / "cv.pdf"
            pdf_dst = self.output_dir / output_name
            pdf_dst.write_bytes(pdf_src.read_bytes())
            return str(pdf_dst)

    async def merge_pdfs(
        self,
        cover_letter_pdf: str,
        cv_pdf: str,
        output_name: str,
    ) -> str:
        """Merges Anschreiben + CV zu einem PDF."""
        # Für jetzt: einfach Anschreiben zurückgeben
        # TODO: pdftk oder pypdf für echtes Merging
        logger.warning("PDF merging not yet implemented – returning cover letter only")
        return cover_letter_pdf
