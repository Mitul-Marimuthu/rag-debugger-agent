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
def fix(
    file_path: str = typer.Argument(..., help="Path to the file to review and fix"),
    no_context: bool = typer.Option(False, "--no-context", help="Disable RAG context retrieval"),
    no_rules: bool = typer.Option(False, "--no-rules", help="Disable rules retrieval"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show fixes without writing files"),
):
    """Review a file and apply fixes locally. Creates a .bak backup before overwriting."""
    from agents.retriever import retrieve_context, retrieve_rules
    from agents.reviewer import review_file
    from agents.action import _apply_fixes
    import shutil

    path = Path(file_path)
    if not path.exists():
        typer.echo(f"Error: file '{file_path}' does not exist.", err=True)
        raise typer.Exit(1)

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    console.print(f"[bold blue]Reviewing:[/bold blue] {file_path}")

    context = [] if no_context else retrieve_context(content, str(path))
    rules = [] if no_rules else retrieve_rules(content, str(path))
    result = review_file(content, str(path), context, rules)

    _print_result(result)

    fixable = [i for i in result.issues if i.fix]
    if not fixable:
        console.print("[yellow]No fixable issues found.[/yellow]")
        return

    console.print(f"\n[bold]{len(fixable)} fixable issue(s) found.[/bold]")

    if dry_run:
        from rich.text import Text
        for issue in fixable:
            body = Text()
            body.append(f"Line {issue.line_start}–{issue.line_end}\n", style="dim")
            body.append(f"{issue.description}\n\n", style="white")
            body.append("Suggested fix:\n", style="bold")
            body.append(issue.fix, style="green")
            console.print(Panel(body, title=f"[cyan]{issue.title}[/cyan]", border_style="cyan"))
        return

    backup = path.with_suffix(path.suffix + ".bak")
    shutil.copy2(path, backup)
    console.print(f"[dim]Backup saved to {backup}[/dim]")

    patched = _apply_fixes(content, result)
    with open(path, "w", encoding="utf-8") as f:
        f.write(patched)

    console.print(f"[green]Fixed {len(fixable)} issue(s) in {path}[/green]")


@app.command()
def fix_file(
    file_path: str = typer.Argument(..., help="Path to the file to review and fix"),
    no_context: bool = typer.Option(False, "--no-context", help="Disable RAG context retrieval"),
    no_rules: bool = typer.Option(False, "--no-rules", help="Disable rules retrieval"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show fixes without writing files"),
):
    """Review a file and write fixes to {filename}_fixed.{ext}. Original is never touched."""
    from agents.retriever import retrieve_context, retrieve_rules
    from agents.reviewer import review_file
    from agents.fixer import apply_fixes_to_copy, count_fixable
    from rich.text import Text

    path = Path(file_path)
    if not path.exists():
        typer.echo(f"Error: file '{file_path}' does not exist.", err=True)
        raise typer.Exit(1)

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    console.print(f"[bold blue]Reviewing:[/bold blue] {file_path}")
    context = [] if no_context else retrieve_context(content, str(path))
    rules = [] if no_rules else retrieve_rules(content, str(path))
    result = review_file(content, str(path), context, rules)

    _print_result(result)

    n = count_fixable(result)
    if n == 0:
        console.print("[yellow]No fixable issues found.[/yellow]")
        return

    if dry_run:
        from rich.text import Text
        for issue in [i for i in result.issues if i.fix]:
            body = Text()
            body.append(f"Line {issue.line_start}–{issue.line_end}\n", style="dim")
            body.append(f"{issue.description}\n\n", style="white")
            body.append("Suggested fix:\n", style="bold")
            body.append(issue.fix, style="green")
            console.print(Panel(body, title=f"[cyan]{issue.title}[/cyan]", border_style="cyan"))
        return

    output = apply_fixes_to_copy(str(path), content, result)
    console.print(f"[green]Wrote {n} fix(es) to[/green] [bold]{output}[/bold]")


@app.command()
def fix_folder(
    folder_path: str = typer.Argument(..., help="Path to the folder to process"),
    no_context: bool = typer.Option(False, "--no-context", help="Disable RAG context retrieval"),
    no_rules: bool = typer.Option(False, "--no-rules", help="Disable rules retrieval"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be fixed without writing files"),
    recursive: bool = typer.Option(True, "--recursive/--no-recursive", help="Walk subdirectories"),
    out_dir: str = typer.Option("fixed", "--out-dir", help="Output folder name (created inside the target folder)"),
):
    """Review every source file in a folder and write all fixed files into a mirrored
    output directory (default: <folder>/fixed/). Files without issues are copied as-is
    so the output folder is a complete, self-contained copy whose files reference each other."""
    import os
    import shutil
    from agents.indexer import SUPPORTED_EXTENSIONS, _ignore_dir
    from agents.retriever import retrieve_context, retrieve_rules
    from agents.reviewer import review_file
    from agents.fixer import apply_fixes_to_path, count_fixable

    root = Path(folder_path).resolve()
    if not root.exists():
        typer.echo(f"Error: folder '{folder_path}' does not exist.", err=True)
        raise typer.Exit(1)

    output_root = root / out_dir
    if not dry_run:
        output_root.mkdir(parents=True, exist_ok=True)
        console.print(f"[dim]Output folder: {output_root}[/dim]")

    processed = fixed = copied = 0

    walker = os.walk(root) if recursive else [(str(root), [], os.listdir(root))]
    for dirpath, dirs, files in walker:
        if recursive:
            dirs[:] = [d for d in dirs if not _ignore_dir(d) and d != out_dir]
        for fname in files:
            fpath = Path(dirpath) / fname
            if fpath.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue

            rel = fpath.relative_to(root)
            dest = output_root / rel

            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except OSError:
                continue

            processed += 1
            console.print(f"[bold blue]Reviewing:[/bold blue] {rel}")

            context = [] if no_context else retrieve_context(content, str(fpath))
            rules = [] if no_rules else retrieve_rules(content, str(fpath))
            result = review_file(content, str(fpath), context, rules)
            _print_result(result)

            n = count_fixable(result)

            if dry_run:
                if n:
                    console.print(f"  [dim](dry-run) {n} fix(es) → {rel}[/dim]")
                    fixed += 1
                else:
                    console.print(f"  [dim](dry-run) no fixes → copy as-is[/dim]")
                    copied += 1
                continue

            if n:
                apply_fixes_to_path(str(dest), content, result)
                console.print(f"  [green]{n} fix(es) written →[/green] fixed/{rel}")
                fixed += 1
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(fpath, dest)
                console.print(f"  [dim]No fixes — copied →[/dim] fixed/{rel}")
                copied += 1

    console.print(
        f"\n[bold green]Done.[/bold green] "
        f"{processed} file(s) processed: {fixed} fixed, {copied} copied unchanged."
        + (f"\n  Output: {output_root}" if not dry_run else "")
    )


@app.command()
def pipeline(
    repo_path: str = typer.Argument(..., help="Local path or 'owner/repo' GitHub identifier"),
    force_index: bool = typer.Option(False, "--force-index", help="Re-index even if cache is fresh"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show fixes without writing files"),
    no_rules: bool = typer.Option(False, "--no-rules", help="Skip rules retrieval"),
):
    """Full pipeline: index a repo, review all source files, and apply fixes locally."""
    import tempfile
    import shutil as _shutil
    from agents.indexer import index_repo
    from agents.retriever import retrieve_context, retrieve_rules
    from agents.reviewer import review_file
    from agents.action import _apply_fixes

    github_repo = None
    tmp_dir = None

    if "/" in repo_path and not Path(repo_path).exists():
        from config import settings
        import git as gitpython

        github_repo = repo_path
        clone_url = f"https://{settings.github_token}@github.com/{github_repo}.git"
        tmp_dir = tempfile.mkdtemp(prefix="cra_pipeline_")
        console.print(f"[bold blue]Cloning[/bold blue] {github_repo} ...")
        try:
            gitpython.Repo.clone_from(clone_url, tmp_dir)
        except Exception as e:
            typer.echo(f"Error cloning repo: {e}", err=True)
            _shutil.rmtree(tmp_dir, ignore_errors=True)
            raise typer.Exit(1)
        root = Path(tmp_dir)
    else:
        root = Path(repo_path).resolve()
        if not root.exists():
            typer.echo(f"Error: path '{repo_path}' does not exist.", err=True)
            raise typer.Exit(1)

    try:
        # 1 — Index
        console.print(f"\n[bold blue]Step 1/3 — Indexing[/bold blue] {github_repo or root}")
        stats = index_repo(str(root), force=force_index, verbose=False)
        console.print(f"  Indexed {stats['indexed']} files, {stats['chunks']} chunks")
        _index_rules()

        # 2 — Review all source files
        console.print("\n[bold blue]Step 2/3 — Reviewing files[/bold blue]")
        from agents.indexer import SUPPORTED_EXTENSIONS, _ignore_dir
        import os

        all_results = []
        for dirpath, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if not _ignore_dir(d)]
            for fname in files:
                fpath = Path(dirpath) / fname
                if fpath.suffix.lower() not in SUPPORTED_EXTENSIONS:
                    continue
                try:
                    with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                except OSError:
                    continue

                console.print(f"  Reviewing [cyan]{fpath.relative_to(root)}[/cyan]...")
                context = retrieve_context(content, str(fpath))
                rules = [] if no_rules else retrieve_rules(content, str(fpath))
                result = review_file(content, str(fpath), context, rules)
                all_results.append((fpath, content, result))
                _print_result(result)

        # 3 — Apply fixes
        console.print("\n[bold blue]Step 3/3 — Applying fixes[/bold blue]")
        fixed_count = 0
        for fpath, content, result in all_results:
            fixable = [i for i in result.issues if i.fix]
            if not fixable:
                continue

            if dry_run:
                console.print(f"  [dim](dry-run) would fix {len(fixable)} issue(s) in {fpath.name}[/dim]")
                continue

            backup = fpath.with_suffix(fpath.suffix + ".bak")
            import shutil
            shutil.copy2(fpath, backup)
            patched = _apply_fixes(content, result)
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(patched)
            console.print(f"  [green]Fixed {len(fixable)} issue(s) in {fpath.name}[/green]")
            fixed_count += 1

        console.print(f"\n[bold green]Pipeline complete.[/bold green] {fixed_count} file(s) patched.")

    finally:
        if tmp_dir:
            _shutil.rmtree(tmp_dir, ignore_errors=True)


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
