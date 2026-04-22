from pathlib import Path

from agents.action import _apply_fixes
from agents.reviewer import ReviewResult


def apply_fixes_to_copy(file_path: str, content: str, result: ReviewResult) -> str:
    """Apply review fixes and write to {stem}_fixed{suffix}. Returns the output path."""
    path = Path(file_path)
    output_path = path.parent / f"{path.stem}_fixed{path.suffix}"
    patched = _apply_fixes(content, result)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(patched)
    return str(output_path)


def apply_fixes_to_path(output_path: str, content: str, result: ReviewResult) -> str:
    """Apply review fixes and write to an explicit output path, creating parent dirs."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    patched = _apply_fixes(content, result)
    with open(out, "w", encoding="utf-8") as f:
        f.write(patched)
    return str(out)


def count_fixable(result: ReviewResult) -> int:
    return sum(1 for i in result.issues if i.fix)
