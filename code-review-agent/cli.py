import typer
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

#testing

app = typer.Typer(
    name="code-review-agent",
    help="Autonomous code review agent with RAG-powered codebase intelligence.",
    add_completion=False,
)
console = Console()


@app.command()
def index(
    repo_path: str = typer.Argument(".", help="Local path or 'owner/repo' GitHub identifier"),
    force: bool = typer.Option(False, "--force", "-f", help="Re-index all files, ignoring cache"),
    verbose: bool = typer.Option(True, "--verbose/--quiet", "-v/-q"),
):
    """Index a codebase into the vector store for RAG retrieval.

    Pass a local path or a GitHub repo identifier (e.g. 'owner/repo').
    """
    import tempfile
    import shutil
    from agents.indexer import index_repo

    github_repo = None
    tmp_dir = None

    if "/" in repo_path and not Path(repo_path).exists():
        # Looks like owner/repo — clone it
        from config import settings
        import git as gitpython

        github_repo = repo_path
        clone_url = f"https://{settings.github_token}@github.com/{github_repo}.git"
        tmp_dir = tempfile.mkdtemp(prefix="cra_index_")
        console.print(f"[bold blue]Cloning[/bold blue] {github_repo} ...")
        try:
            gitpython.Repo.clone_from(clone_url, tmp_dir)
        except Exception as e:
            typer.echo(f"Error cloning repo: {e}", err=True)
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise typer.Exit(1)
        path = Path(tmp_dir)
    else:
        path = Path(repo_path).resolve()
        if not path.exists():
            typer.echo(f"Error: path '{repo_path}' does not exist.", err=True)
            raise typer.Exit(1)

    try:
        console.print(f"[bold blue]Indexing repository:[/bold blue] {github_repo or path}")
        stats = index_repo(str(path), force=force, verbose=verbose)
    finally:
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    table = Table(title="Indexing Complete")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Files processed", str(stats["files"]))
    table.add_row("Files indexed", str(stats["indexed"]))
    table.add_row("Files skipped (unchanged)", str(stats["skipped"]))
    table.add_row("Total chunks stored", str(stats["chunks"]))
    console.print(table)

    _index_rules()


@app.command()
def review(
    file_path: str = typer.Argument(..., help="Path to the file to review"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Save JSON output to file"),
    no_context: bool = typer.Option(False, "--no-context", help="Disable RAG context retrieval"),
    no_rules: bool = typer.Option(False, "--no-rules", help="Disable rules retrieval"),
):
    """Review a single file using the Claude API."""
    from agents.retriever import retrieve_context, retrieve_rules
    from agents.reviewer import review_file

    path = Path(file_path)
    if not path.exists():
        typer.echo(f"Error: file '{file_path}' does not exist.", err=True)
        raise typer.Exit(1)

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    console.print(f"[bold blue]Reviewing:[/bold blue] {file_path}")

    context = []
    if not no_context:
        console.print("  [dim]Retrieving context from codebase...[/dim]")
        context = retrieve_context(content, str(path))
        console.print(f"  [dim]Found {len(context)} relevant chunks[/dim]")

    rules = []
    if not no_rules:
        console.print("  [dim]Retrieving applicable rules...[/dim]")
        rules = retrieve_rules(content, str(path))
        console.print(f"  [dim]Found {len(rules)} applicable rules[/dim]")

    console.print("  [dim]Sending to Claude for review...[/dim]")
    result = review_file(content, str(path), context, rules)

    _print_result(result)

    if output:
        import json
        with open(output, "w") as f:
            json.dump(result.model_dump(), f, indent=2)
        console.print(f"\n[green]Results saved to {output}[/green]")


@app.command()
def review_pr(
    repo: str = typer.Argument(..., help="GitHub repo (owner/name)"),
    pr_number: int = typer.Argument(..., help="Pull request number"),
    post: bool = typer.Option(True, "--post/--no-post", help="Post review comments to GitHub"),
    fix_pr: bool = typer.Option(False, "--fix-pr", help="Create a fix PR with automated patches"),
):
    """Review a GitHub pull request."""
    from gh.client import get_pr_changed_files, get_file_content, get_pr
    from agents.retriever import retrieve_context, retrieve_rules
    from agents.reviewer import review_file
    from agents.action import post_review_to_pr, create_fix_pr

    console.print(f"[bold blue]Reviewing PR #{pr_number}[/bold blue] in {repo}")

    changed_files = get_pr_changed_files(repo, pr_number)
    pr = get_pr(repo, pr_number)
    head_sha = pr.head.sha

    reviewable = [
        f for f in changed_files
        if f["status"] != "removed" and _is_reviewable(f["filename"])
    ]

    console.print(f"  {len(reviewable)} reviewable files found")

    results = []
    for file_info in reviewable:
        console.print(f"  Reviewing [cyan]{file_info['filename']}[/cyan]...")
        content = get_file_content(repo, file_info["filename"], ref=head_sha)
        if not content:
            continue

        context = retrieve_context(content, file_info["filename"])
        rules = retrieve_rules(content, file_info["filename"])
        result = review_file(content, file_info["filename"], context, rules)
        results.append(result)
        _print_result(result)

    if post and results:
        console.print("\n[bold]Posting review to GitHub...[/bold]")
        review_info = post_review_to_pr(repo, pr_number, results)
        console.print(f"[green]Review posted:[/green] {review_info.get('html_url', '')}")

    if fix_pr and results:
        console.print("\n[bold]Creating fix PR...[/bold]")
        fix = create_fix_pr(repo, pr_number, results)
        if fix:
            console.print(f"[green]Fix PR created:[/green] {fix.get('html_url', '')}")
        else:
            console.print("[yellow]No fixable issues found.[/yellow]")


@app.command()
def serve(
    host: Optional[str] = typer.Option(None, help="Override webhook host"),
    port: Optional[int] = typer.Option(None, help="Override webhook port"),
):
    """Start the webhook server to listen for GitHub PR events."""
    from gh.webhook import run_webhook
    from config import settings

    if host:
        settings.webhook_host = host
    if port:
        settings.webhook_port = port

    console.print(
        f"[bold green]Starting webhook server[/bold green] on "
        f"http://{settings.webhook_host}:{settings.webhook_port}"
    )
    run_webhook()


def _print_result(result) -> None:
    severity_color = {
        "has_critical": "red",
        "has_warnings": "yellow",
        "suggestions_only": "blue",
        "clean": "green",
    }
    color = severity_color.get(result.overall_severity, "white")

    console.print(Panel(
        f"[{color}]{result.summary}[/{color}]\n\n"
        f"[red]Critical: {len(result.critical_issues)}[/red]  "
        f"[yellow]Warnings: {len(result.warnings)}[/yellow]  "
        f"[blue]Suggestions: {len(result.suggestions)}[/blue]",
        title=f"[bold]{result.file_path}[/bold]",
        border_style=color,
    ))

    for issue in result.issues:
        color = {"critical": "red", "warning": "yellow", "suggestion": "blue"}.get(issue.severity, "white")
        console.print(
            f"  [{color}][{issue.severity.upper()}][/{color}] "
            f"[bold]{issue.title}[/bold] (line {issue.line_start}–{issue.line_end})"
        )
        console.print(f"    {issue.description}")

    console.print()


def _index_rules() -> None:
    from pathlib import Path as P
    from rag.store import get_or_create_collection
    from config import settings

    rules_dir = P(__file__).parent / "rules"
    if not rules_dir.exists():
        return

    collection = get_or_create_collection(settings.rules_collection_name)
    for rules_file in rules_dir.glob("*.md"):
        with open(rules_file, "r", encoding="utf-8") as f:
            content = f.read()

        sections = content.split("\n## ")
        for i, section in enumerate(sections):
            if not section.strip():
                continue
            doc_id = f"{rules_file.name}:section:{i}"
            collection.upsert(
                documents=[section[:2000]],
                metadatas=[{"file": str(rules_file), "type": "rules", "section": i}],
                ids=[doc_id],
            )

    console.print("[dim]Rules indexed.[/dim]")


def _is_reviewable(filename: str) -> bool:
    reviewable_exts = {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".java", ".rb", ".html"}
    return Path(filename).suffix.lower() in reviewable_exts


if __name__ == "__main__":
    app()
