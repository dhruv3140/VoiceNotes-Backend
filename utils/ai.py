import warnings
warnings.filterwarnings("ignore", category=FutureWarning)
from sentence_transformers import SentenceTransformer
import os
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
def generate_tags(transcript):
    model = genai.GenerativeModel('gemini-3.1-flash-lite') 
    prompt = f"""
    You are a strict tagging assistant. Read the voice note (which may be in English or Hinglish). 
    Output EXACTLY one or two unique relevant tag. Your response must ONLY be a comma-separated list. 
    No intro, no outro, no punctuation at the end.
    Voice Note: {transcript}
    """
    response = model.generate_content(prompt)
    raw_tags_string = response.text.strip()
    tags_list = [tag.strip() for tag in raw_tags_string.split(",")]
    return tags_list

def get_embedding(transcript):
    vector = embedding_model.encode(transcript).tolist()
    return vector