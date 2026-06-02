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
        "Sprache (strikt):\n"
        '- Schreibe KOMPLETT in der Zielsprache – keine Sprachmischung.\n'
        '- Auf DEUTSCH: Nutzerforschung, Prototypenbau, Designsysteme, '
        'Produktverantwortung, Sprint-Planung, KI (statt "User Research", "Prototyping", '
        '"Product Ownership", "Sprint Planning", "AI").\n'
        '- Auf ENGLISCH: User Research, Prototyping, Design Systems, Product Ownership, '
        'Sprint Planning, AI.\n'
        '- Anglizismen nur, wenn sie im Deutschen etabliert sind (z.B. "Sprint", '
        '"Backlog", "Enterprise").\n\n'
        "Ausschlüsse (strikt):\n"
        '- Keine Floskeln: "Sehr geehrte…", "Damen und Herren".\n'
        '- Keine Gesprächseinladung: "Gespräch", "Einladung", "Lassen Sie uns", "Vereinbaren", "Kontaktieren Sie".\n'
        '- Keine "ich freue mich…".\n'
        '- Kein "Mit freundlichen Grüßen".\n'
        '- Keine technischen Tools/Projekte (ERP, WordPress, Cursor, Ollama, ComfyUI, n8n, Synera).\n\n'
        "Format:\n"
        '- 2–3 kurze Absätze, kein Heading, keine Bullet-Listen.\n'
        '- Max. ~180–220 Wörter.\n'
        '- Konsequent "Sie" (Deutsch) bzw. "you" (Englisch).\n'
        '- Professioneller Ton: präzise, sachlich, keine Füllwörter.\n\n'
        "Output: Nur der reine Text, keine Erklärungen."
    )


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


async def _call_critic(
    draft: str,
    job: JobListing,
    profile: ProfileSummary,
    language: str,
    api_key: str,
) -> str | None:
    """Critic-Pass: LLM bewertet und überarbeitet den Draft.

    Erwartet JSON-Antwort: {"score": float, "revised": "..."}
    Gibt die überarbeitete Version zurück, oder None bei Fehler.
    """
    lang_label = "Deutsch" if language == "de" else "Englisch"
    model = os.environ.get("OPENROUTER_CRITIC_MODEL", "google/gemini-2.0-flash-001")

    system_prompt = (
        "Du bist ein erfahrener HR-Consultant und Copy-Editor, der Anschreiben "
        "für technologie-orientierte Bewerber reviewt.\n\n"
        "Deine Aufgabe: Bewerte den folgenden Anschreiben-Draft und überarbeite ihn.\n\n"
        "Bewertungskriterien (jedes 1-10):\n"
        "1. ARGUMENTATION: Macht der Text eine überzeugende Case, oder listet er nur Fakten?\n"
        "2. SPRACHE: Ist der Text konsequent in der Zielsprache (keine Sprachmischung)?\n"
        "3. TON: Professionell ohne steif zu wirken? Konsequent Sie/you?\n"
        "4. SPEZIFITÄT: Sind Behauptungen mit konkreten Belegen (Jahre, Projekte, Zahlen) gestützt?\n"
        "5. HOOK: Ist der Einstieg stark oder generisch?\n"
        "6. ABSCHLUSS: Wird klar, welchen Wert der Bewerber konkret bringt?\n\n"
        "Antworte NUR mit validem JSON in diesem Format:\n"
        "{\n"
        '  "score": 7.5,\n'
        '  "issues": ["schwacher Hook", "fehlende konkrete Belege"],\n'
        '  "revised": "Überarbeiteter Text - gleiche Sprache, gleiche Länge, 2-3 Absätze"\n'
        "}\n\n"
        "WICHTIG: Im 'revised' Feld:\n"
        "- Konsequent in der Zielsprache\n"
        '- Mit "Ich bin der KI-Bewerbungs-Agent" beginnen\n'
        "- Konsequent Sie/you\n"
        '- Keine technischen Tools (ERP, WordPress, Ollama, ComfyUI, n8n)\n'
        "- Max 220 Wörter\n"
        "- NUR das JSON-Objekt, KEINE Markdown-Backticks, KEINE Erklärungen"
    )

    user_prompt = (
        f"Stelle: {job.title} @ {job.company}, {job.location}\n"
        f"Sprache: {lang_label}\n\n"
        f"Profil: {profile.title} | {profile.experience_years} Jahre\n\n"
        f"--- DRAFT ---\n{draft}\n--- ENDE DRAFT ---\n\n"
        f"Bewerte und überarbeite."
    )

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
                    "temperature": 0.4,
                    "max_tokens": 1000,
                    "response_format": {"type": "json_object"},
                },
            )
            if resp.status_code != 200:
                logger.warning(f"Critic error {resp.status_code}: {resp.text[:200]}")
                return None
            content = resp.json()["choices"][0]["message"].get("content")
            if not content:
                return None
            data = json.loads(content)
            revised = data.get("revised", "").strip()
            score = data.get("score", 0)
            issues = data.get("issues", [])
            if not revised or len(revised) < 50:
                logger.warning("Critic lieferte leeren/zu kurzen revised-Text")
                return None
            logger.info(
                f"✅ Critic – Score {score}/10, {len(revised)} chars, "
                f"Issues: {len(issues)}"
            )
            return revised
    except json.JSONDecodeError as e:
        logger.warning(f"Critic lieferte kein valides JSON: {e}")
        return None
    except Exception as e:
        logger.warning(f"Critic call failed: {e}")
        return None


async def generate_cover_letter(
    job: JobListing,
    profile: ProfileSummary,
    bullets: list[str],
    language: str = "de",
    use_critic: bool = True,
) -> str:
    """Generiert Anschreiben via Draft + Critic Pattern.

    1. Draft via Ollama/OpenRouter/DeepSeek/Template
    2. Wenn Draft von LLM kam UND OpenRouter-Key vorhanden: Critic überarbeitet
    3. Bei Critic-Fehler: Original-Draft zurückgeben
    """
    provider = LLM_PROVIDER
    draft: str | None = None
    draft_from_llm = False

    if provider == "ollama":
        model = await _find_ollama_model()
        if model:
            draft = await _call_ollama(job, profile, bullets, language, model)
            if draft:
                draft_from_llm = True

    if not draft and provider in ("openrouter", "ollama"):
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if api_key:
            draft = await _call_openrouter(job, profile, bullets, language, api_key)
            if draft:
                draft_from_llm = True

    if not draft and provider in ("deepseek", "openrouter", "ollama"):
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if api_key:
            draft = await _call_deepseek(job, profile, bullets, language, api_key)
            if draft:
                draft_from_llm = True

    if not draft:
        logger.info("   Kein LLM verfügbar – nutze Template")
        return _template_cover_letter(job, profile, bullets, language)

    if not use_critic or not draft_from_llm:
        return draft

    critic_key = os.environ.get("OPENROUTER_API_KEY")
    if not critic_key:
        logger.info("   Kein OpenRouter-Key für Critic – Draft behalten")
        return draft

    logger.info("🔍 Critic-Pass läuft...")
    revised = await _call_critic(draft, job, profile, language, critic_key)
    if revised:
        logger.info(f"   Draft ({len(draft)}c) → Revised ({len(revised)}c)")
        return revised

    logger.info("   Critic fehlgeschlagen – Draft behalten")
    return draft


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
    """Fallback-Template wenn kein LLM verfügbar.

    Strikt einsprachig (Deutsch ODER Englisch), professionell mit Sie/you,
    2-3 Absätze, konkrete Bullet-Beispiele als Fließtext eingewoben.
    """

    years = getattr(profile, "experience_years", None) or 7

    if language == "en":
        body = (
            f"I am the AI job application agent of Daniel Peters, writing on his behalf. "
            f"My system analysed your posting for {job.title} at {job.company} and identified "
            f"a strong match with his profile.\n\n"
            f"Daniel brings over {years} years of experience across design, product "
            f"ownership, and applied AI. "
        )
        if bullets:
            bullet_text = "; ".join(b.rstrip(".") for b in bullets[:3])
            body += f"His work covers {bullet_text}. "
        body += (
            f"\n\nWhat draws him to {job.company} is the opportunity to apply this experience "
            f"in a setting that values both craft and measurable impact."
        )
        return body

    body = (
        f"Ich bin der KI-Bewerbungs-Agent von Daniel Peters und schreibe Ihnen in seinem "
        f"Auftrag. Mein System hat Ihre Ausschreibung für {job.title} bei {job.company} "
        f"analysiert und eine deutliche Passung zu seinem Profil ermittelt.\n\n"
        f"Daniel bringt über {years} Jahre Berufserfahrung an der Schnittstelle von Design, "
        f"Produktverantwortung und angewandter künstlicher Intelligenz mit. "
    )
    if bullets:
        bullet_text = "; ".join(b.rstrip(".") for b in bullets[:3])
        body += f"Seine Arbeit umfasst {bullet_text}. "
    body += (
        f"\n\nWas ihn an {job.company} besonders anspricht, ist die Möglichkeit, diese "
        f"Erfahrung in einem Umfeld einzubringen, das sowohl gestalterische Qualität als "
        f"auch messbaren Impact verlangt."
    )
    return body


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
