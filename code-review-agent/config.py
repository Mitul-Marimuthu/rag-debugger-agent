from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    anthropic_api_key: str = Field(..., description="Anthropic API key")
    openai_api_key: str = Field(default="", description="Unused")
    gemini_api_key: str = Field(default="", description="Unused")
    github_token: str = Field(..., description="GitHub personal access token")
    github_webhook_secret: str = Field(default="", description="GitHub webhook HMAC secret")

    chroma_path: str = Field(default="./codebase_index", description="ChromaDB persistence path")
    chroma_collection_name: str = Field(default="codebase")
    rules_collection_name: str = Field(default="rules")

    top_k_results: int = Field(default=8, description="Number of RAG results to retrieve")
    min_confidence_threshold: float = Field(default=0.5, description="Minimum similarity score")

    model_name: str = Field(default="claude-opus-4-7")
    embedding_model: str = Field(default="text-embedding-3-small")

    webhook_host: str = Field(default="0.0.0.0")
    webhook_port: int = Field(default=8000)


settings = Settings()
