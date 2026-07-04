from __future__ import annotations

from pathlib import Path

from openai import OpenAI

from app.config.settings import Settings
from app.utils.files import ensure_dir


ASSISTANT_PROMPT = """You are OptiBot, the customer-support bot for OptiSigns.com.

• Tone: helpful, factual, concise.
• Only answer using the uploaded docs.
• Max 5 bullet points; else link to the doc.
• Cite up to 3 "Article URL:" lines per reply."""

ASSISTANT_LOG_NAME = "assistant.json"


class AssistantRunError(RuntimeError):
    pass


class OptiBotAssistantService:
    def __init__(self, settings: Settings) -> None:
        if not settings.has_real_openai_key:
            raise RuntimeError("Set OPENAI_API_KEY or API_KEY before using the assistant.")
        self.settings = settings
        self.client = OpenAI(api_key=settings.openai_api_key)

    def setup(self) -> dict:
        if not self.settings.openai_vector_store_id:
            raise RuntimeError("Set OPENAI_VECTOR_STORE_ID before creating the assistant.")

        requested_model = self.settings.openai_assistant_model
        model = assistant_api_model(requested_model)
        payload = {
            "name": "OptiBot Mini Clone",
            "instructions": ASSISTANT_PROMPT,
            "model": model,
            "tools": [{"type": "file_search"}],
            "tool_resources": {"file_search": {"vector_store_ids": [self.settings.openai_vector_store_id]}},
        }

        assistant_id = self.settings.openai_assistant_id or latest_assistant_id(self.settings.logs_dir)
        if assistant_id:
            assistant = self.client.beta.assistants.update(
                assistant_id=assistant_id,
                **payload,
            )
            action = "updated"
        else:
            assistant = self.client.beta.assistants.create(**payload)
            action = "created"

        summary = {
            "assistant_id": assistant.id,
            "action": action,
            "model": model,
            "requested_model": requested_model,
            "model_fallback_reason": model_fallback_reason(requested_model, model),
            "vector_store_id": self.settings.openai_vector_store_id,
            "playground_url": f"https://platform.openai.com/playground/assistants?assistant={assistant.id}",
        }
        write_assistant_log(self.settings.logs_dir, summary)
        return summary

    def ask(self, question: str) -> str:
        assistant_id = self.settings.openai_assistant_id or latest_assistant_id(self.settings.logs_dir)
        if not assistant_id:
            setup_summary = self.setup()
            assistant_id = setup_summary["assistant_id"]

        thread = self.client.beta.threads.create(messages=[{"role": "user", "content": question}])
        run = self.client.beta.threads.runs.create_and_poll(
            thread_id=thread.id,
            assistant_id=assistant_id,
            poll_interval_ms=1000,
        )
        if run.status != "completed":
            raise AssistantRunError(_run_error_message(run))

        messages = self.client.beta.threads.messages.list(thread_id=thread.id, order="desc", limit=10)
        for message in messages.data:
            if message.role == "assistant":
                return message_to_text(message)
        raise RuntimeError("Assistant completed without returning a message.")


def assistant_api_model(requested_model: str) -> str:
    if requested_model.lower().startswith("gpt-5"):
        return "gpt-4o-mini"
    return requested_model


def model_fallback_reason(requested_model: str, actual_model: str) -> str | None:
    if requested_model == actual_model:
        return None
    return f"{requested_model} is not supported by this Assistants API path; using {actual_model}."


def latest_assistant_id(logs_dir: Path) -> str | None:
    log_path = logs_dir / ASSISTANT_LOG_NAME
    if not log_path.exists():
        return None
    import json

    data = json.loads(log_path.read_text(encoding="utf-8"))
    return data.get("assistant_id")


def write_assistant_log(logs_dir: Path, summary: dict) -> None:
    import json

    ensure_dir(logs_dir)
    (logs_dir / ASSISTANT_LOG_NAME).write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")


def message_to_text(message) -> str:
    parts: list[str] = []
    for content in message.content:
        if getattr(content, "type", None) == "text":
            parts.append(content.text.value)
    return "\n".join(parts).strip()


def _run_error_message(run) -> str:
    message = f"Assistant run ended with status {run.status}"
    last_error = getattr(run, "last_error", None)
    if last_error:
        code = getattr(last_error, "code", None)
        detail = getattr(last_error, "message", None)
        if code or detail:
            message += f"; last_error={code or 'unknown'}: {detail or 'No detail returned.'}"
    return message
