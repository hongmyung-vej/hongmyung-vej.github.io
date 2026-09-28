import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
SEED_VIDEO = "tdcTMnGfUm0"
MAX_PAGES = 10  # 50개씩 총 500개 확인

# 띄어쓰기와 콜론 유무를 허용하고, 이름 뒤의 다른 글자는 구분합니다.
CREDIT = re.compile(
    r"영상\s*편집\s*[:：]?\s*이홍명(?![가-힣A-Za-z0-9_])"
)


def api(resource, **params):
    params["key"] = API_KEY
    url = (
        "https://www.googleapis.com/youtube/v3/"
        + resource
        + "?"
        + urlencode(params)
    )

    try:
        with urlopen(url, timeout=30) as response:
            return json.load(response)
    except HTTPError as error:
        # 키가 들어간 요청 주소는 로그에 출력하지 않습니다.
        raise RuntimeError(
            f"YouTube API 오류: HTTP {error.code}. "
            "API 활성화, 키 제한 및 할당량을 확인하세요."
        ) from None
    except URLError:
        raise RuntimeError("YouTube API 연결에 실패했습니다.") from None


def main():
    if not API_KEY:
        raise RuntimeError("YOUTUBE_API_KEY 비밀 설정이 없습니다.")

    # 예시 영상에서 실제 채널 ID를 확인합니다.
    seed_items = api(
        "videos",
        part="snippet",
        id=SEED_VIDEO,
    ).get("items", [])

    if not seed_items:
        raise RuntimeError(
            "예시 영상을 조회할 수 없습니다. 공개 상태와 영상 ID를 확인하세요."
        )

    channel_id = seed_items[0]["snippet"]["channelId"]

    channels = api(
        "channels",
        part="contentDetails",
        id=channel_id,
    ).get("items", [])

    if not channels:
        raise RuntimeError("채널 정보를 조회할 수 없습니다.")

    playlist_id = channels[0]["contentDetails"]["relatedPlaylists"]["uploads"]

    video_ids = [SEED_VIDEO]
    page_token = ""

    for _ in range(MAX_PAGES):
        result = api(
            "playlistItems",
            part="contentDetails",
            playlistId=playlist_id,
            maxResults=50,
            pageToken=page_token,
        )

        for item in result.get("items", []):
            video_ids.append(item["contentDetails"]["videoId"])

        page_token = result.get("nextPageToken", "")
        if not page_token:
            break

    video_ids = list(dict.fromkeys(video_ids))
    matches = []

    # 영상의 현재 설명과 공개 상태를 다시 확인합니다.
    for start in range(0, len(video_ids), 50):
        result = api(
            "videos",
            part="snippet,status",
            id=",".join(video_ids[start:start + 50]),
        )

        for video in result.get("items", []):
            snippet = video["snippet"]
            status = video.get("status", {})

            if snippet["channelId"] != channel_id:
                continue

            if status.get("privacyStatus") != "public":
                continue

            if not CREDIT.search(snippet.get("description", "")):
                continue

            thumbnails = snippet.get("thumbnails", {})
            thumbnail = next(
                (
                    thumbnails[size]["url"]
                    for size in ("high", "medium", "default")
                    if size in thumbnails
                ),
                "",
            )

            matches.append({
                "id": video["id"],
                "title": snippet["title"],
                "publishedAt": snippet["publishedAt"],
                "thumbnail": thumbnail,
                "url": (
                    "https://www.youtube.com/watch?v=" + video["id"]
                ),
            })

    matches.sort(key=lambda item: item["publishedAt"], reverse=True)

    # 홈페이지에 필요한 파일만 배포 폴더로 복사합니다.
    site = Path("_site")
    if site.exists():
        shutil.rmtree(site)
    site.mkdir()

    for path in Path(".").iterdir():
        if path.is_file() and path.suffix.lower() in {
            ".html", ".css", ".js", ".jpg", ".jpeg",
            ".png", ".webp", ".gif", ".svg", ".ico"
        }:
            shutil.copy2(path, site / path.name)

    (site / "videos.json").write_text(
        json.dumps(
            {
                "updatedAt": datetime.now(timezone.utc).isoformat(),
                "videos": matches,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"{len(video_ids)}개 확인, 조건에 맞는 영상 {len(matches)}개")


if __name__ == "__main__":
    main()
