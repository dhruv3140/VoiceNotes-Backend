from pinecone import Pinecone
import os
from dotenv import load_dotenv
load_dotenv()  
from datetime import datetime

def get_pinecone_index():
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    return pc.Index(os.getenv("PINECONE_INDEX_NAME"))

index = get_pinecone_index()

def save_note(note_id, vector, transcript, tags, user_id, folder_id=None, folder_name="General"):
    now = datetime.utcnow().isoformat()

    storage_object = {
        "id": note_id,
        "values": vector,
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

    index.upsert(vectors=[storage_object])

def search_notes(query_vector, user_id, top_k=3):
    search_results = index.query(
        vector=query_vector,
        top_k=top_k,
        include_metadata=True,
        filter={"user_id": {"$eq": user_id}}
    )
    return search_results.matches
def get_all_notes(user_id, limit=100):
    """Fetches the most recent notes from Pinecone using a dummy zero-vector."""
    zero_vector = [0.0] * 384
    response = index.query(
        vector=zero_vector,
        top_k=limit,
        include_metadata=True,
        filter= {"user_id": {"$eq": user_id}} # Filter notes by user_id
    )
    return response.matches

def delete_note_from_db(note_id):
    """Deletes a note permanently from Pinecone using its ID."""
    index.delete(ids=[note_id])

def update_note_in_db(
    note_id,
    new_vector,
    new_transcript,
    new_tags,
    user_id,
    folder_id=None,
    folder_name="General"
):
    storage_object = {
        "id": note_id,
        "values": new_vector,
        "metadata": {
            "transcript": new_transcript,
            "tags": new_tags,
            "user_id": user_id,
            "folder_id": folder_id if folder_id else 0,
            "folder_name": folder_name or "General",
            "updated_at": datetime.utcnow().isoformat()
        }
    }

    index.upsert(vectors=[storage_object])