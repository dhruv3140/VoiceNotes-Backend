from pinecone import Pinecone
import os
from dotenv import load_dotenv
load_dotenv()  
from datetime import datetime

def get_pinecone_index():
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    return pc.Index(os.getenv("PINECONE_INDEX_NAME"))

index = get_pinecone_index()

def save_note(note_id, transcript, tags, user_id, folder_id=None, folder_name="General"):
    """Saves text and metadata directly. Pinecone handles vectorization automatically."""
    now = datetime.utcnow().isoformat()

    record = {
        "_id": note_id,
        "text": transcript,  # Pinecone serverless embedding model ise khud vectorize kar lega
        "tags": tags,
        "user_id": user_id,
        "folder_id": folder_id if folder_id else 0,
        "folder_name": folder_name or "General",
        "created_at": now,
        "updated_at": now
    }

    # Using upsert_records for integrated serverless text indexing
    index.upsert_records(namespace="", records=[record])

def search_notes(query_text, user_id, top_k=3):
    """Performs semantic search directly using raw query text via Pinecone integrated inference."""
    search_results = index.search_records(
        namespace="",
        query={
            "top_k": top_k,
            "inputs": {"text": query_text},
            "filter": {"user_id": {"$eq": user_id}}
        }
    )
    return search_results.get("result", {}).get("hits", [])

def get_all_notes(user_id, limit=100):
    """Fetches recent notes using Pinecone list/query fallback or metadata filtering."""
    # Since we use integrated text indexing, we fetch matching records by user filter
    response = index.query(
        vector=[0.0] * 384,
        top_k=limit,
        include_metadata=True,
        filter={"user_id": {"$eq": user_id}}
    )
    return response.matches

def delete_note_from_db(note_id):
    """Deletes a note permanently from Pinecone using its ID."""
    index.delete(ids=[note_id], namespace="")

def update_note_in_db(
    note_id,
    new_transcript,
    new_tags,
    user_id,
    folder_id=None,
    folder_name="General"
):
    """Updates/overwrites a note record cleanly without manual vectors."""
    now = datetime.utcnow().isoformat()
    
    record = {
        "_id": note_id,
        "text": new_transcript,
        "tags": new_tags,
        "user_id": user_id,
        "folder_id": folder_id if folder_id else 0,
        "folder_name": folder_name or "General",
        "updated_at": now
    }

    index.upsert_records(namespace="", records=[record])