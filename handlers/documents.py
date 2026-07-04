"""
Handles everything about user-uploaded PDF documents:
  1. Extracting text from the PDF
  2. Splitting that text into smaller "chunks"
  3. Storing those chunks in a vector database tagged with the
     uploader's Telegram user_id so users never see each other's docs

STORAGE BACKEND: Pinecone (cloud-hosted vector DB)
  Pinecone runs in the cloud — data persists across server restarts
  and redeploys, which local ChromaDB cannot do on free hosting tiers.

  ChromaDB code is kept below but commented out. To switch back to
  local ChromaDB (e.g. for local dev without a Pinecone key), just:
    1. Uncomment the ChromaDB block
    2. Comment out the Pinecone block
    3. No other files need changing

USER ISOLATION:
  Every chunk stored in Pinecone is tagged with the user's Telegram
  user_id in its metadata AND in its Pinecone namespace. Namespaces
  are Pinecone's built-in way of partitioning an index — querying one
  namespace never touches another, so User A's documents are
  completely isolated from User B's, even in the same index.
"""
import os
import uuid

# ── Pinecone (ACTIVE) ──────────────────────────────────────────────
from pinecone import Pinecone

# ── ChromaDB (COMMENTED OUT — uncomment to switch back to local DB) ─
# import chromadb

from pypdf import PdfReader
from openai import OpenAI

from config import OPENAI_API_KEY, PINECONE_API_KEY, PINECONE_INDEX_NAME

client_openai = OpenAI(api_key=OPENAI_API_KEY)

# ── Pinecone client setup (ACTIVE) ────────────────────────────────
pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(PINECONE_INDEX_NAME)

# ── ChromaDB client setup (COMMENTED OUT) ────────────────────────
# chroma_client = chromadb.PersistentClient(path="chroma_db")
# collection = chroma_client.get_or_create_collection(name="user_documents")

CHUNK_SIZE_WORDS = 500
EMBEDDING_DIMENSION = 1536  # OpenAI text-embedding-3-small output size


def extract_text_from_pdf(file_path: str) -> str:
    """Reads a PDF file and returns all its text as one big string."""
    reader = PdfReader(file_path)
    full_text = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            full_text.append(text)
    return "\n".join(full_text)


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE_WORDS) -> list[str]:
    """Splits text into chunks of roughly `chunk_size` words each."""
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size):
        chunk = " ".join(words[i : i + chunk_size])
        if chunk.strip():
            chunks.append(chunk)
    return chunks


def embed_text(text: str) -> list[float]:
    """
    Converts text into a numerical embedding using OpenAI.
    Used both when storing chunks and when searching later.
    """
    response = client_openai.embeddings.create(
        model="text-embedding-3-small",
        input=text,
    )
    return response.data[0].embedding


def store_document(file_path: str, user_id: int, filename: str) -> int:
    """
    Extracts text from the PDF, chunks it, embeds each chunk,
    and stores it in Pinecone tagged with this user's ID.

    Pinecone namespaces are used for user isolation — each user's
    chunks live in their own namespace (str(user_id)), so search
    queries for one user never touch another's data.

    Returns the number of chunks stored.
    """
    text = extract_text_from_pdf(file_path)
    if not text.strip():
        raise ValueError(
            "Couldn't extract any text from this PDF. "
            "It might be a scanned/image-only PDF."
        )

    chunks = chunk_text(text)

    # ── Pinecone upsert (ACTIVE) ──────────────────────────────────
    vectors = []
    for chunk in chunks:
        embedding = embed_text(chunk)
        vectors.append({
            "id": str(uuid.uuid4()),
            "values": embedding,
            "metadata": {
                "user_id": str(user_id),
                "filename": filename,
                "text": chunk,        # store text in metadata so we
            },                        # can retrieve it after search
        })

    # Pinecone upsert in batches of 100 (their recommended batch size)
    batch_size = 100
    for i in range(0, len(vectors), batch_size):
        index.upsert(
            vectors=vectors[i : i + batch_size],
            namespace=str(user_id),   # user isolation via namespace
        )

    # ── ChromaDB upsert (COMMENTED OUT) ──────────────────────────
    # for chunk in chunks:
    #     embedding = embed_text(chunk)
    #     collection.add(
    #         ids=[str(uuid.uuid4())],
    #         embeddings=[embedding],
    #         documents=[chunk],
    #         metadatas=[{"user_id": str(user_id), "filename": filename}],
    #     )

    return len(chunks)


def search_user_documents(query: str, user_id: int, top_k: int = 3) -> list[str]:
    """
    Finds the chunks most relevant to `query`, scoped strictly to
    this user's namespace in Pinecone (no cross-user leakage).

    Returns a list of matching text chunks (most relevant first).
    """
    query_embedding = embed_text(query)

    # ── Pinecone query (ACTIVE) ───────────────────────────────────
    results = index.query(
        vector=query_embedding,
        top_k=top_k,
        namespace=str(user_id),       # only search this user's docs
        include_metadata=True,
    )
    chunks = [
        match["metadata"]["text"]
        for match in results["matches"]
        if "text" in match.get("metadata", {})
    ]
    return chunks

    # ── ChromaDB query (COMMENTED OUT) ───────────────────────────
    # results = collection.query(
    #     query_embeddings=[query_embedding],
    #     n_results=top_k,
    #     where={"user_id": str(user_id)},
    # )
    # return results.get("documents", [[]])[0]