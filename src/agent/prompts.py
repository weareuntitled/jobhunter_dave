"""src/agent/prompts.py – Prompt-Builder für Go-API."""

from __future__ import annotations

from src.agent.schemas import EvaluateRequest, ProfileSummary, RejectedJob


def build_evaluation_prompt(request: EvaluateRequest) -> str:
    """Baut den vollständigen System-Prompt für die Go-API-Evaluation."""

    job = request.job
    profile = request.profile
    rejected = request.rejected_context

    # ── Voice Reference ───────────────────────────────────────────
    voice_ref = ""
    if request.voice_samples:
        voice_ref = "\n\n### Stil-Vorlage (Voice Reference)\n"
        for i, sample in enumerate(request.voice_samples[:2], 1):
            voice_ref += f"Beispiel {i}:\n{sample[:500]}...\n\n"

    # ── Rejected Context ───────────────────────────────────────────
    reject_context = ""
    if rejected:
        reject_context = "\n\n### Auto-Alignment: Letzte abgelehnte Jobs\n"
        for r in rejected:
            reject_context += (
                f"- {r.job_title} @ {r.company} (Score: {r.score}): "
                f"{r.rejection_reason}\n"
            )
        reject_context += "\nVermeide diese Fehler im neuen Anschreiben.\n"

    # ── CV Variant Hints ──────────────────────────────────────────
    cv_hint = ""
    if request.cv_variants:
        cv_hint = f"\nVerfügbare CV-Varianten: {', '.join(request.cv_variants)}\n"
        cv_hint += "Wähle die passendste aus und begründe die Wahl.\n"

    # ── Language ──────────────────────────────────────────────────
    lang_instruction = {
        "de": "Schreibe auf Deutsch. Halte den Ton professionell, direkt und authentisch.",
        "en": "Write in English. Keep the tone professional, direct, and authentic.",
    }.get(request.application_language, "Schreibe auf Deutsch.")

    prompt = f"""Du bist ein Automatisierungs-Agent, der Bewerbungen für {profile.name} verfasst.

### Aufgabe
Bewerte die folgende Stelle auf einer Skala von 0-10 und verfasse ein Anschreiben.
Das Anschreiben MUSS aus der Perspektive des Agenten verfasst werden (z.B. "Hallo, ich bin der lokale Automatisierungs-Agent von {profile.name}...").

### Stellenbeschreibung
Titel: {job.title}
Unternehmen: {job.company}
Ort: {job.location}
Beschreibung: {job.description}
Anforderungen: {', '.join(job.requirements) if job.requirements else 'Nicht angegeben'}

### Bewerberprofil
Name: {profile.name}
Titel: {profile.title}
Skills: {', '.join(profile.skills)}
Erfahrung: {profile.experience_years} Jahre
Portfolio: {profile.portfolio_url}
Sprachen: {', '.join(profile.languages)}

{lang_instruction}

{voice_ref}

{reject_context}

{cv_hint}

### Output-Format
Gib ein JSON zurück mit:
- score (float 0-10)
- reasoning (string)
- adapted_cover_letter (string, Agenten-Perspektive)
- matched_keywords (list[string])
- missing_keywords (list[string])
- profile_tip (string | null, nur bei Score > 8)
- selected_cv_variant (string | null)
- agent_voice_confidence (float 0-1)
"""

    return prompt
