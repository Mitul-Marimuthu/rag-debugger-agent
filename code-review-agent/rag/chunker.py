import ast
from pathlib import Path
from typing import Optional
#comment

def chunk_python_file(source_code: str, file_path: str) -> list[dict]:
    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        return _fallback_chunk(source_code, file_path)

    chunks = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            chunk_source = ast.get_source_segment(source_code, node)
            if chunk_source:
                chunks.append({
                    "content": chunk_source,
                    "type": type(node).__name__,
                    "name": node.name,
                    "lineno": node.lineno,
                    "end_lineno": getattr(node, "end_lineno", node.lineno),
                    "file": file_path,
                    "language": "python",
                })

    if not chunks:
        return _fallback_chunk(source_code, file_path)

    return chunks


def chunk_javascript_file(source_code: str, file_path: str) -> list[dict]:
    try:
        import tree_sitter_javascript as tsjs
        from tree_sitter import Language, Parser

        JS_LANGUAGE = Language(tsjs.language())
        parser = Parser(JS_LANGUAGE)
        tree = parser.parse(bytes(source_code, "utf-8"))

        chunks = []
        cursor = tree.walk()

        def visit_node(node):
            if node.type in (
                "function_declaration",
                "arrow_function",
                "method_definition",
                "class_declaration",
            ):
                chunk_text = source_code[node.start_byte:node.end_byte]
                name = ""
                for child in node.children:
                    if child.type == "identifier":
                        name = source_code[child.start_byte:child.end_byte]
                        break

                chunks.append({
                    "content": chunk_text,
                    "type": node.type,
                    "name": name,
                    "lineno": node.start_point[0] + 1,
                    "end_lineno": node.end_point[0] + 1,
                    "file": file_path,
                    "language": "javascript",
                })

            for child in node.children:
                visit_node(child)

        visit_node(tree.root_node)

        if chunks:
            return chunks
    except ImportError:
        pass

    return _fallback_chunk(source_code, file_path)


def chunk_html_file(source_code: str, file_path: str) -> list[dict]:
    import re

    chunks = []
    # Extract <script>, <style>, and <template> blocks as distinct chunks
    for tag in ("script", "style", "template"):
        for m in re.finditer(
            rf"(<{tag}[\s>].*?</{tag}>)", source_code, re.DOTALL | re.IGNORECASE
        ):
            lines_before = source_code[: m.start()].count("\n") + 1
            content = m.group(1)
            end_line = lines_before + content.count("\n")
            chunks.append({
                "content": content,
                "type": tag,
                "name": tag,
                "lineno": lines_before,
                "end_lineno": end_line,
                "file": file_path,
                "language": "html",
            })

    if not chunks:
        return _fallback_chunk(source_code, file_path)
    return chunks


def _fallback_chunk(source_code: str, file_path: str, chunk_size: int = 50) -> list[dict]:
    lines = source_code.splitlines()
    chunks = []
    for i in range(0, len(lines), chunk_size):
        chunk_lines = lines[i:i + chunk_size]
        chunks.append({
            "content": "\n".join(chunk_lines),
            "type": "block",
            "name": f"lines_{i + 1}_{min(i + chunk_size, len(lines))}",
            "lineno": i + 1,
            "end_lineno": min(i + chunk_size, len(lines)),
            "file": file_path,
            "language": "unknown",
        })
    return chunks


def chunk_file(file_path: str, source_code: Optional[str] = None) -> list[dict]:
    path = Path(file_path)

    if source_code is None:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            source_code = f.read()

    ext = path.suffix.lower()

    if ext == ".py":
        return chunk_python_file(source_code, file_path)
    elif ext in (".js", ".jsx", ".ts", ".tsx"):
        return chunk_javascript_file(source_code, file_path)
    elif ext == ".html":
        return chunk_html_file(source_code, file_path)
    else:
        return _fallback_chunk(source_code, file_path)
