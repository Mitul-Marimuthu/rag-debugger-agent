import json
from typing import Optional

from groq import Groq
from pydantic import BaseModel, Field

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
    references: list[str] = Field(default_factory=list)


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


_client: Optional[Groq] = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=settings.groq_api_key)
    return _client


def review_file(
    file_content: str,
    file_path: str,
    context_chunks: list[dict],
    rules: list[dict],
) -> ReviewResult:
    client = _get_client()
    messages = build_review_prompt(file_content, file_path, context_chunks, rules)

    # Flatten content blocks into a single user message string
    parts = []
    for msg in messages:
        for block in msg.get("content", []):
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)

    response = client.chat.completions.create(
        model=settings.model_name,
        messages=[
            {
                "role": "system",
                "content": (
                    f"{SYSTEM_PROMPT}\n\n"
                    f"You MUST respond with a JSON object that exactly matches this schema:\n"
                    f"{json.dumps(REVIEW_SCHEMA, indent=2)}\n\n"
                    f"Do not wrap it in markdown. Return only the raw JSON object."
                ),
            },
            {"role": "user", "content": "\n\n".join(parts)},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )

    raw_json = response.choices[0].message.content or "{}"

    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError:
        data = {"summary": "Failed to parse review output.", "overall_severity": "clean", "issues": []}

    issues = []
    for issue in data.get("issues", []):
        try:
            issues.append(ReviewIssue(**issue))
        except Exception:
            pass

    return ReviewResult(
        file_path=file_path,
        summary=data.get("summary", ""),
        overall_severity=data.get("overall_severity", "clean"),
        issues=issues,
    )
