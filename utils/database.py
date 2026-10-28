from pinecone import Pinecone
import os
import re
from types import SimpleNamespace
from dotenv import load_dotenv
load_dotenv()  
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))

def get_pinecone_index():
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    return pc.Index(os.getenv("PINECONE_INDEX_NAME"))

index = get_pinecone_index()

def save_note(note_id, transcript, tags, user_id, folder_id=None, folder_name="General"):
    now = datetime.now(IST).isoformat()
    storage_object = {
        "id": note_id,
        "values": [0.1] * 384, 
        "metadata": {
            "transcript": transcript,
            "tags": tags,
            "user_id": user_id,
            "folder_id": folder_id if folder_id else 0,
            "folder_name": folder_name or "General",
            "created_at": now,
            "updated_at": now
        }
    }
    index.upsert(vectors=[storage_object], namespace="default")

MAX_NOTES = 1000  # Pinecone's top_k limit when metadata is included


def get_all_notes(user_id, limit=MAX_NOTES):
    dummy_vector = [0.1] * 384
    response = index.query(
        vector=dummy_vector,
        top_k=min(limit, MAX_NOTES),
        include_metadata=True,
        filter={"user_id": {"$eq": user_id}},
        namespace="default"
    )
    return response.matches


def _tokens(text):
    return re.findall(r"\w+", str(text or "").lower())


def search_notes(query_text, user_id, top_k=20):
    """Keyword search over the user's own notes (transcript, tags, folder).

    Notes are stored with a constant placeholder vector, so there is no
    embedding-based search. This ranks by how many query words appear.
    """
    query_tokens = _tokens(query_text)
    if not query_tokens:
        return []

    phrase = " ".join(query_tokens)
    scored = []
    for match in get_all_notes(user_id):
        meta = getattr(match, "metadata", None) or {}
        tags = meta.get("tags") or []
        if isinstance(tags, str):
            tags = [tags]
        haystack = " ".join([
            str(meta.get("transcript", "")),
            " ".join(str(t) for t in tags),
            str(meta.get("folder_name", "")),
        ]).lower()
        words = set(_tokens(haystack))

        hits = sum(1 for t in query_tokens if t in words or t in haystack)
        if hits == 0:
            continue
        frac = hits / len(query_tokens)
        score = 0.3 + 0.6 * frac + (0.1 if phrase in haystack else 0)
        scored.append(SimpleNamespace(id=match.id, score=round(score, 3), metadata=meta))

    scored.sort(key=lambda r: r.score, reverse=True)
    return scored[:top_k]


def get_note_owner(note_id):
    """Returns (exists, owner_user_id, metadata) for a note id."""
    response = index.fetch(ids=[note_id], namespace="default")
    vectors = getattr(response, "vectors", None) or {}
    vector = vectors.get(note_id)
    if vector is None:
        return False, None, {}
    meta = getattr(vector, "metadata", None) or {}
    return True, meta.get("user_id"), dict(meta)


def _same_user(a, b):
    """Pinecone returns numeric metadata as floats (5.0), so compare numerically."""
    try:
        return a is not None and b is not None and int(float(a)) == int(float(b))
    except (TypeError, ValueError):
        return str(a) == str(b)


def user_owns_note(note_id, user_id):
    exists, owner, _ = get_note_owner(note_id)
    return exists and _same_user(owner, user_id)


def delete_note_from_db(note_id, user_id):
    """Deletes a note only if it belongs to user_id. Returns True if deleted."""
    if not user_owns_note(note_id, user_id):
        return False
    index.delete(ids=[note_id], namespace="default")
    return True


def update_note_in_db(note_id, new_transcript, new_tags, user_id, folder_id=None, folder_name="General"):
    """Updates a note only if it belongs to user_id. Returns True if updated."""
    exists, owner, old_meta = get_note_owner(note_id)
    if not exists or not _same_user(owner, user_id):
        return False

    now = datetime.now(IST).isoformat()
    storage_object = {
        "id": note_id,
        "values": [0.1] * 384,
        "metadata": {
            "transcript": new_transcript,
            "tags": new_tags,
            "user_id": owner,
            "folder_id": folder_id if folder_id else 0,
            "folder_name": folder_name or "General",
            "created_at": old_meta.get("created_at", now),
            "updated_at": now
        }
    }
    index.upsert(vectors=[storage_object], namespace="default")
    return True
