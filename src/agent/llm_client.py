"""src/agent/llm_client.py – LLM-gestützte Anschreiben-Generierung via Ollama/OpenRouter/DeepSeek."""

from __future__ import annotations

import json
import logging
import os

import httpx

from src.agent.schemas import JobListing, ProfileSummary

logger = logging.getLogger("job-hunter")

OLLAMA_BASE = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

# Provider-Priorität via env: "ollama" (default), "openrouter", "deepseek"
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "ollama")


def _build_system_prompt(language: str) -> str:
    """Dynamischer System-Prompt mit Sprache und Agent-Erkennung."""
    lang_rule = (
        "Schreibe DIESEN Text komplett auf DEUTSCH. Keine englischen Wörter, keine Mischung."
        if language == "de"
        else "Write THIS text completely in ENGLISH. No German words, no mixing."
    )
    return (
        "Du bist ein KI-Agent, der für Daniel Peters Anschreiben schreibt.\n\n"
        "ERSTE ZEILE (Pflicht):\n"
        'Beginne IMMER mit: "ich bin der KI-Bewerbungs-Agent von Daniel Peters. '
        'Mein System hat Ihre Ausschreibung analysiert und ein starkes Match erkannt."\n\n'
        f"SPRACHE:\n{lang_rule}\n\n"
        "Kontext:\n"
        '- Output geht in "<< cover_letter_body >>".\n'
        '- Sign-off ("Mit freundlichen Grüßen...") kommt danach vom Template.\n'
        '- Der Output darf KEINEN Sign-off enthalten.\n\n'
        "Arbeitgeber-Kontext (NICHT VERWECHSELN):\n"
        '- 8020 Consulting (10/2022-11/2025): Product Owner & Scrum Master (Hauptteil), '
        'Enterprise AI (RAG/BioBert), Enterprise UX (Audi/Porsche/VW, kleinster Anteil)\n'
        '- un​tit​led​-ux / Freelance: UX/UI Design (Hauptteil), Motion Design, Webdesign, '
        '3D, Branding, Full-Stack Dev (Idee→Beta: DevOps, Staging, Security – AI-driven), '
        'FastAPI, LLM/ComfyUI (Hauptteil)\n'
        '- Erwähne 8020 NUR wenn PO/Scrum/Enterprise-AI relevant. '
        'Ansonsten: kein Arbeitgeber nennen oder "in verschiedenen Projekten" / "als Freelancer".\n\n'
        "Inhalt:\n"
        '- Beziehe dich konkret auf die Stellenbeschreibung (2–3 klare Passungen).\n'
        '- Nutze Bulletpoints nur als Material zum Einweben (nicht als Liste).\n'
        '- Daniel nur in 3. Person erwähnen.\n\n'
        "Ausschlüsse (strikt):\n"
        '- Keine Floskeln: "Sehr geehrte…", "Damen und Herren".\n'
        '- Keine Gesprächseinladung: "Gespräch", "Einladung", "Lassen Sie uns", "Vereinbaren", "Kontaktieren Sie".\n'
        '- Keine "ich freue mich…".\n'
        '- Kein "Mit freundlichen Grüßen".\n'
        '- Keine technischen Tools/Projekte (ERP, WordPress, Cursor, Ollama, ComfyUI, n8n, Synera).\n\n'
        "Format:\n"
        '- 2–3 kurze Absätze, kein Heading, keine Bullet-Listen.\n'
        '- Max. ~180–220 Wörter.\n'
        '- Konsequent "Sie".\n\n'
        "Output: Nur der reine Text, keine Erklärungen."
    )


async def generate_cover_letter(
    job: JobListing,
    profile: ProfileSummary,
    bullets: list[str],
    language: str = "de",
) -> str:
    """Generiert Anschreiben via konfiguriertem LLM-Provider (Ollama/OpenRouter/DeepSeek)."""
    provider = LLM_PROVIDER

    if provider == "ollama":
        model = await _find_ollama_model()
        if model:
            text = await _call_ollama(job, profile, bullets, language, model)
            if text:
                return text
        logger.info("   Ollama nicht verfügbar – Fallback")

    if provider in ("openrouter", "ollama"):
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if api_key:
            text = await _call_openrouter(job, profile, bullets, language, api_key)
            if text:
                return text
            logger.info("   OpenRouter nicht verfügbar – Fallback")

    if provider in ("deepseek", "openrouter", "ollama"):
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if api_key:
            text = await _call_deepseek(job, profile, bullets, language, api_key)
            if text:
                return text
            logger.info("   DeepSeek nicht verfügbar – Fallback")

    logger.info("   Kein LLM verfügbar – nutze Template")
    return _template_cover_letter(job, profile, bullets, language)


async def _find_ollama_model() -> str | None:
    """Prüft ob Ollama läuft und gibt Modell-Namen zurück."""
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(f"{OLLAMA_BASE}/api/tags")
            if resp.status_code != 200:
                return None
            models = resp.json().get("models", [])
            if not models:
                return None
            # Bevorzuge llama3.1/3.2 oder mistral, sonst erstes verfügbares
            preferred = ["llama3.2", "llama3.1", "mistral", "mixtral", "qwen2.5"]
            for name in preferred:
                for m in models:
                    if name in m["name"]:
                        return m["name"]
            return models[0]["name"]
    except (httpx.ConnectError, httpx.TimeoutException):
        logger.debug("   Ollama nicht erreichbar")
        return None
    except Exception as e:
        logger.debug(f"   Ollama check failed: {e}")
        return None


async def _call_ollama(
    job: JobListing, profile: ProfileSummary, bullets: list[str],
    language: str, model: str,
) -> str | None:
    """Ruft lokales Ollama-Modell auf."""
    bullet_text = _build_bullet_text(bullets)
    user_prompt = _build_user_prompt(job, profile, bullet_text, language)
    system_prompt = _build_system_prompt(language)

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{OLLAMA_BASE}/v1/chat/completions",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.7,
                    "max_tokens": 600,
                },
            )
            if resp.status_code != 200:
                logger.warning(f"Ollama error {resp.status_code}: {resp.text[:200]}")
                return None
            content = resp.json()["choices"][0]["message"].get("content")
            if not content:
                return None
            text = content.strip()
            logger.info(f"✅ Ollama ({model}) – {len(text)} chars")
            return text
    except Exception as e:
        logger.warning(f"Ollama call failed: {e}")
        return None


async def _call_openrouter(
    job: JobListing, profile: ProfileSummary, bullets: list[str],
    language: str, api_key: str,
) -> str | None:
    """Ruft OpenRouter API auf (beliebiges Modell via OPENROUTER_MODEL env)."""
    bullet_text = _build_bullet_text(bullets)
    user_prompt = _build_user_prompt(job, profile, bullet_text, language)
    system_prompt = _build_system_prompt(language)
    model = os.environ.get("OPENROUTER_MODEL", "google/gemini-2.0-flash-001")

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "HTTP-Referer": "https://github.com/untitled-ux",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.7,
                    "max_tokens": 600,
                },
            )
            if resp.status_code != 200:
                logger.warning(f"OpenRouter error {resp.status_code}: {resp.text[:200]}")
                return None
            content = resp.json()["choices"][0]["message"].get("content")
            if not content:
                return None
            text = content.strip()
            logger.info(f"✅ OpenRouter ({model}) – {len(text)} chars")
            return text
    except Exception as e:
        logger.warning(f"OpenRouter call failed: {e}")
        return None


async def _call_deepseek(
    job: JobListing, profile: ProfileSummary, bullets: list[str],
    language: str, api_key: str,
) -> str | None:
    """Ruft DeepSeek API auf."""
    bullet_text = _build_bullet_text(bullets)
    user_prompt = _build_user_prompt(job, profile, bullet_text, language)
    system_prompt = _build_system_prompt(language)

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "deepseek-chat",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.7,
                    "max_tokens": 600,
                },
            )
            if resp.status_code != 200:
                logger.warning(f"DeepSeek error {resp.status_code}: {resp.text[:200]}")
                return None
            content = resp.json()["choices"][0]["message"].get("content")
            if not content:
                return None
            text = content.strip()
            logger.info(f"✅ DeepSeek – {len(text)} chars")
            return text
    except Exception as e:
        logger.warning(f"DeepSeek call failed: {e}")
        return None


def _build_bullet_text(bullets: list[str]) -> str:
    return "\n".join(f"- {b}" for b in bullets[:4])


def _build_user_prompt(
    job: JobListing, profile: ProfileSummary, bullet_text: str, language: str,
) -> str:
    lang_label = "Deutsch" if language == "de" else "Englisch"
    return (
        f"Stelle: {job.title} @ {job.company}, {job.location}\n"
        f"Beschreibung: {job.description[:1500]}\n\n"
        f"Daniel: {profile.title} | Skills: {', '.join(profile.skills)}\n\n"
        f"WICHTIG – Arbeitgeber-Kontext (nicht verwechseln):\n"
        f"• 8020 Consulting (10/2022–11/2025): Product Ownership & Scrum Master (Hauptteil), "
        f"Enterprise AI (RAG/BioBert), "
        f"Enterprise UX & Research (Audi/Porsche/VW, kleinster Anteil), "
        f"Motion Design für Kunden\n"
        f"• un​tit​led​-ux / Freelance (laufend): UX/UI Design (Hauptteil), "
        f"Webdesign (WordPress/Webflow/React), 3D/Blender, Branding, "
        f"Full-Stack Development – von der Idee bis zur fertigen Beta: "
        f"DevOps, Staging, Security Testing – alles AI-driven. "
        f"FastAPI, LLM/ComfyUI (Hauptteil)\n\n"
        f"REGEL: Erwähne 8020 NUR bei PO/Scrum oder Enterprise-AI-Themen. "
        f"Bei UX/UI, Motion, Web, LLM, FastAPI KEINEN Arbeitgeber nennen "
        f"oder \"in verschiedenen Projekten\" / \"als Freelancer\".\n\n"
        f"Material zum Einweben (als Fließtext, keine Liste):\n{bullet_text}\n\n"
        f"Sprache: {lang_label}\n"
        f"Strikte Regeln:\n"
        f"- Keine Floskeln, keine Gesprächseinladung, kein Sign-off.\n"
        f"- Keine technischen Tools (ERP, WordPress, Cursor, Ollama, ComfyUI, n8n, Synera).\n"
        f"- Max 220 Wörter, 2-3 Absätze.\n"
        f"- Schreib nur den reinen Text, keine Erklärungen."
    )


def _template_cover_letter(
    job: JobListing,
    profile: ProfileSummary,
    bullets: list[str],
    language: str,
) -> str:
    """Fallback-Template wenn kein LLM verfügbar."""

    if language == "en":
        return (
            f"I am the AI job application agent of Daniel Peters. My system analyzed your posting "
            f"for {job.title} at {job.company} and identified a match.\n\n"
            f"As a UX/UI Designer & AI Product Specialist, Daniel brings hands-on experience in "
            f"user research, prototyping, design systems, and product ownership "
            f"from various project and consulting contexts."
        )

    return (
        f"ich bin der KI-Bewerbungs-Agent von Daniel Peters. Mein System hat Ihre Ausschreibung "
        f"für {job.title} bei {job.company} analysiert und ein starkes Match erkannt.\n\n"
        f"Als UX/UI Designer & AI Product Specialist bringt Daniel praktische Erfahrung in "
        f"User Research, Prototyping, Designsystemen und Product Ownership "
        f"aus verschiedenen Projekt- und Beratungskontexten mit."
    )


# ── Job-Detail-Extraktion für Swipe-Karten ──────────────────────

EXTRACT_PROMPT = (
    "Extrahiere aus dieser deutschen oder englischen Stellenanzeige folgende Felder "
    "als JSON. Halte dich kurz (max 1-2 Sätze pro Feld, 80 Zeichen).\n\n"
    "Rückgabeformat (NUR gültiges JSON, keine Erklärungen):\n"
    "{\n"
    '  "tasks": ["Aufgabe 1", "Aufgabe 2", "Aufgabe 3"],\n'
    '  "company_info": "1 Satz zur Firma",\n'
    '  "perks": ["Perk 1", "Perk 2"],\n'
    '  "tech_stack": ["Tool 1", "Tool 2"],\n'
    '  "salary": "55.000-70.000 € oder null"\n'
    "}\n\n"
    "Regeln:\n"
    "- tasks: 3 Kernaufgaben aus der Beschreibung\n"
    "- company_info: Branche, Größe, Kultur wenn erwähnt – sonst leerer String ''\n"
    "- perks: Benefits (Jobrad, Home-Office, Weiterbildung etc.) – Max 3\n"
    "- tech_stack: Genannte Tools/Technologien (Figma, React, AWS etc.) – Max 3\n"
    "- salary: Nur wenn explizit genannt, sonst null\n"
    "- NUR das JSON-Objekt zurückgeben, keine Markdown-Backticks, keine Erklärungen"
)


async def extract_job_details(description: str) -> dict:
    """Extrahiert strukturierte Felder aus einer Job-Beschreibung per LLM."""
    provider = os.environ.get("LLM_PROVIDER", "ollama")

    user_prompt = f"JOB-BESCHREIBUNG:\n{description[:2000]}"

    if provider == "openrouter":
        return await _call_openrouter_extract(user_prompt)
    return await _call_ollama_extract(user_prompt)


async def _call_openrouter_extract(user_prompt: str) -> dict:
    model = os.environ.get("OPENROUTER_MODEL", "deepseek/deepseek-v4-flash")
    headers = {
        "Authorization": f"Bearer {os.environ.get('OPENROUTER_API_KEY', '')}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": EXTRACT_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 500,
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers, json=payload,
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"].get("content", "")
            if not content:
                return _extract_fallback()
            return _parse_extract_json(content)
    except Exception:
        return _extract_fallback()


async def _call_ollama_extract(user_prompt: str) -> dict:
    payload = {
        "model": os.environ.get("OLLAMA_MODEL", "deepseek-r1:32b"),
        "messages": [
            {"role": "system", "content": EXTRACT_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 500},
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{OLLAMA_BASE}/api/chat", json=payload,
            )
            response.raise_for_status()
            data = response.json()
            content = data.get("message", {}).get("content", "")
            if not content:
                return _extract_fallback()
            return _parse_extract_json(content)
    except Exception:
        return _extract_fallback()


def _parse_extract_json(content: str) -> dict:
    content = content.strip()
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1])
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        for prefix, suffix in [("{", "}"), ("[", "]")]:
            start = content.find(prefix)
            end = content.rfind(suffix)
            if start >= 0 and end > start:
                try:
                    return json.loads(content[start:end + 1])
                except json.JSONDecodeError:
                    pass
        return _extract_fallback()


def _extract_fallback() -> dict:
    return {
        "tasks": [],
        "company_info": "",
        "perks": [],
        "tech_stack": [],
        "salary": None,
    }
