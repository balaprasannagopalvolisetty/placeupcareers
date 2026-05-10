"""
AI Email Personalizer (uses existing GROQ_API_KEY)

Adopted patterns from github.com/praneethravuri/jobs-tools (template +
{name}/{company}/{position} placeholders + AI rephrase) and adapted to use
Groq, which the user already has a key for (free 14,400 req/day on
llama-3.3-70b-versatile). Falls back to template-only if no Groq key.

Critical rule: this module DRAFTS emails. It NEVER sends them. The user
copies the draft into their own email client and reviews/edits before
hitting send. This keeps PlaceUp on the right side of CAN-SPAM /
unsubscribe / spoofing rules.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from app.config import settings
from app.models.contact import Contact

logger = logging.getLogger(__name__)


GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"


DEFAULT_SUBJECT_TEMPLATE = "Discovering {position} opportunities at {company}"

DEFAULT_BODY_TEMPLATE = """Hi {first_name},

I came across the {position} role at {company} and wanted to reach out directly. \
My background is in {candidate_skills} and I've been particularly impressed by \
{company}'s work in this space.

I'd love a brief 15-minute conversation to learn more about what your team is looking for \
and share how my experience aligns. I'm available {availability}.

Thanks for your time,
{candidate_name}
{candidate_linkedin}
"""


def _render_template(template: str, ctx: dict) -> str:
    """Safe placeholder rendering — missing keys become empty string, not KeyError."""
    class _SafeDict(dict):
        def __missing__(self, key):
            return ""
    return template.format_map(_SafeDict(ctx))


async def _groq_rephrase(prompt: str, *, api_key: str, model: str) -> Optional[str]:
    """Single Groq chat completion. Returns None on failure (degrades to template)."""
    if not api_key:
        return None
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": (
                "You rewrite outreach emails to sound natural, specific, and concise. "
                "Keep the rewrite under 150 words. Preserve every {placeholder} marker EXACTLY. "
                "Do not invent facts about the recipient or company beyond what's in the input. "
                "Return only the rewritten email body, no preamble."
            )},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4,
        "max_tokens": 600,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(GROQ_CHAT_URL, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        logger.warning("Groq rephrase failed: %s", exc)
        return None
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError):
        return None


def render_template_only(
    *,
    contact: Contact,
    company: str,
    position: str,
    candidate_name: str = "",
    candidate_skills: str = "",
    candidate_linkedin: str = "",
    availability: str = "this week",
    subject_template: str = DEFAULT_SUBJECT_TEMPLATE,
    body_template: str = DEFAULT_BODY_TEMPLATE,
) -> dict:
    """Render the email purely from templates — no AI call. Always works, $0 cost."""
    first_name = (contact.first_name or (contact.full_name or "").split(" ", 1)[0] or "there").strip()
    ctx = {
        "first_name": first_name,
        "full_name": contact.full_name or first_name,
        "company": company,
        "position": position,
        "candidate_name": candidate_name,
        "candidate_skills": candidate_skills,
        "candidate_linkedin": candidate_linkedin,
        "availability": availability,
    }
    return {
        "to": contact.email,
        "subject": _render_template(subject_template, ctx),
        "body": _render_template(body_template, ctx),
        "personalized_with_ai": False,
        "model": None,
    }


async def draft_personalized_email(
    *,
    contact: Contact,
    company: str,
    position: str,
    candidate_name: str = "",
    candidate_skills: str = "",
    candidate_linkedin: str = "",
    availability: str = "this week",
    subject_template: str = DEFAULT_SUBJECT_TEMPLATE,
    body_template: str = DEFAULT_BODY_TEMPLATE,
    byok_groq_key: Optional[str] = None,
) -> dict:
    """Generate a personalized email draft.

    Pipeline:
      1. Render the base template with placeholders.
      2. If a Groq key is available (BYOK first, then platform), ask the LLM
         to rewrite for natural tone. Returns the LLM rewrite if successful.
      3. Otherwise return the template-rendered version verbatim.

    Returns dict with: to, subject, body, personalized_with_ai, model.
    DOES NOT SEND. The user must review and send from their own email client.
    """
    # Always render template first as the safe fallback
    draft = render_template_only(
        contact=contact, company=company, position=position,
        candidate_name=candidate_name, candidate_skills=candidate_skills,
        candidate_linkedin=candidate_linkedin, availability=availability,
        subject_template=subject_template, body_template=body_template,
    )

    api_key = (byok_groq_key or settings.groq_api_key or "").strip()
    if not api_key:
        return draft

    # Ask Groq to humanize the body. Subject line stays templated for predictability.
    prompt = (
        f"Recipient: {contact.full_name or 'there'} "
        f"({(contact.title or 'team member')}) at {company}.\n\n"
        f"Sender background: {candidate_name} — skills: {candidate_skills}.\n\n"
        f"Original email:\n---\n{draft['body']}\n---\n\n"
        f"Rewrite the body so it sounds like a thoughtful person, not a template. "
        f"Keep it under 150 words. Be specific about the role ({position}) and company ({company})."
    )
    rewritten = await _groq_rephrase(prompt, api_key=api_key, model=settings.llm_model)
    if rewritten:
        draft["body"] = rewritten
        draft["personalized_with_ai"] = True
        draft["model"] = settings.llm_model
    return draft
