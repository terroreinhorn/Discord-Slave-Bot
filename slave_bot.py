# =====================================================================
# SLAVE DISCORD MUSIC BOT — VERSION: v2.2.0
# =====================================================================
BOT_VERSION = "v2.2.0"

import asyncio
import base64
from collections import deque
import difflib
import glob
import html as html_lib
import io
import json
import os
import random
import re
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp

# =====================================================================
# CONFIGURATION — PASTE YOUR DISCORD BOT TOKEN ON LINE 33 BELOW
# =====================================================================
DISCORD_TOKEN = "YOUR_DISCORD_BOT_TOKEN_HERE"

# Optional Spotify Developer credentials (leave empty "" to use automatic zero-config mode)
SPOTIFY_CLIENT_ID = ""
SPOTIFY_CLIENT_SECRET = ""

# Persistent JSON file for saved playlists, personal likes, and crash-recovery sessions
DATA_FILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "slave_data.json")

# Temporary directory for fallback audio caching if a direct stream returns HTTP 403
TEMP_CACHE_DIR = os.path.join(tempfile.gettempdir(), "slave_audio_cache")
os.makedirs(TEMP_CACHE_DIR, exist_ok=True)

# Fast TTL cache for live slash-command autocomplete and instant search resolution
_AUTOCOMPLETE_CACHE: dict[str, tuple[float, list[dict]]] = {}
_AUTOCOMPLETE_CACHE_TTL = 180.0  # 3 minutes

# Options for extracting dedicated playlist URLs (/playlist?list=...)
YTDL_FLAT_OPTS = {
    "extract_flat": "in_playlist",
    "playlistend": 100,
    "quiet": True,
    "no_warnings": True,
    "ignoreerrors": True,
    "default_search": "ytsearch",
}

# Options for extracting a single song URL (strictly blocks playlists/mixes)
YTDL_SINGLE_OPTS = {
    "extract_flat": False,
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "ignoreerrors": True,
}

# Options for fallback yt-dlp searches
YTDL_SEARCH_OPTS = {
    "extract_flat": "in_playlist",
    "playlistend": 10,
    "quiet": True,
    "no_warnings": True,
    "ignoreerrors": True,
    "default_search": "ytsearch",
}

# Primary stream extraction options:
# - check_formats="selected" makes yt-dlp test the googlevideo URL for HTTP 403 before returning it
# - js_runtimes enables node/deno if installed on Zorin OS for 2026 YouTube challenges
YTDL_STREAM_OPTS = {
    "format": "bestaudio[ext=m4a]/bestaudio[acodec=opus]/bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "check_formats": "selected",
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
    "js_runtimes": {"deno": {}, "node": {}},
}

# Fallback stream extraction options using alternative YouTube clients if the default client 403s
YTDL_FALLBACK_STREAM_OPTS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "check_formats": "selected",
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
    "js_runtimes": {"deno": {}, "node": {}},
    "extractor_args": {
        "youtube": {
            "player_client": ["web_embedded", "ios", "mweb", "tv"],
        }
    },
}

FFMPEG_HTTP_RECONNECT_OPTS = (
    "-reconnect 1 -reconnect_streamed 1 -reconnect_on_network_error 1 "
    "-reconnect_on_http_error 4xx,5xx -reconnect_delay_max 5 "
    "-thread_queue_size 4096 -nostdin"
)

ytdl_flat = yt_dlp.YoutubeDL(YTDL_FLAT_OPTS)
ytdl_single = yt_dlp.YoutubeDL(YTDL_SINGLE_OPTS)
ytdl_search = yt_dlp.YoutubeDL(YTDL_SEARCH_OPTS)
ytdl_stream = yt_dlp.YoutubeDL(YTDL_STREAM_OPTS)
ytdl_fallback_stream = yt_dlp.YoutubeDL(YTDL_FALLBACK_STREAM_OPTS)

SPOTIFY_URL_RE = re.compile(
    r"open\.spotify\.com/(?:intl-[a-zA-Z-]+/)?(?:embed/)?(track|playlist|album|artist)/([A-Za-z0-9]{22})"
)
_spotify_token_cache: dict[str, float | str] = {"token": "", "expires_at": 0.0}
_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Noise suffixes commonly added to YouTube video titles and channel names
_CHANNEL_NOISE_RE = re.compile(
    r"(?:\s*[-–—]\s*Topic|\s*VEVO|\s+Official(?:\s+Channel|\s+Artist\s+Channel)?|\s+Music)$",
    re.IGNORECASE,
)
_TITLE_NOISE_RE = re.compile(
    r"\s*[\(\[]"
    r"(?:official\s+(?:music\s+)?video|official\s+audio|official\s+lyric\s+video|"
    r"official\s+visualizer|lyric\s+video|lyrics|audio|visualizer|hd|hq|4k|"
    r"full\s+audio|music\s+video)"
    r"[\)\]]",
    re.IGNORECASE,
)


# =====================================================================
# PERSISTENT DATA STORAGE (PLAYLISTS, LIKES & CRASH-RECOVERY SESSIONS)
# =====================================================================
def _load_persistent_data() -> dict:
    """Loads saved server playlists, user liked tracks, and active sessions from slave_data.json."""
    if not os.path.exists(DATA_FILE_PATH):
        return {"playlists": {}, "likes": {}, "sessions": {}}
    try:
        with open(DATA_FILE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return {"playlists": {}, "likes": {}, "sessions": {}}
            data.setdefault("playlists", {})
            data.setdefault("likes", {})
            data.setdefault("sessions", {})
            return data
    except Exception as e:
        print(f"[STORAGE WARN] Could not load {DATA_FILE_PATH}: {e}")
        return {"playlists": {}, "likes": {}, "sessions": {}}


def _save_persistent_data(data: dict) -> None:
    """Saves server playlists, user liked tracks, and active sessions to slave_data.json."""
    try:
        with open(DATA_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[STORAGE WARN] Could not save {DATA_FILE_PATH}: {e}")


# =====================================================================
# COMPOSER / ARTIST & DURATION FORMATTING HELPERS
# =====================================================================
def clean_artist_name(raw_artist: str | None) -> str:
    """Cleans channel/uploader names like 'Daft Punk - Topic' or 'DaftPunkVEVO' into 'Daft Punk'."""
    if not raw_artist:
        return ""
    artist = html_lib.unescape(str(raw_artist)).replace("\u00a0", " ").strip()
    artist = _CHANNEL_NOISE_RE.sub("", artist).strip()
    if artist.lower() in ("unknown", "unknown artist", "youtube", "various artists", "na", "none"):
        return ""
    return artist


def clean_song_title(raw_title: str | None) -> str:
    """Cleans noisy tags like '(Official Video)' from a track title."""
    if not raw_title:
        return "Unknown Track"
    title = html_lib.unescape(str(raw_title)).replace("\u00a0", " ").strip()
    cleaned = _TITLE_NOISE_RE.sub("", title).strip()
    return cleaned or title


def format_artist_and_title(
    raw_title: str | None,
    raw_artist: str | None = None,
) -> tuple[str, str, str]:
    """
    Ensures every song is displayed as 'Composer - Song Title' (e.g. 'Daft Punk - Revolution 909').
    Returns (full_display_title, composer_name, song_title).
    """
    title = clean_song_title(raw_title)
    artist = clean_artist_name(raw_artist)

    for sep in (" - ", " – ", " — "):
        if sep in title:
            left, right = title.split(sep, 1)
            left_clean = clean_artist_name(left)
            right_clean = clean_song_title(right)
            if left_clean and right_clean:
                if not artist or artist.lower() in left_clean.lower() or left_clean.lower() in artist.lower():
                    return f"{left_clean} - {right_clean}", left_clean, right_clean

    if artist:
        if title.lower().startswith(artist.lower() + " - "):
            song_part = title[len(artist) + 3 :].strip()
            return f"{artist} - {song_part}", artist, song_part
        if artist.lower() not in title.lower():
            return f"{artist} - {title}", artist, title

    return title, artist, title


def extract_entry_artist(entry: dict) -> str:
    """Extracts the best composer/artist string from a yt-dlp entry dict."""
    if not entry:
        return ""
    for key in ("artist", "creator", "composer"):
        val = entry.get(key)
        if isinstance(val, str) and val.strip():
            return clean_artist_name(val)
    artists_list = entry.get("artists")
    if isinstance(artists_list, list) and artists_list:
        names = [
            clean_artist_name(a.get("name") if isinstance(a, dict) else str(a))
            for a in artists_list
        ]
        names = [n for n in names if n]
        if names:
            return ", ".join(names)
    for key in ("uploader", "channel"):
        val = entry.get(key)
        if isinstance(val, str) and val.strip():
            return clean_artist_name(val)
    return ""


def parse_duration_str(dur_str: str | int | float | None) -> int:
    """Converts a duration like '5:26', '1:02:15', or 326 into integer seconds."""
    if dur_str is None:
        return 0
    if isinstance(dur_str, (int, float)):
        return max(0, int(dur_str))
    s = str(dur_str).strip()
    if s.isdigit():
        return int(s)
    parts = s.split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except ValueError:
        pass
    return 0


def format_seconds(seconds: int | float | None) -> str:
    """Formats seconds into MM:SS or HH:MM:SS."""
    if not seconds or seconds <= 0:
        return "0:00"
    total = int(seconds)
    hrs, rem = divmod(total, 3600)
    mins, secs = divmod(rem, 60)
    if hrs > 0:
        return f"{hrs}:{mins:02d}:{secs:02d}"
    return f"{mins}:{secs:02d}"


def build_progress_bar(elapsed: float, duration: int, length: int = 14) -> str:
    """Builds a visual progress bar like '01:24 ━━━●────────── 05:26'."""
    elapsed = max(0.0, elapsed)
    if duration <= 0:
        return f"`{format_seconds(elapsed)} ━━━●────────── LIVE`"
    ratio = min(1.0, max(0.0, elapsed / float(duration)))
    dot_pos = int(round(ratio * (length - 1)))
    bar = "━" * dot_pos + "●" + "─" * (length - 1 - dot_pos)
    return f"`{format_seconds(elapsed)} {bar} {format_seconds(duration)}`"


def format_source_badge(source_label: str, compact: bool = False) -> str:
    """Returns a visual badge for YouTube Music, Spotify, or YouTube."""
    if source_label == "YouTube Music":
        return "🎵 YT Music" if compact else "🎵 YouTube Music"
    if source_label == "Spotify":
        return "🟢 Spotify"
    return "▶️ YouTube"


def format_source_icon(source_label: str) -> str:
    """Returns a compact icon representing the track source."""
    if source_label == "YouTube Music":
        return "🎵"
    if source_label == "Spotify":
        return "🟢"
    return "▶️"


# =====================================================================
# NETWORKING, INNERTUBE (YT MUSIC & YOUTUBE), SPOTIFY & CATALOG SEARCH
# =====================================================================
def _http_get_text(url: str, headers: dict | None = None, timeout: float = 10.0) -> str:
    """Performs an HTTP GET request and returns the UTF-8 response body."""
    merged_headers = dict(_HTTP_HEADERS)
    if headers:
        merged_headers.update(headers)
    req = urllib.request.Request(url, headers=merged_headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _http_post_json(url: str, payload: dict, headers: dict | None = None, timeout: float = 8.0) -> dict:
    """Performs an HTTP POST request with a JSON payload and returns parsed JSON."""
    merged_headers = dict(_HTTP_HEADERS)
    merged_headers["Content-Type"] = "application/json"
    if headers:
        merged_headers.update(headers)
    raw_body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=raw_body, headers=merged_headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def _walk_json_key(obj, target_key: str):
    """Recursively yields all values matching `target_key` inside a nested JSON structure."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == target_key:
                yield v
            yield from _walk_json_key(v, target_key)
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk_json_key(item, target_key)


def _search_ytmusic_innertube_sync(query: str, limit: int = 8) -> list[dict]:
    """
    Directly queries YouTube Music's InnerTube API ('WEB_REMIX' client) for Songs.
    Uses an in-memory TTL cache so live autocomplete and subsequent play commands are instant.
    """
    cache_key = f"{query.strip().lower()}::{limit}"
    now = time.monotonic()
    cached = _AUTOCOMPLETE_CACHE.get(cache_key)
    if cached and (now - cached[0]) < _AUTOCOMPLETE_CACHE_TTL:
        return [dict(item) for item in cached[1]]

    url = "https://music.youtube.com/youtubei/v1/search?prettyPrint=false"
    headers = {
        "Origin": "https://music.youtube.com",
        "Referer": "https://music.youtube.com/",
    }
    results: list[dict] = []
    seen_ids: set[str] = set()

    for params in ("EgWKAQIIAWoKEAkQBRAKEAMQBA==", None):
        payload: dict = {
            "context": {
                "client": {
                    "clientName": "WEB_REMIX",
                    "clientVersion": "1.20240101.01.00",
                    "hl": "en",
                    "gl": "US",
                }
            },
            "query": query,
        }
        if params:
            payload["params"] = params

        try:
            data = _http_post_json(url, payload, headers=headers, timeout=6.0)
        except Exception as e:
            print(f"[YTM INNERTUBE WARN] Request failed: {e}")
            continue

        for item in _walk_json_key(data, "musicResponsiveListItemRenderer"):
            if not isinstance(item, dict):
                continue

            video_id = item.get("playlistItemData", {}).get("videoId")
            if not video_id:
                for we in _walk_json_key(item, "watchEndpoint"):
                    if isinstance(we, dict) and we.get("videoId"):
                        video_id = we["videoId"]
                        break
            if not video_id or len(str(video_id)) != 11 or video_id in seen_ids:
                continue

            flex_cols = item.get("flexColumns", [])
            if not flex_cols:
                continue

            col0_runs = (
                flex_cols[0]
                .get("musicResponsiveListItemFlexColumnRenderer", {})
                .get("text", {})
                .get("runs", [])
            )
            raw_title = "".join(r.get("text", "") for r in col0_runs).strip()
            if not raw_title:
                continue

            artists: list[str] = []
            duration_sec = 0
            if len(flex_cols) > 1:
                col1_runs = (
                    flex_cols[1]
                    .get("musicResponsiveListItemFlexColumnRenderer", {})
                    .get("text", {})
                    .get("runs", [])
                )
                segments: list[str] = []
                current_seg: list[str] = []
                for r in col1_runs:
                    txt = r.get("text", "")
                    if txt.strip() == "•":
                        if current_seg:
                            segments.append("".join(current_seg).strip())
                            current_seg = []
                    else:
                        current_seg.append(txt)
                if current_seg:
                    segments.append("".join(current_seg).strip())

                if segments and re.match(r"^\d+:\d{2}(?::\d{2})?$", segments[-1]):
                    duration_sec = parse_duration_str(segments.pop())
                if segments and segments[0].lower() in (
                    "song",
                    "video",
                    "episode",
                    "single",
                    "track",
                ):
                    segments.pop(0)
                if segments:
                    artists.append(segments[0])

            artist_str = clean_artist_name(", ".join(artists))
            full_title, clean_art, clean_tr = format_artist_and_title(raw_title, artist_str)

            thumbs = (
                item.get("thumbnail", {})
                .get("musicThumbnailRenderer", {})
                .get("thumbnails", [])
            )
            thumb_url = thumbs[-1].get("url", "") if thumbs else f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"

            seen_ids.add(video_id)
            results.append(
                {
                    "url": f"https://music.youtube.com/watch?v={video_id}",
                    "video_id": video_id,
                    "title": full_title,
                    "artist": clean_art,
                    "track_name": clean_tr,
                    "duration": duration_sec,
                    "thumbnail": thumb_url,
                    "source": "YouTube Music",
                }
            )
            if len(results) >= limit:
                break

        if len(results) >= 3:
            break

    if results:
        _AUTOCOMPLETE_CACHE[cache_key] = (now, [dict(r) for r in results])
        # Also prime exact title lookup so selecting an autocomplete option resolves in 0ms
        for r in results:
            title_key = f"{r['title'].lower()}::6"
            if title_key not in _AUTOCOMPLETE_CACHE:
                _AUTOCOMPLETE_CACHE[title_key] = (now, [dict(r)])

    return results


def _search_youtube_innertube_sync(query: str, limit: int = 8) -> list[dict]:
    """
    Directly queries standard YouTube's InnerTube API ('WEB' client) for videos.
    Formats every result with its channel/composer name ('Composer - Title').
    """
    url = "https://www.youtube.com/youtubei/v1/search?prettyPrint=false"
    payload = {
        "context": {
            "client": {
                "clientName": "WEB",
                "clientVersion": "2.20240101.00.00",
                "hl": "en",
                "gl": "US",
            }
        },
        "query": query,
    }
    headers = {
        "Origin": "https://www.youtube.com",
        "Referer": "https://www.youtube.com/",
    }
    results: list[dict] = []
    seen_ids: set[str] = set()

    try:
        data = _http_post_json(url, payload, headers=headers, timeout=7.0)
    except Exception as e:
        print(f"[YT INNERTUBE WARN] Request failed: {e}")
        return []

    for vr in _walk_json_key(data, "videoRenderer"):
        if not isinstance(vr, dict):
            continue
        video_id = vr.get("videoId")
        if not video_id or len(str(video_id)) != 11 or video_id in seen_ids:
            continue

        title_runs = vr.get("title", {}).get("runs", [])
        raw_title = "".join(r.get("text", "") for r in title_runs).strip()
        if not raw_title:
            raw_title = vr.get("title", {}).get("simpleText", "").strip()
        if not raw_title:
            continue

        owner_runs = (
            vr.get("ownerText", {}).get("runs")
            or vr.get("longBylineText", {}).get("runs")
            or vr.get("shortBylineText", {}).get("runs")
            or []
        )
        raw_uploader = "".join(r.get("text", "") for r in owner_runs).strip()

        dur_text = vr.get("lengthText", {}).get("simpleText", "")
        duration_sec = parse_duration_str(dur_text)

        thumbs = vr.get("thumbnail", {}).get("thumbnails", [])
        thumb_url = thumbs[-1].get("url", "") if thumbs else f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"

        full_title, clean_art, clean_tr = format_artist_and_title(raw_title, raw_uploader)
        seen_ids.add(video_id)
        results.append(
            {
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "video_id": video_id,
                "title": full_title,
                "artist": clean_art,
                "track_name": clean_tr,
                "duration": duration_sec,
                "thumbnail": thumb_url,
                "source": "YouTube",
            }
        )
        if len(results) >= limit:
            break

    return results


def _fetch_ytmusic_radio_sync(video_id: str) -> list[dict]:
    """Fetches related radio tracks for Autoplay mode from YouTube Music's 'next' endpoint."""
    if not video_id or len(video_id) != 11:
        return []
    url = "https://music.youtube.com/youtubei/v1/next?prettyPrint=false"
    payload = {
        "context": {
            "client": {
                "clientName": "WEB_REMIX",
                "clientVersion": "1.20240101.01.00",
                "hl": "en",
                "gl": "US",
            }
        },
        "videoId": video_id,
        "playlistId": f"RDAMVM{video_id}",
        "isAudioOnly": True,
    }
    results: list[dict] = []
    try:
        data = _http_post_json(url, payload, headers={"Origin": "https://music.youtube.com"}, timeout=7.0)
        for pvr in _walk_json_key(data, "playlistPanelVideoRenderer"):
            if not isinstance(pvr, dict):
                continue
            vid = pvr.get("videoId")
            if not vid or vid == video_id or len(str(vid)) != 11:
                continue
            raw_title = "".join(r.get("text", "") for r in pvr.get("title", {}).get("runs", [])).strip()
            byline_runs = pvr.get("longBylineText", {}).get("runs", [])
            artist_parts = []
            for r in byline_runs:
                t = r.get("text", "").strip()
                if t == "•":
                    break
                artist_parts.append(t)
            raw_artist = "".join(artist_parts).strip()
            dur_text = "".join(r.get("text", "") for r in pvr.get("lengthText", {}).get("runs", [])).strip()
            duration_sec = parse_duration_str(dur_text)
            thumbs = pvr.get("thumbnail", {}).get("thumbnails", [])
            thumb_url = thumbs[-1].get("url", "") if thumbs else f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
            full_title, clean_art, clean_tr = format_artist_and_title(raw_title, raw_artist)
            results.append(
                {
                    "url": f"https://music.youtube.com/watch?v={vid}",
                    "video_id": vid,
                    "title": full_title,
                    "artist": clean_art,
                    "track_name": clean_tr,
                    "duration": duration_sec,
                    "thumbnail": thumb_url,
                    "source": "YouTube Music",
                }
            )
            if len(results) >= 10:
                break
    except Exception as e:
        print(f"[AUTOPLAY WARN] Radio lookup failed: {e}")
    return results


def _get_spotify_bearer_token() -> str | None:
    """Gets an official Spotify API token if SPOTIFY_CLIENT_ID/SECRET are configured."""
    now = time.time()
    if _spotify_token_cache["token"] and now < float(_spotify_token_cache["expires_at"]) - 30:
        return str(_spotify_token_cache["token"])

    if SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET:
        try:
            creds = f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode("utf-8")
            b64_creds = base64.b64encode(creds).decode("ascii")
            body = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode("utf-8")
            req = urllib.request.Request(
                "https://accounts.spotify.com/api/token",
                data=body,
                headers={
                    "Authorization": f"Basic {b64_creds}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=8.0) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            token = payload.get("access_token")
            if token:
                _spotify_token_cache["token"] = token
                _spotify_token_cache["expires_at"] = now + int(payload.get("expires_in", 3600))
                return token
        except Exception as e:
            print(f"[SPOTIFY WARN] Failed to fetch official client_credentials token: {e}")

    return None


def _extract_spotify_url_sync(raw_url: str) -> list[dict]:
    """
    Extracts a single song or a full playlist/album/artist top-tracks list from a
    Spotify URL without requiring API keys, always formatted as 'Composer - Song Title'.
    """
    target_url = raw_url.strip()

    if "spotify.link" in target_url or "spoti.fi" in target_url:
        try:
            req = urllib.request.Request(target_url, headers=_HTTP_HEADERS)
            with urllib.request.urlopen(req, timeout=8.0) as resp:
                target_url = resp.geturl()
        except Exception as e:
            print(f"[SPOTIFY WARN] Could not resolve short link {target_url}: {e}")

    match = SPOTIFY_URL_RE.search(target_url)
    if not match:
        return []

    resource_type, resource_id = match.group(1).lower(), match.group(2)
    embed_url = f"https://open.spotify.com/embed/{resource_type}/{resource_id}"
    print(f"[SPOTIFY] Extracting {resource_type.upper()} ({resource_id}) via {embed_url}")

    try:
        embed_html = _http_get_text(embed_url)
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', embed_html, re.DOTALL)
        if m:
            data = json.loads(m.group(1))
            entity = (
                data.get("props", {})
                .get("pageProps", {})
                .get("state", {})
                .get("data", {})
                .get("entity", {})
            )
            if entity:
                images = entity.get("visualIdentity", {}).get("image", [])
                entity_thumb = images[-1].get("url", "") if images else ""

                if resource_type == "track":
                    raw_title = (entity.get("title") or entity.get("name") or "").strip()
                    artists = [
                        a.get("name", "").strip()
                        for a in (entity.get("artists") or [])
                        if isinstance(a, dict) and a.get("name")
                    ]
                    artist_str = ", ".join(artists) or (
                        entity.get("subtitle") or ""
                    ).replace("\u00a0", " ").strip()
                    duration_sec = int(entity.get("duration", 0)) // 1000
                    if raw_title:
                        full_title, clean_art, clean_tr = format_artist_and_title(raw_title, artist_str)
                        canonical_url = f"https://open.spotify.com/track/{resource_id}"
                        return [
                            {
                                "url": canonical_url,
                                "title": full_title,
                                "artist": clean_art,
                                "track_name": clean_tr,
                                "duration": duration_sec,
                                "thumbnail": entity_thumb,
                                "search_query": full_title,
                                "source": "Spotify",
                            }
                        ]
                else:
                    track_list = entity.get("trackList") or []
                    results = []
                    for item in track_list[:100]:
                        t_title = (item.get("title") or item.get("name") or "").strip()
                        t_artist = (item.get("subtitle") or "").replace("\u00a0", " ").strip()
                        if not t_title:
                            continue
                        full_title, clean_art, clean_tr = format_artist_and_title(t_title, t_artist)
                        dur_sec = int(item.get("duration", 0)) // 1000
                        uri = item.get("uri") or ""
                        if uri.startswith("spotify:track:"):
                            tid = uri.split(":")[-1]
                            t_url = f"https://open.spotify.com/track/{tid}"
                        else:
                            t_url = f"https://open.spotify.com/{resource_type}/{resource_id}"
                        results.append(
                            {
                                "url": t_url,
                                "title": full_title,
                                "artist": clean_art,
                                "track_name": clean_tr,
                                "duration": dur_sec,
                                "thumbnail": entity_thumb,
                                "search_query": full_title,
                                "source": "Spotify",
                            }
                        )
                    if results:
                        return results
    except Exception as e:
        print(f"[SPOTIFY WARN] Embed extraction failed for {embed_url}: {e}")

    if resource_type == "track":
        canonical_url = f"https://open.spotify.com/track/{resource_id}"
        try:
            page_html = _http_get_text(canonical_url)
            og_title_m = re.search(
                r'<meta\s+(?:property|name)="og:title"\s+content="([^"]+)"', page_html
            )
            artist_m = re.search(
                r'<meta\s+(?:property|name)="music:musician_description"\s+content="([^"]+)"',
                page_html,
            )
            img_m = re.search(
                r'<meta\s+(?:property|name)="og:image"\s+content="([^"]+)"', page_html
            )
            dur_m = re.search(
                r'<meta\s+(?:property|name)="music:duration"\s+content="(\d+)"', page_html
            )
            if og_title_m:
                t_title = html_lib.unescape(og_title_m.group(1)).strip()
                t_artist = html_lib.unescape(artist_m.group(1)).strip() if artist_m else ""
                full_title, clean_art, clean_tr = format_artist_and_title(t_title, t_artist)
                return [
                    {
                        "url": canonical_url,
                        "title": full_title,
                        "artist": clean_art,
                        "track_name": clean_tr,
                        "duration": int(dur_m.group(1)) if dur_m else 0,
                        "thumbnail": img_m.group(1) if img_m else "",
                        "search_query": full_title,
                        "source": "Spotify",
                    }
                ]
        except Exception as e:
            print(f"[SPOTIFY WARN] Static HTML fallback failed: {e}")

    return []


def _search_spotify_and_catalog_sync(query: str, limit: int = 6) -> list[dict]:
    """
    Step 2 in the search chain (Spotify / Music Catalog):
    Uses official Spotify API if configured, and falls back to Apple iTunes
    zero-config catalog search to resolve canonical 'Composer - Song Title' tracks.
    """
    results: list[dict] = []

    token = _get_spotify_bearer_token()
    if token:
        api_url = (
            f"https://api.spotify.com/v1/search?q={urllib.parse.quote_plus(query)}&type=track&limit={limit}"
        )
        try:
            raw = _http_get_text(api_url, headers={"Authorization": f"Bearer {token}"}, timeout=6.0)
            data = json.loads(raw)
            for item in data.get("tracks", {}).get("items", []):
                if not item or item.get("type") != "track":
                    continue
                track_id = item.get("id")
                raw_title = (item.get("name") or "").strip()
                artists = [
                    a.get("name", "").strip()
                    for a in (item.get("artists") or [])
                    if isinstance(a, dict) and a.get("name")
                ]
                artist_str = ", ".join(artists)
                images = item.get("album", {}).get("images", [])
                thumb = images[0].get("url", "") if images else ""
                dur_sec = int(item.get("duration_ms", 0)) // 1000
                if track_id and raw_title:
                    full_title, clean_art, clean_tr = format_artist_and_title(raw_title, artist_str)
                    results.append(
                        {
                            "url": f"https://open.spotify.com/track/{track_id}",
                            "title": full_title,
                            "artist": clean_art,
                            "track_name": clean_tr,
                            "duration": dur_sec,
                            "thumbnail": thumb,
                            "search_query": full_title,
                            "source": "Spotify",
                        }
                    )
            if results:
                return results
        except Exception as e:
            print(f"[SPOTIFY API WARN] Catalog search error: {e}")

    itunes_url = (
        f"https://itunes.apple.com/search?term={urllib.parse.quote_plus(query)}"
        f"&media=music&entity=song&limit={limit}"
    )
    try:
        raw = _http_get_text(itunes_url, timeout=6.0)
        data = json.loads(raw)
        for item in data.get("results", []):
            raw_title = (item.get("trackName") or "").strip()
            raw_artist = (item.get("artistName") or "").strip()
            if not raw_title:
                continue
            full_title, clean_art, clean_tr = format_artist_and_title(raw_title, raw_artist)
            dur_sec = int(item.get("trackTimeMillis", 0)) // 1000
            thumb = (item.get("artworkUrl100") or "").replace("100x100bb", "600x600bb")
            track_view_url = item.get("trackViewUrl") or f"https://music.youtube.com/search?q={urllib.parse.quote_plus(full_title)}"
            results.append(
                {
                    "url": track_view_url,
                    "title": full_title,
                    "artist": clean_art,
                    "track_name": clean_tr,
                    "duration": dur_sec,
                    "thumbnail": thumb,
                    "search_query": full_title,
                    "source": "Spotify",
                }
            )
    except Exception as e:
        print(f"[CATALOG WARN] iTunes catalog lookup failed: {e}")

    return results


# =====================================================================
# SMART SEARCH SCORING & "DID YOU MEAN?" CANDIDATE SUGGESTIONS
# =====================================================================
_STOPWORDS = {"the", "a", "an", "by", "of", "in", "on", "to", "for", "and", "feat", "ft", "official", "audio", "song"}


def _normalize_for_match(text: str) -> str:
    """Lowercases and removes non-alphanumeric punctuation for fuzzy matching."""
    text = html_lib.unescape(text).lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def compute_match_score(query: str, candidate: dict) -> float:
    """
    Computes a confidence score (0.0 to 1.0) measuring how well `candidate`
    matches the user's `query`.
    """
    q_norm = _normalize_for_match(query)
    c_title_norm = _normalize_for_match(candidate.get("title", ""))
    c_track_norm = _normalize_for_match(candidate.get("track_name", ""))
    if not q_norm or not c_title_norm:
        return 0.0

    if q_norm in c_title_norm or c_track_norm == q_norm:
        return 0.98

    q_tokens = [t for t in q_norm.split() if len(t) > 1 and t not in _STOPWORDS]
    if not q_tokens:
        q_tokens = q_norm.split()

    c_tokens = set(c_title_norm.split())

    matched_tokens = 0.0
    for qt in q_tokens:
        if qt in c_tokens or qt in c_title_norm:
            matched_tokens += 1.0
        else:
            best_tok_sim = max(
                (difflib.SequenceMatcher(None, qt, ct).ratio() for ct in c_tokens),
                default=0.0,
            )
            if best_tok_sim >= 0.80:
                matched_tokens += 0.85
            elif best_tok_sim >= 0.70:
                matched_tokens += 0.5

    token_ratio = matched_tokens / max(1, len(q_tokens))
    seq_ratio = difflib.SequenceMatcher(None, q_norm, c_title_norm).ratio()
    track_seq_ratio = difflib.SequenceMatcher(None, q_norm, c_track_norm).ratio() if c_track_norm else 0.0

    return max(token_ratio * 0.75 + max(seq_ratio, track_seq_ratio) * 0.25, seq_ratio, track_seq_ratio)


def _parse_single_track_entry(entry: dict, source_label: str) -> dict | None:
    """Validates and formats a single playable track entry from yt-dlp as 'Composer - Song'."""
    if not entry:
        return None
    if entry.get("_type") == "playlist" or entry.get("ie_key") in ("YoutubeTab", "YoutubeMusicSearchURL"):
        return None

    video_id = entry.get("id") or ""
    raw_url = entry.get("url") or entry.get("webpage_url") or ""

    if not video_id and "watch?v=" in raw_url:
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(raw_url).query)
        if "v" in qs and qs["v"]:
            video_id = qs["v"][0]

    if video_id.startswith(("UC", "PL", "VL", "OL", "MPREb_")):
        return None

    if len(video_id) == 11:
        if source_label == "YouTube Music":
            url = f"https://music.youtube.com/watch?v={video_id}"
        else:
            url = f"https://www.youtube.com/watch?v={video_id}"
    elif "watch?v=" in raw_url:
        url = raw_url
    else:
        return None

    raw_title = entry.get("track") or entry.get("title") or "Unknown Track"
    raw_artist = extract_entry_artist(entry)
    full_title, clean_art, clean_tr = format_artist_and_title(raw_title, raw_artist)
    duration_sec = parse_duration_str(entry.get("duration"))
    thumb = entry.get("thumbnail") or (f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg" if len(video_id) == 11 else "")

    return {
        "url": url,
        "video_id": video_id if len(video_id) == 11 else "",
        "title": full_title,
        "artist": clean_art,
        "track_name": clean_tr,
        "duration": duration_sec,
        "thumbnail": thumb,
        "source": source_label,
    }


def _normalize_youtube_url(raw_url: str) -> tuple[str, bool, str]:
    """
    Cleans a YouTube or YouTube Music URL so that copying a song link containing
    '&list=RD...' (YouTube Mix/Radio) or '&list=PL...' plays ONLY that single song.
    """
    parsed = urllib.parse.urlparse(raw_url)
    host = parsed.netloc.lower()
    source_label = "YouTube Music" if "music.youtube.com" in host else "YouTube"
    qs = urllib.parse.parse_qs(parsed.query)

    video_id = None
    if "youtu.be" in host:
        video_id = parsed.path.lstrip("/").split("/")[0] or None
    elif "v" in qs and qs["v"]:
        video_id = qs["v"][0]

    if video_id:
        if source_label == "YouTube Music":
            clean_url = f"https://music.youtube.com/watch?v={video_id}"
        else:
            clean_url = f"https://www.youtube.com/watch?v={video_id}"
        return clean_url, False, source_label

    is_playlist = "playlist" in parsed.path.lower() and "list" in qs
    return raw_url, is_playlist, source_label


async def search_tracks_with_suggestions(query: str) -> tuple[list[dict], list[dict]]:
    """
    Searches for a query across:
      1. YouTube Music
      2. Spotify / Music Catalog
      3. Basic YouTube
    Returns `(exact_matches, candidate_suggestions)`:
      - If a confident match is found, `exact_matches` has `[best_track]` and `candidate_suggestions` has alternatives.
      - If no confident match is found, `exact_matches` is `[]` and `candidate_suggestions` has up to 5 songs it could be.
    """
    cleaned = query.strip().strip('"').strip("'").strip("“”‘’").strip()
    loop = asyncio.get_running_loop()

    candidates: list[dict] = []
    seen_titles: set[str] = set()

    def _add_candidates(items: list[dict]):
        for it in items:
            norm_key = _normalize_for_match(it.get("title", ""))
            if norm_key and norm_key not in seen_titles:
                seen_titles.add(norm_key)
                it["match_score"] = compute_match_score(cleaned, it)
                candidates.append(it)

    # 1. Search Priority #1: YouTube Music (Direct InnerTube API + cache)
    print(f"[SEARCH 1/3] Searching YouTube Music for: '{cleaned}'")
    ytm_results = await loop.run_in_executor(
        None, lambda: _search_ytmusic_innertube_sync(cleaned, limit=6)
    )
    _add_candidates(ytm_results)

    if ytm_results and ytm_results[0].get("match_score", 0.0) >= 0.55:
        best = ytm_results[0]
        print(f"[SEARCH 1/3] Matched on YouTube Music: {best['title']} (score={best['match_score']:.2f})")
        return [best], candidates[:5]

    # 2. Search Priority #2: Spotify / Music Catalog
    print(f"[SEARCH 2/3] Checking Spotify / Music Catalog for: '{cleaned}'")
    sp_results = await loop.run_in_executor(
        None, lambda: _search_spotify_and_catalog_sync(cleaned, limit=5)
    )
    _add_candidates(sp_results)

    if sp_results and sp_results[0].get("match_score", 0.0) >= 0.60:
        best = sp_results[0]
        print(f"[SEARCH 2/3] Matched on Spotify Catalog: {best['title']} (score={best['match_score']:.2f})")
        return [best], candidates[:5]

    # 3. Search Priority #3: Basic YouTube (InnerTube + yt-dlp fallback)
    print(f"[SEARCH 3/3] Checking basic YouTube for: '{cleaned}'")
    yt_results = await loop.run_in_executor(
        None, lambda: _search_youtube_innertube_sync(cleaned, limit=6)
    )
    if not yt_results:
        try:
            yt_data = await loop.run_in_executor(
                None, lambda: ytdl_search.extract_info(f"ytsearch6:{cleaned}", download=False)
            )
            if yt_data:
                for entry in yt_data.get("entries", [yt_data]):
                    parsed = _parse_single_track_entry(entry, "YouTube")
                    if parsed:
                        yt_results.append(parsed)
        except Exception as e:
            print(f"[SEARCH WARN] yt-dlp fallback failed: {e}")

    _add_candidates(yt_results)

    source_priority = {"YouTube Music": 3, "Spotify": 2, "YouTube": 1}
    candidates.sort(
        key=lambda x: (round(x.get("match_score", 0.0), 2), source_priority.get(x.get("source", ""), 0)),
        reverse=True,
    )

    if candidates and candidates[0].get("match_score", 0.0) >= 0.52:
        best = candidates[0]
        print(f"[SEARCH MATCH] Selected best match: {best['title']} [{best['source']}] (score={best['match_score']:.2f})")
        return [best], candidates[:5]

    # 4. If no confident match was found, gather broadened "Did you mean?" suggestions
    print(f"[SEARCH SUGGESTIONS] No confident match for '{cleaned}'. Building candidate list...")
    words = [w for w in re.split(r"\s+", cleaned) if len(w) >= 3]
    if len(words) >= 2:
        broad_query = " ".join(words[:2])
        broad_ytm = await loop.run_in_executor(
            None, lambda: _search_ytmusic_innertube_sync(broad_query, limit=5)
        )
        _add_candidates(broad_ytm)

    if len(candidates) < 5 and words:
        longest_word = max(words, key=len)
        broad_sp = await loop.run_in_executor(
            None, lambda: _search_spotify_and_catalog_sync(longest_word, limit=5)
        )
        _add_candidates(broad_sp)

    candidates.sort(key=lambda x: x.get("match_score", 0.0), reverse=True)
    return [], candidates[:5]


async def extract_entries(query_or_url: str) -> tuple[list[dict], list[dict]]:
    """
    Extracts tracks from a direct URL (YouTube, YouTube Music, or Spotify song/playlist/album),
    OR searches in priority order (1. YouTube Music -> 2. Spotify -> 3. YouTube).
    Returns `(tracks_to_queue, suggestions_if_not_found)`.
    """
    cleaned = query_or_url.strip().strip('"').strip("'").strip("“”‘’").strip()
    loop = asyncio.get_running_loop()

    if cleaned.startswith(("http://", "https://")):
        parsed_host = urllib.parse.urlparse(cleaned).netloc.lower()

        if any(domain in parsed_host for domain in ("spotify.com", "spotify.link", "spoti.fi")):
            entries = await loop.run_in_executor(None, lambda: _extract_spotify_url_sync(cleaned))
            print(f"[SPOTIFY] Found {len(entries)} track(s) from Spotify URL.")
            return entries, []

        clean_url, is_playlist, source_label = _normalize_youtube_url(cleaned)
        mode_str = "PLAYLIST" if is_playlist else "SINGLE TRACK"
        print(f"[YT-DLP] Extracting direct {source_label} {mode_str} URL: {clean_url}")

        extractor = ytdl_flat if is_playlist else ytdl_single
        data = await loop.run_in_executor(
            None, lambda: extractor.extract_info(clean_url, download=False)
        )
        if not data:
            return [], []

        entries = []
        if is_playlist and "entries" in data:
            for entry in data["entries"]:
                if not entry:
                    continue
                vid = entry.get("id") or ""
                url = entry.get("url") or entry.get("webpage_url")
                if url and not url.startswith("http"):
                    if source_label == "YouTube Music":
                        url = f"https://music.youtube.com/watch?v={url}"
                    else:
                        url = f"https://www.youtube.com/watch?v={url}"
                raw_title = entry.get("track") or entry.get("title") or "Unknown Track"
                raw_artist = extract_entry_artist(entry)
                full_title, clean_art, clean_tr = format_artist_and_title(raw_title, raw_artist)
                dur_sec = parse_duration_str(entry.get("duration"))
                thumb = entry.get("thumbnail") or (f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg" if len(vid) == 11 else "")
                if url:
                    entries.append(
                        {
                            "url": url,
                            "video_id": vid if len(vid) == 11 else "",
                            "title": full_title,
                            "artist": clean_art,
                            "track_name": clean_tr,
                            "duration": dur_sec,
                            "thumbnail": thumb,
                            "source": source_label,
                        }
                    )
        else:
            if "entries" in data and data["entries"]:
                data = data["entries"][0]
            vid = data.get("id") or ""
            url = data.get("webpage_url") or data.get("url") or clean_url
            if url and not url.startswith("http"):
                if source_label == "YouTube Music":
                    url = f"https://music.youtube.com/watch?v={url}"
                else:
                    url = f"https://www.youtube.com/watch?v={url}"
            raw_title = data.get("track") or data.get("title") or "Unknown Track"
            raw_artist = extract_entry_artist(data)
            full_title, clean_art, clean_tr = format_artist_and_title(raw_title, raw_artist)
            dur_sec = parse_duration_str(data.get("duration"))
            thumb = data.get("thumbnail") or (f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg" if len(vid) == 11 else "")
            entries.append(
                {
                    "url": url,
                    "video_id": vid if len(vid) == 11 else "",
                    "title": full_title,
                    "artist": clean_art,
                    "track_name": clean_tr,
                    "duration": dur_sec,
                    "thumbnail": thumb,
                    "source": source_label,
                }
            )

        print(f"[YT-DLP] Found {len(entries)} track(s) from URL.")
        return entries, []

    return await search_tracks_with_suggestions(cleaned)


# =====================================================================
# ANTI-403 AUDIO STREAM RESOLUTION, PRE-RESOLVER & LYRICS
# =====================================================================
def _probe_stream_url_sync(stream_url: str, http_headers: dict | None) -> bool:
    """
    Tests whether `stream_url` is accessible using the exact `http_headers` from yt-dlp.
    Returns True if HTTP 200/206 is returned, or False if HTTP 403 Forbidden occurs.
    """
    if not stream_url or not stream_url.startswith(("http://", "https://")):
        return os.path.exists(stream_url)
    if ".m3u8" in stream_url:
        return True
    headers = dict(_HTTP_HEADERS)
    if http_headers:
        for k, v in http_headers.items():
            if k and v:
                headers[str(k)] = str(v)
    headers["Range"] = "bytes=0-16384"
    try:
        req = urllib.request.Request(stream_url, headers=headers)
        with urllib.request.urlopen(req, timeout=6.0) as resp:
            status = getattr(resp, "status", 200)
            chunk = resp.read(64)
            return status in (200, 206) and len(chunk) > 0
    except urllib.error.HTTPError as e:
        print(f"[STREAM PROBE WARN] HTTP {e.code} on direct stream URL.")
        return False
    except Exception as e:
        print(f"[STREAM PROBE WARN] Probe error: {e}")
        return False


def _download_audio_to_temp_sync(target_url: str) -> tuple[dict | None, str | None]:
    """
    Layer 3 Fallback: Uses yt-dlp's internal downloader to save the audio track into
    /tmp/slave_audio_cache so FFmpeg can play the local file with zero HTTP 403 errors.
    """
    token = f"track_{int(time.time() * 1000)}_{random.randint(1000, 9999)}"
    outtmpl = os.path.join(TEMP_CACHE_DIR, f"{token}.%(ext)s")
    dl_opts = {
        "format": "bestaudio[ext=m4a]/bestaudio[acodec=opus]/bestaudio/best",
        "outtmpl": outtmpl,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "retries": 5,
        "fragment_retries": 5,
        "source_address": "0.0.0.0",
        "js_runtimes": {"deno": {}, "node": {}},
        "extractor_args": {
            "youtube": {
                "player_client": ["web_embedded", "ios", "mweb", "tv", "web"],
            }
        },
    }
    try:
        with yt_dlp.YoutubeDL(dl_opts) as ydl_dl:
            info = ydl_dl.extract_info(target_url, download=True)
            if not info:
                return None, None
            if "entries" in info and info["entries"]:
                info = info["entries"][0]
            matches = glob.glob(os.path.join(TEMP_CACHE_DIR, f"{token}.*"))
            for filepath in matches:
                if not filepath.endswith(".part") and os.path.getsize(filepath) > 0:
                    print(f"[LOCAL CACHE] Downloaded clean audio file: {filepath}")
                    return info, filepath
    except Exception as e:
        print(f"[LOCAL CACHE ERROR] Download fallback failed for {target_url}: {e}")
    return None, None


def _extract_verified_stream_sync(target_url: str) -> tuple[dict | None, str | None, dict, str | None]:
    """
    3-Layer Anti-403 Stream Extractor:
      1. Extracts stream with `check_formats="selected"` and probes it with yt-dlp's `http_headers`.
      2. If HTTP 403 occurs, retries with fallback player clients (`web_embedded`, `ios`, `mweb`, `tv`).
      3. If direct streaming still gets 403, downloads the track to `/tmp/slave_audio_cache` via yt-dlp.
    Returns `(info_dict, playable_url_or_filepath, http_headers, local_temp_filepath)`.
    """
    for label, extractor in (("primary", ytdl_stream), ("fallback-client", ytdl_fallback_stream)):
        try:
            data = extractor.extract_info(target_url, download=False)
            if data and "entries" in data and data["entries"]:
                data = data["entries"][0]
            if data and data.get("url"):
                s_url = data["url"]
                headers = dict(data.get("http_headers") or {})
                if _probe_stream_url_sync(s_url, headers):
                    return data, s_url, headers, None
                print(f"[ANTI-403] {label} stream URL failed HTTP probe, trying next layer...")
        except Exception as e:
            print(f"[ANTI-403 WARN] {label} extraction error: {e}")

    print(f"[ANTI-403] Falling back to local temp audio download for: {target_url}")
    info, local_path = _download_audio_to_temp_sync(target_url)
    if info and local_path:
        return info, local_path, {}, local_path

    return None, None, {}, None


async def resolve_stream(track_item: dict) -> dict | None:
    """
    Fetches a verified playable audio stream (or local cached audio file),
    preserving 'Composer - Song Title', duration, thumbnail, and HTTP headers for FFmpeg.
    """
    url = track_item.get("url", "")
    source_label = track_item.get("source", "YouTube")
    loop = asyncio.get_running_loop()

    if source_label == "Spotify" or "spotify.com" in url or "apple.com" in url:
        search_query = track_item.get("search_query") or track_item.get("title") or ""
        print(f"[SPOTIFY -> AUDIO] Resolving playable studio stream for: '{search_query}'")
        target_watch_url = None

        ytm_matches = await loop.run_in_executor(
            None, lambda: _search_ytmusic_innertube_sync(search_query, limit=3)
        )
        if ytm_matches:
            target_watch_url = ytm_matches[0]["url"]
            if not track_item.get("video_id"):
                track_item["video_id"] = ytm_matches[0].get("video_id", "")
            if not track_item.get("duration"):
                track_item["duration"] = ytm_matches[0].get("duration", 0)
            if not track_item.get("thumbnail"):
                track_item["thumbnail"] = ytm_matches[0].get("thumbnail", "")

        if not target_watch_url:
            target_watch_url = f"ytsearch1:{search_query} Official Audio"

        data, stream_url, http_headers, local_file = await loop.run_in_executor(
            None, lambda: _extract_verified_stream_sync(target_watch_url)
        )
        if not data or not stream_url:
            return None

        vid = track_item.get("video_id") or data.get("id") or ""
        return {
            "stream_url": stream_url,
            "http_headers": http_headers,
            "local_file": local_file,
            "title": track_item.get("title") or data.get("title", "Unknown Track"),
            "artist": track_item.get("artist", ""),
            "track_name": track_item.get("track_name", ""),
            "webpage_url": url,
            "video_id": vid if len(str(vid)) == 11 else "",
            "duration": track_item.get("duration") or parse_duration_str(data.get("duration")),
            "thumbnail": track_item.get("thumbnail") or data.get("thumbnail") or "",
            "requester": track_item.get("requester", ""),
            "source": "Spotify",
        }

    standard_watch_url = url
    vid_candidate = track_item.get("video_id") or ""
    if len(str(vid_candidate)) == 11:
        standard_watch_url = f"https://www.youtube.com/watch?v={vid_candidate}"

    data, stream_url, http_headers, local_file = await loop.run_in_executor(
        None, lambda: _extract_verified_stream_sync(standard_watch_url)
    )
    if not data or not stream_url:
        return None

    raw_title = track_item.get("title") or data.get("track") or data.get("title") or "Unknown Track"
    raw_artist = track_item.get("artist") or extract_entry_artist(data)
    full_title, clean_art, clean_tr = format_artist_and_title(raw_title, raw_artist)
    vid = track_item.get("video_id") or data.get("id") or ""
    dur_sec = track_item.get("duration") or parse_duration_str(data.get("duration"))
    thumb = (
        track_item.get("thumbnail")
        or data.get("thumbnail")
        or (f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg" if len(str(vid)) == 11 else "")
    )

    webpage_url = data.get("webpage_url", url)
    if source_label == "YouTube Music" and "www.youtube.com/watch" in webpage_url:
        webpage_url = webpage_url.replace("www.youtube.com/watch", "music.youtube.com/watch")

    return {
        "stream_url": stream_url,
        "http_headers": http_headers,
        "local_file": local_file,
        "title": full_title,
        "artist": clean_art,
        "track_name": clean_tr,
        "webpage_url": webpage_url,
        "video_id": vid if len(str(vid)) == 11 else "",
        "duration": dur_sec,
        "thumbnail": thumb,
        "requester": track_item.get("requester", ""),
        "source": source_label,
    }


def _cleanup_track_temp_file(track: dict | None) -> None:
    """Safely removes any pre-resolved cached audio file if a queued track is discarded."""
    if not isinstance(track, dict):
        return
    pre = track.get("_pre_resolved_stream")
    if isinstance(pre, dict):
        lf = pre.get("local_file")
        if lf and os.path.exists(lf):
            try:
                os.remove(lf)
            except Exception:
                pass
    lf_direct = track.get("local_file")
    if lf_direct and os.path.exists(lf_direct):
        try:
            os.remove(lf_direct)
        except Exception:
            pass


def _is_pre_resolved_stream_valid(pre: dict | None, resolved_at: float) -> bool:
    """Checks whether a pre-resolved stream dict is still fresh and ready for instant playback."""
    if not isinstance(pre, dict) or not pre.get("stream_url"):
        return False
    # Signed googlevideo URLs last several hours; treat < 15 minutes as fresh
    if (time.monotonic() - resolved_at) > 900.0:
        return False
    local_file = pre.get("local_file")
    if local_file and not os.path.exists(local_file):
        return False
    return True


def _fetch_lyrics_sync(query_or_title: str, artist_hint: str = "", track_hint: str = "") -> dict | None:
    """Queries the public LRCLIB API (https://lrclib.net/api/search) for song lyrics."""
    q = query_or_title.strip()
    if artist_hint and track_hint:
        url = (
            f"https://lrclib.net/api/search?artist_name={urllib.parse.quote_plus(artist_hint)}"
            f"&track_name={urllib.parse.quote_plus(track_hint)}"
        )
    else:
        url = f"https://lrclib.net/api/search?q={urllib.parse.quote_plus(q)}"

    try:
        raw = _http_get_text(url, timeout=8.0)
        items = json.loads(raw)
        if not isinstance(items, list) or not items:
            if artist_hint and track_hint:
                fallback_url = f"https://lrclib.net/api/search?q={urllib.parse.quote_plus(q)}"
                items = json.loads(_http_get_text(fallback_url, timeout=8.0))
        for item in items or []:
            plain = (item.get("plainLyrics") or "").strip()
            synced = (item.get("syncedLyrics") or "").strip()
            if plain or synced:
                if not plain and synced:
                    plain = re.sub(r"\[\d+:\d+\.\d+\]\s*", "", synced)
                full_t, art, trk = format_artist_and_title(
                    item.get("trackName") or q, item.get("artistName") or artist_hint
                )
                return {
                    "title": full_t,
                    "album": item.get("albumName") or "",
                    "lyrics": plain,
                }
    except Exception as e:
        print(f"[LYRICS WARN] LRCLIB lookup failed: {e}")
    return None


class SteadyOpusSource(discord.AudioSource):
    """
    Wraps FFmpegOpusAudio, prevents the 'slow down then speed up' rubber-band effect,
    and automatically deletes any temporary cached audio file when playback finishes.
    """

    def __init__(
        self,
        inner: discord.FFmpegOpusAudio,
        voice_client: discord.VoiceClient | None,
        local_file: str | None = None,
    ):
        self.inner = inner
        self.vc = voice_client
        self.local_file = local_file
        self.keep_local_file = False

    def is_opus(self) -> bool:
        return True

    def read(self) -> bytes:
        t0 = time.perf_counter()
        data = self.inner.read()
        elapsed = time.perf_counter() - t0

        if elapsed > 0.045 and self.vc is not None:
            player = getattr(self.vc, "_player", None)
            if player is not None and hasattr(player, "_start") and hasattr(player, "loops"):
                player._start = time.perf_counter() - (player.loops * 0.02)
        return data

    def cleanup(self) -> None:
        self.inner.cleanup()
        if not self.keep_local_file and self.local_file and os.path.exists(self.local_file):
            try:
                os.remove(self.local_file)
            except Exception:
                pass


def _build_ffmpeg_before_options(
    stream_url: str,
    http_headers: dict | None,
    seek_seconds: int = 0,
) -> str:
    """
    Builds FFmpeg `before_options` including the exact User-Agent and HTTP headers
    that yt-dlp used when signing the googlevideo.com stream URL (preventing HTTP 403).
    """
    parts: list[str] = []
    if seek_seconds > 0:
        parts.append(f"-ss {int(seek_seconds)}")

    if stream_url.startswith(("http://", "https://")):
        if http_headers:
            ua = http_headers.get("User-Agent") or http_headers.get("user-agent")
            if ua:
                safe_ua = str(ua).replace('"', "'")
                parts.append(f'-user_agent "{safe_ua}"')

            header_lines = []
            for k, v in http_headers.items():
                if k.lower() in ("user-agent", "host", "range", "accept-encoding"):
                    continue
                safe_v = str(v).replace('"', "'").replace("\r", "").replace("\n", "")
                header_lines.append(f"{k}: {safe_v}")
            if header_lines:
                joined_headers = "\r\n".join(header_lines) + "\r\n"
                parts.append(f'-headers "{joined_headers}"')

        parts.append(FFMPEG_HTTP_RECONNECT_OPTS)
    else:
        parts.append("-nostdin")

    return " ".join(parts)


async def build_audio_source(
    stream_url: str,
    volume: float,
    voice_client: discord.VoiceClient | None,
    seek_seconds: int = 0,
    http_headers: dict | None = None,
    local_file: str | None = None,
    normalize_audio: bool = True,
) -> SteadyOpusSource:
    """
    Creates a high-stability Opus audio stream with exact yt-dlp headers,
    optional seeking, and automatic studio loudness normalization (`dynaudnorm`).
    """
    before_opts = _build_ffmpeg_before_options(stream_url, http_headers, seek_seconds=seek_seconds)
    filters: list[str] = []
    if normalize_audio:
        filters.append("dynaudnorm=f=150:g=13:p=0.90:m=10.0")
    filters.append(f"volume={volume:.2f}")
    filters.append("aresample=async=1:min_hard_comp=0.100:first_pts=0")
    filter_chain = ",".join(filters)

    ffmpeg_opts = f'-vn -filter:a "{filter_chain}" -bufsize 8192k'
    opus_source = await discord.FFmpegOpusAudio.from_probe(
        stream_url,
        method="fallback",
        before_options=before_opts,
        options=ffmpeg_opts,
    )
    return SteadyOpusSource(opus_source, voice_client, local_file=local_file)


class GuildMusicState:
    """Manages the playlist queue, track history, playback clock, pre-resolver, and settings for a server."""

    def __init__(self):
        self.queue: deque[dict] = deque()
        self.history: deque[dict] = deque(maxlen=25)
        self.current: dict | None = None
        self.voice_client: discord.VoiceClient | None = None
        self.text_channel: discord.abc.Messageable | None = None
        self.loop_mode: str = "off"  # "off", "track", or "queue"
        self.autoplay: bool = False
        self.normalize_audio: bool = True  # Studio loudness normalization ON by default
        self.volume: float = 0.8  # Default 80%
        self.started_at: float = 0.0
        self.seek_offset: float = 0.0
        self.paused_at: float | None = None
        self.suppress_after_callback: bool = False
        self.user_skipped: bool = False
        self.consecutive_failures: int = 0
        self.auto_paused_alone: bool = False
        self.alone_disconnect_task: asyncio.Task | None = None
        self.pre_resolve_task: asyncio.Task | None = None
        self.last_np_message: discord.Message | None = None

    def get_elapsed_seconds(self) -> float:
        """Returns the current playback position in seconds for the active song."""
        if not self.current or self.started_at <= 0:
            return 0.0
        now = self.paused_at if self.paused_at is not None else time.monotonic()
        elapsed = self.seek_offset + max(0.0, now - self.started_at)
        dur = self.current.get("duration") or 0
        if dur > 0:
            return min(float(dur), elapsed)
        return elapsed


# =====================================================================
# FAVORITES, SAVED PLAYLISTS, CRASH RECOVERY & VOICE PERMISSION RULE
# =====================================================================
def _serialize_track_for_storage(track: dict) -> dict:
    """Stores clean metadata for a song so it can be reloaded anytime."""
    return {
        "url": track.get("webpage_url") or track.get("url") or "",
        "video_id": track.get("video_id") or "",
        "title": track.get("title") or "Unknown Track",
        "artist": track.get("artist") or "",
        "track_name": track.get("track_name") or "",
        "duration": int(track.get("duration") or 0),
        "thumbnail": track.get("thumbnail") or "",
        "source": track.get("source") or "YouTube Music",
    }


def save_liked_track_for_user(user_id: int, track: dict) -> tuple[bool, str]:
    """Saves `track` to a user's personal liked songs list in `slave_data.json`."""
    data = _load_persistent_data()
    uid = str(user_id)
    user_likes: list[dict] = data.setdefault("likes", {}).setdefault(uid, [])
    serialized = _serialize_track_for_storage(track)
    norm_title = _normalize_for_match(serialized["title"])

    for existing in user_likes:
        if _normalize_for_match(existing.get("title", "")) == norm_title:
            return False, f"❤️ **{serialized['title']}** is already in your liked songs ({len(user_likes)} total)."

    user_likes.append(serialized)
    _save_persistent_data(data)
    return True, f"❤️ Saved **{serialized['title']}** to your personal liked songs! (`{len(user_likes)}` total)"


def save_active_session_snapshot(guild_id: int, state: GuildMusicState, clear_snapshot: bool = False) -> None:
    """
    Persists the active queue and player settings for `guild_id` to `slave_data.json`
    so the session can be restored in 1 click if the bot or laptop restarts.
    """
    data = _load_persistent_data()
    sessions = data.setdefault("sessions", {})
    gid_str = str(guild_id)

    if clear_snapshot:
        if gid_str in sessions:
            del sessions[gid_str]
            _save_persistent_data(data)
        return

    tracks_to_save: list[dict] = []
    if state.current:
        tracks_to_save.append(_serialize_track_for_storage(state.current))
    for item in state.queue:
        tracks_to_save.append(_serialize_track_for_storage(item))

    if not tracks_to_save:
        return

    vc_id = (
        state.voice_client.channel.id
        if (state.voice_client and state.voice_client.is_connected() and state.voice_client.channel)
        else None
    )
    tc_id = getattr(state.text_channel, "id", None)

    sessions[gid_str] = {
        "saved_at": int(time.time()),
        "voice_channel_id": vc_id,
        "text_channel_id": tc_id,
        "loop_mode": state.loop_mode,
        "autoplay": state.autoplay,
        "normalize_audio": state.normalize_audio,
        "volume": state.volume,
        "tracks": tracks_to_save[:100],
    }
    _save_persistent_data(data)


def check_voice_permission(
    member: discord.Member | discord.User,
    state: GuildMusicState,
) -> tuple[bool, str]:
    """
    Enforces the Voice-Chat-Only Control Rule:
    - Users NOT in a voice channel cannot add music, skip, move, pause, or change volume.
    - If slave is already connected to a voice channel, the user must be in that SAME voice channel.
    """
    if not isinstance(member, discord.Member) or not member.voice or not member.voice.channel:
        return (
            False,
            "🔒 **Voice Chat Required:** You must be inside a voice channel to add or control music. "
            "*(Outside voice chat, you can only view `/playlist`, `/np`, `/slave lyrics`, and `/slave help`.)*",
        )

    user_channel = member.voice.channel
    if state.voice_client and state.voice_client.is_connected() and state.voice_client.channel:
        bot_channel = state.voice_client.channel
        if user_channel != bot_channel:
            return (
                False,
                f"🔒 **Wrong Voice Channel:** You must be in **{bot_channel.name}** to control **slave**.",
            )

    return True, ""


# =====================================================================
# RICH EMBEDS & INTERACTIVE UI VIEWS (PLAYER, PLAYLIST, SUGGESTIONS, RESTORE)
# =====================================================================
PLAYLIST_PAGE_SIZE = 10


def build_now_playing_embed(state: GuildMusicState, status_header: str = "🎶 Now Playing") -> discord.Embed:
    """Builds a rich Now Playing embed with Composer - Song Title, artwork, and progress bar."""
    cur = state.current or {}
    title = cur.get("title", "Unknown Track")
    url = cur.get("webpage_url") or cur.get("url") or ""
    source_badge = format_source_badge(cur.get("source", "YouTube"))
    elapsed = state.get_elapsed_seconds()
    duration = int(cur.get("duration") or 0)
    progress = build_progress_bar(elapsed, duration)

    loop_labels = {"off": "Off", "track": "🔂 Single Track", "queue": "🔁 Whole Playlist"}
    autoplay_label = "📻 ON" if state.autoplay else "Off"
    norm_label = "🎚️ ON" if state.normalize_audio else "Off"
    requester = cur.get("requester") or "Voice Member"

    desc_lines = [
        f"**[{title}]({url})**" if url else f"**{title}**",
        "",
        progress,
        "",
        f"**Source:** `{source_badge}` • **Requested by:** `{requester}`",
        (
            f"**Volume:** `{int(state.volume * 100)}%` • **Norm:** `{norm_label}` • "
            f"**Loop:** `{loop_labels.get(state.loop_mode, 'Off')}` • **Autoplay:** `{autoplay_label}`"
        ),
    ]
    if len(state.queue) > 0:
        next_track = state.queue[0]
        ready_bolt = " ⚡" if _is_pre_resolved_stream_valid(
            next_track.get("_pre_resolved_stream"), next_track.get("_pre_resolved_at", 0.0)
        ) else ""
        desc_lines.append(f"**Up Next (#1){ready_bolt}:** `{next_track.get('title', 'Unknown')}`")

    embed = discord.Embed(
        title=f"{status_header} — slave {BOT_VERSION}",
        description="\n".join(desc_lines),
        color=discord.Color.blurple(),
    )
    thumb = cur.get("thumbnail")
    if thumb and thumb.startswith("http"):
        embed.set_thumbnail(url=thumb)
    return embed


def build_playlist_embed(state: GuildMusicState, page: int) -> tuple[discord.Embed, int, int]:
    """Builds a single compact page of the playlist so text chat stays clean."""
    total_tracks = len(state.queue)
    total_pages = max(1, (total_tracks + PLAYLIST_PAGE_SIZE - 1) // PLAYLIST_PAGE_SIZE)
    page = max(1, min(page, total_pages))

    lines: list[str] = []
    if state.current:
        cur_icon = format_source_icon(state.current.get("source", "YouTube"))
        cur_dur = format_seconds(state.current.get("duration"))
        lines.append(
            f"**Now Playing:** {cur_icon} [{state.current['title']}]({state.current['webpage_url']}) `[{cur_dur}]`"
        )
    else:
        lines.append("**Now Playing:** *Nothing currently playing*")

    loop_labels = {"off": "Off", "track": "Single Track", "queue": "Whole Playlist"}
    lines.append(
        f"**Settings:** Loop: `{loop_labels.get(state.loop_mode, 'Off')}` | "
        f"Autoplay: `{'ON' if state.autoplay else 'Off'}` | "
        f"Norm: `{'ON' if state.normalize_audio else 'Off'}` | "
        f"Volume: `{int(state.volume * 100)}%`\n"
    )

    if total_tracks == 0:
        lines.append("*The upcoming playlist is empty.*")
    else:
        start_idx = (page - 1) * PLAYLIST_PAGE_SIZE
        end_idx = min(start_idx + PLAYLIST_PAGE_SIZE, total_tracks)
        lines.append(f"**Upcoming Tracks ({start_idx + 1}–{end_idx} of {total_tracks}):**")
        queue_slice = list(state.queue)[start_idx:end_idx]
        for idx, item in enumerate(queue_slice, start=start_idx + 1):
            t_title = item.get("title", "Unknown Track")
            if len(t_title) > 62:
                t_title = t_title[:59] + "..."
            icon = format_source_icon(item.get("source", "YouTube"))
            dur_str = format_seconds(item.get("duration"))
            bolt = " ⚡" if idx == 1 and _is_pre_resolved_stream_valid(
                item.get("_pre_resolved_stream"), item.get("_pre_resolved_at", 0.0)
            ) else ""
            lines.append(f"`{idx}.` {icon} {t_title} `[{dur_str}]`{bolt}")

    embed = discord.Embed(
        title=f"🎶 slave Playlist ({BOT_VERSION}) — {total_tracks} track(s)",
        description="\n".join(lines),
        color=discord.Color.blurple(),
    )
    embed.set_footer(
        text=f"Page {page}/{total_pages} • Click 'Full List' below for a private scrollable view of all tracks"
    )
    return embed, page, total_pages


def build_full_playlist_text(state: GuildMusicState) -> str:
    """Formats every single track in the playlist into a clean text file for scrolling."""
    header = [f"=== SLAVE FULL PLAYLIST ({BOT_VERSION}) ==="]
    if state.current:
        cur_badge = format_source_badge(state.current.get("source", "YouTube"), compact=True)
        cur_dur = format_seconds(state.current.get("duration"))
        header.append(f"Now Playing: [{cur_badge}] {state.current['title']} [{cur_dur}]")
    header.append(f"Total Upcoming Tracks: {len(state.queue)}")
    header.append("=" * 44 + "\n")

    body = [
        f"{idx:3d}. [{format_source_badge(item.get('source', 'YouTube'), compact=True)}] "
        f"{item.get('title', 'Unknown Track')} [{format_seconds(item.get('duration'))}]"
        for idx, item in enumerate(state.queue, start=1)
    ]
    return "\n".join(header + body)


class NowPlayingControlView(discord.ui.View):
    """
    10 Interactive player buttons attached directly to 'Now Playing' cards:
    Row 0: [⏮️ Prev] [⏯️ Pause/Resume] [⏭️ Skip] [🔂 Loop] [🔀 Shuffle]
    Row 1: [❤️ Like] [📜 Lyrics] [📻 Autoplay] [🎚️ Norm] [⏹️ Stop]
    """

    def __init__(self, bot_instance: "SlaveBot", guild_id: int):
        super().__init__(timeout=600)
        self.bot_instance = bot_instance
        self.guild_id = guild_id

    async def _verify_voice(self, interaction: discord.Interaction) -> GuildMusicState | None:
        state = self.bot_instance.get_guild_state(self.guild_id)
        allowed, reason = check_voice_permission(interaction.user, state)
        if not allowed:
            await interaction.response.send_message(reason, ephemeral=True)
            return None
        return state

    @discord.ui.button(emoji="⏮️", label="Prev", style=discord.ButtonStyle.secondary, row=0)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = await self._verify_voice(interaction)
        if not state:
            return
        if not state.history:
            await interaction.response.send_message("❌ No previous track in history.", ephemeral=True)
            return
        prev_track = state.history.pop()
        if state.current:
            state.queue.appendleft(dict(state.current))
        state.queue.appendleft(prev_track)
        await interaction.response.defer()
        if state.voice_client and (state.voice_client.is_playing() or state.voice_client.is_paused()):
            state.user_skipped = True
            state.voice_client.stop()
        else:
            await self.bot_instance.play_next(self.guild_id)

    @discord.ui.button(emoji="⏯️", label="Pause/Resume", style=discord.ButtonStyle.primary, row=0)
    async def pause_resume_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = await self._verify_voice(interaction)
        if not state or not state.voice_client:
            return
        vc = state.voice_client
        if vc.is_playing():
            vc.pause()
            state.paused_at = time.monotonic()
            await interaction.response.edit_message(
                embed=build_now_playing_embed(state, "⏸️ Paused"), view=self
            )
        elif vc.is_paused():
            if state.paused_at is not None:
                state.started_at += time.monotonic() - state.paused_at
                state.paused_at = None
            state.auto_paused_alone = False
            vc.resume()
            await interaction.response.edit_message(
                embed=build_now_playing_embed(state, "🎶 Now Playing"), view=self
            )
        else:
            await interaction.response.send_message("❌ Nothing is playing right now.", ephemeral=True)

    @discord.ui.button(emoji="⏭️", label="Skip", style=discord.ButtonStyle.secondary, row=0)
    async def skip_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = await self._verify_voice(interaction)
        if not state or not state.voice_client:
            return
        if state.voice_client.is_playing() or state.voice_client.is_paused():
            skipped_title = state.current["title"] if state.current else "current track"
            state.user_skipped = True
            state.voice_client.stop()
            await interaction.response.send_message(f"⏭️ Skipped **{skipped_title}**.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Nothing is playing to skip.", ephemeral=True)

    @discord.ui.button(emoji="🔂", label="Loop", style=discord.ButtonStyle.secondary, row=0)
    async def loop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = await self._verify_voice(interaction)
        if not state:
            return
        order = ["off", "track", "queue"]
        next_idx = (order.index(state.loop_mode) + 1) % len(order) if state.loop_mode in order else 0
        state.loop_mode = order[next_idx]
        save_active_session_snapshot(self.guild_id, state)
        await interaction.response.edit_message(embed=build_now_playing_embed(state), view=self)

    @discord.ui.button(emoji="🔀", label="Shuffle", style=discord.ButtonStyle.secondary, row=0)
    async def shuffle_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = await self._verify_voice(interaction)
        if not state:
            return
        if len(state.queue) < 2:
            await interaction.response.send_message("❌ Need at least 2 tracks in the playlist to shuffle.", ephemeral=True)
            return
        temp = list(state.queue)
        random.shuffle(temp)
        state.queue = deque(temp)
        self.bot_instance.trigger_pre_resolve(self.guild_id)
        save_active_session_snapshot(self.guild_id, state)
        await interaction.response.edit_message(embed=build_now_playing_embed(state), view=self)

    @discord.ui.button(emoji="❤️", label="Like", style=discord.ButtonStyle.success, row=1)
    async def like_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = self.bot_instance.get_guild_state(self.guild_id)
        if not state.current:
            await interaction.response.send_message("❌ Nothing is currently playing to like.", ephemeral=True)
            return
        _, msg = save_liked_track_for_user(interaction.user.id, state.current)
        await interaction.response.send_message(msg, ephemeral=True)

    @discord.ui.button(emoji="📜", label="Lyrics", style=discord.ButtonStyle.secondary, row=1)
    async def lyrics_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = self.bot_instance.get_guild_state(self.guild_id)
        if not state.current:
            await interaction.response.send_message("❌ Nothing is playing right now.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        cur = state.current
        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(
            None,
            lambda: _fetch_lyrics_sync(
                cur.get("title", ""), cur.get("artist", ""), cur.get("track_name", "")
            ),
        )
        if not res:
            await interaction.followup.send(f"❌ Could not find lyrics for **{cur.get('title')}**.", ephemeral=True)
            return
        lyrics_text = res["lyrics"]
        if len(lyrics_text) <= 3800:
            emb = discord.Embed(
                title=f"📜 Lyrics — {res['title']}",
                description=lyrics_text,
                color=discord.Color.gold(),
            )
            await interaction.followup.send(embed=emb, ephemeral=True)
        else:
            buf = io.BytesIO(lyrics_text.encode("utf-8"))
            await interaction.followup.send(
                content=f"📜 **Full Lyrics — {res['title']}:**",
                file=discord.File(buf, filename="lyrics.txt"),
                ephemeral=True,
            )

    @discord.ui.button(emoji="📻", label="Autoplay", style=discord.ButtonStyle.secondary, row=1)
    async def autoplay_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = await self._verify_voice(interaction)
        if not state:
            return
        state.autoplay = not state.autoplay
        save_active_session_snapshot(self.guild_id, state)
        await interaction.response.edit_message(embed=build_now_playing_embed(state), view=self)

    @discord.ui.button(emoji="🎚️", label="Norm", style=discord.ButtonStyle.secondary, row=1)
    async def norm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = await self._verify_voice(interaction)
        if not state:
            return
        state.normalize_audio = not state.normalize_audio
        save_active_session_snapshot(self.guild_id, state)
        await interaction.response.edit_message(embed=build_now_playing_embed(state), view=self)

    @discord.ui.button(emoji="⏹️", label="Stop", style=discord.ButtonStyle.danger, row=1)
    async def stop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = await self._verify_voice(interaction)
        if not state:
            return
        await self.bot_instance.stop_and_cleanup(self.guild_id, clear_session=True)
        await interaction.response.send_message("⏹️ Stopped playback, cleared playlist, and left voice.")


class SessionRestoreView(discord.ui.View):
    """1-Click button posted after a reboot if a previous music session was interrupted."""

    def __init__(self, bot_instance: "SlaveBot", guild_id: int):
        super().__init__(timeout=3600)
        self.bot_instance = bot_instance
        self.guild_id = guild_id

    @discord.ui.button(emoji="🔄", label="Restore Previous Session", style=discord.ButtonStyle.success)
    async def restore_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not isinstance(interaction.user, discord.Member) or not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message(
                "🔒 Join a voice channel first, then click **🔄 Restore Previous Session**!",
                ephemeral=True,
            )
            return

        await interaction.response.defer()
        ok, msg = await self.bot_instance.restore_guild_session(
            interaction.guild, interaction.user, interaction.channel
        )
        if ok:
            button.disabled = True
            await interaction.edit_original_response(view=self)
        await interaction.followup.send(msg)


class SearchSuggestionsView(discord.ui.View):
    """
    Interactive 'Did you mean?' buttons shown when a song search is ambiguous or not found.
    Clicking 1..5 immediately queues and plays that candidate song.
    """

    def __init__(
        self,
        bot_instance: "SlaveBot",
        guild_id: int,
        candidates: list[dict],
        play_next_flag: bool = False,
    ):
        super().__init__(timeout=180)
        self.bot_instance = bot_instance
        self.guild_id = guild_id
        self.candidates = candidates[:5]
        self.play_next_flag = play_next_flag

        for idx, cand in enumerate(self.candidates, start=1):
            label_title = cand.get("title", "Unknown")
            if len(label_title) > 72:
                label_title = label_title[:69] + "..."
            btn = discord.ui.Button(
                label=f"{idx}. {label_title}",
                style=discord.ButtonStyle.primary if idx == 1 else discord.ButtonStyle.secondary,
                row=(idx - 1) // 2,
            )
            btn.callback = self._make_pick_callback(cand)
            self.add_item(btn)

    def _make_pick_callback(self, chosen_track: dict):
        async def _callback(interaction: discord.Interaction):
            state = self.bot_instance.get_guild_state(self.guild_id)
            if not interaction.user.voice or not interaction.user.voice.channel:
                await interaction.response.send_message(
                    "🔒 You must be in a voice channel to pick a song.", ephemeral=True
                )
                return

            allowed, reason = check_voice_permission(interaction.user, state)
            if not allowed:
                await interaction.response.send_message(reason, ephemeral=True)
                return

            await interaction.response.defer()
            voice_channel = interaction.user.voice.channel
            if state.voice_client is None or not state.voice_client.is_connected():
                state.voice_client = await voice_channel.connect()
            elif state.voice_client.channel != voice_channel:
                await state.voice_client.move_to(voice_channel)

            state.text_channel = interaction.channel
            state.consecutive_failures = 0
            track_copy = dict(chosen_track)
            track_copy["requester"] = interaction.user.display_name

            if self.play_next_flag:
                state.queue.appendleft(track_copy)
                pos_text = "at **#1 (Up Next)**"
            else:
                state.queue.append(track_copy)
                pos_text = f"at **#{len(state.queue)}**"

            for child in self.children:
                if isinstance(child, discord.ui.Button):
                    child.disabled = True

            badge = format_source_badge(track_copy.get("source", "YouTube"))
            dur_str = format_seconds(track_copy.get("duration"))
            await interaction.edit_original_response(
                content=f"✅ Selected **[{badge}] {track_copy['title']}** `[{dur_str}]` — queued {pos_text}!",
                embed=None,
                view=self,
            )

            save_active_session_snapshot(self.guild_id, state)
            if not state.voice_client.is_playing() and not state.voice_client.is_paused():
                await self.bot_instance.play_next(self.guild_id)
            else:
                self.bot_instance.trigger_pre_resolve(self.guild_id)

        return _callback


class PlaylistPaginatorView(discord.ui.View):
    """Interactive buttons to flip through playlist pages in-place or open a scrollable full list."""

    def __init__(self, state: GuildMusicState, initial_page: int = 1):
        super().__init__(timeout=300)
        self.state = state
        self.page = initial_page
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        total_tracks = len(self.state.queue)
        total_pages = max(1, (total_tracks + PLAYLIST_PAGE_SIZE - 1) // PLAYLIST_PAGE_SIZE)
        self.page = max(1, min(self.page, total_pages))

        self.first_btn.disabled = self.page <= 1
        self.prev_btn.disabled = self.page <= 1
        self.next_btn.disabled = self.page >= total_pages
        self.last_btn.disabled = self.page >= total_pages
        self.full_list_btn.disabled = total_tracks == 0

    @discord.ui.button(label="⏮️", style=discord.ButtonStyle.secondary)
    async def first_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = 1
        self._sync_buttons()
        embed, self.page, _ = build_playlist_embed(self.state, self.page)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="◀️", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page -= 1
        self._sync_buttons()
        embed, self.page, _ = build_playlist_embed(self.state, self.page)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="▶️", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 1
        self._sync_buttons()
        embed, self.page, _ = build_playlist_embed(self.state, self.page)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="⏭️", style=discord.ButtonStyle.secondary)
    async def last_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        total_tracks = len(self.state.queue)
        self.page = max(1, (total_tracks + PLAYLIST_PAGE_SIZE - 1) // PLAYLIST_PAGE_SIZE)
        self._sync_buttons()
        embed, self.page, _ = build_playlist_embed(self.state, self.page)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="📄 Full List (Scrollable)", style=discord.ButtonStyle.primary)
    async def full_list_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.state.queue:
            await interaction.response.send_message("📭 The playlist is currently empty.", ephemeral=True)
            return
        full_text = build_full_playlist_text(self.state)
        buffer = io.BytesIO(full_text.encode("utf-8"))
        file = discord.File(fp=buffer, filename="full_playlist.txt")
        await interaction.response.send_message(
            content=f"📜 **Full Scrollable Playlist ({len(self.state.queue)} tracks)** — *(Only visible to you)*:",
            file=file,
            ephemeral=True,
        )


# =====================================================================
# BOT INITIALIZATION, PRE-RESOLVER, SINGLE CARD CLEANUP & PLAYBACK ENGINE
# =====================================================================
class SlaveBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.voice_states = True
        intents.guilds = True
        intents.messages = True
        intents.message_content = True

        super().__init__(command_prefix="!", intents=intents, help_command=None)
        self.music_states: dict[int, GuildMusicState] = {}

    def get_guild_state(self, guild_id: int) -> GuildMusicState:
        if guild_id not in self.music_states:
            self.music_states[guild_id] = GuildMusicState()
        return self.music_states[guild_id]

    async def delete_previous_np_card(self, state: GuildMusicState) -> None:
        """Deletes the previous 'Now Playing' card so only one active player card stays in chat."""
        if state.last_np_message is not None:
            old_msg = state.last_np_message
            state.last_np_message = None
            try:
                await old_msg.delete()
            except Exception:
                pass

    async def send_single_np_card(self, guild_id: int, status_header: str = "🎶 Now Playing") -> None:
        """Deletes any older Now Playing message and posts a fresh interactive card at the bottom of chat."""
        state = self.get_guild_state(guild_id)
        if not state.text_channel or not state.current:
            return
        await self.delete_previous_np_card(state)
        view = NowPlayingControlView(self, guild_id)
        embed = build_now_playing_embed(state, status_header)
        try:
            state.last_np_message = await state.text_channel.send(embed=embed, view=view)
        except Exception as e:
            print(f"[NP CARD WARN] Could not send Now Playing card: {e}")

    def trigger_pre_resolve(self, guild_id: int) -> None:
        """Starts a background task to pre-resolve the stream for #1 Up Next (zero-gap transitions)."""
        state = self.get_guild_state(guild_id)
        if state.pre_resolve_task and not state.pre_resolve_task.done():
            state.pre_resolve_task.cancel()
        if not state.queue or state.loop_mode == "track":
            return

        async def _pre_resolve_worker():
            try:
                await asyncio.sleep(1.5)
                if not state.queue or state.loop_mode == "track":
                    return
                next_track = state.queue[0]
                if _is_pre_resolved_stream_valid(
                    next_track.get("_pre_resolved_stream"),
                    next_track.get("_pre_resolved_at", 0.0),
                ):
                    return
                print(f"[PRE-RESOLVE ⚡] Pre-loading stream for Up Next (#1): {next_track.get('title')}")
                resolved = await resolve_stream(next_track)
                if resolved and state.queue and state.queue[0] is next_track:
                    next_track["_pre_resolved_stream"] = resolved
                    next_track["_pre_resolved_at"] = time.monotonic()
                    print(f"[PRE-RESOLVE ⚡] Ready for instant transition: {resolved.get('title')}")
                elif resolved and resolved.get("local_file"):
                    # Queue order changed while resolving; clean up temp file
                    _cleanup_track_temp_file(resolved)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                print(f"[PRE-RESOLVE WARN] Background pre-load error: {e}")

        state.pre_resolve_task = asyncio.create_task(_pre_resolve_worker())

    async def stop_and_cleanup(self, guild_id: int, clear_session: bool = True) -> None:
        """Stops playback, cleans up pre-resolved temp files, deletes the old NP card, and leaves voice."""
        state = self.get_guild_state(guild_id)
        if state.pre_resolve_task and not state.pre_resolve_task.done():
            state.pre_resolve_task.cancel()
        for t in state.queue:
            _cleanup_track_temp_file(t)
        state.queue.clear()
        state.current = None
        state.loop_mode = "off"
        state.suppress_after_callback = True
        if clear_session:
            save_active_session_snapshot(guild_id, state, clear_snapshot=True)
        await self.delete_previous_np_card(state)
        if state.voice_client:
            try:
                await state.voice_client.disconnect()
            except Exception:
                pass
            state.voice_client = None
        await self.update_presence_status()

    async def restore_guild_session(
        self,
        guild: discord.Guild,
        user: discord.Member,
        text_channel: discord.abc.Messageable,
    ) -> tuple[bool, str]:
        """Restores a guild's saved session from slave_data.json into the active queue and starts playing."""
        state = self.get_guild_state(guild.id)
        allowed, reason = check_voice_permission(user, state)
        if not allowed:
            return False, reason

        data = _load_persistent_data()
        sess = data.get("sessions", {}).get(str(guild.id))
        if not sess or not sess.get("tracks"):
            return False, "📭 No interrupted session found to restore on this server."

        voice_channel = user.voice.channel
        if state.voice_client is None or not state.voice_client.is_connected():
            state.voice_client = await voice_channel.connect()
        elif state.voice_client.channel != voice_channel:
            await state.voice_client.move_to(voice_channel)

        state.text_channel = text_channel
        state.loop_mode = sess.get("loop_mode", "off")
        state.autoplay = bool(sess.get("autoplay", False))
        state.normalize_audio = bool(sess.get("normalize_audio", True))
        state.volume = float(sess.get("volume", 0.8))
        state.consecutive_failures = 0

        tracks = sess.get("tracks", [])
        for t in tracks:
            copy_t = dict(t)
            copy_t["requester"] = f"{user.display_name} (Restored)"
            state.queue.append(copy_t)

        if not state.voice_client.is_playing() and not state.voice_client.is_paused():
            await self.play_next(guild.id)
        else:
            self.trigger_pre_resolve(guild.id)

        return True, f"🔄 Restored **{len(tracks)} track(s)** from your previous session!"

    async def update_presence_status(self) -> None:
        """Dynamically updates slave's Discord status to show the currently playing 'Composer - Song'."""
        active_title = None
        for st in self.music_states.values():
            if st.current and st.voice_client and st.voice_client.is_connected():
                active_title = st.current.get("title")
                break
        try:
            if active_title:
                await self.change_presence(
                    activity=discord.Activity(
                        type=discord.ActivityType.listening,
                        name=active_title[:120],
                    )
                )
            else:
                await self.change_presence(activity=None)
        except Exception as e:
            print(f"[PRESENCE WARN] Could not update presence: {e}")

    async def on_ready(self):
        print("=" * 64)
        print(f"slave Music Bot — Version: {BOT_VERSION}")
        print(f"Logged in as: {self.user} (ID: {self.user.id})")
        ffmpeg_path = shutil.which("ffmpeg")
        print(f"FFmpeg installed: {'YES (' + ffmpeg_path + ')' if ffmpeg_path else 'NO! Please install ffmpeg'}")
        js_runtime = shutil.which("deno") or shutil.which("node") or shutil.which("nodejs")
        print(f"JS Runtime (node/deno): {'YES (' + js_runtime + ')' if js_runtime else 'Not found (optional: sudo apt install nodejs)'}")

        try:
            import nacl  # noqa: F401
            print("PyNaCl (voice library) installed: YES")
        except ImportError:
            print("PyNaCl (voice library) installed: NO! Run: pip install PyNaCl")

        print(f"Connected to {len(self.guilds)} server(s):")
        for guild in self.guilds:
            print(f" - {guild.name} (ID: {guild.id}) -> Syncing Hybrid /slave + shortcut commands...")
            try:
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
            except Exception as e:
                print(f"   Failed to sync to {guild.name}: {e}")

        try:
            self.tree.clear_commands(guild=None)
            await self.tree.sync(guild=None)
        except Exception as e:
            print(f"Global cleanup note: {e}")

        # Check for recent interrupted sessions (< 12 hours old) and offer a 1-click restore prompt
        data = _load_persistent_data()
        sessions = data.get("sessions", {})
        now_ts = int(time.time())
        for guild in self.guilds:
            sess = sessions.get(str(guild.id))
            if not sess or not sess.get("tracks"):
                continue
            if (now_ts - int(sess.get("saved_at", 0))) > 43200:
                continue
            tc_id = sess.get("text_channel_id")
            if tc_id:
                ch = guild.get_channel(int(tc_id))
                if ch:
                    tracks = sess["tracks"]
                    first_title = tracks[0].get("title", "Unknown Track")
                    emb = discord.Embed(
                        title=f"🔄 slave {BOT_VERSION} Rebooted — Previous Session Found",
                        description=(
                            f"Found an interrupted queue with **{len(tracks)} track(s)** "
                            f"(starting with **{first_title}**).\n\n"
                            "Join a voice channel and click **🔄 Restore Previous Session** below "
                            "(or run `/slave restore`) to pick up right where you left off!"
                        ),
                        color=discord.Color.green(),
                    )
                    try:
                        await ch.send(embed=emb, view=SessionRestoreView(self, guild.id))
                    except Exception:
                        pass

        print(f"slave {BOT_VERSION} is online and ready!")
        print("=" * 64)

    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        """
        Smart Auto-Pause When Alone:
        - When all human members leave the active voice channel, pauses playback immediately
          and starts a 3-minute countdown before disconnecting.
        - If a human rejoins within 3 minutes, automatically resumes playback!
        """
        guild = member.guild
        state = self.music_states.get(guild.id)
        if not state or not state.voice_client or not state.voice_client.is_connected():
            return

        bot_channel = state.voice_client.channel
        if not bot_channel:
            return

        humans = [m for m in bot_channel.members if not m.bot]
        vc = state.voice_client

        if len(humans) == 0:
            if vc.is_playing():
                vc.pause()
                state.paused_at = time.monotonic()
                state.auto_paused_alone = True
                if state.text_channel:
                    await state.text_channel.send(
                        "⏸️ **Auto-Paused:** Everyone left the voice channel. "
                        "I'll wait 3 minutes before disconnecting."
                    )

            if state.alone_disconnect_task is None or state.alone_disconnect_task.done():
                async def _wait_and_leave():
                    try:
                        await asyncio.sleep(180)
                        if state.voice_client and state.voice_client.is_connected():
                            current_humans = [m for m in state.voice_client.channel.members if not m.bot]
                            if len(current_humans) == 0:
                                await self.stop_and_cleanup(guild.id, clear_session=False)
                                if state.text_channel:
                                    await state.text_channel.send(
                                        "👋 Left the voice channel after 3 minutes of inactivity. "
                                        "*(Use `/slave restore` to resume your queue later!)*"
                                    )
                    except asyncio.CancelledError:
                        pass

                state.alone_disconnect_task = asyncio.create_task(_wait_and_leave())
        else:
            if state.alone_disconnect_task and not state.alone_disconnect_task.done():
                state.alone_disconnect_task.cancel()
                state.alone_disconnect_task = None
            if state.auto_paused_alone and vc.is_paused():
                if state.paused_at is not None:
                    state.started_at += time.monotonic() - state.paused_at
                    state.paused_at = None
                state.auto_paused_alone = False
                vc.resume()
                if state.text_channel:
                    await state.text_channel.send("▶️ **Welcome back!** Resumed playback automatically.")

    async def play_next(self, guild_id: int, seek_seconds: int = 0):
        """
        Plays the next song in the queue (using the pre-resolved stream if ready for 0.0s gap),
        triggers background pre-resolving for the following track, and updates the single player card.
        """
        state = self.get_guild_state(guild_id)

        if state.voice_client is None or not state.voice_client.is_connected():
            state.current = None
            await self.update_presence_status()
            return

        if state.consecutive_failures >= 3:
            state.current = None
            state.consecutive_failures = 0
            await self.update_presence_status()
            if state.text_channel:
                await state.text_channel.send(
                    "⚠️ **Playback Paused (3 failed streams in a row):** "
                    "Your remaining playlist has been preserved so it won't get skipped! "
                    "Please update `yt-dlp` on your Zorin laptop (`pip install -U --pre \"yt-dlp[default,curl-cffi]\"` "
                    "and `sudo apt install -y nodejs`) and restart `slave-bot`."
                )
            return

        next_item = None
        if seek_seconds > 0 and state.current:
            next_item = dict(state.current)
        else:
            if state.current and state.loop_mode != "track":
                state.history.append(dict(state.current))

            if state.loop_mode == "track" and state.current:
                next_item = dict(state.current)
            elif state.queue:
                if state.loop_mode == "queue" and state.current:
                    state.queue.append(
                        {
                            "url": state.current.get("webpage_url") or state.current.get("url"),
                            "video_id": state.current.get("video_id", ""),
                            "title": state.current.get("title", "Unknown Track"),
                            "artist": state.current.get("artist", ""),
                            "track_name": state.current.get("track_name", ""),
                            "duration": state.current.get("duration", 0),
                            "thumbnail": state.current.get("thumbnail", ""),
                            "requester": state.current.get("requester", ""),
                            "source": state.current.get("source", "YouTube"),
                        }
                    )
                next_item = state.queue.popleft()
            elif state.autoplay and (state.current or state.history):
                seed_track = state.current or state.history[-1]
                seed_vid = seed_track.get("video_id", "")
                loop = asyncio.get_running_loop()
                print(f"[AUTOPLAY] Finding related song for: {seed_track.get('title')}")
                radio_candidates = []
                if len(str(seed_vid)) == 11:
                    radio_candidates = await loop.run_in_executor(
                        None, lambda: _fetch_ytmusic_radio_sync(seed_vid)
                    )
                if not radio_candidates and seed_track.get("artist"):
                    radio_candidates = await loop.run_in_executor(
                        None, lambda: _search_ytmusic_innertube_sync(seed_track["artist"], limit=8)
                    )
                recent_titles = {_normalize_for_match(h.get("title", "")) for h in state.history}
                if state.current:
                    recent_titles.add(_normalize_for_match(state.current.get("title", "")))
                for cand in radio_candidates:
                    if _normalize_for_match(cand.get("title", "")) not in recent_titles:
                        cand["requester"] = "📻 Autoplay"
                        next_item = cand
                        break

        if not next_item:
            state.current = None
            state.consecutive_failures = 0
            save_active_session_snapshot(guild_id, state, clear_snapshot=True)
            await self.delete_previous_np_card(state)
            await self.update_presence_status()
            if state.text_channel:
                await state.text_channel.send("✅ Queue finished! Use `/play` or `/slave play` to add more music.")
            return

        # Check if Next-Track Pre-Resolver already resolved this track!
        pre_stream = next_item.pop("_pre_resolved_stream", None)
        pre_at = next_item.pop("_pre_resolved_at", 0.0)
        if seek_seconds == 0 and _is_pre_resolved_stream_valid(pre_stream, pre_at):
            print(f"[ZERO-GAP ⚡] Starting pre-resolved track immediately: {pre_stream.get('title')}")
            stream_info = pre_stream
            if next_item.get("requester"):
                stream_info["requester"] = next_item["requester"]
        else:
            stream_info = await resolve_stream(next_item)

        if not stream_info:
            state.consecutive_failures += 1
            if state.text_channel:
                await state.text_channel.send(
                    f"⚠️ Could not load audio for **{next_item.get('title', 'track')}**, skipping..."
                )
            await self.play_next(guild_id)
            return

        state.current = stream_info
        save_active_session_snapshot(guild_id, state)

        try:
            source = await build_audio_source(
                stream_info["stream_url"],
                state.volume,
                state.voice_client,
                seek_seconds=seek_seconds,
                http_headers=stream_info.get("http_headers"),
                local_file=stream_info.get("local_file"),
                normalize_audio=state.normalize_audio,
            )
        except Exception as e:
            print(f"[FFMPEG ERROR] {e}")
            state.consecutive_failures += 1
            if state.text_channel:
                await state.text_channel.send(
                    f"⚠️ Audio pipeline error on **{stream_info['title']}**, skipping..."
                )
            await self.play_next(guild_id)
            return

        state.started_at = time.monotonic()
        state.seek_offset = float(seek_seconds)
        state.paused_at = None
        state.user_skipped = False

        def after_playing(error):
            if error:
                print(f"[PLAYER ERROR] {error}")
            if state.suppress_after_callback:
                state.suppress_after_callback = False
                return

            play_duration = time.monotonic() - state.started_at
            if not state.user_skipped and play_duration < 4.0 and seek_seconds == 0:
                state.consecutive_failures += 1
                print(
                    f"[PLAYER WARN] Track ended prematurely after {play_duration:.1f}s "
                    f"(failure #{state.consecutive_failures})"
                )
            else:
                state.consecutive_failures = 0

            asyncio.run_coroutine_threadsafe(self.play_next(guild_id), self.loop)

        state.voice_client.play(source, after=after_playing)
        await self.update_presence_status()

        # Trigger background pre-resolver for the next track in queue
        self.trigger_pre_resolve(guild_id)

        if state.text_channel and seek_seconds == 0:
            await self.send_single_np_card(guild_id, "🎶 Now Playing")


bot = SlaveBot()


# =====================================================================
# LIVE SLASH-COMMAND AUTOCOMPLETE (SONGS & SAVED SERVER PLAYLISTS)
# =====================================================================
async def play_query_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    """
    Live autocomplete dropdown for `/play`, `/slave play`, and `/slave playnext`:
    - Ignores URLs (`http://` or `https://`) so pasting links is never interrupted.
    - When empty, suggests the user's liked songs or recent server history.
    - As the user types, queries YouTube Music InnerTube with a 2.2s timeout and TTL cache.
    """
    q = current.strip()
    if q.startswith(("http://", "https://", "www.", "open.spotify.com")):
        return []

    if len(q) < 2:
        suggestions: list[app_commands.Choice[str]] = []
        seen: set[str] = set()
        data = _load_persistent_data()
        user_likes = data.get("likes", {}).get(str(interaction.user.id), [])
        for lk in reversed(user_likes[-5:]):
            t_title = lk.get("title", "")
            if t_title and t_title not in seen:
                seen.add(t_title)
                dur = format_seconds(lk.get("duration"))
                label = f"❤️ {t_title} [{dur}]"[:100]
                suggestions.append(app_commands.Choice(name=label, value=t_title[:100]))

        if interaction.guild_id and len(suggestions) < 5:
            state = bot.get_guild_state(interaction.guild_id)
            for h in reversed(list(state.history)):
                t_title = h.get("title", "")
                if t_title and t_title not in seen:
                    seen.add(t_title)
                    dur = format_seconds(h.get("duration"))
                    label = f"🕒 {t_title} [{dur}]"[:100]
                    suggestions.append(app_commands.Choice(name=label, value=t_title[:100]))
                    if len(suggestions) >= 5:
                        break
        return suggestions[:5]

    loop = asyncio.get_running_loop()
    try:
        results = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: _search_ytmusic_innertube_sync(q, limit=5)),
            timeout=2.2,
        )
    except Exception:
        return []

    choices: list[app_commands.Choice[str]] = []
    for item in results[:5]:
        title = item.get("title", "Unknown Track")
        dur = format_seconds(item.get("duration"))
        display_name = f"🎵 {title} [{dur}]"
        if len(display_name) > 100:
            display_name = display_name[:97] + "..."
        choices.append(app_commands.Choice(name=display_name, value=title[:100]))
    return choices


async def saved_playlist_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    """Live autocomplete dropdown for `/slave load` and `/slave deletesaved`."""
    if not interaction.guild_id:
        return []
    data = _load_persistent_data()
    guild_pl = data.get("playlists", {}).get(str(interaction.guild_id), {})
    q = current.strip().lower()
    choices: list[app_commands.Choice[str]] = []
    for name, tracks in guild_pl.items():
        if not q or q in name.lower():
            label = f"💾 {name} ({len(tracks)} tracks)"[:100]
            choices.append(app_commands.Choice(name=label, value=name[:100]))
            if len(choices) >= 25:
                break
    return choices


# =====================================================================
# SHARED QUEUE HELPER (HANDLES EXACT MATCHES & "DID YOU MEAN?" PROMPTS)
# =====================================================================
async def handle_queue_tracks(
    guild: discord.Guild,
    user: discord.Member,
    text_channel: discord.abc.Messageable,
    query: str,
    play_next_flag: bool = False,
) -> tuple[str | None, discord.Embed | None, discord.ui.View | None]:
    """
    Connects to the user's voice channel, resolves `query`, and either:
      - Queues the matched song/playlist formatted as 'Composer - Song Title', OR
      - Returns a 'Did you mean?' suggestion card with clickable buttons if the song wasn't found.
    """
    state = bot.get_guild_state(guild.id)

    allowed, reason = check_voice_permission(user, state)
    if not allowed:
        return reason, None, None

    voice_channel = user.voice.channel
    try:
        if state.voice_client is None or not state.voice_client.is_connected():
            state.voice_client = await voice_channel.connect()
        elif state.voice_client.channel != voice_channel:
            await state.voice_client.move_to(voice_channel)
    except Exception as e:
        return f"❌ Failed to join voice channel: `{e}`", None, None

    state.text_channel = text_channel
    state.consecutive_failures = 0

    tracks, suggestions = await extract_entries(query)
    if not tracks:
        if suggestions:
            lines = [
                f"I couldn't find an exact match for **`{query}`**.",
                "",
                "**Did you mean one of these songs?** *(Click a button below to play it)*:",
            ]
            for idx, cand in enumerate(suggestions[:5], start=1):
                badge = format_source_badge(cand.get("source", "YouTube"), compact=True)
                dur = format_seconds(cand.get("duration"))
                lines.append(f"`{idx}.` **[{badge}]** {cand.get('title', 'Unknown')} `[{dur}]`")

            embed = discord.Embed(
                title="🔎 Song Not Found — Did You Mean?",
                description="\n".join(lines),
                color=discord.Color.orange(),
            )
            view = SearchSuggestionsView(bot, guild.id, suggestions[:5], play_next_flag=play_next_flag)
            return None, embed, view

        return (
            f"❌ Could not find any song matching **`{query}`** on YouTube Music, Spotify, or YouTube.",
            None,
            None,
        )

    for t in tracks:
        t["requester"] = user.display_name

    if play_next_flag:
        for t in reversed(tracks):
            state.queue.appendleft(t)
        if len(tracks) == 1:
            t = tracks[0]
            badge = format_source_badge(t.get("source", "YouTube"))
            dur = format_seconds(t.get("duration"))
            msg = f"⏭️ Queued **[{badge}] {t['title']}** `[{dur}]` at **#1 (Up Next)**!"
        else:
            badge = format_source_badge(tracks[0].get("source", "YouTube"))
            msg = f"⏭️ Inserted **{len(tracks)} tracks** from **{badge}** at the front of the playlist!"
    else:
        for t in tracks:
            state.queue.append(t)
        if len(tracks) == 1:
            t = tracks[0]
            badge = format_source_badge(t.get("source", "YouTube"))
            dur = format_seconds(t.get("duration"))
            msg = f"✅ Added **[{badge}] {t['title']}** `[{dur}]` to the playlist (`#{len(state.queue)}`)."
        else:
            badge = format_source_badge(tracks[0].get("source", "YouTube"))
            msg = f"📜 Added **{len(tracks)} tracks** from **{badge}** to the playlist."

    save_active_session_snapshot(guild.id, state)

    if not state.voice_client.is_playing() and not state.voice_client.is_paused():
        await bot.play_next(guild.id)
    else:
        bot.trigger_pre_resolve(guild.id)

    return msg, None, None


# =====================================================================
# UNIFIED /slave SLASH COMMAND GROUP (MAX 25 SUBCOMMANDS IN DISCORD)
# =====================================================================
class SafeSlaveGroup(app_commands.Group):
    """
    A crash-proof subclass of discord.app_commands.Group that:
    1. Automatically overwrites any duplicate command name instead of crashing.
    2. Never raises 'ValueError: maximum number of child commands exceeded' even if
       a file is accidentally pasted twice.
    """

    def add_command(self, command: app_commands.Command | app_commands.Group, *, override: bool = True):
        if command.name in self._children:
            super().add_command(command, override=True)
            return
        if len(self._children) >= 25:
            print(
                f"[COMMAND GROUP WARN] Skipping /{self.name} {command.name} because "
                "Discord allows a maximum of 25 subcommands per group."
            )
            return
        super().add_command(command, override=override)


slave_group = SafeSlaveGroup(
    name="slave",
    description="Control the slave music bot (1. YouTube Music -> 2. Spotify -> 3. YouTube)",
)


@slave_group.command(
    name="play",
    description="Play a song ('Composer - Title') or URL/playlist (with live YouTube Music autocomplete)",
)
@app_commands.describe(query="Song name (e.g. 'Daft Punk - Revolution 909') or URL")
@app_commands.autocomplete(query=play_query_autocomplete)
async def slave_play(interaction: discord.Interaction, query: str):
    state = bot.get_guild_state(interaction.guild_id)
    allowed, reason = check_voice_permission(interaction.user, state)
    if not allowed:
        await interaction.response.send_message(reason, ephemeral=True)
        return

    await interaction.response.defer(thinking=True)
    msg, embed, view = await handle_queue_tracks(
        interaction.guild, interaction.user, interaction.channel, query, play_next_flag=False
    )
    if embed and view:
        await interaction.followup.send(embed=embed, view=view)
    else:
        await interaction.followup.send(msg or "❌ Unexpected error.")


@slave_group.command(
    name="playnext",
    description="Insert a song or URL right at #1 so it plays immediately after the current track",
)
@app_commands.describe(query="Song name or URL to play next")
@app_commands.autocomplete(query=play_query_autocomplete)
async def slave_playnext(interaction: discord.Interaction, query: str):
    state = bot.get_guild_state(interaction.guild_id)
    allowed, reason = check_voice_permission(interaction.user, state)
    if not allowed:
        await interaction.response.send_message(reason, ephemeral=True)
        return

    await interaction.response.defer(thinking=True)
    msg, embed, view = await handle_queue_tracks(
        interaction.guild, interaction.user, interaction.channel, query, play_next_flag=True
    )
    if embed and view:
        await interaction.followup.send(embed=embed, view=view)
    else:
        await interaction.followup.send(msg or "❌ Unexpected error.")


@slave_group.command(name="move", description="Move a song from one position in the playlist to another")
@app_commands.describe(
    from_pos="Current track number in /slave playlist (e.g. 8)",
    to_pos="New position number in /slave playlist (e.g. 1)",
)
async def slave_move(interaction: discord.Interaction, from_pos: int, to_pos: int):
    state = bot.get_guild_state(interaction.guild_id)
    allowed, reason = check_voice_permission(interaction.user, state)
    if not allowed:
        await interaction.response.send_message(reason, ephemeral=True)
        return

    q_len = len(state.queue)
    if q_len < 2:
        await interaction.response.send_message("❌ Need at least 2 tracks in the playlist to move songs.", ephemeral=True)
        return
    if from_pos < 1 or from_pos > q_len or to_pos < 1 or to_pos > q_len:
        await interaction.response.send_message(f"❌ Positions must be between `1` and `{q_len}`.", ephemeral=True)
        return
    if from_pos == to_pos:
        await interaction.response.send_message("ℹ️ Track is already at that position.", ephemeral=True)
        return

    temp = list(state.queue)
    moved_track = temp.pop(from_pos - 1)
    temp.insert(to_pos - 1, moved_track)
    state.queue = deque(temp)
    bot.trigger_pre_resolve(interaction.guild_id)
    save_active_session_snapshot(interaction.guild_id, state)

    await interaction.response.send_message(
        f"↕️ Moved **{moved_track['title']}** from `#{from_pos}` to `#{to_pos}`!"
    )


@slave_group.command(name="playlist", description="View the playlist with interactive page buttons (open to everyone)")
@app_commands.describe(page="Page number to view (default: 1)")
async def slave_playlist(interaction: discord.Interaction, page: int = 1):
    state = bot.get_guild_state(interaction.guild_id)
    if not state.current and not state.queue:
        await interaction.response.send_message("📭 The playlist is currently empty.")
        return
    embed, actual_page, _ = build_playlist_embed(state, page)
    view = PlaylistPaginatorView(state, initial_page=actual_page)
    await interaction.response.send_message(embed=embed, view=view)


@slave_group.command(name="seek", description="Jump to a timestamp in the current song (e.g. 1:30 or 0:00)")
@app_commands.describe(timestamp="Timestamp like '1:30', '0:00', or seconds like '90'")
async def slave_seek(interaction: discord.Interaction, timestamp: str):
    state = bot.get_guild_state(interaction.guild_id)
    allowed, reason = check_voice_permission(interaction.user, state)
    if not allowed:
        await interaction.response.send_message(reason, ephemeral=True)
        return
    if not state.current or not state.voice_client:
        await interaction.response.send_message("❌ Nothing is playing right now.", ephemeral=True)
        return

    target_sec = parse_duration_str(timestamp)
    dur = int(state.current.get("duration") or 0)
    if dur > 0 and target_sec >= dur:
        await interaction.response.send_message(
            f"❌ Timestamp `{format_seconds(target_sec)}` is past the song duration (`{format_seconds(dur)}`).",
            ephemeral=True,
        )
        return

    await interaction.response.defer()
    state.suppress_after_callback = True
    if state.voice_client.is_playing() or state.voice_client.is_paused():
        if isinstance(state.voice_client.source, SteadyOpusSource):
            state.voice_client.source.keep_local_file = True
        state.voice_client.stop()
    await bot.play_next(interaction.guild_id, seek_seconds=target_sec)
    await interaction.followup.send(
        f"⏩ Jumped to **`{format_seconds(target_sec)}`** in **{state.current['title']}**!"
    )


@slave_group.command(name="previous", description="Jump back to the previously played track")
async def slave_previous(interaction: discord.Interaction):
    state = bot.get_guild_state(interaction.guild_id)
    allowed, reason = check_voice_permission(interaction.user, state)
    if not allowed:
        await interaction.response.send_message(reason, ephemeral=True)
        return
    if not state.history:
        await interaction.response.send_message("❌ No previous tracks in history yet.", ephemeral=True)
        return

    prev_track = state.history.pop()
    if state.current:
        state.queue.appendleft(dict(state.current))
    state.queue.appendleft(prev_track)

    await interaction.response.send_message(f"⏮️ Returning to previous track: **{prev_track['title']}**...")
    if state.voice_client and (state.voice_client.is_playing() or state.voice_client.is_paused()):
        state.user_skipped = True
        state.voice_client.stop()
    else:
        await bot.play_next(interaction.guild_id)


@slave_group.command(name="autoplay", description="Toggle Autoplay Radio mode when the playlist runs out")
async def slave_autoplay(interaction: discord.Interaction):
    state = bot.get_guild_state(interaction.guild_id)
    allowed, reason = check_voice_permission(interaction.user, state)
    if not allowed:
        await interaction.response.send_message(reason, ephemeral=True)
        return
    state.autoplay = not state.autoplay
    save_active_session_snapshot(interaction.guild_id, state)
    status = "📻 **ENABLED**" if state.autoplay else "📴 **DISABLED**"
    await interaction.response.send_message(
        f"{status} Autoplay mode! When the queue ends, I will automatically play related songs."
    )


@slave_group.command(name="restore", description="Restore and resume the last interrupted queue after a reboot")
async def slave_restore(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    ok, msg = await bot.restore_guild_session(interaction.guild, interaction.user, interaction.channel)
    await interaction.followup.send(msg)


@slave_group.command(name="removedupes", description="Remove duplicate songs from the upcoming playlist")
async def slave_removedupes(interaction: discord.Interaction):
    state = bot.get_guild_state(interaction.guild_id)
    allowed, reason = check_voice_permission(interaction.user, state)
    if not allowed:
        await interaction.response.send_message(reason, ephemeral=True)
        return
    if not state.queue:
        await interaction.response.send_message("📭 The playlist is empty.", ephemeral=True)
        return

    seen: set[str] = set()
    deduped: list[dict] = []
    removed = 0
    for item in state.queue:
        key = _normalize_for_match(item.get("title", "")) or item.get("url", "")
        if key in seen:
            _cleanup_track_temp_file(item)
            removed += 1
        else:
            seen.add(key)
            deduped.append(item)

    state.queue = deque(deduped)
    bot.trigger_pre_resolve(interaction.guild_id)
    save_active_session_snapshot(interaction.guild_id, state)
    await interaction.response.send_message(
        f"🧹 Removed **{removed}** duplicate track(s). (`{len(state.queue)}` tracks remaining)"
    )


@slave_group.command(name="lyrics", description="Fetch lyrics for the current song or a song query (open to everyone)")
@app_commands.describe(query="Optional song name (leave empty for the currently playing track)")
async def slave_lyrics(interaction: discord.Interaction, query: str | None = None):
    state = bot.get_guild_state(interaction.guild_id)
    artist_hint = ""
    track_hint = ""
    if not query:
        if not state.current:
            await interaction.response.send_message(
                "❌ Nothing is playing right now. Provide a song title: `/slave lyrics [song]`.",
                ephemeral=True,
            )
            return
        query = state.current.get("title", "")
        artist_hint = state.current.get("artist", "")
        track_hint = state.current.get("track_name", "")

    await interaction.response.defer(thinking=True)
    loop = asyncio.get_running_loop()
    res = await loop.run_in_executor(
        None, lambda: _fetch_lyrics_sync(query, artist_hint, track_hint)
    )
    if not res:
        await interaction.followup.send(f"❌ Could not find lyrics for **`{query}`**.")
        return

    lyrics_text = res["lyrics"]
    if len(lyrics_text) <= 3800:
        embed = discord.Embed(
            title=f"📜 Lyrics — {res['title']}",
            description=lyrics_text,
            color=discord.Color.gold(),
        )
        if res.get("album"):
            embed.set_footer(text=f"Album: {res['album']}")
        await interaction.followup.send(embed=embed)
    else:
        buf = io.BytesIO(lyrics_text.encode("utf-8"))
        await interaction.followup.send(
            content=f"📜 **Full Lyrics — {res['title']}:**",
            file=discord.File(buf, filename="lyrics.txt"),
        )


@slave_group.command(
    name="save",
    description="Save current queue as a server playlist (or type 'list' to view saved playlists)",
)
@app_commands.describe(name="Name for this saved playlist (or type 'list' to see all saved playlists)")
async def slave_save(interaction: discord.Interaction, name: str):
    clean_name = name.strip().lower()[:50]
    data = _load_persistent_data()
    guild_pl = data.setdefault("playlists", {}).setdefault(str(interaction.guild_id), {})

    if clean_name == "list":
        if not guild_pl:
            await interaction.response.send_message(
                "📭 No saved playlists on this server yet. Save one with `/slave save [name]`!"
            )
            return
        lines = [f"• **`{p_name}`** — `{len(tracks)} track(s)`" for p_name, tracks in guild_pl.items()]
        embed = discord.Embed(
            title="💾 Saved Server Playlists",
            description="\n".join(lines),
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed)
        return

    state = bot.get_guild_state(interaction.guild_id)
    allowed, reason = check_voice_permission(interaction.user, state)
    if not allowed:
        await interaction.response.send_message(reason, ephemeral=True)
        return

    tracks_to_save: list[dict] = []
    if state.current:
        tracks_to_save.append(_serialize_track_for_storage(state.current))
    for item in state.queue:
        tracks_to_save.append(_serialize_track_for_storage(item))

    if not tracks_to_save:
        await interaction.response.send_message("❌ Nothing is playing or queued to save.", ephemeral=True)
        return

    guild_pl[clean_name] = tracks_to_save
    _save_persistent_data(data)

    await interaction.response.send_message(
        f"💾 Saved playlist **`{clean_name}`** with **{len(tracks_to_save)} track(s)**! "
        f"Load it anytime with `/slave load {clean_name}` (or view all with `/slave save list`)."
    )


@slave_group.command(
    name="load",
    description="Load and play a saved server playlist (with live autocomplete, or 'list' to view all)",
)
@app_commands.describe(name="Name of the saved playlist to load (or 'list' to view all)")
@app_commands.autocomplete(name=saved_playlist_autocomplete)
async def slave_load(interaction: discord.Interaction, name: str):
    clean_name = name.strip().lower()
    data = _load_persistent_data()
    guild_pl = data.get("playlists", {}).get(str(interaction.guild_id), {})

    if clean_name == "list":
        if not guild_pl:
            await interaction.response.send_message(
                "📭 No saved playlists on this server yet. Save one with `/slave save [name]`!"
            )
            return
        lines = [f"• **`{p_name}`** — `{len(tracks)} track(s)`" for p_name, tracks in guild_pl.items()]
        embed = discord.Embed(
            title="💾 Saved Server Playlists",
            description="\n".join(lines),
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed)
        return

    state = bot.get_guild_state(interaction.guild_id)
    allowed, reason = check_voice_permission(interaction.user, state)
    if not allowed:
        await interaction.response.send_message(reason, ephemeral=True)
        return

    if clean_name not in guild_pl:
        available = ", ".join(f"`{k}`" for k in guild_pl.keys()) or "*None saved yet*"
        await interaction.response.send_message(
            f"❌ Saved playlist **`{clean_name}`** not found. Available playlists: {available}",
            ephemeral=True,
        )
        return

    saved_tracks = guild_pl[clean_name]
    voice_channel = interaction.user.voice.channel
    if state.voice_client is None or not state.voice_client.is_connected():
        state.voice_client = await voice_channel.connect()
    elif state.voice_client.channel != voice_channel:
        await state.voice_client.move_to(voice_channel)

    state.text_channel = interaction.channel
    state.consecutive_failures = 0
    for t in saved_tracks:
        copy_t = dict(t)
        copy_t["requester"] = interaction.user.display_name
        state.queue.append(copy_t)

    save_active_session_snapshot(interaction.guild_id, state)
    await interaction.response.send_message(
        f"📂 Loaded **{len(saved_tracks)} track(s)** from saved playlist **`{clean_name}`**!"
    )
    if not state.voice_client.is_playing() and not state.voice_client.is_paused():
        await bot.play_next(interaction.guild_id)
    else:
        bot.trigger_pre_resolve(interaction.guild_id)


@slave_group.command(name="deletesaved", description="Delete a saved server playlist")
@app_commands.describe(name="Name of the saved playlist to delete")
@app_commands.autocomplete(name=saved_playlist_autocomplete)
async def slave_deletesaved(interaction: discord.Interaction, name: str):
    state = bot.get_guild_state(interaction.guild_id)
    allowed, reason = check_voice_permission(interaction.user, state)
    if not allowed:
        await interaction.response.send_message(reason, ephemeral=True)
        return

    clean_name = name.strip().lower()
    data = _load_persistent_data()
    guild_pl = data.get("playlists", {}).get(str(interaction.guild_id), {})
    if clean_name not in guild_pl:
        await interaction.response.send_message(f"❌ Saved playlist **`{clean_name}`** not found.", ephemeral=True)
        return
    del guild_pl[clean_name]
    _save_persistent_data(data)
    await interaction.response.send_message(f"🗑️ Deleted saved playlist **`{clean_name}`**.")


@slave_group.command(name="like", description="Heart/save the currently playing song to your personal favorites")
async def slave_like(interaction: discord.Interaction):
    state = bot.get_guild_state(interaction.guild_id)
    if not state.current:
        await interaction.response.send_message("❌ Nothing is playing right now to like.", ephemeral=True)
        return
    _, msg = save_liked_track_for_user(interaction.user.id, state.current)
    await interaction.response.send_message(msg, ephemeral=True)


@slave_group.command(name="playlikes", description="Queue all songs from your personal liked songs list")
async def slave_playlikes(interaction: discord.Interaction):
    state = bot.get_guild_state(interaction.guild_id)
    allowed, reason = check_voice_permission(interaction.user, state)
    if not allowed:
        await interaction.response.send_message(reason, ephemeral=True)
        return

    data = _load_persistent_data()
    user_likes = data.get("likes", {}).get(str(interaction.user.id), [])
    if not user_likes:
        await interaction.response.send_message(
            "💔 You don't have any liked songs yet! Click **❤️ Like** or run `/slave like` while a song is playing.",
            ephemeral=True,
        )
        return

    voice_channel = interaction.user.voice.channel
    if state.voice_client is None or not state.voice_client.is_connected():
        state.voice_client = await voice_channel.connect()
    elif state.voice_client.channel != voice_channel:
        await state.voice_client.move_to(voice_channel)

    state.text_channel = interaction.channel
    state.consecutive_failures = 0
    for t in user_likes:
        copy_t = dict(t)
        copy_t["requester"] = interaction.user.display_name
        state.queue.append(copy_t)

    save_active_session_snapshot(interaction.guild_id, state)
    await interaction.response.send_message(
        f"❤️ Queued **{len(user_likes)}** song(s) from **{interaction.user.display_name}**'s liked tracks!"
    )
    if not state.voice_client.is_playing() and not state.voice_client.is_paused():
        await bot.play_next(interaction.guild_id)
    else:
        bot.trigger_pre_resolve(interaction.guild_id)


@slave_group.command(name="clear", description="Clear all upcoming tracks from the playlist")
async def slave_clear(interaction: discord.Interaction):
    state = bot.get_guild_state(interaction.guild_id)
    allowed, reason = check_voice_permission(interaction.user, state)
    if not allowed:
        await interaction.response.send_message(reason, ephemeral=True)
        return
    if state.pre_resolve_task and not state.pre_resolve_task.done():
        state.pre_resolve_task.cancel()
    count = len(state.queue)
    for t in state.queue:
        _cleanup_track_temp_file(t)
    state.queue.clear()
    save_active_session_snapshot(interaction.guild_id, state)
    await interaction.response.send_message(f"🗑️ Cleared **{count}** upcoming track(s) from the playlist.")


@slave_group.command(name="shuffle", description="Randomly shuffle the current playlist")
async def slave_shuffle(interaction: discord.Interaction):
    state = bot.get_guild_state(interaction.guild_id)
    allowed, reason = check_voice_permission(interaction.user, state)
    if not allowed:
        await interaction.response.send_message(reason, ephemeral=True)
        return
    if len(state.queue) < 2:
        await interaction.response.send_message("❌ Need at least 2 tracks in the playlist to shuffle.", ephemeral=True)
        return
    temp = list(state.queue)
    random.shuffle(temp)
    state.queue = deque(temp)
    bot.trigger_pre_resolve(interaction.guild_id)
    save_active_session_snapshot(interaction.guild_id, state)
    await interaction.response.send_message(f"🔀 Shuffled **{len(state.queue)}** tracks in the playlist!")


@slave_group.command(name="pause", description="Pause or resume the currently playing song")
async def slave_pause(interaction: discord.Interaction):
    state = bot.get_guild_state(interaction.guild_id)
    allowed, reason = check_voice_permission(interaction.user, state)
    if not allowed:
        await interaction.response.send_message(reason, ephemeral=True)
        return
    if state.voice_client and state.voice_client.is_playing():
        state.voice_client.pause()
        state.paused_at = time.monotonic()
        await interaction.response.send_message("⏸️ Paused playback. *(Run `/slave pause` again to resume)*")
    elif state.voice_client and state.voice_client.is_paused():
        if state.paused_at is not None:
            state.started_at += time.monotonic() - state.paused_at
            state.paused_at = None
        state.auto_paused_alone = False
        state.voice_client.resume()
        await interaction.response.send_message("▶️ Resumed playback.")
    else:
        await interaction.response.send_message("❌ Nothing is currently playing.", ephemeral=True)


@slave_group.command(name="skip", description="Skip current song, or jump to a specific track number in the playlist")
@app_commands.describe(position="Optional track number from /playlist to jump to (1, 2, 3...)")
async def slave_skip(interaction: discord.Interaction, position: int | None = None):
    state = bot.get_guild_state(interaction.guild_id)
    allowed, reason = check_voice_permission(interaction.user, state)
    if not allowed:
        await interaction.response.send_message(reason, ephemeral=True)
        return

    if position is not None:
        if position < 1 or position > len(state.queue):
            await interaction.response.send_message(
                f"❌ Invalid position. Enter a number between 1 and {len(state.queue)}.", ephemeral=True
            )
            return
        for _ in range(position - 1):
            discarded = state.queue.popleft()
            _cleanup_track_temp_file(discarded)
        target = state.queue[0]["title"]
        state.consecutive_failures = 0
        if state.voice_client and (state.voice_client.is_playing() or state.voice_client.is_paused()):
            state.user_skipped = True
            state.voice_client.stop()
        else:
            await bot.play_next(interaction.guild_id)
        await interaction.response.send_message(f"⏭️ Jumped to **#{position}: {target}**!")
        return

    if state.voice_client and (state.voice_client.is_playing() or state.voice_client.is_paused()):
        skipped_title = state.current["title"] if state.current else "current track"
        state.user_skipped = True
        state.voice_client.stop()
        await interaction.response.send_message(f"⏭️ Skipped **{skipped_title}**.")
    else:
        await interaction.response.send_message("❌ Nothing is playing right now.", ephemeral=True)


@slave_group.command(name="remove", description="Remove a specific song from the playlist by its number")
@app_commands.describe(position="Track number in /playlist to remove (1, 2, 3...)")
async def slave_remove(interaction: discord.Interaction, position: int):
    state = bot.get_guild_state(interaction.guild_id)
    allowed, reason = check_voice_permission(interaction.user, state)
    if not allowed:
        await interaction.response.send_message(reason, ephemeral=True)
        return
    if position < 1 or position > len(state.queue):
        await interaction.response.send_message(
            f"❌ Invalid position. Enter a number between 1 and {len(state.queue)}.", ephemeral=True
        )
        return
    temp = list(state.queue)
    removed = temp.pop(position - 1)
    _cleanup_track_temp_file(removed)
    state.queue = deque(temp)
    bot.trigger_pre_resolve(interaction.guild_id)
    save_active_session_snapshot(interaction.guild_id, state)
    await interaction.response.send_message(f"🗑️ Removed **#{position}: {removed['title']}** from the playlist.")


@slave_group.command(name="loop", description="Set loop mode (off, single track, or whole playlist)")
@app_commands.describe(mode="Choose 'off', 'track', or 'queue'")
@app_commands.choices(
    mode=[
        app_commands.Choice(name="Off (Normal)", value="off"),
        app_commands.Choice(name="Single Track", value="track"),
        app_commands.Choice(name="Whole Playlist", value="queue"),
    ]
)
async def slave_loop(interaction: discord.Interaction, mode: app_commands.Choice[str]):
    state = bot.get_guild_state(interaction.guild_id)
    allowed, reason = check_voice_permission(interaction.user, state)
    if not allowed:
        await interaction.response.send_message(reason, ephemeral=True)
        return
    state.loop_mode = mode.value
    save_active_session_snapshot(interaction.guild_id, state)
    labels = {"off": "⏹️ Loop disabled.", "track": "🔂 Looping current track.", "queue": "🔁 Looping whole playlist."}
    await interaction.response.send_message(labels[mode.value])


@slave_group.command(name="volume", description="Set playback volume (1 to 200%)")
@app_commands.describe(level="Volume percentage between 1 and 200")
async def slave_volume(interaction: discord.Interaction, level: int):
    state = bot.get_guild_state(interaction.guild_id)
    allowed, reason = check_voice_permission(interaction.user, state)
    if not allowed:
        await interaction.response.send_message(reason, ephemeral=True)
        return
    if level < 1 or level > 200:
        await interaction.response.send_message("❌ Please choose a volume between 1 and 200.", ephemeral=True)
        return
    state.volume = level / 100.0
    save_active_session_snapshot(interaction.guild_id, state)
    await interaction.response.send_message(
        f"🔊 Volume set to **{level}%** *(applies to the next track or `/slave seek`)*."
    )


@slave_group.command(name="nowplaying", description="Show the rich Now Playing card with progress bar & controls")
async def slave_nowplaying(interaction: discord.Interaction):
    state = bot.get_guild_state(interaction.guild_id)
    if not state.current:
        await interaction.response.send_message("📭 Nothing is playing right now.")
        return
    await state.bot_instance_delete_np(state) if hasattr(state, "bot_instance_delete_np") else await bot.delete_previous_np_card(state)
    embed = build_now_playing_embed(state)
    view = NowPlayingControlView(bot, interaction.guild_id)
    await interaction.response.send_message(embed=embed, view=view)
    try:
        state.last_np_message = await interaction.original_response()
    except Exception:
        pass


@slave_group.command(name="stop", description="Stop playback, clear the playlist, and leave voice")
async def slave_stop(interaction: discord.Interaction):
    state = bot.get_guild_state(interaction.guild_id)
    allowed, reason = check_voice_permission(interaction.user, state)
    if not allowed:
        await interaction.response.send_message(reason, ephemeral=True)
        return
    await bot.stop_and_cleanup(interaction.guild_id, clear_session=True)
    await interaction.response.send_message("⏹️ Stopped playback, cleared playlist, and left the voice channel.")


@slave_group.command(name="help", description="List all available /slave and shortcut commands (open to everyone)")
async def slave_help(interaction: discord.Interaction):
    help_text = (
        f"🎵 **slave Music Bot Commands (`{BOT_VERSION}` — Hybrid Style 1):**\n"
        "*Search Priority: 1. YouTube Music → 2. Spotify → 3. YouTube (Displayed as `Composer - Song`)*\n\n"
        "⚡ **Fast Top-Level Shortcuts:**\n"
        "• `/play [song or url]` — Play with live YouTube Music autocomplete *(Voice Only)*\n"
        "• `/skip [position]` — Skip current song or jump to `#` *(Voice Only)*\n"
        "• `/playlist [page]` — Interactive playlist + **Full Scrollable List** *(Everyone)*\n"
        "• `/np` — Single clean Now Playing card with progress bar & 10 buttons *(Everyone)*\n\n"
        "🛠️ **Full `/slave` Suite:**\n"
        "• `/slave play` & `/slave playnext` — Queue song/playlist (with live autocomplete)\n"
        "• `/slave move [from] [to]` — Move a song in the playlist, e.g. `/slave move 8 1`\n"
        "• `/slave seek [mm:ss]` / `/slave previous` / `/slave pause` / `/slave loop` / `/slave volume`\n"
        "• `/slave autoplay` — Toggle endless related-songs radio mode\n"
        "• `/slave restore` — Restore interrupted session after a bot or laptop reboot\n"
        "• `/slave save [name]`, `/slave load [name]`, `/slave deletesaved [name]` — Custom server playlists\n"
        "• `/slave like` & `/slave playlikes` — Save favorite songs & queue all your likes\n"
        "• `/slave lyrics [song]` — View full song lyrics *(Everyone)*\n"
        "• `/slave removedupes` / `/slave clear` / `/slave shuffle` / `/slave remove [#]` / `/slave stop`"
    )
    await interaction.response.send_message(help_text)


bot.tree.add_command(slave_group, override=True)


# =====================================================================
# HYBRID STYLE 1: FAST TOP-LEVEL SHORTCUT COMMANDS (/play, /skip, /playlist, /np)
# =====================================================================
@bot.tree.command(
    name="play",
    description="Fast shortcut for /slave play (with live YouTube Music autocomplete)",
)
@app_commands.describe(query="Song name (e.g. 'Daft Punk - Revolution 909') or URL")
@app_commands.autocomplete(query=play_query_autocomplete)
async def shortcut_play(interaction: discord.Interaction, query: str):
    await slave_play.callback(interaction, query)


@bot.tree.command(
    name="skip",
    description="Fast shortcut for /slave skip (skip current track or jump to track #)",
)
@app_commands.describe(position="Optional track number from /playlist to jump to (1, 2, 3...)")
async def shortcut_skip(interaction: discord.Interaction, position: int | None = None):
    await slave_skip.callback(interaction, position)


@bot.tree.command(
    name="playlist",
    description="Fast shortcut for /slave playlist (interactive queue + scrollable full list)",
)
@app_commands.describe(page="Page number to view (default: 1)")
async def shortcut_playlist(interaction: discord.Interaction, page: int = 1):
    await slave_playlist.callback(interaction, page)


@bot.tree.command(
    name="np",
    description="Fast shortcut for /slave nowplaying (rich player card & buttons)",
)
async def shortcut_np(interaction: discord.Interaction):
    await slave_nowplaying.callback(interaction)


# =====================================================================
# CHAT FALLBACK: ALLOWS "/slave ..." OR "!slave ..." IN TEXT CHAT
# =====================================================================
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return

    raw = message.content.strip()
    if not raw.lower().startswith(("/slave", "!slave")):
        return

    remainder = raw[6:].strip()
    state = bot.get_guild_state(message.guild.id)

    if not remainder or remainder.lower() == "help":
        await message.channel.send(
            f"🎵 **slave (`{BOT_VERSION}`)** — Try `/play`, `/slave play Daft Punk - Revolution 909`, "
            "`/playlist`, `/np`, `/slave restore`, or `/slave help`."
        )
        return

    parts = remainder.split(maxsplit=1)
    sub = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if sub in ("playlist", "queue", "pl", "q"):
        page = int(arg) if arg.isdigit() else 1
        if not state.current and not state.queue:
            await message.channel.send("📭 The playlist is currently empty.")
        else:
            embed, actual_page, _ = build_playlist_embed(state, page)
            view = PlaylistPaginatorView(state, initial_page=actual_page)
            await message.channel.send(embed=embed, view=view)
        return

    if sub in ("nowplaying", "np"):
        if not state.current:
            await message.channel.send("📭 Nothing is playing right now.")
        else:
            state.text_channel = message.channel
            await bot.send_single_np_card(message.guild.id, "🎶 Now Playing")
        return

    if sub == "lyrics":
        q = arg or (state.current.get("title", "") if state.current else "")
        if not q:
            await message.channel.send("❌ Specify a song or play a track first.")
            return
        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(None, lambda: _fetch_lyrics_sync(q))
        if not res:
            await message.channel.send(f"❌ Could not find lyrics for **`{q}`**.")
        else:
            emb = discord.Embed(
                title=f"📜 Lyrics — {res['title']}",
                description=res["lyrics"][:3800],
                color=discord.Color.gold(),
            )
            await message.channel.send(embed=emb)
        return

    allowed, reason = check_voice_permission(message.author, state)
    if not allowed:
        await message.channel.send(reason)
        return

    if sub == "clear":
        if state.pre_resolve_task and not state.pre_resolve_task.done():
            state.pre_resolve_task.cancel()
        count = len(state.queue)
        for t in state.queue:
            _cleanup_track_temp_file(t)
        state.queue.clear()
        save_active_session_snapshot(message.guild.id, state)
        await message.channel.send(f"🗑️ Cleared **{count}** track(s) from the playlist.")
    elif sub == "shuffle":
        if len(state.queue) < 2:
            await message.channel.send("❌ Need at least 2 tracks in the playlist to shuffle.")
        else:
            temp = list(state.queue)
            random.shuffle(temp)
            state.queue = deque(temp)
            bot.trigger_pre_resolve(message.guild.id)
            save_active_session_snapshot(message.guild.id, state)
            await message.channel.send(f"🔀 Shuffled **{len(state.queue)}** tracks!")
    elif sub == "removedupes":
        seen: set[str] = set()
        deduped = []
        removed = 0
        for it in state.queue:
            k = _normalize_for_match(it.get("title", ""))
            if k in seen:
                _cleanup_track_temp_file(it)
                removed += 1
            else:
                seen.add(k)
                deduped.append(it)
        state.queue = deque(deduped)
        bot.trigger_pre_resolve(message.guild.id)
        save_active_session_snapshot(message.guild.id, state)
        await message.channel.send(f"🧹 Removed **{removed}** duplicate track(s).")
    elif sub == "autoplay":
        state.autoplay = not state.autoplay
        save_active_session_snapshot(message.guild.id, state)
        await message.channel.send(f"📻 Autoplay is now **{'ON' if state.autoplay else 'OFF'}**.")
    elif sub in ("normalize", "norm"):
        state.normalize_audio = not state.normalize_audio
        save_active_session_snapshot(message.guild.id, state)
        await message.channel.send(
            f"🎚️ Studio Loudness Normalization is now **{'ON' if state.normalize_audio else 'OFF'}**."
        )
    elif sub == "restore":
        _, msg = await bot.restore_guild_session(message.guild, message.author, message.channel)
        await message.channel.send(msg)
    elif sub in ("prev", "previous", "back"):
        if not state.history:
            await message.channel.send("❌ No previous track in history.")
        else:
            prev_t = state.history.pop()
            if state.current:
                state.queue.appendleft(dict(state.current))
            state.queue.appendleft(prev_t)
            if state.voice_client and (state.voice_client.is_playing() or state.voice_client.is_paused()):
                state.user_skipped = True
                state.voice_client.stop()
            else:
                await bot.play_next(message.guild.id)
            await message.channel.send(f"⏮️ Returning to **{prev_t['title']}**...")
    elif sub == "seek" and arg:
        if not state.current or not state.voice_client:
            await message.channel.send("❌ Nothing is playing right now.")
        else:
            sec = parse_duration_str(arg)
            state.suppress_after_callback = True
            if isinstance(state.voice_client.source, SteadyOpusSource):
                state.voice_client.source.keep_local_file = True
            state.voice_client.stop()
            await bot.play_next(message.guild.id, seek_seconds=sec)
            await message.channel.send(f"⏩ Jumped to `{format_seconds(sec)}`!")
    elif sub == "replay":
        if not state.current or not state.voice_client:
            await message.channel.send("❌ Nothing is playing right now.")
        else:
            state.suppress_after_callback = True
            if isinstance(state.voice_client.source, SteadyOpusSource):
                state.voice_client.source.keep_local_file = True
            state.voice_client.stop()
            await bot.play_next(message.guild.id, seek_seconds=0)
            await message.channel.send("⏪ Restarted current song!")
    elif sub == "pause":
        if state.voice_client and state.voice_client.is_playing():
            state.voice_client.pause()
            state.paused_at = time.monotonic()
            await message.channel.send("⏸️ Paused playback.")
    elif sub == "resume":
        if state.voice_client and state.voice_client.is_paused():
            if state.paused_at is not None:
                state.started_at += time.monotonic() - state.paused_at
                state.paused_at = None
            state.voice_client.resume()
            await message.channel.send("▶️ Resumed playback.")
    elif sub == "skip":
        if state.voice_client and (state.voice_client.is_playing() or state.voice_client.is_paused()):
            state.user_skipped = True
            state.voice_client.stop()
            await message.channel.send("⏭️ Skipped track.")
    elif sub == "stop":
        await bot.stop_and_cleanup(message.guild.id, clear_session=True)
        await message.channel.send("⏹️ Stopped and left voice.")
    elif sub == "move":
        nums = arg.split()
        if len(nums) == 2 and nums[0].isdigit() and nums[1].isdigit():
            f_pos, t_pos = int(nums[0]), int(nums[1])
            q_len = len(state.queue)
            if 1 <= f_pos <= q_len and 1 <= t_pos <= q_len:
                temp = list(state.queue)
                mv = temp.pop(f_pos - 1)
                temp.insert(t_pos - 1, mv)
                state.queue = deque(temp)
                bot.trigger_pre_resolve(message.guild.id)
                save_active_session_snapshot(message.guild.id, state)
                await message.channel.send(f"↕️ Moved **{mv['title']}** from `#{f_pos}` to `#{t_pos}`!")
    elif sub == "playnext" and arg:
        status = await message.channel.send(f"🔎 Searching for `{arg}` to play next...")
        msg, embed, view = await handle_queue_tracks(
            message.guild, message.author, message.channel, arg, play_next_flag=True
        )
        if embed and view:
            await status.edit(content=None, embed=embed, view=view)
        else:
            await status.edit(content=msg)
    else:
        query = arg if (sub == "play" and arg) else remainder
        status = await message.channel.send(f"🔎 Searching for `{query}`...")
        msg, embed, view = await handle_queue_tracks(
            message.guild, message.author, message.channel, query, play_next_flag=False
        )
        if embed and view:
            await status.edit(content=None, embed=embed, view=view)
        else:
            await status.edit(content=msg)


if __name__ == "__main__":
    if not DISCORD_TOKEN or DISCORD_TOKEN == "YOUR_DISCORD_BOT_TOKEN_HERE":
        print("ERROR: Please paste your Discord bot token on Line 33 of slave_bot.py!")
        sys.exit(1)
    bot.run(DISCORD_TOKEN)
