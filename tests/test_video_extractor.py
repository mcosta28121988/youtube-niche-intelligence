from unittest.mock import patch

from src.api.video_extractor import get_video_statistics


@patch("src.api.video_extractor.get_youtube_client")
def test_video_statistics(mock_client):

    youtube = mock_client.return_value

    youtube.videos.return_value.list.return_value.execute.return_value = {
        "items": [
            {
                "id": "video123",
                "snippet": {
                    "channelId": "channel123",
                    "title": "Test video",
                    "categoryId": "22",
                    "publishedAt": "2026-01-01T00:00:00Z"
                },
                "statistics": {
                    "viewCount": "1000",
                    "likeCount": "100",
                    "commentCount": "10"
                },
                "contentDetails": {
                    "duration": "PT10M"
                }
            }
        ]
    }

    result = get_video_statistics(["video123"])

    assert len(result) == 1

    assert result[0]["video_id"] == "video123"

    assert result[0]["views"] == 1000

    assert result[0]["likes"] == 100