import re
from datetime import datetime

from agents.reviewer import ReviewResult, ReviewIssue
from github.client import (
    create_branch,
    update_file_on_branch,
    create_pull_request,
    post_pr_review,
    post_pr_comment,
    get_file_content,
    get_default_branch,
    label_pr,
)


SEVERITY_LABELS = {
    "critical": "review: critical",
    "warning": "review: warning",
    "suggestion": "review: suggestion",
    "clean": "review: clean",
}

SEVERITY_EMOJI = {
    "critical": "🔴",
    "warning": "🟡",
    "suggestion": "🔵",
}

TYPE_EMOJI = {
    "bug": "🐛",
    "security": "🔒",
    "code_smell": "👃",
    "style": "✨",
    "performance": "⚡",
}


def _build_review_comment_body(results: list[ReviewResult]) -> str:
    total_critical = sum(len(r.critical_issues) for r in results)
    total_warnings = sum(len(r.warnings) for r in results)
    total_suggestions = sum(len(r.suggestions) for r in results)

    lines = [
        "## 🤖 Automated Code Review",
        "",
        f"**{len(results)} file(s) reviewed** | "
        f"{SEVERITY_EMOJI['critical']} {total_critical} critical | "
        f"{SEVERITY_EMOJI['warning']} {total_warnings} warnings | "
        f"{SEVERITY_EMOJI['suggestion']} {total_suggestions} suggestions",
        "",
    ]

    for result in results:
        if not result.issues:
            lines.append(f"### ✅ `{result.file_path}` — No issues found")
            lines.append("")
            continue

        lines.append(f"### `{result.file_path}`")
        lines.append(f"> {result.summary}")
        lines.append("")

        for issue in result.issues:
            emoji = SEVERITY_EMOJI.get(issue.severity, "⚪")
            type_emoji = TYPE_EMOJI.get(issue.type, "")
            lines.append(
                f"#### {emoji} {type_emoji} **{issue.title}** (lines {issue.line_start}–{issue.line_end})"
            )
            lines.append(f"**Type:** `{issue.type}` | **Severity:** `{issue.severity}`")
            lines.append("")
            lines.append(issue.description)
            lines.append("")
            lines.append(f"**Why this matters:** {issue.explanation}")
            lines.append("")
            if issue.fix:
                lines.append("**Suggested fix:**")
                lines.append("```")
                lines.append(issue.fix)
                lines.append("```")
            if issue.references:
                lines.append(f"**References:** {', '.join(issue.references)}")
            lines.append("")
            lines.append("---")
            lines.append("")

    return "\n".join(lines)


def _build_inline_comments(result: ReviewResult) -> list[dict]:
    comments = []
    for issue in result.issues:
        body_parts = [
            f"{SEVERITY_EMOJI.get(issue.severity, '')} **{issue.title}**",
            "",
            issue.description,
            "",
            f"_{issue.explanation}_",
        ]
        if issue.fix:
            body_parts += ["", "**Fix:**", "```", issue.fix, "```"]
        if issue.references:
            body_parts.append(f"\n_References: {', '.join(issue.references)}_")

        comments.append({
            "path": result.file_path,
            "line": issue.line_end,
            "body": "\n".join(body_parts),
        })
    return comments


def post_review_to_pr(
    repo_name: str,
    pr_number: int,
    results: list[ReviewResult],
) -> dict:
    review_body = _build_review_comment_body(results)
    inline_comments = []
    for result in results:
        inline_comments.extend(_build_inline_comments(result))

    overall_severities = [r.overall_severity for r in results]
    if "has_critical" in overall_severities:
        event = "REQUEST_CHANGES"
    elif "has_warnings" in overall_severities:
        event = "COMMENT"
    else:
        event = "COMMENT"

    try:
        review = post_pr_review(
            repo_name=repo_name,
            pr_number=pr_number,
            review_body=review_body,
            comments=inline_comments,
            event=event,
        )
    except Exception:
        review = post_pr_comment(repo_name, pr_number, review_body)

    worst = "clean"
    priority = ["has_critical", "has_warnings", "suggestions_only", "clean"]
    for level in priority:
        if level in overall_severities:
            worst = level
            break

    severity_key = worst.replace("has_", "").replace("_only", "")
    label = SEVERITY_LABELS.get(severity_key, SEVERITY_LABELS["clean"])
    try:
        label_pr(repo_name, pr_number, [label])
    except Exception:
        pass

    return review


def create_fix_pr(
    repo_name: str,
    base_pr_number: int,
    results: list[ReviewResult],
    base_branch: str | None = None,
) -> dict | None:
    fixable = [r for r in results if any(i.fix for i in r.issues)]
    if not fixable:
        return None

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    fix_branch = f"review-fixes/{base_pr_number}/{timestamp}"
    base = base_branch or get_default_branch(repo_name)

    try:
        create_branch(repo_name, fix_branch, base_ref=base)
    except Exception as e:
        print(f"Failed to create branch: {e}")
        return None

    fixed_files = []
    for result in fixable:
        original = get_file_content(repo_name, result.file_path, ref=base)
        if original is None:
            continue

        patched = _apply_fixes(original, result)
        if patched == original:
            continue

        success = update_file_on_branch(
            repo_name=repo_name,
            file_path=result.file_path,
            new_content=patched,
            commit_message=f"fix: apply automated review fixes to {result.file_path}",
            branch_name=fix_branch,
        )
        if success:
            fixed_files.append(result.file_path)

    if not fixed_files:
        return None

    pr_body = _build_fix_pr_body(results, base_pr_number, fixed_files)
    pr = create_pull_request(
        repo_name=repo_name,
        title=f"🤖 Automated fixes for PR #{base_pr_number}",
        body=pr_body,
        head_branch=fix_branch,
        base_branch=base,
    )

    return pr


def _apply_fixes(source: str, result: ReviewResult) -> str:
    lines = source.splitlines(keepends=True)

    for issue in sorted(result.issues, key=lambda i: i.line_start, reverse=True):
        if not issue.fix:
            continue

        start = max(0, issue.line_start - 1)
        end = min(len(lines), issue.line_end)

        indent = _detect_indent(lines[start] if start < len(lines) else "")
        fix_lines = issue.fix.splitlines(keepends=True)
        indented_fix = [indent + l.lstrip() if l.strip() else l for l in fix_lines]
        if indented_fix and not indented_fix[-1].endswith("\n"):
            indented_fix[-1] += "\n"

        lines[start:end] = indented_fix

    return "".join(lines)


def _detect_indent(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]


def _build_fix_pr_body(results: list[ReviewResult], original_pr: int, fixed_files: list[str]) -> str:
    lines = [
        f"## 🤖 Automated Review Fixes",
        "",
        f"This PR contains automated fixes generated by the code review agent for PR #{original_pr}.",
        "",
        "### Files fixed",
        "",
    ]
    for f in fixed_files:
        lines.append(f"- `{f}`")
    lines += [
        "",
        "### Issues addressed",
        "",
    ]
    for result in results:
        for issue in result.issues:
            if issue.fix:
                lines.append(
                    f"- **{result.file_path}:{issue.line_start}** — {issue.title} (`{issue.severity}`)"
                )

    lines += [
        "",
        "> ⚠️ Please review these fixes before merging. Automated fixes may require manual adjustment.",
    ]
    return "\n".join(lines)
