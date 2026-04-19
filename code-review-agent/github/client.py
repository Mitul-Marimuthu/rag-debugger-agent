import base64
from typing import Optional

from github import Github, GithubException
from github.Repository import Repository
from github.PullRequest import PullRequest

from config import settings


_gh: Optional[Github] = None


def _get_github() -> Github:
    global _gh
    if _gh is None:
        _gh = Github(settings.github_token)
    return _gh


def get_repo(repo_name: str) -> Repository:
    return _get_github().get_repo(repo_name)


def get_pr(repo_name: str, pr_number: int) -> PullRequest:
    repo = get_repo(repo_name)
    return repo.get_pull(pr_number)


def get_pr_changed_files(repo_name: str, pr_number: int) -> list[dict]:
    pr = get_pr(repo_name, pr_number)
    files = []
    for f in pr.get_files():
        files.append({
            "filename": f.filename,
            "status": f.status,
            "additions": f.additions,
            "deletions": f.deletions,
            "patch": f.patch,
            "sha": f.sha,
        })
    return files


def get_file_content(repo_name: str, file_path: str, ref: str = "main") -> Optional[str]:
    repo = get_repo(repo_name)
    try:
        content = repo.get_contents(file_path, ref=ref)
        return base64.b64decode(content.content).decode("utf-8", errors="replace")
    except GithubException:
        return None


def get_default_branch(repo_name: str) -> str:
    repo = get_repo(repo_name)
    return repo.default_branch


def create_branch(repo_name: str, branch_name: str, base_ref: Optional[str] = None) -> str:
    repo = get_repo(repo_name)
    base = base_ref or repo.default_branch
    source = repo.get_branch(base)
    repo.create_git_ref(ref=f"refs/heads/{branch_name}", sha=source.commit.sha)
    return branch_name


def update_file_on_branch(
    repo_name: str,
    file_path: str,
    new_content: str,
    commit_message: str,
    branch_name: str,
) -> bool:
    repo = get_repo(repo_name)
    try:
        existing = repo.get_contents(file_path, ref=branch_name)
        repo.update_file(
            path=file_path,
            message=commit_message,
            content=new_content,
            sha=existing.sha,
            branch=branch_name,
        )
        return True
    except GithubException:
        return False


def create_pull_request(
    repo_name: str,
    title: str,
    body: str,
    head_branch: str,
    base_branch: Optional[str] = None,
) -> dict:
    repo = get_repo(repo_name)
    base = base_branch or repo.default_branch
    pr = repo.create_pull(title=title, body=body, head=head_branch, base=base)
    return {
        "number": pr.number,
        "html_url": pr.html_url,
        "title": pr.title,
    }


def post_pr_review(
    repo_name: str,
    pr_number: int,
    review_body: str,
    comments: list[dict],
    event: str = "COMMENT",
) -> dict:
    pr = get_pr(repo_name, pr_number)
    head_sha = pr.head.sha

    review_comments = []
    for c in comments:
        comment = {
            "path": c["path"],
            "body": c["body"],
        }
        if "line" in c:
            comment["line"] = c["line"]
        review_comments.append(comment)

    review = pr.create_review(
        body=review_body,
        event=event,
        comments=review_comments,
    )

    return {"id": review.id, "html_url": review.html_url}


def post_pr_comment(repo_name: str, pr_number: int, body: str) -> dict:
    pr = get_pr(repo_name, pr_number)
    issue = pr.as_issue()
    comment = issue.create_comment(body)
    return {"id": comment.id, "html_url": comment.html_url}


def label_pr(repo_name: str, pr_number: int, labels: list[str]) -> None:
    pr = get_pr(repo_name, pr_number)
    issue = pr.as_issue()
    issue.set_labels(*labels)
