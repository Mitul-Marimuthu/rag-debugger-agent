import json
from typing import Optional

from google import genai as google_genai
from google.genai import types as genai_types
from pydantic import BaseModel, Field

from config import settings
from prompts.review_prompt import SYSTEM_PROMPT, build_review_prompt


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


_client: Optional[google_genai.Client] = None


def _get_client() -> google_genai.Client:
    global _client
    if _client is None:
        _client = google_genai.Client(api_key=settings.gemini_api_key)
    return _client


def review_file(
    file_content: str,
    file_path: str,
    context_chunks: list[dict],
    rules: list[dict],
) -> ReviewResult:
    client = _get_client()
    messages = build_review_prompt(file_content, file_path, context_chunks, rules)

    # Flatten the messages list into a single user prompt string
    parts = []
    for msg in messages:
        for block in msg.get("content", []):
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
    prompt = "\n\n".join(parts)

    response = client.models.generate_content(
        model=settings.model_name,
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
        ),
    )

    try:
        data = json.loads(response.text)
    except (json.JSONDecodeError, AttributeError):
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
