import os

from dotenv import load_dotenv
from googleapiclient.discovery import build

load_dotenv()


def get_youtube_client():

    api_key = os.getenv("YOUTUBE_API_KEY")

    if not api_key:
        raise ValueError(
            "YOUTUBE_API_KEY is missing from .env"
        )

    return build(
        "youtube",
        "v3",
        developerKey=api_key
    )