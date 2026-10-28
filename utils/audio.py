import requests
import os
from io import BytesIO
from pydub import AudioSegment
from dotenv import load_dotenv
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
class TranscriptionError(Exception):
    """Raised when audio cannot be transcribed. Nothing should be saved."""


def transcribe_audio(audio_bytes):
    """Splits long audio into chunks, transcribes them, and merges the text.

    Raises TranscriptionError if any chunk fails or no speech is found, so a
    failure is never saved as a note.
    """
    try:
        audio = AudioSegment.from_file(BytesIO(audio_bytes))
    except Exception as e:
        print(f"Could not decode audio: {e}")
        raise TranscriptionError("Could not read the audio file.")

    chunk_length_ms = 25000
    audio_length_ms = len(audio)
    total_chunks = (audio_length_ms // chunk_length_ms) + (1 if audio_length_ms % chunk_length_ms > 0 else 0)
    print(f"Total Audio Length: {audio_length_ms / 1000}s | Total Chunks: {total_chunks}")
    full_transcript = []
    url = "https://api.sarvam.ai/speech-to-text"
    headers = {'api-subscription-key': SARVAM_API_KEY}

    for i in range(total_chunks):
        start_time = i * chunk_length_ms
        end_time = min((i + 1) * chunk_length_ms, audio_length_ms)
        chunk = audio[start_time:end_time]

        chunk_buffer = BytesIO()
        chunk.export(chunk_buffer, format="wav", bitrate="64k")
        chunk_bytes = chunk_buffer.getvalue()

        files = {
            'file': (f'chunk_{i}.wav', chunk_bytes, 'audio/mpeg')
        }
        try:
            response = requests.post(url, files=files, headers=headers, timeout=60)
        except Exception as e:
            print(f"Chunk {i} request failed: {e}")
            raise TranscriptionError("Transcription service is unavailable.")

        if response.status_code != 200:
            print(f"Failed to transcribe chunk {i}: {response.status_code}")
            raise TranscriptionError("Transcription failed. Please retry.")

        text = response.json().get('transcript', '').strip()
        if text:
            full_transcript.append(text)

    final_text = " ".join(full_transcript)
    if not final_text:
        raise TranscriptionError("No speech was detected in the recording.")
    return final_text
