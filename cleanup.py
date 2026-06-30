"""
One-off utility to inspect and clean up documents stored in the
vector DB (chroma_db). Run this directly — it's not part of the bot.

USAGE:
  1. First, LIST what's stored, to find the exact filename to delete:
       python cleanup.py list

  2. Then DELETE a specific file's chunks (must match filename exactly,
     as shown by the list command):
       python cleanup.py delete "wrong_file.pdf"

  Optionally restrict either command to one user:
       python cleanup.py list --user 123456789
       python cleanup.py delete "wrong_file.pdf" --user 123456789
"""
import sys
import chromadb

chroma_client = chromadb.PersistentClient(path="chroma_db")
collection = chroma_client.get_or_create_collection(name="user_documents")


def list_documents(user_id: str | None = None) -> None:
    """Prints every distinct (user_id, filename) pair currently stored,
    with a count of how many chunks each has."""
    where = {"user_id": user_id} if user_id else None
    results = collection.get(where=where, include=["metadatas"])

    metadatas = results.get("metadatas", [])
    if not metadatas:
        print("No documents found.")
        return

    counts = {}
    for meta in metadatas:
        key = (meta.get("user_id"), meta.get("filename"))
        counts[key] = counts.get(key, 0) + 1

    print(f"{'User ID':<15} {'Filename':<40} {'Chunks'}")
    print("-" * 65)
    for (uid, filename), count in counts.items():
        print(f"{uid:<15} {filename:<40} {count}")


def delete_document(filename: str, user_id: str | None = None) -> None:
    """Deletes all chunks matching this filename (optionally scoped
    to one user_id too, in case two users uploaded same-named files)."""
    if user_id:
        where = {"$and": [{"filename": filename}, {"user_id": user_id}]}
    else:
        where = {"filename": filename}

    # First check how many would be deleted, so we can confirm.
    matches = collection.get(where=where, include=[])
    ids_to_delete = matches.get("ids", [])

    if not ids_to_delete:
        print(f"No chunks found matching filename='{filename}'"
              f"{f' and user_id={user_id}' if user_id else ''}.")
        return

    confirm = input(
        f"About to delete {len(ids_to_delete)} chunk(s) for "
        f"'{filename}'{f' (user {user_id})' if user_id else ''}. "
        f"Type 'yes' to confirm: "
    )
    if confirm.strip().lower() != "yes":
        print("Cancelled.")
        return

    collection.delete(ids=ids_to_delete)
    print(f"Deleted {len(ids_to_delete)} chunk(s).")


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
            print("Usage: python cleanup_documents.py delete \"filename.pdf\"")
            sys.exit(1)
        delete_document(args[1], user_id=user_id)