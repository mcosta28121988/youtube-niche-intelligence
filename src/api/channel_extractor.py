import logging

from src.api.youtube_client import get_youtube_client
from src.api.retry import execute_with_retry

logger = logging.getLogger(__name__)


def get_channel_statistics(
    channel_ids: list[str]
) -> list[dict]:

    youtube = get_youtube_client()

    results = []

    unique_ids = list(dict.fromkeys(channel_ids))

    for i in range(0, len(unique_ids), 50):

        batch = unique_ids[i:i + 50]

        request = youtube.channels().list(
            part="snippet,statistics,contentDetails",
            id=",".join(batch)
        )

        response = execute_with_retry(request)

        for item in response.get("items", []):

            snippet = item["snippet"]
            stats = item.get("statistics", {})

            results.append({
                "channel_id": item["id"],
                "channel_name": snippet["title"],
                "published_at": snippet["publishedAt"],
                "subscribers": int(
                    stats.get("subscriberCount", 0)
                ),
                "total_views": int(
                    stats.get("viewCount", 0)
                ),
                "video_count": int(
                    stats.get("videoCount", 0)
                ),
                "uploads_playlist_id": item[
                    "contentDetails"
                ]["relatedPlaylists"]["uploads"]
            })

    logger.info(
        "Channel extraction completed: %s channels",
        len(results)
    )

    return results