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
    now = datetime.utcnow().isoformat()

    record = {
        "_id": note_id,
        "text": transcript,
        "tags": tags,
        "user_id": user_id,
        "folder_id": folder_id if folder_id else 0,
        "folder_name": folder_name or "General",
        "created_at": now,
        "updated_at": now
    }

    # namespace ko "default" kar dein ya hata dein
    index.upsert_records(namespace="default", records=[record])

def search_notes(query_text, user_id, top_k=3):
    search_results = index.search_records(
        namespace="default",
        query={
            "top_k": top_k,
            "inputs": {"text": query_text},
            "filter": {"user_id": {"$eq": user_id}}
        }
    )
    return search_results.get("result", {}).get("hits", [])

def delete_note_from_db(note_id):
    index.delete(ids=[note_id], namespace="default")

def update_note_in_db(
    note_id,
    new_transcript,
    new_tags,
    user_id,
    folder_id=None,
    folder_name="General"
):
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

    index.upsert_records(namespace="default", records=[record])