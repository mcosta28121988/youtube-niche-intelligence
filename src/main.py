import html

from src.api.youtube_client import get_youtube_client
from src.api.video_extractor import get_video_statistics


def main():

    youtube = get_youtube_client()

    response = youtube.search().list(
        part="snippet",
        q="history documentary",
        type="video",
        maxResults=5,
        order="viewCount"
    ).execute()

    video_ids = [
        item["id"]["videoId"]
        for item in response.get("items", [])
    ]

    videos = get_video_statistics(video_ids)

    for video in videos:

        print("-" * 50)

        print("Title:", html.unescape(video["title"]))
        print("Video ID:", video["video_id"])
        print("Channel ID:", video["channel_id"])
        print("Views:", video["views"])
        print("Likes:", video["likes"])
        print("Comments:", video["comments"])
        print("Duration:", video["duration"])
        print("Published:", video["published_at"])


if __name__ == "__main__":
    main()