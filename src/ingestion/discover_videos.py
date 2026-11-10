import logging

from src.api.youtube_client import get_youtube_client
from src.api.retry import execute_with_retry

logger = logging.getLogger(__name__)


def search_videos(
    keyword: str,
    max_pages: int = 1
) -> list[dict]:

    youtube = get_youtube_client()

    videos = []
    next_page_token = None

    for page in range(max_pages):

        logger.info(
            "Searching keyword '%s', page %s",
            keyword,
            page + 1
        )

        request = youtube.search().list(
            part="snippet",
            q=keyword,
            type="video",
            maxResults=50,
            order="viewCount",
            pageToken=next_page_token
        )

        response = execute_with_retry(request)

        for item in response.get("items", []):

            videos.append({
                "video_id": item["id"]["videoId"],
                "channel_id": item["snippet"]["channelId"],
                "title": item["snippet"]["title"],
                "description": item["snippet"]["description"],
                "channel_title": item["snippet"]["channelTitle"],
                "published_at": item["snippet"]["publishedAt"],
                "keyword": keyword
            })

        next_page_token = response.get("nextPageToken")

        if not next_page_token:
            break

    logger.info(
        "Discovery completed. Retrieved %s videos for '%s'",
        len(videos),
        keyword
    )

    return videos