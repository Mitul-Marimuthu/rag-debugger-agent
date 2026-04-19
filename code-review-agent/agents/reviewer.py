import json
from dataclasses import dataclass, field
from typing import Optional

import anthropic
from pydantic import BaseModel

from config import settings
from prompts.review_prompt import SYSTEM_PROMPT, REVIEW_SCHEMA, build_review_prompt


class ReviewIssue(BaseModel):
    type: str
    severity: str
    line_start: int
    line_end: int
    title: str
    description: str
    explanation: str
    fix: str
    references: list[str] = field(default_factory=list)


class ReviewResult(BaseModel):
    file_path: str
    summary: str
    overall_severity: str
    issues: list[ReviewIssue]

    @property
    def critical_issues(self) -> list[ReviewIssue]:
        return [i for i in self.issues if i.severity == "critical"]

    @property
    def warnings(self) -> list[ReviewIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def suggestions(self) -> list[ReviewIssue]:
        return [i for i in self.issues if i.severity == "suggestion"]


_client: Optional[anthropic.Anthropic] = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _client


def review_file(
    file_content: str,
    file_path: str,
    context_chunks: list[dict],
    rules: list[dict],
) -> ReviewResult:
    client = _get_client()
    messages = build_review_prompt(file_content, file_path, context_chunks, rules)

    with client.messages.stream(
        model=settings.model_name,
        max_tokens=16000,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        thinking={"type": "adaptive"},
        messages=messages,
        output_config={
            "format": {
                "type": "json_schema",
                "schema": REVIEW_SCHEMA,
            }
        },
    ) as stream:
        final = stream.get_final_message()

    raw_json = next(
        (b.text for b in final.content if b.type == "text"),
        "{}",
    )

    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError:
        data = {"summary": "Failed to parse review output.", "overall_severity": "clean", "issues": []}

    issues = [ReviewIssue(**issue) for issue in data.get("issues", [])]

    return ReviewResult(
        file_path=file_path,
        summary=data.get("summary", ""),
        overall_severity=data.get("overall_severity", "clean"),
        issues=issues,
    )
