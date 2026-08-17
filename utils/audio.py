import requests
import os
from io import BytesIO
from pydub import AudioSegment
from dotenv import load_dotenv
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
def transcribe_audio(audio_bytes):
    """Splits long audio into 1-minute chunks, transcribes them, and merges the text."""
    try:
        audio = AudioSegment.from_file(BytesIO(audio_bytes)) 
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
            response = requests.post(url, files=files, headers=headers, timeout=60)
            if response.status_code == 200:
                text = response.json().get('transcript', '').strip()
                if text:
                    full_transcript.append(text)
            else:
                print(f"Failed to transcribe chunk {i}: {response.text}")
                

        final_text = " ".join(full_transcript)
        return final_text if final_text else "Audio processing completed, but no text was captured."
        
    except Exception as e:
        print(f"Advanced Chunking Transcription failed: {e}")
        return "Audio transcription failed due to chunking or processing limits."