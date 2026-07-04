from __future__ import annotations

from app.services.assistant import ASSISTANT_PROMPT, assistant_api_model, model_fallback_reason


def test_assistant_prompt_matches_requirement():
    assert ASSISTANT_PROMPT == """You are OptiBot, the customer-support bot for OptiSigns.com.

• Tone: helpful, factual, concise.
• Only answer using the uploaded docs.
• Max 5 bullet points; else link to the doc.
• Cite up to 3 "Article URL:" lines per reply."""

