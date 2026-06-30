"""
Handles everything about user-uploaded PDF documents:
  1. Extracting text from the PDF
  2. Splitting that text into smaller "chunks" (LLMs and search
     work better on focused snippets than one giant blob of text)
  3. Storing those chunks in a local vector database (ChromaDB),
     tagged with the uploader's Telegram user_id so users never
     see each other's documents.

WHY CHUNKING:
  If a user uploads a 40-page report, we can't paste the whole
  thing into a single OpenAI call (too long, too unfocused).
  Instead we cut it into ~500-word pieces. When the user later
  asks a question, we only need to find and send the few chunks
  that are actually relevant to that question.

WHY A VECTOR DATABASE:
  "Relevant to the question" can't be found by simple keyword
  matching alone (e.g. user asks "outlook" but doc says "forecast").
  A vector DB stores each chunk as a numerical "embedding" that
  captures meaning, so we can search by semantic similarity.
  ChromaDB runs locally on your laptop — no separate server,
  no extra signup.
"""
import os
import uuid

import chromadb
from pypdf import PdfReader
from openai import OpenAI

from config import OPENAI_API_KEY

client_openai = OpenAI(api_key=OPENAI_API_KEY)

# Persistent local vector DB — creates a "chroma_db" folder next to this file
chroma_client = chromadb.PersistentClient(path="chroma_db")
collection = chroma_client.get_or_create_collection(name="user_documents")

CHUNK_SIZE_WORDS = 500  # roughly how many words go into one chunk


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
    Converts text into a numerical embedding (a list of numbers
    representing its meaning) using OpenAI's embedding model.
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
    and stores it in the vector DB tagged with this user's ID.

    Returns the number of chunks stored (useful for confirming
    to the user how much was processed).
    """
    text = extract_text_from_pdf(file_path)
    if not text.strip():
        raise ValueError(
            "Couldn't extract any text from this PDF. "
            "It might be a scanned/image-only PDF."
        )

    chunks = chunk_text(text)

    for chunk in chunks:
        embedding = embed_text(chunk)
        collection.add(
            ids=[str(uuid.uuid4())],
            embeddings=[embedding],
            documents=[chunk],
            metadatas=[{"user_id": str(user_id), "filename": filename}],
        )

    return len(chunks)


def search_user_documents(query: str, user_id: int, top_k: int = 3) -> list[str]:
    """
    Finds the chunks most relevant to `query`, but ONLY from
    documents uploaded by this specific user_id.

    Returns a list of matching text chunks (most relevant first).
    """
    query_embedding = embed_text(query)

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where={"user_id": str(user_id)},  # critical: isolates users from each other
    )

    documents = results.get("documents", [[]])[0]
    return documents