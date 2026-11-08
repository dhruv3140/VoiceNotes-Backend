# VoxNote AI - Voice Notes Backend

FastAPI backend for VoxNote AI, a voice-notes application with Hindi and English transcription, note storage, tagging and semantic search.

## What it does

- **Audio transcription:** accepts uploads up to 25 MB, splits long audio into 25-second chunks and transcribes with the Sarvam AI speech-to-text API (Hindi and English). A failed transcription is never saved as a note.
- **Notes API:** create, read, update and delete text or transcribed notes, organized into folders, per user.
- **Automatic tagging:** generates one or two tags per note with a Groq-hosted LLM, handling English and Hinglish text.
- **Search:** user-scoped keyword search by default. Optional Pinecone embeddings add semantic matching when `SEMANTIC_SEARCH_ENABLED=true`; embedding failures leave notes saveable and search can fall back to keywords.
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


## Architecture and request flow

- `main.py` defines the FastAPI notes endpoints and mounts the authentication router.
- `auth/` stores user accounts in SQLAlchemy, issues JWTs and handles password, Google and OTP flows.
- `utils/audio.py` decodes uploaded audio and sends 25-second WAV chunks to Sarvam AI. The API rejects empty uploads and files above 25 MB. A transcription error returns HTTP 502 before any note is saved.
- `utils/ai.py` generates tags with Groq. `utils/database.py` stores note metadata and vectors in Pinecone, scoped to the authenticated user.
- Note updates and deletes check ownership before changing data. A missing or other user's note returns HTTP 404.

SQL stores account data; notes and their metadata are stored in Pinecone. Search is not evidence of a production-scale benchmark: listing/search currently examines at most 1,000 notes per user.

## Notes API

All `/notes` routes require `Authorization: Bearer <access_token>`. With the backend running, open `/docs` for the generated request and response schemas.

| Method | Route | Purpose |
| --- | --- | --- |
| POST | `/notes/text` | Save text with generated tags and optional folder metadata |
| GET | `/notes` | List the current user's notes; includes a `truncated` flag |
| POST | `/notes/audio` | Upload multipart field `file`; transcribe, tag and save |
| POST | `/notes/search` | Search with JSON `{"query": "..."}`; returns `search_mode` |
| PUT | `/notes/{note_id}` | Update an owned note's text and folder metadata |
| DELETE | `/notes/{note_id}` | Delete an owned note |

## Tests

The following isolated setup was used for the 12-test local run. It installs the imports needed by this test suite, not the full production provider stack:

```bash
python -m venv .venv-test
source .venv-test/bin/activate
pip install pytest fastapi httpx sqlalchemy python-dotenv python-jose \
  passlib "bcrypt<4" python-multipart requests email-validator \
  psycopg2-binary google-auth sib-api-v3-sdk resend
python -m pytest -q
```

Run these commands from the repository root. The run passed all 12 tests with one Starlette/httpx deprecation warning. Dependencies other than the bcrypt compatibility constraint are not pinned here; this documents the tested procedure, not a locked environment.

The local test run used `bcrypt<4` for compatibility with the existing Passlib stack; this is not verification that the unconstrained latest dependency set works. The test harness uses a local SQLite test database and in-memory Pinecone stand-in. It replaces provider calls; passing tests do not verify live speech-to-text, embedding, email or SMS services.

Coverage includes cross-user update/delete rejection, user-scoped search, listing more than 100 notes, failed transcription not being saved, OTP throttling/lockout, and semantic-search fallback/backfill behavior. The current suite has 12 tests.
