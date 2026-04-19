from pathlib import Path

from rag.store import query_collection
from config import settings


def retrieve_context(file_content: str, file_path: str) -> list[dict]:
    query_text = _build_query_from_file(file_content, file_path)

    chunks = query_collection(
        query_text=query_text,
        n_results=settings.top_k_results,
        exclude_file=file_path,
        collection_name=settings.chroma_collection_name,
        min_score=settings.min_confidence_threshold,
    )

    return chunks


def retrieve_rules(file_content: str, file_path: str) -> list[dict]:
    ext = Path(file_path).suffix.lower()
    language = _detect_language(ext)

    queries = [
        f"{language} security vulnerabilities authentication authorization",
        f"{language} code quality best practices",
        "SQL injection XSS CSRF security",
        "error handling exception management",
    ]

    seen = set()
    rules = []
    for q in queries:
        results = query_collection(
            query_text=q,
            n_results=3,
            collection_name=settings.rules_collection_name,
            min_score=0.3,
        )
        for r in results:
            rid = r["content"][:100]
            if rid not in seen:
                seen.add(rid)
                rules.append(r)

    return rules


def _build_query_from_file(file_content: str, file_path: str) -> str:
    lines = file_content.splitlines()
    imports = [l.strip() for l in lines[:50] if l.strip().startswith(("import ", "from ", "require(", "use "))]
    first_funcs = [l.strip() for l in lines if l.strip().startswith(("def ", "class ", "function ", "async def "))][:5]

    parts = [file_path]
    if imports:
        parts.append(" ".join(imports[:10]))
    if first_funcs:
        parts.append(" ".join(first_funcs))

    return " ".join(parts)


def _detect_language(ext: str) -> str:
    mapping = {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".go": "go",
        ".java": "java",
        ".rb": "ruby",
    }
    return mapping.get(ext, "general")
