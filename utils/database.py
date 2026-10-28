from pinecone import Pinecone
import os
import math
import re
from types import SimpleNamespace
from dotenv import load_dotenv
load_dotenv()  
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))

pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))


def get_pinecone_index():
    return pc.Index(os.getenv("PINECONE_INDEX_NAME"))

index = get_pinecone_index()

# Embeddings come from Pinecone Inference (same provider that already stores the
# notes). llama-text-embed-v2 supports 384 dims, matching the existing index.
EMBED_MODEL = "llama-text-embed-v2"
EMBED_DIM = 384
EMBED_TAG = f"{EMBED_MODEL}-{EMBED_DIM}"
EMBED_MAX_CHARS = 6000
EMBED_BATCH = 90
BACKFILL_PER_SEARCH = 90
SEMANTIC_MIN_SCORE = 0.30
# Off until the Pinecone account, index (dimension/metric) and embedding quota
# are confirmed. Set SEMANTIC_SEARCH_ENABLED=true in the server environment to turn on.
SEMANTIC_ENABLED = os.getenv("SEMANTIC_SEARCH_ENABLED", "false").strip().lower() == "true"


def embed_texts(texts, input_type):
    """Returns a list of 384-float vectors, or raises if the embedding call fails."""
    out = []
    for i in range(0, len(texts), EMBED_BATCH):
        batch = [str(t or " ")[:EMBED_MAX_CHARS] or " " for t in texts[i:i + EMBED_BATCH]]
        res = pc.inference.embed(
            model=EMBED_MODEL,
            inputs=batch,
            parameters={"input_type": input_type, "truncate": "END", "dimension": EMBED_DIM},
        )
        for item in res:
            vals = getattr(item, "values", None)
            if vals is None and isinstance(item, dict):
                vals = item.get("values")
            vals = [float(x) for x in vals]
            if len(vals) != EMBED_DIM:
                raise ValueError("Unexpected embedding size")
            out.append(vals)
    if len(out) != len(texts):
        raise ValueError("Embedding count mismatch")
    return out


def _note_text(transcript, tags, folder_name=None):
    tag_text = ", ".join(str(t) for t in (tags or [])) if not isinstance(tags, str) else tags
    return f"{transcript}\nTags: {tag_text}".strip()


def _vector_for_note(transcript, tags, folder_name=None):
    """Returns (vector, embedding_tag). Falls back to the placeholder vector if embedding fails."""
    if not SEMANTIC_ENABLED:
        return [0.1] * EMBED_DIM, None
    try:
        return embed_texts([_note_text(transcript, tags, folder_name)], "passage")[0], EMBED_TAG
    except Exception as e:
        print(f"Embedding failed, saving without embedding: {type(e).__name__}")
        return [0.1] * EMBED_DIM, None

def save_note(note_id, transcript, tags, user_id, folder_id=None, folder_name="General"):
    now = datetime.now(IST).isoformat()
    vector, tag = _vector_for_note(transcript, tags, folder_name)
    metadata = {
        "transcript": transcript,
        "tags": tags,
        "user_id": user_id,
        "folder_id": folder_id if folder_id else 0,
        "folder_name": folder_name or "General",
        "created_at": now,
        "updated_at": now
    }
    if tag:
        metadata["embedding"] = tag
    storage_object = {"id": note_id, "values": vector, "metadata": metadata}
    index.upsert(vectors=[storage_object], namespace="default")

MAX_NOTES = 1000  # Pinecone's top_k limit when metadata is included


def get_all_notes(user_id, limit=MAX_NOTES, include_values=False):
    dummy_vector = [0.1] * 384
    response = index.query(
        vector=dummy_vector,
        top_k=min(limit, MAX_NOTES),
        include_metadata=True,
        include_values=include_values,
        filter={"user_id": {"$eq": user_id}},
        namespace="default"
    )
    return response.matches


def _tokens(text):
    return re.findall(r"\w+", str(text or "").lower())


def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _keyword_score(query_tokens, phrase, meta):
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
        return 0.0
    frac = hits / len(query_tokens)
    return 0.3 + 0.6 * frac + (0.1 if phrase in haystack else 0)


def _backfill_embeddings(notes):
    """Embeds notes saved before embeddings existed. Only the vector and an
    'embedding' tag change; all metadata is preserved. Returns {note_id: vector}."""
    todo = [n for n in notes if (getattr(n, "metadata", None) or {}).get("embedding") != EMBED_TAG]
    todo = todo[:BACKFILL_PER_SEARCH]
    if not todo:
        return {}
    vectors = embed_texts(
        [_note_text(n.metadata.get("transcript", ""), n.metadata.get("tags")) for n in todo],
        "passage",
    )
    done = {}
    upserts = []
    for n, vec in zip(todo, vectors):
        meta = dict(n.metadata)
        meta["embedding"] = EMBED_TAG
        upserts.append({"id": n.id, "values": vec, "metadata": meta})
        done[n.id] = vec
    index.upsert(vectors=upserts, namespace="default")
    return done


def search_notes(query_text, user_id, top_k=20):
    """Searches the user's own notes. Returns (results, mode) where mode is
    "semantic" (meaning + keywords) or "keyword" (embeddings off or unavailable)."""
    query_tokens = _tokens(query_text)
    if not query_tokens:
        return [], "keyword"
    phrase = " ".join(query_tokens)

    notes = get_all_notes(user_id, include_values=True)

    semantic = {}
    mode = "keyword"
    try:
        if not SEMANTIC_ENABLED:
            raise RuntimeError("semantic search disabled")
        fresh = _backfill_embeddings(notes)
        query_vec = embed_texts([str(query_text)], "query")[0]
        for n in notes:
            meta = getattr(n, "metadata", None) or {}
            vec = fresh.get(n.id)
            if vec is None and meta.get("embedding") == EMBED_TAG:
                vec = list(getattr(n, "values", None) or [])
            if vec and len(vec) == EMBED_DIM:
                semantic[n.id] = _cosine(query_vec, vec)
        mode = "semantic"
    except Exception as e:
        if SEMANTIC_ENABLED:
            print(f"Semantic search unavailable, using keyword search: {type(e).__name__}: {str(e)[:300]}", flush=True)

    scored = []
    for n in notes:
        meta = getattr(n, "metadata", None) or {}
        kw = _keyword_score(query_tokens, phrase, meta)
        sem = semantic.get(n.id, 0.0)
        sem = sem if sem >= SEMANTIC_MIN_SCORE else 0.0
        score = max(kw, sem)
        if score > 0:
            scored.append(SimpleNamespace(id=n.id, score=round(score, 3), metadata=meta))

    scored.sort(key=lambda r: r.score, reverse=True)
    return scored[:top_k], mode


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
    vector, tag = _vector_for_note(new_transcript, new_tags, folder_name)
    metadata = {
        "transcript": new_transcript,
        "tags": new_tags,
        "user_id": owner,
        "folder_id": folder_id if folder_id else 0,
        "folder_name": folder_name or "General",
        "created_at": old_meta.get("created_at", now),
        "updated_at": now
    }
    if tag:
        metadata["embedding"] = tag
    storage_object = {"id": note_id, "values": vector, "metadata": metadata}
    index.upsert(vectors=[storage_object], namespace="default")
    return True
