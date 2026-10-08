import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

from gemini_call import generate_content_with_fallback

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise ValueError("GEMINI_API_KEY is missing from .env")

client = genai.Client(api_key=api_key)

MODEL_NAME = "gemini-3.5-flash-lite"

def analyze_image(image_path, user_question):
    """
    Analyze an uploaded screenshot/error image.

    This function does NOT create an incident.
    It only extracts useful technical information
    from the image.
    """

    with open(image_path, "rb") as image_file:
        image_bytes = image_file.read()

    prompt = f"""
You are assisting with a ServiceNow ITOM technical issue.

The user reported:

{user_question}

Analyze the attached image.

Identify useful information such as:

- Error messages
- Exception names
- HTTP status codes
- MID Server errors
- Connection errors
- ServiceNow errors
- Stack traces
- Configuration values
- Timestamps
- Hostnames
- Other technically relevant information

Do NOT invent information.

If the image does not contain useful technical information,
say so clearly.

Return a concise technical summary that can be given to
a ServiceNow ITOM troubleshooting system.
"""

    response = generate_content_with_fallback(
        client,
        model=MODEL_NAME,
        contents=[
            prompt,
            types.Part.from_bytes(
                data=image_bytes,
                mime_type=_get_mime_type(image_path),
            ),
        ],
    )

    return response.text or "No useful information could be extracted from the image."


def _get_mime_type(image_path):

    extension = os.path.splitext(image_path)[1].lower()

    mime_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }
    return mime_types.get(extension, "application/octet-stream")