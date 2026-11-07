# VoxNote AI - Voice Notes Backend

FastAPI backend for VoxNote AI, a voice-notes application with Hindi and English transcription, note storage, tagging and semantic search.

## What it does

- **Audio transcription:** accepts uploads up to 25 MB, splits long audio into 25-second chunks and transcribes with the Sarvam AI speech-to-text API (Hindi and English). A failed transcription is never saved as a note.
- **Notes API:** create, read, update and delete text or transcribed notes, organized into folders, per user.
- **Automatic tagging:** generates one or two tags per note with a Groq-hosted LLM, handling English and Hinglish text.
- **Semantic search:** Pinecone vector search over note embeddings, with a graceful fallback that keeps notes saveable if the embedding service is unavailable.
- **Authentication:** JWT auth with bcrypt password hashing, Google sign-in, email/SMS OTP, and rate limiting.

## Tech stack

- Python, FastAPI, SQLAlchemy, PostgreSQL
- Sarvam AI (speech-to-text), Groq (tagging), Pinecone (semantic search)
- python-jose + passlib (JWT/bcrypt), pytest (12 tests)

## Run locally

```bash
pip install -r requirements.txt
# environment variables: database URL, SARVAM_API_KEY, GROQ_API_KEY,
# PINECONE_API_KEY, JWT secret, OTP/email/SMS provider keys
uvicorn main:app --reload
```

The frontend expects this API at VITE_API_URL (see VoiceNotes-Frontend).
