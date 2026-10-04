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
    ImageClip, AudioFileClip, CompositeAudioClip, concatenate_videoclips,
)
from moviepy.audio.fx.all import audio_loop

# ------------------------------------------------------------------
# SETTINGS (yahan apne hisaab se badlein)
# ------------------------------------------------------------------
CHANNEL_NAME = "Spiritual Bhakti"      # video par dikhne wala channel naam
GEMINI_MODELS = [
    os.environ.get("GEMINI_MODEL", "gemini-3.8-flash"),
    "gemini-3.8-flash",
    "gemini-flash-latest",
]
VOICE = "hi-IN-MadhurNeural"           # female ke liye: hi-IN-SwaraNeural
PRIVACY = "public"                     # testing ke liye "private" kar sakte hain
BGM_VOLUME = 0.12
FPS = 10
W, H = 1280, 720

GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
PIXABAY_KEY = os.environ.get("PIXABAY_API_KEY")
YT_CLIENT_ID = os.environ.get("YOUTUBE_CLIENT_ID")
YT_CLIENT_SECRET = os.environ.get("YOUTUBE_CLIENT_SECRET")
YT_REFRESH_TOKEN = os.environ.get("YOUTUBE_REFRESH_TOKEN")
TOPIC = (os.environ.get("TOPIC") or "").strip()   # n8n se aa sakta hai


def check_secrets():
    missing = [n for n, v in [
        ("GEMINI_API_KEY", GEMINI_KEY), ("PIXABAY_API_KEY", PIXABAY_KEY),
        ("YOUTUBE_CLIENT_ID", YT_CLIENT_ID), ("YOUTUBE_CLIENT_SECRET", YT_CLIENT_SECRET),
        ("YOUTUBE_REFRESH_TOKEN", YT_REFRESH_TOKEN)] if not v]
    if missing:
        raise SystemExit("Ye secrets khaali hain: " + ", ".join(missing))


# ------------------------------------------------------------------
# 1. Gemini se script, title, description, tags, thumbnail text
# ------------------------------------------------------------------
def parse_json(text):
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    return json.loads(text)


def generate_content():
    ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    today = datetime.datetime.now(ist).strftime("%d %B %Y")

    if TOPIC:
        topic_line = f"Topic for today's video: {TOPIC}."
    else:
        topic_line = (
            "If a major Hindu festival or an eclipse (grahan) falls within the "
            "next 2 days, write about it. Otherwise pick a beautiful story of "
            "a Hindu deity or saint."
        )

    prompt = f"""
You write scripts for a Hindi devotional (bhakti) YouTube channel.
Today's date (IST) is {today}. {topic_line}

Write a long, calm, devotional narration in Hindi (Devanagari script) of about
1500-2000 words, suitable for a 10-12 minute video. Keep facts accurate as per
Hindu scriptures and traditions. No superstition, no fear-based claims, no
medical or astrology predictions.

Return ONLY valid JSON (no markdown) with these keys:
- "title": Hindi, catchy, max 90 characters
- "description": Hindi, 120-200 words, hashtags at the end
- "tags": list of 10-15 strings (Hindi + English)
- "thumbnail_text": max 6 Hindi words, punchy
- "image_queries": list of 8 short English search queries for stock photos
   that match the story (temple, diya, lotus, god idol, aarti, etc.)
- "story": the full narration, plain text only, no headings, no stage directions
"""
    client = genai.Client(api_key=GEMINI_KEY)
    last_error = None
    for model_name in dict.fromkeys(GEMINI_MODELS):      # duplicates hata kar
        for attempt in range(1, 6):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json"),
                )
                data = parse_json(response.text)
                if len(data.get("story", "")) < 500:
                    raise ValueError("story bahut chhoti aayi")
                print("Gemini model used:", model_name, "| title:", data.get("title"))
                return data
            except Exception as e:
                last_error = e
                msg = str(e)
                print(f"[{model_name}] attempt {attempt} failed: {msg[:150]}")
                if "404" in msg or "NOT_FOUND" in msg:
                    break                       # ye model hi nahi hai -> agla model
                if isinstance(e, ValueError):
                    time.sleep(5)               # JSON/short story: jaldi dobara
                else:
                    time.sleep(min(30 * attempt, 90))   # 503 etc: ruk kar dobara
    raise RuntimeError("Gemini se content nahi mila") from last_error


# ------------------------------------------------------------------
# 2. Voiceover (Edge TTS, fail ho to gTTS)
# ------------------------------------------------------------------
async def _edge_save(text, path):
    import edge_tts
    await edge_tts.Communicate(text, VOICE, rate="-5%").save(path)


def make_voiceover(text, path="audio.mp3"):
    for attempt in range(1, 4):
        try:
            asyncio.run(_edge_save(text, path))
            if os.path.exists(path) and os.path.getsize(path) > 10000:
                print("Voiceover ready (edge-tts)")
                return path
            raise RuntimeError("audio khaali hai")
        except Exception as e:
            print(f"Edge TTS attempt {attempt} failed:", str(e)[:150])
            time.sleep(5 * attempt)
    print("Edge TTS fail hua, gTTS use kar rahe hain...")
    from gtts import gTTS
    gTTS(text=text, lang="hi", slow=False).save(path)
    print("Voiceover ready (gTTS)")
    return path


# ------------------------------------------------------------------
# 3. Pixabay se images
# ------------------------------------------------------------------
def download_images(queries, max_images=8):
    paths, seen = [], set()
    headers = {"User-Agent": "Mozilla/5.0"}
    for q in queries:
        if len(paths) >= max_images:
            break
        try:
            r = requests.get(
                "https://pixabay.com/api/",
                params={
                    "key": PIXABAY_KEY, "q": q, "image_type": "photo",
                    "orientation": "horizontal", "safesearch": "true",
                    "per_page": 5,
                },
                headers=headers, timeout=30,
            ).json()
            for hit in r.get("hits", []):
                url = hit["largeImageURL"]
                if url in seen:
                    continue
                seen.add(url)
                path = f"bg_{len(paths)}.jpg"
                with open(path, "wb") as f:
                    f.write(requests.get(url, headers=headers, timeout=60).content)
                Image.open(path).verify()          # kharab image pakadne ke liye
                paths.append(path)
                break
        except Exception as e:
            print("Image error:", q, str(e)[:100])
    if not paths and os.path.exists("Logo.jpg"):
        paths = ["Logo.jpg"]                       # koi image na mile to logo hi chalega
    print("Images:", len(paths))
    return paths


# ------------------------------------------------------------------
# 4. Fonts, frames aur thumbnail (Pillow se)
# ------------------------------------------------------------------
LATIN_FONTS = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "font.ttf"]
DEVA_FONTS = [
    "font.ttf",
    "/usr/share/fonts/truetype/lohit-devanagari/Lohit-Devanagari.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
]
_font_cache = {}


def _open_font(path, size):
    if not os.path.exists(path):
        return None
    try:
        return ImageFont.truetype(path, size, layout_engine=ImageFont.Layout.RAQM)
    except Exception:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            return None


def _has_glyph(font, ch):
    """True agar font me ye akshar sach me hai (khaali dabba nahi)."""
    try:
        a = Image.new("L", (150, 150), 0)
        b = Image.new("L", (150, 150), 0)
        ImageDraw.Draw(a).text((10, 10), ch, font=font, fill=255)
        ImageDraw.Draw(b).text((10, 10), "\U0010FFFF", font=font, fill=255)
        return a.tobytes() != b.tobytes()
    except Exception:
        return False


def font_for(text, size):
    is_hindi = any("\u0900" <= c <= "\u097F" for c in text)
    key = (is_hindi, size)
    if key in _font_cache:
        return _font_cache[key]
    candidates = DEVA_FONTS if is_hindi else LATIN_FONTS
    test_char = "क" if is_hindi else "A"
    chosen = None
    for p in candidates:
        f = _open_font(p, size)
        if f and _has_glyph(f, test_char):
            chosen = f
            break
    if chosen is None:
        for p in candidates:
            chosen = _open_font(p, size)
            if chosen:
                break
    if chosen is None:
        chosen = ImageFont.load_default()
    _font_cache[key] = chosen
    return chosen


def cover_crop(img):
    img = img.convert("RGB")
    scale = max(W / img.width, H / img.height)
    img = img.resize((int(img.width * scale) + 1, int(img.height * scale) + 1), Image.LANCZOS)
    left = (img.width - W) // 2
    top = (img.height - H) // 2
    return img.crop((left, top, left + W, top + H))


def circle_logo(size):
    logo = Image.open("Logo.jpg").convert("RGBA").resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size - 1, size - 1], fill=255)
    return logo, mask


def make_frame(bg_path):
    img = cover_crop(Image.open(bg_path)).convert("RGBA")
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    d.rectangle([0, H - 95, W, H], fill=(0, 0, 0, 150))

    x = 20
    if os.path.exists("Logo.jpg"):
        logo, mask = circle_logo(70)
        overlay.paste(logo, (20, H - 83), mask)
        x = 105
    d.text((x, H - 78), CHANNEL_NAME, font=font_for(CHANNEL_NAME, 34),
           fill=(255, 255, 255, 255))

    bx0, by0, bx1, by1 = W - 290, H - 78, W - 20, H - 18
    d.rounded_rectangle([bx0, by0, bx1, by1], radius=14, fill=(220, 20, 20, 255))
    d.text((bx0 + 32, by0 + 12), "SUBSCRIBE", font=font_for("SUBSCRIBE", 32),
           fill=(255, 255, 255, 255))
    return Image.alpha_composite(img, overlay).convert("RGB")


def wrap_text(draw, text, font, max_width):
    lines, line = [], ""
    for word in text.split():
        test = (line + " " + word).strip()
        if draw.textlength(test, font=font) <= max_width:
            line = test
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def make_thumbnail(bg_path, text, out_path="thumb.jpg"):
    img = cover_crop(Image.open(bg_path)).convert("RGBA")
    img = Image.alpha_composite(img, Image.new("RGBA", (W, H), (0, 0, 0, 110)))
    d = ImageDraw.Draw(img)
    font = font_for(text, 100)
    lines = wrap_text(d, text, font, W - 160)[:3]
    y = (H - len(lines) * 125) // 2
    for line in lines:
        d.text((80, y), line, font=font, fill=(255, 215, 0, 255),
               stroke_width=6, stroke_fill=(0, 0, 0, 255))
        y += 125
    if os.path.exists("Logo.jpg"):
        logo, mask = circle_logo(140)
        img.paste(logo, (W - 170, 30), mask)
    img.convert("RGB").save(out_path, quality=90)
    print("Thumbnail ready")
    return out_path


# ------------------------------------------------------------------
# 5. Background music (automatic, copyright-free)
# ------------------------------------------------------------------
def generate_bgm(path="bgm_gen.wav", loop_sec=24, sr=22050):
    """Tanpura jaisi drone + soft pad + ghanti. Har baar alag swar (root note).
    Khud ban-ti hai, isliye copyright ka koi issue nahi."""
    root = random.choice([130.81, 146.83, 164.81, 174.61, 196.00])
    n = int(loop_sec * sr)
    t = np.arange(n) / sr
    out = np.zeros(n)

    def add_tone(freqs_amps, start, length, decay, amp):
        m = int(length * sr)
        tt = np.arange(m) / sr
        env = np.exp(-tt / decay) * (1 - np.exp(-tt / 0.02))
        tone = sum(a * np.sin(2 * np.pi * f * tt) for f, a in freqs_amps)
        idx = (int(start * sr) + np.arange(m)) % n
        out[idx] += tone * env * amp

    def string(f):
        return [(f * h, 1.0 / h ** 1.3) for h in range(1, 7)]

    for cycle in range(4):                                   # Pa - Sa - Sa - Sa(low)
        base = cycle * 6.0
        for i, f in enumerate([root * 1.5, root * 2, root * 2, root]):
            add_tone(string(f), base + i * 1.5, 7.0, 2.2, 0.22)

    for start in (6.0, 18.0):                                # halki ghanti
        add_tone([(root * 4 * r, a) for r, a in [(1, 1), (2.76, .4), (5.4, .2)]],
                 start, 8.0, 2.5, 0.06)

    for k, (mult, amp) in enumerate([(1, .10), (1.5, .06), (2, .05)], start=1):
        f = round(root * mult * loop_sec) / loop_sec         # soft pad
        lfo = 0.6 + 0.4 * np.sin(2 * np.pi * (k + 1) / loop_sec * t)
        out += amp * np.sin(2 * np.pi * f * t) * lfo

    out = out / np.max(np.abs(out)) * 0.8
    right = np.roll(out, int(0.012 * sr))
    stereo = (np.stack([out, right], axis=1) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(stereo.tobytes())
    return path


def get_bgm():
    files = glob.glob("music/*.mp3") + glob.glob("music/*.wav") + glob.glob("bgm*.mp3")
    if files:
        choice = random.choice(files)
        print("BGM (file):", choice)
        return choice
    print("BGM (generated)")
    return generate_bgm()


# ------------------------------------------------------------------
# 6. Video render
# ------------------------------------------------------------------
def render_video(image_paths, audio_path, bgm_path, output_path="final_video.mp4"):
    voice = AudioFileClip(audio_path)
    duration = voice.duration
    per_image = duration / len(image_paths)

    clips = [ImageClip(np.array(make_frame(p))).set_duration(per_image)
             for p in image_paths]
    video = concatenate_videoclips(clips, method="compose")

    if bgm_path:
        bgm = audio_loop(AudioFileClip(bgm_path).volumex(BGM_VOLUME), duration=duration)
        final_audio = CompositeAudioClip([voice, bgm]).set_duration(duration)
    else:
        final_audio = voice

    video = video.set_audio(final_audio)
    video.write_videofile(
        output_path, fps=FPS, codec="libx264", audio_codec="aac",
        preset="ultrafast", threads=2,
    )
    print("Video rendered, minutes:", round(duration / 60, 1))
    return output_path


# ------------------------------------------------------------------
# 7. YouTube upload
# ------------------------------------------------------------------
def clean(s):
    return re.sub(r"[<>]", "", str(s)).strip()


def cut_bytes(s, limit):
    return s.encode("utf-8")[:limit].decode("utf-8", "ignore")


def upload_youtube(video_path, thumb_path, title, description, tags):
    creds = Credentials(
        None,
        refresh_token=YT_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=YT_CLIENT_ID,
        client_secret=YT_CLIENT_SECRET,
    )
    youtube = build("youtube", "v3", credentials=creds)

    clean_tags, total = [], 0
    for t in tags:
        t = clean(t).replace(",", "")
        if t and total + len(t) < 450:
            clean_tags.append(t)
            total += len(t)

    body = {
        "snippet": {
            "title": clean(title)[:100],
            "description": cut_bytes(clean(description), 4800),   # YouTube limit bytes me
            "tags": clean_tags,
            "categoryId": "22",
            "defaultLanguage": "hi",
        },
        "status": {"privacyStatus": PRIVACY, "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
    response = youtube.videos().insert(
        part="snippet,status", body=body, media_body=media
    ).execute()
    video_id = response.get("id")
    print("Uploaded! https://youtu.be/" + str(video_id))

    try:
        youtube.thumbnails().set(
            videoId=video_id, media_body=MediaFileUpload(thumb_path)
        ).execute()
        print("Thumbnail set")
    except Exception as e:
        print("Thumbnail error (channel verify hona zaroori hai):", str(e)[:200])
    return video_id


# ------------------------------------------------------------------
if __name__ == "__main__":
    print("Starting Daily Bhakti Video Automation...")
    check_secrets()

    data = generate_content()
    title = data.get("title") or "भगवान की सुंदर कथा"
    story = data["story"]
    description = (data.get("description") or "") + (
        f"\n\n🙏 {CHANNEL_NAME} - रोज़ एक नई भक्ति कथा के लिए चैनल को "
        "Subscribe करें और बेल आइकन दबाएँ।"
    )
    tags = data.get("tags") or ["bhakti", "katha"]
    thumb_text = data.get("thumbnail_text") or title
    queries = data.get("image_queries") or ["hindu temple", "diya lamp", "lotus flower"]

    make_voiceover(story, "audio.mp3")
    images = download_images(queries)
    if not images:
        raise SystemExit("Error: koi image nahi mili (Pixabay key check karein).")

    thumb = make_thumbnail(images[0], thumb_text)
    bgm = get_bgm()
    video = render_video(images, "audio.mp3", bgm)
    upload_youtube(video, thumb, title, description, tags)
    
