import os
import re
import json
import time
import math
import wave
import asyncio
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

from google import genai
from google.genai import types

from moviepy.editor import (
    AudioFileClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageClip,
    concatenate_videoclips,
)

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials


try:
    import edge_tts
except Exception:
    edge_tts = None

try:
    from gtts import gTTS
except Exception:
    gTTS = None


BASE = Path(__file__).resolve().parent
OUTPUT_DIR = BASE / "output"
ASSET_DIR = BASE / "assets"
OUTPUT_DIR.mkdir(exist_ok=True)
ASSET_DIR.mkdir(exist_ok=True)

W = 1280
H = 720
FPS = 15

TOPIC = os.environ.get(
    "TOPIC",
    "आज का भक्तिमय प्रेरक विचार"
).strip()

GEMINI_KEY = os.environ.get(
    "GEMINI_API_KEY",
    ""
).strip()

PIXABAY_KEY = os.environ.get(
    "PIXABAY_API_KEY",
    ""
).strip()

TTS_VOICE = os.environ.get(
    "TTS_VOICE",
    "hi-IN-SwaraNeural"
)

GEMINI_MODELS = [
    os.environ.get(
        "GEMINI_MODEL",
        "gemini-3.8-flash"
    ),
    "gemini-3.8-flash",
    "gemini-flash-latest",
]


def clean_text(text):
    text = text or ""
    text = re.sub(
        r"```(?:json)?",
        "",
        text,
        flags=re.IGNORECASE
    )
    return text.replace("```", "").strip()


def parse_json(text):
    text = clean_text(text)
    try:
        return json.loads(text)
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
        raise


def generate_content():
    if not GEMINI_KEY:
        raise RuntimeError("GEMINI_API_KEY secret missing")

    prompt = f"""
Create a Hindi devotional YouTube video script about:

{TOPIC}

Return ONLY valid JSON.

Required format:
{{
  "title": "short Hindi title",
  "description": "YouTube description",
  "story": "long Hindi narration",
  "scenes": [
    {{
      "text": "short scene description",
      "query": "English image search query"
    }}
  ]
}}

Rules:
1. Story should be natural Hindi.
2. Story should be emotional and engaging.
3. It should be suitable for Hindi voice-over.
4. Avoid markdown.
5. Story should preferably be 3500-5000 words.
6. Provide 12-20 scene queries.
7. Scene queries should be safe and suitable for copyright-free stock images.
8. Use generic spiritual, temple, nature and devotional imagery where appropriate.
"""

    client = genai.Client(api_key=GEMINI_KEY)
    last_error = None

    for model_name in dict.fromkeys(GEMINI_MODELS):
        for attempt in range(1, 4):
            try:
                print(f"[GEMINI] model={model_name} attempt={attempt}")

                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        max_output_tokens=12000,
                        automatic_function_calling=(
                            types.AutomaticFunctionCallingConfig(
                                disable=True
                            )
                        ),
                    ),
                )

                data = parse_json(response.text)
                story = str(data.get("story", "")).strip()

                if len(story) < 800:
                    raise ValueError("Generated story bahut chhoti hai")

                data["title"] = (
                    str(data.get("title", TOPIC)).strip() or TOPIC
                )
                data["description"] = str(
                    data.get("description", "")
                ).strip()
                data["scenes"] = data.get("scenes") or []

                print("[GEMINI] story length:", len(story))
                return data

            except Exception as exc:
                last_error = exc
                print("[GEMINI] error:", exc)
                time.sleep(3)

    raise RuntimeError(f"Gemini failed: {last_error}")


def split_paragraphs(story):
    parts = [
        x.strip()
        for x in re.split(r"\n+", story)
        if x.strip()
    ]

    if len(parts) < 4:
        parts = [
            x.strip()
            for x in re.split(r"(?<=[।!?])\s+", story)
            if x.strip()
        ]

    return parts


def pixabay_image(query, index):
    if not PIXABAY_KEY:
        return None

    try:
        response = requests.get(
            "https://pixabay.com/api/",
            params={
                "key": PIXABAY_KEY,
                "q": query,
                "image_type": "photo",
                "orientation": "horizontal",
                "safesearch": "true",
                "per_page": 10,
            },
            timeout=25,
        )
        response.raise_for_status()

        hits = response.json().get("hits", [])
        if not hits:
            return None

        selected = hits[index % len(hits)]
        url = (
            selected.get("largeImageURL")
            or selected.get("webformatURL")
        )

        if not url:
            return None

        output = ASSET_DIR / f"scene_{index:02d}.jpg"

        image_response = requests.get(url, timeout=30)
        image_response.raise_for_status()
        output.write_bytes(image_response.content)

        return str(output)

    except Exception as exc:
        print(f"[PIXABAY] failed: {query} -> {exc}")
        return None


def make_fallback_image(path, title):
    image = Image.new("RGB", (W, H), (20, 20, 20))
    draw = ImageDraw.Draw(image)

    font = None
    font_path = BASE / "font.ttf"

    if font_path.exists():
        try:
            font = ImageFont.truetype(str(font_path), 52)
        except Exception:
            font = None

    if font is None:
        font = ImageFont.load_default()

    text = title[:80]

    box = draw.multiline_textbbox(
        (0, 0),
        text,
        font=font,
        spacing=10,
        align="center"
    )

    tw = box[2] - box[0]
    th = box[3] - box[1]

    draw.multiline_text(
        ((W - tw) / 2, (H - th) / 2),
        text,
        font=font,
        fill="white",
        spacing=10,
        align="center"
    )

    image.save(path, quality=90)


def download_images(scenes):
    files = []
    queries = []

    for item in scenes:
        if isinstance(item, dict):
            query = str(
                item.get(
                    "query",
                    "spiritual nature India"
                )
            ).strip()
        else:
            query = "spiritual nature India"

        if query:
            queries.append(query)

    if not queries:
        queries = ["spiritual nature India"] * 12

    queries = queries[:24]

    for index, query in enumerate(queries):
        print(
            f"[IMAGE] {index + 1}/{len(queries)}: {query}"
        )

        path = pixabay_image(query, index)
        if path:
            files.append(path)

    if not files:
        fallback = ASSET_DIR / "fallback.jpg"
        make_fallback_image(fallback, TOPIC)
        files.append(str(fallback))

    return files


def synthesize_tts(text, output_path):
    if edge_tts is not None:
        async def create_audio():
            communicate = edge_tts.Communicate(
                text,
                TTS_VOICE
            )
            await communicate.save(str(output_path))

        asyncio.run(create_audio())
        return str(output_path)

    if gTTS is not None:
        audio = gTTS(
            text=text,
            lang="hi",
            slow=False
        )
        audio.save(str(output_path))
        return str(output_path)

    raise RuntimeError("edge-tts/gTTS available nahi hai")


def generate_bgm(path="bgm_gen.wav", loop_sec=24, sr=22050):
    output = OUTPUT_DIR / path
    duration = float(loop_sec)
    total_samples = int(duration * sr)

    volume = 0.055
    notes = [261.63, 329.63, 392.00, 523.25]
    chunk_size = 4096

    with wave.open(str(output), "wb") as wav_file:
        wav_file.setnchannels(2)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sr)

        for start in range(0, total_samples, chunk_size):
            end = min(start + chunk_size, total_samples)
            frames = bytearray()

            for sample_number in range(start, end):
                current_time = sample_number / sr

                note = notes[
                    int(current_time / 3.0) % len(notes)
                ]

                fade_in = min(1.0, current_time / 0.8)
                fade_out = min(
                    1.0,
                    (duration - current_time) / 1.0
                )

                envelope = fade_in * fade_out

                sample = (
                    volume
                    * envelope
                    * (
                        math.sin(
                            2 * math.pi * note * current_time
                        )
                        + 0.35
                        * math.sin(
                            2
                            * math.pi
                            * note
                            * 2
                            * current_time
                        )
                    )
                )

                sample = max(-1.0, min(1.0, sample))
                value = int(sample * 32767)

                frames.extend(
                    value.to_bytes(
                        2,
                        "little",
                        signed=True
                    )
                )
                frames.extend(
                    value.to_bytes(
                        2,
                        "little",
                        signed=True
                    )
                )

            wav_file.writeframes(frames)

    print("[BGM] created:", output)
    return str(output)


def crop_cover(image_path):
    image = Image.open(image_path).convert("RGB")

    target_ratio = W / H
    current_ratio = image.width / image.height

    if current_ratio > target_ratio:
        new_width = int(image.height * target_ratio)
        left = (image.width - new_width) // 2

        image = image.crop(
            (
                left,
                0,
                left + new_width,
                image.height
            )
        )
    else:
        new_height = int(image.width / target_ratio)
        top = (image.height - new_height) // 2

        image = image.crop(
            (
                0,
                top,
                image.width,
                top + new_height
            )
        )

    return image.resize(
        (W, H),
        Image.Resampling.LANCZOS
    )


def build_scene_clips(image_files, audio_duration):
    if not image_files:
        raise RuntimeError("No images available")

    duration_each = max(
        4.0,
        audio_duration / len(image_files)
    )

    clips = []

    for index, image_path in enumerate(image_files):
        try:
            prepared = ASSET_DIR / f"prepared_{index:02d}.jpg"

            crop_cover(image_path).save(
                prepared,
                quality=88
            )

            clip = (
                ImageClip(str(prepared))
                .set_duration(duration_each)
            )

            clips.append(clip)

        except Exception as exc:
            print(
                "[VIDEO] image skipped:",
                image_path,
                exc
            )

    if not clips:
        raise RuntimeError(
            "Could not create video clips"
        )

    video = concatenate_videoclips(
        clips,
        method="chain"
    )

    return video.set_fps(FPS)


def add_logo(video):
    logo_path = BASE / "Logo.jpg"

    if not logo_path.exists():
        return video

    try:
        logo = (
            ImageClip(str(logo_path))
            .resize(width=150)
            .set_duration(video.duration)
            .set_position(
                (W - 175, 25)
            )
        )

        return CompositeVideoClip(
            [video, logo],
            size=(W, H)
        )

    except Exception as exc:
        print("[LOGO] skipped:", exc)
        return video


def render_video(title, story, image_files):
    voice_path = OUTPUT_DIR / "voice.mp3"

    synthesize_tts(
        story,
        voice_path
    )

    print("[TTS] created:", voice_path)

    voice = AudioFileClip(str(voice_path))

    video = build_scene_clips(
        image_files,
        voice.duration
    )

    video = video.set_duration(voice.duration)
    video = add_logo(video)

    bgm_path = generate_bgm()

    bgm = (
        AudioFileClip(bgm_path)
        .volumex(0.12)
        .set_duration(voice.duration)
    )

    audio = CompositeAudioClip(
        [voice, bgm]
    )

    video = video.set_audio(audio)

    output = OUTPUT_DIR / "bhakti_video.mp4"

    print("[VIDEO] rendering:", output)

    video.write_videofile(
        str(output),
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        preset="medium",
        threads=2,
        temp_audiofile=str(
            OUTPUT_DIR / "temp_audio.m4a"
        ),
        remove_temp=True,
    )

    for obj in (bgm, voice, audio, video):
        try:
            obj.close()
        except Exception:
            pass

    print("[VIDEO] completed:", output)
    return str(output)


def youtube_service():
    client_id = os.environ.get(
        "YOUTUBE_CLIENT_ID",
        ""
    ).strip()

    client_secret = os.environ.get(
        "YOUTUBE_CLIENT_SECRET",
        ""
    ).strip()

    refresh_token = os.environ.get(
        "YOUTUBE_REFRESH_TOKEN",
        ""
    ).strip()

    if not client_id:
        raise RuntimeError("YOUTUBE_CLIENT_ID missing")

    if not client_secret:
        raise RuntimeError("YOUTUBE_CLIENT_SECRET missing")

    if not refresh_token:
        raise RuntimeError("YOUTUBE_REFRESH_TOKEN missing")

    credentials = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=[
            "https://www.googleapis.com/auth/youtube.upload"
        ],
    )

    from google.auth.transport.requests import Request

    credentials.refresh(Request())

    return build(
        "youtube",
        "v3",
        credentials=credentials
    )


def cut_bytes(text, limit=4800):
    text = text or ""
    raw = text.encode("utf-8")

    if len(raw) <= limit:
        return text

    return raw[:limit].decode(
        "utf-8",
        errors="ignore"
    )


def upload_youtube(video_path, title, description):
    youtube = youtube_service()

    body = {
        "snippet": {
            "title": title[:100],
            "description": cut_bytes(
                description or TOPIC
            ),
            "categoryId": "22",
        },
        "status": {
            "privacyStatus": os.environ.get(
                "YOUTUBE_PRIVACY",
                "private"
            ),
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        video_path,
        mimetype="video/mp4",
        chunksize=8 * 1024 * 1024,
        resumable=True,
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None

    while response is None:
        status, response = request.next_chunk()

        if status:
            print(
                "[YOUTUBE] upload:",
                int(status.progress() * 100),
                "%"
            )

    video_id = response.get("id")

    print("[YOUTUBE] uploaded:", video_id)
    return video_id


def main():
    print("=" * 60)
    print("DAILY BHAKTI VIDEO AUTOMATION")
    print("=" * 60)
    print("TOPIC:", TOPIC)
    print("=" * 60)

    data = generate_content()

    story = data["story"]
    title = data.get("title") or TOPIC

    description = (
        data.get("description")
        or f"{title}\n\n{story[:3000]}"
    )

    paragraphs = split_paragraphs(story)

    print(
        "[SCRIPT] paragraphs:",
        len(paragraphs)
    )

    images = download_images(
        data.get("scenes", [])
    )

    print("[IMAGE] total:", len(images))

    video_path = render_video(
        title,
        story,
        images
    )

    print("[VIDEO] file:", video_path)

    skip = os.environ.get(
        "SKIP_YOUTUBE",
        ""
    ).lower()

    if skip in {"1", "true", "yes"}:
        print("[YOUTUBE] SKIP_YOUTUBE enabled")
        return

    upload_youtube(
        video_path,
        title,
        description
    )

    print("=" * 60)
    print("[DONE] AUTOMATION COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
