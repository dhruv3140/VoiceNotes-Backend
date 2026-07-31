from pinecone import Pinecone
import os
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
    # Hum vector ki jagah dummy vector ya direct metadata upsert karenge
    storage_object = {
        "id": note_id,
        "values": [0.1] * 384,  # Dummy stable vector taaki Pinecone index khush rahe
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

def get_all_notes(user_id, limit=100):
    # Dummy vector se query karne par user ke saare notes metadata ke sath mil jayenge
    dummy_vector = [0.1] * 384
    response = index.query(
        vector=dummy_vector,
        top_k=limit,
        include_metadata=True,
        filter={"user_id": {"$eq": user_id}},
        namespace="default"
    )
    return response.matches

def search_notes(query_text, user_id, top_k=3):
    """Performs search using dummy vector since we are storing direct metadata notes."""
    dummy_vector = [0.1] * 384
    search_results = index.query(
        vector=dummy_vector,
        top_k=top_k,
        include_metadata=True,
        filter={"user_id": {"$eq": user_id}},
        namespace="default"
    )
    return search_results.matches

def delete_note_from_db(note_id):
    index.delete(ids=[note_id], namespace="default")

def update_note_in_db(note_id, new_transcript, new_tags, user_id, folder_id=None, folder_name="General"):
    now = datetime.now(IST).isoformat()
    storage_object = {
        "id": note_id,
        "values": [0.1] * 384,
        "metadata": {
            "transcript": new_transcript,
            "tags": new_tags,
            "user_id": user_id,
            "folder_id": folder_id if folder_id else 0,
            "folder_name": folder_name or "General",
            "updated_at": now
        }
    }
    index.upsert(vectors=[storage_object], namespace="default")