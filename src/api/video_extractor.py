from src.api.youtube_client import get_youtube_client


def get_video_statistics(video_ids: list[str]) -> list[dict]:

    youtube = get_youtube_client()

    results = []

    for i in range(0, len(video_ids), 50):

        batch = video_ids[i:i + 50]

        response = youtube.videos().list(
            part="snippet,statistics,contentDetails",
            id=",".join(batch)
        ).execute()

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

    return results