import logging
import html

from src.utils.logging_config import setup_logging

from src.ingestion.discover_videos import search_videos
from src.api.video_extractor import get_video_statistics
from src.api.channel_extractor import get_channel_statistics


def main():

    setup_logging()

    logger = logging.getLogger("pipeline")

    keywords = [
        "history documentary",
        "space documentary",
        "ancient civilizations"
    ]

    try:

        all_videos = []

        # STEP 1: Discovery
        for keyword in keywords:

            videos = search_videos(
                keyword=keyword,
                max_pages=1
            )

            all_videos.extend(videos)

        # STEP 2: Remove duplicate video IDs
        unique_videos = {
            video["video_id"]: video
            for video in all_videos
        }

        video_ids = list(unique_videos.keys())

        # STEP 3: Video enrichment
        video_data = get_video_statistics(video_ids)

        # STEP 4: Channel extraction
        channel_ids = list({
            video["channel_id"]
            for video in video_data
        })

        channel_data = get_channel_statistics(channel_ids)

        # STEP 5: Summary
        logger.info("Pipeline completed successfully")

        logger.info("Videos discovered: %s", len(video_ids))

        logger.info("Videos enriched: %s", len(video_data))

        logger.info("Channels extracted: %s", len(channel_data))

        for video in video_data[:5]:

            print("-" * 50)
            print("Title:", html.unescape(video["title"]))
            print("Views:", video["views"])
            print("Likes:", video["likes"])
            print("Comments:", video["comments"])

    except Exception:

        logger.exception("Pipeline execution failed")
        raise


if __name__ == "__main__":
    main()