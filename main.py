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
from utils.audio import transcribe_audio, TranscriptionError
from starlette.concurrency import run_in_threadpool
from utils.ai import generate_tags  
from groq import Groq
from utils.database import user_owns_note, save_note, get_all_notes, search_notes, delete_note_from_db, update_note_in_db
from utils.sms_service import send_sms_via_gateway

MAX_AUDIO_BYTES = 25 * 1024 * 1024

app = FastAPI()

origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://localhost",
    "https://voice-notes-frontend-lemon.vercel.app",  
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
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
    audio_bytes = await file.read(MAX_AUDIO_BYTES + 1)
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio file is too large.")
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Audio file is empty.")

    try:
        transcript = await run_in_threadpool(transcribe_audio, audio_bytes)
    except TranscriptionError as e:
        raise HTTPException(status_code=502, detail=str(e))

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
    if not user_owns_note(note_id, current_user.id):
        raise HTTPException(status_code=404, detail="Note not found")

    text = note.text.strip()
    tags = await generate_tags(text)

    updated = update_note_in_db(
        note_id,
        text,
        tags,
        current_user.id,
        note.folder_id,
        note.folder_name
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Note not found")

    return {"success": True, "message": "Note updated"}

@app.delete("/notes/{note_id}")
def delete_note(note_id: str, current_user: User = Depends(get_current_user)):
    if not delete_note_from_db(note_id, current_user.id):
        raise HTTPException(status_code=404, detail="Note not found")
    return {"success": True, "message": "Note deleted"}