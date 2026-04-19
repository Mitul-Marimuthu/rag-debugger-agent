import hashlib
import hmac
import json
from typing import Annotated

from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import JSONResponse

from config import settings
from agents.indexer import delta_index
from agents.retriever import retrieve_context, retrieve_rules
from agents.reviewer import review_file
from agents.action import post_review_to_pr, create_fix_pr
from gh.client import get_pr_changed_files, get_file_content, get_pr

app = FastAPI(title="Code Review Agent Webhook")


def _verify_signature(payload: bytes, signature: str) -> bool:
    if not settings.github_webhook_secret:
        return True
    expected = "sha256=" + hmac.new(
        settings.github_webhook_secret.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@app.post("/webhook")
async def github_webhook(
    request: Request,
    x_github_event: Annotated[str, Header()] = "",
    x_hub_signature_256: Annotated[str, Header()] = "",
):
    body = await request.body()

    if settings.github_webhook_secret and not _verify_signature(body, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    if x_github_event == "pull_request":
        action = payload.get("action", "")
        if action in ("opened", "synchronize", "reopened"):
            pr_number = payload["pull_request"]["number"]
            repo_name = payload["repository"]["full_name"]
            head_sha = payload["pull_request"]["head"]["sha"]

            import asyncio
            asyncio.create_task(_handle_pr_review(repo_name, pr_number, head_sha))
            return JSONResponse({"status": "review_queued", "pr": pr_number})

    return JSONResponse({"status": "ignored", "event": x_github_event})


@app.get("/health")
async def health():
    return {"status": "ok"}


async def _handle_pr_review(repo_name: str, pr_number: int, head_sha: str) -> None:
    try:
        changed_files = get_pr_changed_files(repo_name, pr_number)
        pr = get_pr(repo_name, pr_number)
        base_ref = pr.base.ref

        code_files = [
            f for f in changed_files
            if f["status"] != "removed" and _is_reviewable(f["filename"])
        ]

        results = []
        for file_info in code_files:
            content = get_file_content(repo_name, file_info["filename"], ref=head_sha)
            if not content:
                continue

            context = retrieve_context(content, file_info["filename"])
            rules = retrieve_rules(content, file_info["filename"])
            result = review_file(content, file_info["filename"], context, rules)
            results.append(result)

        if results:
            post_review_to_pr(repo_name, pr_number, results)
            create_fix_pr(repo_name, pr_number, results, base_branch=base_ref)

    except Exception as e:
        print(f"Error handling PR #{pr_number}: {e}")


def _is_reviewable(filename: str) -> bool:
    reviewable_exts = {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".java", ".rb"}
    from pathlib import Path
    return Path(filename).suffix.lower() in reviewable_exts


def run_webhook():
    import uvicorn
    uvicorn.run(app, host=settings.webhook_host, port=settings.webhook_port)
