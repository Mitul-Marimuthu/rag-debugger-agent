import pytest
from unittest.mock import patch, MagicMock

SAMPLE_CHUNKS = [
    {
        "content": "def hello():\n    return 'hi'",
        "type": "FunctionDef",
        "name": "hello",
        "lineno": 1,
        "end_lineno": 2,
        "file": "test.py",
        "language": "python",
    }
]


@patch("rag.store._get_client")
@patch("rag.store._get_embedding_function")
def test_add_chunks_calls_collection(mock_ef, mock_client):
    mock_collection = MagicMock()
    mock_collection.get.return_value = {"ids": []}
    mock_client.return_value.get_or_create_collection.return_value = mock_collection
    mock_ef.return_value = MagicMock()

    from rag.store import add_chunks
    add_chunks(SAMPLE_CHUNKS, "test_collection")

    mock_collection.add.assert_called_once()


@patch("rag.store._get_client")
@patch("rag.store._get_embedding_function")
def test_add_chunks_empty_noop(mock_ef, mock_client):
    from rag.store import add_chunks
    add_chunks([], "test_collection")
    mock_client.assert_not_called()


@patch("rag.store._get_client")
@patch("rag.store._get_embedding_function")
def test_query_returns_filtered_results(mock_ef, mock_client):
    mock_collection = MagicMock()
    mock_collection.query.return_value = {
        "documents": [["def hello(): pass"]],
        "metadatas": [[{"file": "other.py", "type": "FunctionDef", "name": "hello", "lineno": 1, "end_lineno": 2, "language": "python"}]],
        "distances": [[0.1]],
    }
    mock_client.return_value.get_or_create_collection.return_value = mock_collection
    mock_ef.return_value = MagicMock()

    from rag.store import query_collection
    results = query_collection("hello function", n_results=5, min_score=0.5)
    assert len(results) == 1
    assert results[0]["score"] == pytest.approx(0.9)
