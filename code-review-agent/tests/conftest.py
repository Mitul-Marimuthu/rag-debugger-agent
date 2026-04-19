import os
import pytest


@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test_anthropic_key")
    monkeypatch.setenv("OPENAI_API_KEY", "test_openai_key")
    monkeypatch.setenv("GITHUB_TOKEN", "test_github_token")
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "test_secret")
    monkeypatch.setenv("CHROMA_PATH", "/tmp/test_chroma")
