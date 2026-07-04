"""
One-off utility to inspect and clean up documents stored in the
vector DB. Run this directly — it's not part of the bot.

USAGE:
  1. LIST what's stored:
       python cleanup_documents.py list

  2. DELETE a specific file's chunks:
       python cleanup_documents.py delete "wrong_file.pdf"

  Optionally restrict either command to one user:
       python cleanup_documents.py list --user 123456789
       python cleanup_documents.py delete "wrong_file.pdf" --user 123456789

STORAGE BACKEND: Pinecone (active) / ChromaDB (commented out below)
"""
import sys
from collections import defaultdict

# ── Pinecone (ACTIVE) ──────────────────────────────────────────────
from pinecone import Pinecone
from config import PINECONE_API_KEY, PINECONE_INDEX_NAME

pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(PINECONE_INDEX_NAME)

# ── ChromaDB (COMMENTED OUT) ──────────────────────────────────────
# import chromadb
# chroma_client = chromadb.PersistentClient(path="chroma_db")
# collection = chroma_client.get_or_create_collection(name="user_documents")


def list_documents(user_id: str | None = None) -> None:
    """
    Prints every distinct (user_id, filename) pair currently stored.
    Pinecone doesn't have a native "list all metadata" endpoint, so we
    use list() to get all vector IDs in a namespace, then fetch their
    metadata in batches to summarise what's stored.
    """
    # ── Pinecone list (ACTIVE) ────────────────────────────────────
    namespaces = [user_id] if user_id else _get_all_namespaces()
    if not namespaces:
        print("No documents found.")
        return

    counts = defaultdict(int)
    for ns in namespaces:
        for id_batch in index.list(namespace=ns):
            vectors = index.fetch(ids=id_batch, namespace=ns)
            for vec_id, vec in vectors["vectors"].items():
                filename = vec.get("metadata", {}).get("filename", "unknown")
                counts[(ns, filename)] += 1

    print(f"{'User ID':<15} {'Filename':<40} {'Chunks'}")
    print("-" * 65)
    for (uid, filename), count in counts.items():
        print(f"{uid:<15} {filename:<40} {count}")

    # ── ChromaDB list (COMMENTED OUT) ────────────────────────────
    # where = {"user_id": user_id} if user_id else None
    # results = collection.get(where=where, include=["metadatas"])
    # metadatas = results.get("metadatas", [])
    # if not metadatas:
    #     print("No documents found.")
    #     return
    # counts = {}
    # for meta in metadatas:
    #     key = (meta.get("user_id"), meta.get("filename"))
    #     counts[key] = counts.get(key, 0) + 1
    # print(f"{'User ID':<15} {'Filename':<40} {'Chunks'}")
    # print("-" * 65)
    # for (uid, filename), count in counts.items():
    #     print(f"{uid:<15} {filename:<40} {count}")


def delete_document(filename: str, user_id: str | None = None) -> None:
    """
    Deletes all chunks matching this filename, scoped to one user
    namespace if provided, otherwise searches all namespaces.
    """
    # ── Pinecone delete (ACTIVE) ──────────────────────────────────
    namespaces = [user_id] if user_id else _get_all_namespaces()
    total_deleted = 0

    for ns in namespaces:
        ids_to_delete = []
        for id_batch in index.list(namespace=ns):
            vectors = index.fetch(ids=id_batch, namespace=ns)
            for vec_id, vec in vectors["vectors"].items():
                if vec.get("metadata", {}).get("filename") == filename:
                    ids_to_delete.append(vec_id)

        if ids_to_delete:
            confirm = input(
                f"About to delete {len(ids_to_delete)} chunk(s) for "
                f"'{filename}' in namespace '{ns}'. "
                f"Type 'yes' to confirm: "
            )
            if confirm.strip().lower() == "yes":
                index.delete(ids=ids_to_delete, namespace=ns)
                total_deleted += len(ids_to_delete)
                print(f"Deleted {len(ids_to_delete)} chunk(s) from namespace '{ns}'.")
            else:
                print(f"Cancelled for namespace '{ns}'.")

    if total_deleted == 0 and not ids_to_delete:
        print(f"No chunks found matching filename='{filename}'.")

    # ── ChromaDB delete (COMMENTED OUT) ──────────────────────────
    # if user_id:
    #     where = {"$and": [{"filename": filename}, {"user_id": user_id}]}
    # else:
    #     where = {"filename": filename}
    # matches = collection.get(where=where, include=[])
    # ids_to_delete = matches.get("ids", [])
    # if not ids_to_delete:
    #     print(f"No chunks found matching filename='{filename}'.")
    #     return
    # confirm = input(f"About to delete {len(ids_to_delete)} chunk(s). Type 'yes': ")
    # if confirm.strip().lower() == "yes":
    #     collection.delete(ids=ids_to_delete)
    #     print(f"Deleted {len(ids_to_delete)} chunk(s).")
    # else:
    #     print("Cancelled.")


def _get_all_namespaces() -> list[str]:
    """Returns all namespaces (user IDs) that have data in the index."""
    stats = index.describe_index_stats()
    return list(stats.get("namespaces", {}).keys())


if __name__ == "__main__":
    args = sys.argv[1:]

    if not args or args[0] not in ("list", "delete"):
        print(__doc__)
        sys.exit(1)

    user_id = None
    if "--user" in args:
        idx = args.index("--user")
        user_id = args[idx + 1]
        args = args[:idx] + args[idx + 2:]

    if args[0] == "list":
        list_documents(user_id=user_id)
    elif args[0] == "delete":
        if len(args) < 2:
            print('Usage: python cleanup_documents.py delete "filename.pdf"')
            sys.exit(1)
        delete_document(args[1], user_id=user_id)