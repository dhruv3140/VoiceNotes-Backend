from auth.database import Base, engine
from auth import models
from auth.routes import router as auth_router
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uuid
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from auth.security import get_current_user
from auth.models import User
from utils.audio import transcribe_audio
from utils.ai import generate_tags  
from groq import Groq
from utils.database import save_note, get_all_notes, search_notes, delete_note_from_db, update_note_in_db
from utils.sms_service import send_sms_via_gateway

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://voice-notes-frontend-lemon.vercel.app/", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)
app.include_router(auth_router)

class TextNote(BaseModel):
    text: str
    folder_id: int | None = None
    folder_name: str | None = "General"

class SearchQuery(BaseModel):
    query: str

class UpdateNote(BaseModel):
    text: str
    folder_id: int | None = None
    folder_name: str | None = "General"

@app.get("/")
def home():
    return {"message": "Backend running"}

@app.post("/notes/text")
async def create_text_note(note: TextNote, current_user: User = Depends(get_current_user)):
    text = note.text.strip()
    tags = await generate_tags(text)
    note_id = str(uuid.uuid4())

    save_note(note_id, text, tags, current_user.id, note.folder_id, note.folder_name)
    return {"success": True, "id": note_id}

@app.get("/notes")
async def get_notes(current_user: User = Depends(get_current_user)):
    notes = get_all_notes(current_user.id)
    clean_notes = []

    for note in notes:
        clean_notes.append({
            "id": note.id,
            "metadata": note.metadata
        })

    return {
        "success": True,
        "notes": clean_notes
    }


@app.post("/notes/audio")
async def create_audio_note(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    audio_bytes = await file.read()
    transcript = transcribe_audio(audio_bytes)
    tags = await generate_tags(transcript)
    note_id = str(uuid.uuid4())

    save_note(note_id, transcript, tags, current_user.id, 0, "General")

    return {
        "success": True,
        "id": note_id,
        "transcript": transcript
    }

@app.post("/notes/search")
def search_note(query: SearchQuery, current_user: User = Depends(get_current_user)):
    results = search_notes(query.query, current_user.id)
    clean_results = []

    for r in results:
        score = getattr(r, 'score', 1.0) 
        if score >= 0.3:
            clean_results.append({
                "id": getattr(r, 'id', getattr(r, '_id', None)),
                "score": score,
                "metadata": getattr(r, 'metadata', r)
            })

    return {
        "success": True,
        "results": clean_results
    }

@app.put("/notes/{note_id}")
async def update_note(
    note_id: str,
    note: UpdateNote,
    current_user: User = Depends(get_current_user)
):
    text = note.text.strip()
    tags = await generate_tags(text)

    update_note_in_db(
        note_id,
        text,
        tags,
        current_user.id,
        note.folder_id,
        note.folder_name
    )

    return {"success": True, "message": "Note updated"}

@app.delete("/notes/{note_id}")
def delete_note(note_id: str, current_user: User = Depends(get_current_user)):
    delete_note_from_db(note_id)
    return {"success": True, "message": "Note deleted"}