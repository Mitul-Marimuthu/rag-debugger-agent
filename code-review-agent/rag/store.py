from typing import Optional, List

from google import genai as google_genai
import chromadb
from config import settings


_chroma_client: Optional[chromadb.PersistentClient] = None
_gemini_client: Optional[google_genai.Client] = None


def _get_client() -> chromadb.PersistentClient:
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(path=settings.chroma_path)
    return _chroma_client


def _get_gemini() -> google_genai.Client:
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = google_genai.Client(api_key=settings.gemini_api_key)
    return _gemini_client


def _embed(texts: List[str], task_type: str = "retrieval_document") -> List[List[float]]:
    client = _get_gemini()
    embeddings = []
    for text in texts:
        response = client.models.embed_content(
            model=settings.embedding_model,
            contents=text,
            config={"task_type": task_type},
        )
        embeddings.append(response.embeddings[0].values)
    return embeddings


def get_or_create_collection(collection_name: str) -> chromadb.Collection:
    return _get_client().get_or_create_collection(collection_name)


def add_chunks(chunks: List[dict], collection_name: str = None) -> None:
    if not chunks:
        return

    col_name = collection_name or settings.chroma_collection_name
    collection = get_or_create_collection(col_name)

    documents = [c["content"] for c in chunks]
    metadatas = [
        {
            "file": c["file"],
            "type": c["type"],
            "name": c.get("name", ""),
            "lineno": c.get("lineno", 0),
            "end_lineno": c.get("end_lineno", 0),
            "language": c.get("language", "unknown"),
        }
        for c in chunks
    ]
    ids = [f"{c['file']}:{c.get('lineno', 0)}:{c.get('name', 'block')}" for c in chunks]

    existing = collection.get(ids=ids)
    existing_ids = set(existing["ids"])
    new_indices = [i for i, id_ in enumerate(ids) if id_ not in existing_ids]
    update_indices = [i for i, id_ in enumerate(ids) if id_ in existing_ids]

    if new_indices:
        new_docs = [documents[i] for i in new_indices]
        collection.add(
            documents=new_docs,
            embeddings=_embed(new_docs, "retrieval_document"),
            metadatas=[metadatas[i] for i in new_indices],
            ids=[ids[i] for i in new_indices],
        )

    if update_indices:
        upd_docs = [documents[i] for i in update_indices]
        collection.update(
            documents=upd_docs,
            embeddings=_embed(upd_docs, "retrieval_document"),
            metadatas=[metadatas[i] for i in update_indices],
            ids=[ids[i] for i in update_indices],
        )


def query_collection(
    query_text: str,
    n_results: int = None,
    exclude_file: str = None,
    collection_name: str = None,
    min_score: float = None,
) -> List[dict]:
    col_name = collection_name or settings.chroma_collection_name
    collection = get_or_create_collection(col_name)
    k = n_results or settings.top_k_results
    threshold = min_score if min_score is not None else settings.min_confidence_threshold

    where = None
    if exclude_file:
        where = {"file": {"$ne": exclude_file}}

    try:
        query_embedding = _embed([query_text], "retrieval_query")[0]
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=k,
            where=where,
        )
    except Exception:
        return []

    chunks = []
    if not results["documents"] or not results["documents"][0]:
        return chunks

    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        score = 1 - dist
        if score >= threshold:
            chunks.append({"content": doc, "metadata": meta, "score": score})

    return chunks


def delete_file_chunks(file_path: str, collection_name: str = None) -> None:
    col_name = collection_name or settings.chroma_collection_name
    collection = get_or_create_collection(col_name)

    existing = collection.get(where={"file": {"$eq": file_path}})
    if existing["ids"]:
        collection.delete(ids=existing["ids"])


def collection_count(collection_name: str = None) -> int:
    col_name = collection_name or settings.chroma_collection_name
    collection = get_or_create_collection(col_name)
    return collection.count()
