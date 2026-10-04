import os
import re
import json
import glob
import wave
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
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
VOICE = "hi-IN-MadhurNeural"           # female ke liye: hi-IN-SwaraNeural
PRIVACY = "public"                     # testing ke liye "private" kar sakte hain
BGM_VOLUME = 0.12
W, H = 1280, 720

GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
PIXABAY_KEY = os.environ.get("PIXABAY_API_KEY")
YT_CLIENT_ID = os.environ.get("YOUTUBE_CLIENT_ID")
YT_CLIENT_SECRET = os.environ.get("YOUTUBE_CLIENT_SECRET")
YT_REFRESH_TOKEN = os.environ.get("YOUTUBE_REFRESH_TOKEN")
TOPIC = (os.environ.get("TOPIC") or "").strip()   # n8n se aa sakta hai


# ------------------------------------------------------------------
# 1. Gemini se script, title, description, tags, thumbnail text
# ------------------------------------------------------------------
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
- "description": Hindi, 150-250 words, hashtags at the end
- "tags": list of 10-15 strings (Hindi + English)
- "thumbnail_text": max 6 Hindi words, punchy
- "image_queries": list of 8 short English search queries for stock photos
   that match the story (temple, diya, lotus, god idol, aarti, etc.)
- "story": the full narration, plain text only, no headings, no stage directions
"""
    client = genai.Client(api_key=GEMINI_KEY)
    response = None
    last_error = None
    # Ek model band ho jaye to agla try hoga
    for model_name in [GEMINI_MODEL, "gemini-3.8-flash", "gemini-flash-latest"]:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json"),
            )
            print("Gemini model used:", model_name)
            break
        except Exception as e:
            last_error = e
            print("Model failed:", model_name, str(e)[:150])
    if response is None:
        raise last_error
    text = response.text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    data = json.loads(text)
    print("Gemini content ready:", data.get("title"))
    return data


# ------------------------------------------------------------------
# 2. Voiceover (Edge TTS)
# ------------------------------------------------------------------
async def make_voiceover(text, output_path="audio.mp3"):
    import edge_tts
    communicate = edge_tts.Communicate(text, VOICE, rate="-5%")
    await communicate.save(output_path)
    print("Voiceover ready")
    return output_path


# ------------------------------------------------------------------
# 3. Pixabay se images
# ------------------------------------------------------------------
def download_images(queries, max_images=8):
    paths = []
    seen = set()
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
                timeout=30,
            ).json()
            for hit in r.get("hits", []):
                url = hit["largeImageURL"]
                if url in seen:
                    continue
                seen.add(url)
                path = f"bg_{len(paths)}.jpg"
                with open(path, "wb") as f:
                    f.write(requests.get(url, timeout=60).content)
                paths.append(path)
                break
        except Exception as e:
            print("Image error:", q, e)
    if not paths and os.path.exists("Logo.jpg"):
        paths = ["Logo.jpg"]     # koi image na mile to logo hi chalega
    print("Images:", len(paths))
    return paths


# ------------------------------------------------------------------
# 4. Frames aur thumbnail (Pillow se)
# ------------------------------------------------------------------
def load_font(size):
    try:
        return ImageFont.truetype("font.ttf", size, layout_engine=ImageFont.Layout.RAQM)
    except Exception:
        try:
            return ImageFont.truetype("font.ttf", size)
        except Exception:
            return ImageFont.load_default()


def cover_crop(img):
    img = img.convert("RGB")
    scale = max(W / img.width, H / img.height)
    img = img.resize((int(img.width * scale) + 1, int(img.height * scale) + 1), Image.LANCZOS)
    left = (img.width - W) // 2
    top = (img.height - H) // 2
    return img.crop((left, top, left + W, top + H))


def make_frame(bg_path):
    img = cover_crop(Image.open(bg_path)).convert("RGBA")
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    d.rectangle([0, H - 95, W, H], fill=(0, 0, 0, 150))

    x = 20
    if os.path.exists("Logo.jpg"):
        logo = Image.open("Logo.jpg").convert("RGBA").resize((70, 70), Image.LANCZOS)
        mask = Image.new("L", (70, 70), 0)
        ImageDraw.Draw(mask).ellipse([0, 0, 70, 70], fill=255)
        overlay.paste(logo, (20, H - 83), mask)
        x = 105

    d.text((x, H - 78), CHANNEL_NAME, font=load_font(34), fill=(255, 255, 255, 255))

    # Subscribe button
    bx0, by0, bx1, by1 = W - 290, H - 78, W - 20, H - 18
    d.rounded_rectangle([bx0, by0, bx1, by1], radius=14, fill=(220, 20, 20, 255))
    d.text((bx0 + 32, by0 + 10), "SUBSCRIBE", font=load_font(34), fill=(255, 255, 255, 255))

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
    font = load_font(100)
    lines = wrap_text(d, text, font, W - 160)[:3]
    y = (H - len(lines) * 125) // 2
    for line in lines:
        d.text((80, y), line, font=font, fill=(255, 215, 0, 255),
               stroke_width=6, stroke_fill=(0, 0, 0, 255))
        y += 125
    if os.path.exists("Logo.jpg"):
        logo = Image.open("Logo.jpg").convert("RGBA").resize((140, 140), Image.LANCZOS)
        mask = Image.new("L", (140, 140), 0)
        ImageDraw.Draw(mask).ellipse([0, 0, 140, 140], fill=255)
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

    # Tanpura: Pa - Sa - Sa - Sa(low)
    for cycle in range(4):
        base = cycle * 6.0
        for i, f in enumerate([root * 1.5, root * 2, root * 2, root]):
            add_tone(string(f), base + i * 1.5, 7.0, 2.2, 0.22)

    # Halki ghanti
    for start in (6.0, 18.0):
        add_tone([(root * 4 * r, a) for r, a in [(1, 1), (2.76, .4), (5.4, .2)]],
                 start, 8.0, 2.5, 0.06)

    # Soft pad
    for k, (mult, amp) in enumerate([(1, .10), (1.5, .06), (2, .05)], start=1):
        f = round(root * mult * loop_sec) / loop_sec
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
    # 1) Agar repo me "music" folder me apne mp3/wav hain to unme se random
    files = glob.glob("music/*.mp3") + glob.glob("music/*.wav") + glob.glob("bgm*.mp3")
    if files:
        choice = random.choice(files)
        print("BGM (file):", choice)
        return choice
    # 2) Warna automatic bani hui music
    print("BGM (generated)")
    return generate_bgm()


# ------------------------------------------------------------------
# 6. Video render
# ------------------------------------------------------------------
def render_video(image_paths, audio_path, bgm_path, output_path="final_video.mp4"):
    voice = AudioFileClip(audio_path)
    duration = voice.duration
    per_image = duration / len(image_paths)

    clips = []
    for p in image_paths:
        frame = np.array(make_frame(p))
        clips.append(ImageClip(frame).set_duration(per_image))
    video = concatenate_videoclips(clips, method="compose")

    if bgm_path:
        bgm = AudioFileClip(bgm_path).volumex(BGM_VOLUME)
        bgm = audio_loop(bgm, duration=duration)
        final_audio = CompositeAudioClip([voice, bgm])
    else:
        final_audio = voice

    video = video.set_audio(final_audio)
    video.write_videofile(
        output_path, fps=15, codec="libx264", audio_codec="aac",
        preset="ultrafast", threads=2,
    )
    print("Video rendered")
    return output_path


# ------------------------------------------------------------------
# 7. YouTube upload
# ------------------------------------------------------------------
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
        t = str(t).strip()
        if t and total + len(t) < 450:
            clean_tags.append(t)
            total += len(t)

    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:4900],
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
    print("Uploaded! Video ID:", video_id)

    try:
        youtube.thumbnails().set(
            videoId=video_id, media_body=MediaFileUpload(thumb_path)
        ).execute()
        print("Thumbnail set")
    except Exception as e:
        print("Thumbnail error (channel verify hona zaroori hai):", e)
    return video_id


# ------------------------------------------------------------------
if __name__ == "__main__":
    print("Starting Daily Bhakti Video Automation...")

    data = generate_content()
    title = data.get("title", "भगवान की सुंदर कथा")
    story = data["story"]
    description = data.get("description", "") + (
        f"\n\n🙏 {CHANNEL_NAME} - रोज़ एक नई भक्ति कथा के लिए चैनल को "
        "Subscribe करें और बेल आइकन दबाएँ।"
    )
    tags = data.get("tags", ["bhakti", "katha"])
    thumb_text = data.get("thumbnail_text", title)
    queries = data.get("image_queries") or ["hindu temple", "diya lamp", "lotus"]

    asyncio.run(make_voiceover(story, "audio.mp3"))
    images = download_images(queries)
    if not images:
        raise SystemExit("Error: koi image nahi mili (Pixabay key check karein).")

    thumb = make_thumbnail(images[0], thumb_text)
    bgm = get_bgm()
    video = render_video(images, "audio.mp3", bgm)
    upload_youtube(video, thumb, title, description, tags)
    
