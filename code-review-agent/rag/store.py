import chromadb
from chromadb.utils import embedding_functions
from config import settings


_client: chromadb.PersistentClient | None = None


def _get_client() -> chromadb.PersistentClient:
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=settings.chroma_path)
    return _client


def _get_embedding_function():
    return embedding_functions.OpenAIEmbeddingFunction(
        api_key=settings.openai_api_key,
        model_name=settings.embedding_model,
    )


def get_or_create_collection(collection_name: str) -> chromadb.Collection:
    client = _get_client()
    ef = _get_embedding_function()
    return client.get_or_create_collection(collection_name, embedding_function=ef)


def add_chunks(chunks: list[dict], collection_name: str = None) -> None:
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
        collection.add(
            documents=[documents[i] for i in new_indices],
            metadatas=[metadatas[i] for i in new_indices],
            ids=[ids[i] for i in new_indices],
        )

    if update_indices:
        collection.update(
            documents=[documents[i] for i in update_indices],
            metadatas=[metadatas[i] for i in update_indices],
            ids=[ids[i] for i in update_indices],
        )


def query_collection(
    query_text: str,
    n_results: int = None,
    exclude_file: str = None,
    collection_name: str = None,
    min_score: float = None,
) -> list[dict]:
    col_name = collection_name or settings.chroma_collection_name
    collection = get_or_create_collection(col_name)
    k = n_results or settings.top_k_results
    threshold = min_score if min_score is not None else settings.min_confidence_threshold

    where = None
    if exclude_file:
        where = {"file": {"$ne": exclude_file}}

    try:
        results = collection.query(
            query_texts=[query_text],
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
