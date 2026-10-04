import os
import re
import json
import glob
import wave
import time
import random
import asyncio
import datetime
import requests
import numpy as np

from PIL import Image, ImageDraw, ImageFont
from google import genai
from google.genai import types
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

from moviepy.editor import (
    VideoClip,
    AudioFileClip,
    CompositeAudioClip,
    concatenate_videoclips,
)
from moviepy.audio.fx.all import audio_loop


# ================================================================
# SETTINGS
# ================================================================

CHANNEL_NAME = "Spiritual Bhakti"

GEMINI_MODELS = [
    os.environ.get("GEMINI_MODEL", "gemini-3.8-flash"),
    "gemini-3.8-flash",
    "gemini-flash-latest",
]

VOICE = "hi-IN-MadhurNeural"

PRIVACY = "public"

BGM_VOLUME = 0.12

TARGET_MINUTES = 10

SECONDS_PER_IMAGE = 25

ZOOM = 1.12

FPS = 15

W = 1280
H = 720


# ================================================================
# API KEYS / SECRETS
# ================================================================

GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
PIXABAY_KEY = os.environ.get("PIXABAY_API_KEY")

YT_CLIENT_ID = os.environ.get("YOUTUBE_CLIENT_ID")
YT_CLIENT_SECRET = os.environ.get("YOUTUBE_CLIENT_SECRET")
YT_REFRESH_TOKEN = os.environ.get("YOUTUBE_REFRESH_TOKEN")

TOPIC = (os.environ.get("TOPIC") or "").strip()


# ================================================================
# CHECK SECRETS
# ================================================================

def check_secrets():

    missing = []

    secrets = [
        ("GEMINI_API_KEY", GEMINI_KEY),
        ("PIXABAY_API_KEY", PIXABAY_KEY),
        ("YOUTUBE_CLIENT_ID", YT_CLIENT_ID),
        ("YOUTUBE_CLIENT_SECRET", YT_CLIENT_SECRET),
        ("YOUTUBE_REFRESH_TOKEN", YT_REFRESH_TOKEN),
    ]

    for name, value in secrets:
        if not value:
            missing.append(name)

    if missing:
        raise SystemExit(
            "Ye secrets khaali hain: " + ", ".join(missing)
        )


# ================================================================
# JSON PARSER
# ================================================================

def parse_json(text):

    text = (text or "").strip()

    text = re.sub(
        r"^```(?:json)?|```$",
        "",
        text,
        flags=re.M
    ).strip()

    return json.loads(text)


# ================================================================
# GEMINI CONTENT GENERATION
# ================================================================

def generate_content():

    ist = datetime.timezone(
        datetime.timedelta(hours=5, minutes=30)
    )

    today = datetime.datetime.now(ist).strftime(
        "%d %B %Y"
    )

    if TOPIC:

        topic_line = (
            f"Topic for today's video: {TOPIC}."
        )

    else:

        topic_line = (
            "If a major Hindu festival or an eclipse "
            "(grahan) falls within the next 2 days, "
            "write about it. Otherwise pick a beautiful "
            "story of a Hindu deity or saint."
        )

    WORDS = TARGET_MINUTES * 130

    prompt = f"""
You write scripts for a Hindi devotional bhakti YouTube channel.

Today's date (IST) is {today}.

{topic_line}

Write a long, calm, devotional narration in Hindi "
(Devanagari script) of about {WORDS} words.

It MUST be long enough for a {TARGET_MINUTES}-minute video.

Do not stop early.

Tell the story in detail with many scenes.

Keep facts accurate according to Hindu scriptures and traditions.

No superstition.
No fear-based claims.
No medical predictions.
No astrology predictions.

Return ONLY valid JSON.

Do NOT use markdown.

JSON must contain exactly these keys:

"title":
Hindi catchy YouTube title, maximum 90 characters.

"description":
Hindi YouTube description, 120-200 words.
Add relevant hashtags at the end.

"tags":
List of 10-15 Hindi + English tags.

"thumbnail_text":
Maximum 6 Hindi words.

"image_queries":
List of 24 short English search queries for stock photos.
Examples:
hindu temple
diya lamp
lotus flower
hindu god idol
aarti
temple bells
spiritual sunrise

"story":
Full Hindi narration.
Plain text only.
No headings.
No stage directions.
No markdown.

Make sure the JSON is valid.
"""

    client = genai.Client(
        api_key=GEMINI_KEY
    )

    last_error = None

    # Duplicate models remove
    models_to_try = list(
        dict.fromkeys(GEMINI_MODELS)
    )

    for model_name in models_to_try:

        for attempt in range(1, 6):

            try:

                print(
                    f"Gemini: trying {model_name}, "
                    f"attempt {attempt}/5"
                )

                # ==================================================
                # IMPORTANT FIX:
                # Automatic Function Calling explicitly disabled.
                # ==================================================

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

                if not response.text:

                    raise ValueError(
                        "Gemini ne empty response diya"
                    )

                data = parse_json(
                    response.text
                )

                story = data.get("story", "")

                if len(story) < 800:

                    raise ValueError(
                        "story bahut chhoti aayi"
                    )

                print(
                    "Gemini model used:",
                    model_name
                )

                print(
                    "Title:",
                    data.get("title")
                )

                print(
                    "Story characters:",
                    len(story)
                )

                return data

            except Exception as e:

                last_error = e

                msg = str(e)

                print(
                    f"[{model_name}] "
                    f"attempt {attempt} failed:"
                )

                print(
                    msg[:500]
                )

                # Model available nahi hai
                if (
                    "404" in msg
                    or "NOT_FOUND" in msg
                    or "not found" in msg.lower()
                ):

                    print(
                        "Ye model available nahi hai. "
                        "Next model try kar rahe hain..."
                    )

                    break

                # JSON ya short story issue
                if isinstance(e, ValueError):

                    time.sleep(5)

                else:

                    # Temporary API / server error
                    wait_time = min(
                        30 * attempt,
                        90
                    )

                    print(
                        f"{wait_time} seconds wait..."
                    )

                    time.sleep(
                        wait_time
                    )

    raise RuntimeError(
        "Gemini se content nahi mila"
    ) from last_error


# ================================================================
# EDGE TTS
# ================================================================

async def _edge_save(text, path):

    import edge_tts

    communicate = edge_tts.Communicate(
        text,
        VOICE,
        rate="-5%"
    )

    await communicate.save(path)


def make_voiceover(
    text,
    path="audio.mp3"
):

    for attempt in range(1, 4):

        try:

            print(
                f"Voice generation attempt "
                f"{attempt}/3..."
            )

            asyncio.run(
                _edge_save(
                    text,
                    path
                )
            )

            if (
                os.path.exists(path)
                and os.path.getsize(path) > 10000
            ):

                print(
                    "Voiceover ready (edge-tts)"
                )

                return path

            raise RuntimeError(
                "audio khaali hai"
            )

        except Exception as e:

            print(
                f"Edge TTS attempt {attempt} failed:",
                str(e)[:300]
            )

            time.sleep(
                5 * attempt
            )

    print(
        "Edge TTS fail hua, gTTS use kar rahe hain..."
    )

    from gtts import gTTS

    gTTS(
        text=text,
        lang="hi",
        slow=False
    ).save(path)

    print(
        "Voiceover ready (gTTS)"
    )

    return path


# ================================================================
# PIXABAY IMAGE DOWNLOAD
# ================================================================

def download_images(
    queries,
    max_images=20
):

    paths = []

    seen = set()

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    for q in queries:

        if len(paths) >= max_images:
            break

        try:

            print(
                "Searching image:",
                q
            )

            response = requests.get(

                "https://pixabay.com/api/",

                params={
                    "key": PIXABAY_KEY,
                    "q": q,
                    "image_type": "photo",
                    "orientation": "horizontal",
                    "safesearch": "true",
                    "per_page": 6,
                },

                headers=headers,

                timeout=30,
            )

            response.raise_for_status()

            data = response.json()

            taken = 0

            for hit in data.get(
                "hits",
                []
            ):

                if taken >= 2:
                    break

                if len(paths) >= max_images:
                    break

                url = hit.get(
                    "largeImageURL"
                )

                if not url:
                    continue

                if url in seen:
                    continue

                seen.add(url)

                path = (
                    f"bg_{len(paths)}.jpg"
                )

                image_response = requests.get(
                    url,
                    headers=headers,
                    timeout=60
                )

                image_response.raise_for_status()

                with open(
                    path,
                    "wb"
                ) as f:

                    f.write(
                        image_response.content
                    )

                # Check image
                Image.open(
                    path
                ).verify()

                paths.append(path)

                taken += 1

        except Exception as e:

            print(
                "Image error:",
                q,
                str(e)[:200]
            )

    # Fallback logo
    if (
        not paths
        and os.path.exists("Logo.jpg")
    ):

        paths = [
            "Logo.jpg"
        ]

    print(
        "Images downloaded:",
        len(paths)
    )

    return paths


# ================================================================
# FONTS
# ================================================================

LATIN_FONTS = [

    "/usr/share/fonts/truetype/dejavu/"
    "DejaVuSans-Bold.ttf",

    "font.ttf",
]


DEVA_FONTS = [

    "font.ttf",

    "/usr/share/fonts/truetype/lohit-devanagari/"
    "Lohit-Devanagari.ttf",

    "/usr/share/fonts/truetype/noto/"
    "NotoSansDevanagari-Bold.ttf",
]


_font_cache = {}


def _open_font(
    path,
    size
):

    if not os.path.exists(path):
        return None

    try:

        return ImageFont.truetype(
            path,
            size,
            layout_engine=ImageFont.Layout.RAQM
        )

    except Exception:

        try:

            return ImageFont.truetype(
                path,
                size
            )

        except Exception:

            return None


def _has_glyph(
    font,
    ch
):

    try:

        a = Image.new(
            "L",
            (150, 150),
            0
        )

        b = Image.new(
            "L",
            (150, 150),
            0
        )

        ImageDraw.Draw(a).text(
            (10, 10),
            ch,
            font=font,
            fill=255
        )

        ImageDraw.Draw(b).text(
            (10, 10),
            "\U0010FFFF",
            font=font,
            fill=255
        )

        return (
            a.tobytes()
            != b.tobytes()
        )

    except Exception:

        return False


def font_for(
    text,
    size
):

    is_hindi = any(
        "\u0900" <= c <= "\u097F"
        for c in text
    )

    key = (
        is_hindi,
        size
    )

    if key in _font_cache:
        return _font_cache[key]

    candidates = (
        DEVA_FONTS
        if is_hindi
        else LATIN_FONTS
    )

    test_char = (
        "क"
        if is_hindi
        else "A"
    )

    chosen = None

    for p in candidates:

        f = _open_font(
            p,
            size
        )

        if (
            f
            and _has_glyph(
                f,
                test_char
            )
        ):

            chosen = f
            break

    if chosen is None:

        for p in candidates:

            chosen = _open_font(
                p,
                size
            )

            if chosen:
                break

    if chosen is None:

        chosen = ImageFont.load_default()

    _font_cache[key] = chosen

    return chosen


# ================================================================
# IMAGE CROP
# ================================================================

def cover_crop(
    img,
    w=W,
    h=H
):

    img = img.convert(
        "RGB"
    )

    scale = max(
        w / img.width,
        h / img.height
    )

    img = img.resize(
        (
            int(img.width * scale) + 1,
            int(img.height * scale) + 1
        ),
        Image.LANCZOS
    )

    left = (
        img.width - w
    ) // 2

    top = (
        img.height - h
    ) // 2

    return img.crop(
        (
            left,
            top,
            left + w,
            top + h
        )
    )


# ================================================================
# LOGO
# ================================================================

def circle_logo(size):

    logo = Image.open(
        "Logo.jpg"
    ).convert(
        "RGBA"
    ).resize(
        (size, size),
        Image.LANCZOS
    )

    mask = Image.new(
        "L",
        (size, size),
        0
    )

    ImageDraw.Draw(
        mask
    ).ellipse(
        [
            0,
            0,
            size - 1,
            size - 1
        ],
        fill=255
    )

    return logo, mask


# ================================================================
# VIDEO OVERLAY
# ================================================================

def make_overlay():

    overlay = Image.new(
        "RGBA",
        (W, H),
        (0, 0, 0, 0)
    )

    d = ImageDraw.Draw(
        overlay
    )

    d.rectangle(
        [
            0,
            H - 95,
            W,
            H
        ],
        fill=(0, 0, 0, 150)
    )

    x = 20

    if os.path.exists(
        "Logo.jpg"
    ):

        logo, mask = circle_logo(
            70
        )

        overlay.paste(
            logo,
            (20, H - 83),
            mask
        )

        x = 105

    d.text(
        (x, H - 78),
        CHANNEL_NAME,
        font=font_for(
            CHANNEL_NAME,
            34
        ),
        fill=(
            255,
            255,
            255,
            255
        )
    )

    bx0 = W - 290
    by0 = H - 78
    bx1 = W - 20
    by1 = H - 18

    d.rounded_rectangle(
        [
            bx0,
            by0,
            bx1,
            by1
        ],
        radius=14,
        fill=(
            220,
            20,
            20,
            255
        )
    )

    d.text(
        (
            bx0 + 32,
            by0 + 12
        ),
        "SUBSCRIBE",
        font=font_for(
            "SUBSCRIBE",
            32
        ),
        fill=(
            255,
            255,
            255,
            255
        )
    )

    return overlay


# ================================================================
# TEXT WRAP
# ================================================================

def wrap_text(
    draw,
    text,
    font,
    max_width
):

    lines = []

    line = ""

    for word in text.split():

        test = (
            line + " " + word
        ).strip()

        if draw.textlength(
            test,
            font=font
        ) <= max_width:

            line = test

        else:

            if line:
                lines.append(line)

            line = word

    if line:
        lines.append(line)

    return lines


# ================================================================
# THUMBNAIL
# ================================================================

def make_thumbnail(
    bg_path,
    text,
    out_path="thumb.jpg"
):

    img = cover_crop(
        Image.open(bg_path)
    ).convert(
        "RGBA"
    )

    dark = Image.new(
        "RGBA",
        (W, H),
        (0, 0, 0, 110)
    )

    img = Image.alpha_composite(
        img,
        dark
    )

    d = ImageDraw.Draw(
        img
    )

    font = font_for(
        text,
        100
    )

    lines = wrap_text(
        d,
        text,
        font,
        W - 160
    )[:3]

    y = (
        H - len(lines) * 125
    ) // 2

    for line in lines:

        d.text(
            (80, y),
            line,
            font=font,
            fill=(
                255,
                215,
                0,
                255
            ),
            stroke_width=6,
            stroke_fill=(
                0,
                0,
                0,
                255
            )
        )

        y += 125

    if os.path.exists(
        "Logo.jpg"
    ):

        logo, mask = circle_logo(
            140
        )

        img.paste(
            logo,
            (W - 170, 30),
            mask
        )

    img.convert(
        "RGB"
    ).save(
        out_path,
        quality=90
    )

    print(
        "Thumbnail ready"
    )

    return out_path


# ================================================================
# GENERATED BACKGROUND MUSIC
# ================================================================

def generate_bgm(
    path="bgm_gen.wav",
    loop_sec=24,
    sr=22050
):

    root = random.choice(
        [
            130.81,
            146.83,
            164.81,
            174.61,
            196.00
        ]
    )

    n = int(
        loop_sec * sr
    )

    t = np.arange(n) / sr

    out = np.zeros(n)

    def add_tone(
        freqs_amps,
        start,
        length,
        decay,
        amp
    ):

        m = int(
            length * sr
        )

        tt = np.arange(m) / sr

        env = (
            np.exp(
                -tt / decay
            )
            * (
                1 -
                np.exp(-tt / 0.02)
            )
        )

        tone = sum(
            a *
            np.sin(
                2 *
                np.pi *
                f *
                tt
            )
            for f, a 
