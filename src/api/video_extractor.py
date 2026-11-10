import logging

from src.api.youtube_client import get_youtube_client
from src.api.retry import execute_with_retry

logger = logging.getLogger(__name__)


def get_video_statistics(
    video_ids: list[str]
) -> list[dict]:

    youtube = get_youtube_client()

    results = []

    unique_ids = list(dict.fromkeys(video_ids))

    for i in range(0, len(unique_ids), 50):

        batch = unique_ids[i:i + 50]

        logger.info(
            "Extracting statistics for %s videos",
            len(batch)
        )

        request = youtube.videos().list(
            part="snippet,statistics,contentDetails",
            id=",".join(batch)
        )

        response = execute_with_retry(request)

        for item in response.get("items", []):

            snippet = item["snippet"]
            stats = item.get("statistics", {})
            details = item.get("contentDetails", {})

            results.append({
                "video_id": item["id"],
                "channel_id": snippet["channelId"],
                "title": snippet["title"],
                "category_id": snippet.get("categoryId"),
                "published_at": snippet["publishedAt"],
                "duration": details.get("duration"),
                "views": int(stats.get("viewCount", 0)),
                "likes": int(stats.get("likeCount", 0)),
                "comments": int(stats.get("commentCount", 0))
            })

    logger.info(
        "Video enrichment completed: %s videos",
        len(results)
    )

    return results