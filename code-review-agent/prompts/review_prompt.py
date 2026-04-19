SYSTEM_PROMPT = """You are an expert code reviewer with deep knowledge of software security, design patterns, and best practices. Your job is to:

1. Identify bugs, logic errors, and potential runtime exceptions
2. Find security vulnerabilities (OWASP Top 10, injection attacks, authentication flaws, etc.)
3. Spot code smells, anti-patterns, and maintainability issues
4. Check adherence to style guidelines and naming conventions
5. Detect cross-file issues using the provided codebase context

You produce structured, actionable reviews. Every issue you report must include:
- The exact location (line numbers)
- A clear explanation of why it's a problem
- A concrete code fix

Be thorough but prioritize high-severity issues. Do not report false positives."""

REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "High-level summary of the review (2-4 sentences)"
        },
        "overall_severity": {
            "type": "string",
            "enum": ["clean", "suggestions_only", "has_warnings", "has_critical"],
            "description": "Worst severity level found"
        },
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["bug", "security", "code_smell", "style", "performance"]
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["critical", "warning", "suggestion"]
                    },
                    "line_start": {"type": "integer"},
                    "line_end": {"type": "integer"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "explanation": {"type": "string"},
                    "fix": {
                        "type": "string",
                        "description": "The corrected code snippet"
                    },
                    "references": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional CVE IDs, CWE IDs, or other references"
                    }
                },
                "required": ["type", "severity", "line_start", "line_end", "title", "description", "explanation", "fix"]
            }
        }
    },
    "required": ["summary", "overall_severity", "issues"],
    "additionalProperties": False
}


def build_review_prompt(
    file_content: str,
    file_path: str,
    context_chunks: list[dict],
    rules: list[dict],
) -> list[dict]:
    numbered_content = "\n".join(
        f"{i + 1:4d} | {line}"
        for i, line in enumerate(file_content.splitlines())
    )

    context_text = ""
    if context_chunks:
        context_parts = []
        for chunk in context_chunks[:8]:
            meta = chunk.get("metadata", {})
            context_parts.append(
                f"[{meta.get('file', 'unknown')}:{meta.get('lineno', '?')} — {meta.get('name', 'block')}]\n{chunk['content']}"
            )
        context_text = "\n\n---\n\n".join(context_parts)

    rules_text = ""
    if rules:
        rules_parts = [r["content"] for r in rules[:6]]
        rules_text = "\n\n".join(rules_parts)

    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": f"## File under review: `{file_path}`\n\n```\n{numbered_content}\n```",
                },
            ],
        }
    ]

    if context_text:
        messages[0]["content"].append({
            "type": "text",
            "text": f"\n\n## Related code from codebase (for cross-file reasoning)\n\n{context_text}",
        })

    if rules_text:
        messages[0]["content"].append({
            "type": "text",
            "text": f"\n\n## Security and style rules to apply\n\n{rules_text}",
        })

    messages[0]["content"].append({
        "type": "text",
        "text": (
            "\n\nPlease review the file above and return a JSON object matching the schema exactly. "
            "Reference line numbers from the numbered file listing. "
            "Use the related codebase context to identify cross-file issues."
        ),
    })

    return messages
