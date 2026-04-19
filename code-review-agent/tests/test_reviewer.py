import pytest
import json
from unittest.mock import MagicMock, patch
from agents.reviewer import review_file, ReviewResult, ReviewIssue

SAMPLE_CODE = """
import os

def get_user(user_id):
    query = f"SELECT * FROM users WHERE id = {user_id}"
    return db.execute(query)

def delete_file(path):
    os.system(f"rm -rf {path}")
"""

MOCK_REVIEW_RESPONSE = {
    "summary": "Critical SQL injection and command injection vulnerabilities found.",
    "overall_severity": "has_critical",
    "issues": [
        {
            "type": "security",
            "severity": "critical",
            "line_start": 4,
            "line_end": 5,
            "title": "SQL Injection",
            "description": "User input directly interpolated into SQL query.",
            "explanation": "An attacker can manipulate the query to extract or modify arbitrary data.",
            "fix": 'db.execute("SELECT * FROM users WHERE id = ?", (user_id,))',
            "references": ["CWE-89", "OWASP A03"],
        }
    ],
}


@patch("agents.reviewer._get_client")
def test_review_file_returns_result(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    mock_final = MagicMock()
    mock_final.content = [
        MagicMock(type="text", text=json.dumps(MOCK_REVIEW_RESPONSE))
    ]

    mock_stream = MagicMock()
    mock_stream.__enter__ = MagicMock(return_value=mock_stream)
    mock_stream.__exit__ = MagicMock(return_value=False)
    mock_stream.get_final_message = MagicMock(return_value=mock_final)
    mock_client.messages.stream.return_value = mock_stream

    result = review_file(SAMPLE_CODE, "app.py", [], [])

    assert isinstance(result, ReviewResult)
    assert result.file_path == "app.py"
    assert result.overall_severity == "has_critical"
    assert len(result.issues) == 1


@patch("agents.reviewer._get_client")
def test_review_file_malformed_json(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    mock_final = MagicMock()
    mock_final.content = [MagicMock(type="text", text="not json")]

    mock_stream = MagicMock()
    mock_stream.__enter__ = MagicMock(return_value=mock_stream)
    mock_stream.__exit__ = MagicMock(return_value=False)
    mock_stream.get_final_message = MagicMock(return_value=mock_final)
    mock_client.messages.stream.return_value = mock_stream

    result = review_file(SAMPLE_CODE, "app.py", [], [])
    assert isinstance(result, ReviewResult)
    assert result.issues == []


def test_review_issue_severity_filter():
    result = ReviewResult(
        file_path="app.py",
        summary="test",
        overall_severity="has_critical",
        issues=[
            ReviewIssue(type="security", severity="critical", line_start=1, line_end=2,
                        title="t", description="d", explanation="e", fix="f"),
            ReviewIssue(type="style", severity="suggestion", line_start=3, line_end=4,
                        title="t2", description="d2", explanation="e2", fix="f2"),
        ],
    )
    assert len(result.critical_issues) == 1
    assert len(result.suggestions) == 1
    assert len(result.warnings) == 0
