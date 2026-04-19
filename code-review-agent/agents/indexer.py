import os
import hashlib
import json
from pathlib import Path

from rag.chunker import chunk_file
from rag.store import add_chunks, delete_file_chunks, get_or_create_collection
from config import settings

SUPPORTED_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".java", ".rb"}
HASH_CACHE_FILE = ".index_hashes.json"
IGNORE_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build", ".next"}


def _file_hash(file_path: str) -> str:
    h = hashlib.md5()
    with open(file_path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def _load_hash_cache(repo_path: str) -> dict[str, str]:
    cache_path = os.path.join(repo_path, HASH_CACHE_FILE)
    if os.path.exists(cache_path):
        with open(cache_path, "r") as f:
            return json.load(f)
    return {}


def _save_hash_cache(repo_path: str, cache: dict[str, str]) -> None:
    cache_path = os.path.join(repo_path, HASH_CACHE_FILE)
    with open(cache_path, "w") as f:
        json.dump(cache, f)


def _should_index(file_path: str) -> bool:
    path = Path(file_path)
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        return False
    for part in path.parts:
        if part in IGNORE_DIRS:
            return False
    return True


def index_file(file_path: str, collection_name: str = None) -> int:
    col_name = collection_name or settings.chroma_collection_name
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()
    except (IOError, OSError):
        return 0

    if not source.strip():
        return 0

    chunks = chunk_file(file_path, source)
    if chunks:
        delete_file_chunks(file_path, col_name)
        add_chunks(chunks, col_name)

    return len(chunks)


def index_repo(repo_path: str, force: bool = False, verbose: bool = True) -> dict:
    hash_cache = _load_hash_cache(repo_path) if not force else {}
    stats = {"indexed": 0, "skipped": 0, "files": 0, "chunks": 0}

    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        for fname in files:
            fpath = os.path.join(root, fname)
            if not _should_index(fpath):
                continue

            stats["files"] += 1
            current_hash = _file_hash(fpath)

            if not force and hash_cache.get(fpath) == current_hash:
                stats["skipped"] += 1
                continue

            n_chunks = index_file(fpath)
            hash_cache[fpath] = current_hash
            stats["indexed"] += 1
            stats["chunks"] += n_chunks

            if verbose:
                print(f"  Indexed {fpath} ({n_chunks} chunks)")

    _save_hash_cache(repo_path, hash_cache)

    also_index_docs(repo_path)

    if verbose:
        print(f"\nIndexing complete: {stats['indexed']} files indexed, {stats['skipped']} skipped, {stats['chunks']} total chunks")

    return stats


def delta_index(changed_files: list[str], repo_path: str = ".") -> dict:
    hash_cache = _load_hash_cache(repo_path)
    stats = {"indexed": 0, "chunks": 0}

    for fpath in changed_files:
        if not os.path.exists(fpath) or not _should_index(fpath):
            delete_file_chunks(fpath)
            continue

        n_chunks = index_file(fpath)
        hash_cache[fpath] = _file_hash(fpath)
        stats["indexed"] += 1
        stats["chunks"] += n_chunks

    _save_hash_cache(repo_path, hash_cache)
    return stats


def also_index_docs(repo_path: str) -> None:
    doc_files = []
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        for fname in files:
            if fname.lower() in ("readme.md", "readme.txt", "readme.rst", "contributing.md"):
                doc_files.append(os.path.join(root, fname))

    if not doc_files:
        return

    collection = get_or_create_collection(settings.chroma_collection_name)
    for fpath in doc_files:
        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except (IOError, OSError):
            continue

        if not content.strip():
            continue

        lines = content.splitlines()
        chunk_size = 100
        for i in range(0, len(lines), chunk_size):
            chunk_text = "\n".join(lines[i:i + chunk_size])
            doc_id = f"{fpath}:doc:{i}"
            try:
                collection.upsert(
                    documents=[chunk_text],
                    metadatas=[{"file": fpath, "type": "documentation", "name": "doc", "lineno": i, "end_lineno": i + chunk_size, "language": "markdown"}],
                    ids=[doc_id],
                )
            except Exception:
                pass
