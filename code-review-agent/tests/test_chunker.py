import pytest
from rag.chunker import chunk_python_file, chunk_file, _fallback_chunk

SIMPLE_PYTHON = """
def hello(name: str) -> str:
    return f"Hello, {name}!"

class Greeter:
    def __init__(self, prefix: str):
        self.prefix = prefix

    def greet(self, name: str) -> str:
        return f"{self.prefix} {name}"
"""

BROKEN_PYTHON = "def broken(: pass"


def test_chunk_python_functions():
    chunks = chunk_python_file(SIMPLE_PYTHON, "test.py")
    names = [c["name"] for c in chunks]
    assert "hello" in names
    assert "Greeter" in names


def test_chunk_python_methods():
    chunks = chunk_python_file(SIMPLE_PYTHON, "test.py")
    names = [c["name"] for c in chunks]
    assert "greet" in names
    assert "__init__" in names


def test_chunk_python_lineno():
    chunks = chunk_python_file(SIMPLE_PYTHON, "test.py")
    func_chunk = next(c for c in chunks if c["name"] == "hello")
    assert func_chunk["lineno"] > 0


def test_chunk_broken_python_fallback():
    chunks = chunk_python_file(BROKEN_PYTHON, "test.py")
    assert len(chunks) > 0
    assert chunks[0]["type"] == "block"


def test_fallback_chunk_size():
    source = "\n".join(f"line {i}" for i in range(200))
    chunks = _fallback_chunk(source, "test.py", chunk_size=50)
    assert len(chunks) == 4


def test_chunk_file_dispatch_python():
    chunks = chunk_file("test.py", SIMPLE_PYTHON)
    assert any(c["language"] == "python" for c in chunks)


def test_chunk_file_dispatch_unknown():
    chunks = chunk_file("test.css", "body { color: red; }")
    assert len(chunks) > 0
