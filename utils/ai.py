import os
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)
from dotenv import load_dotenv
from groq import Groq

load_dotenv()
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
async def generate_tags(transcript):
    # model = genai.GenerativeModel('gemini-2.5-flash') 
    prompt = f"""
    You are a strict tagging assistant. Read the voice note (which may be in English or Hinglish). 
    Output EXACTLY one or two unique relevant tag. Your response must ONLY be a comma-separated list. 
    No intro, no outro, no punctuation at the end.
    Voice Note: {transcript}
    """
    response = groq_client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.2,
        max_tokens=200
    )
    raw_tags_string = response.choices[0].message.content.strip()
    tags_list = [tag.strip() for tag in raw_tags_string.split(",")]
    return tags_list