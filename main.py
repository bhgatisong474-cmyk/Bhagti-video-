import os
import re
import json
import glob
import html
import math
import wave
import subprocess
import time
import bisect
import random
import asyncio
import datetime
import requests
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from moviepy.editor import (
    VideoClip, AudioFileClip, CompositeAudioClip, concatenate_audioclips,
)
from moviepy.audio.fx.all import audio_loop, audio_fadeout

# ------------------------------------------------------------------
# SETTINGS
# ------------------------------------------------------------------
CHANNEL_NAME = "Spiritual Bhakti"      
GEMINI_MODELS = [
    os.environ.get("GEMINI_MODEL", "gemini-3.8-flash"),
    "gemini-3.8-flash",
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
]
VOICE = "hi-IN-MadhurNeural"           # female: hi-IN-SwaraNeural
USE_TRENDING = True                    
VOICE_RATE = "+18%"                    # तेज़ और आकर्षक वॉइस पेसिंग
PRIVACY = "public"
MIN_CHAPTERS = 5                       
MAX_CHAPTERS = 8                      
WORDS_PER_CHAPTER = 260
SECONDS_PER_IMAGE = 6                  # फ़ास्ट विजुअल चेंज ताकि ऑडियंस एंगेज रहे
ZMAX = 1.25                            
FADE = 0.8                             
BGM_VOLUME = 0.10
FPS = 24
W, H = 1280, 720

GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
PIXABAY_KEY = os.environ.get("PIXABAY_API_KEY")
YT_CLIENT_ID = os.environ.get("YOUTUBE_CLIENT_ID")
YT_CLIENT_SECRET = os.environ.get("YOUTUBE_CLIENT_SECRET")
YT_REFRESH_TOKEN = os.environ.get("YOUTUBE_REFRESH_TOKEN")
TOPIC = (os.environ.get("TOPIC") or "").strip()

TOPICS = [
    "Hanuman ji ka Sanjeevani buti lana",
    "Prahlad aur Narasimha avatar ki katha",
    "Dhruv ki tapasya aur Shiv bhakti",
    "Sudama aur Shri Krishna ki pavitra mitrata",
    "Shabri ke jhoothe ber aur Shri Ram ki kripa",
    "Ganesh ji ki mata-pita ki parikrama ka rahasya",
    "Gajendra Moksha ki katha aur mahatva",
    "Bhagirath aur Ganga avataran ki katha",
    "Samudra manthan aur Amrit ki katha",
    "Hanuman ji ka Lanka dahan aur Ravan ka ghamand",
    "Shri Krishna ki Govardhan leela",
    "Mahabharat: Karna ka daan aur uske punya",
    "Bhagavad Gita: Arjun ka moh aur Krishna gyan",
    "Mata Durga aur Mahishasur mardini katha",
    "Ganesh-Lakshmi puja ka rahasya aur mahatva",
    "Shiv ji ne vish piya: Neelkanth ki katha",
    "Ardhnarishwar swaroop ka rahasya",
    "Ram Setu nirman aur gilahri ka yogdan",
    "Satyanarayan katha ka mahatva aur labh",
    "Ekadashi vrat ka mahatva aur katha",
]

FESTIVALS = {
    "2026-10-20": "Dussehra (Vijayadashami): Shri Ram ki Ravan par vijay ki katha",
    "2026-10-29": "Karwa Chauth ki katha aur mahatva",
    "2026-11-06": "Dhanteras: Bhagwan Dhanvantari aur Dhanteras ki katha",
    "2026-11-08": "Diwali: Lakshmi Puja aur Shri Ram ke Ayodhya lautne ki katha",
    "2026-11-10": "Govardhan Puja: Shri Krishna ne Govardhan parvat uthaya",
    "2026-11-11": "Bhai Dooj: Yamraj aur Yamuna ki katha",
    "2026-11-13": "Chhath Puja: Surya dev aur Chhathi maiya ki katha",
    "2026-11-20": "Dev Uthani Ekadashi: Bhagwan Vishnu ka yog nidra se jaagna",
    "2026-11-21": "Tulsi Vivah: Tulsi mata aur Shaligram ki katha",
    "2026-12-20": "Gita Jayanti: Bhagavad Gita ka janm aur sandesh",
    "2027-01-14": "Makar Sankranti: Surya dev ka Uttarayan me pravesh",
    "2027-03-06": "Maha Shivratri: Shiv ji ki katha aur mahatva",
    "2027-03-22": "Holi: Radha Krishna ki Holi leela aur Bhakti",
    "2027-04-15": "Ram Navami: Shri Ram ke janm ki katha",
    "2027-04-20": "Hanuman Jayanti: Hanuman ji ke janm ki katha",
    "2027-08-24": "Krishna Janmashtami: Shri Krishna ke janm ki katha",
    "2027-09-04": "Ganesh Chaturthi: Ganesh ji ke janm ki katha",
}

def check_secrets():
    missing = [n for n, v in [
        ("GEMINI_API_KEY", GEMINI_KEY), ("PIXABAY_API_KEY", PIXABAY_KEY),
        ("YOUTUBE_CLIENT_ID", YT_CLIENT_ID), ("YOUTUBE_CLIENT_SECRET", YT_CLIENT_SECRET),
        ("YOUTUBE_REFRESH_TOKEN", YT_REFRESH_TOKEN)] if not v]
    if missing:
        raise SystemExit("Ye secrets khaali hain: " + ", ".join(missing))

def parse_json(text):
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    return json.loads(text)

def ask_gemini(prompt, as_json=False, check=None, max_rounds=8):
    models = list(dict.fromkeys(GEMINI_MODELS))
    dead = set()
    last_error = None
    for rnd in range(1, max_rounds + 1):
        alive = [m for m in models if m not in dead]
        if not alive:
            break
        for model_name in alive:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
            try:
                payload = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
                if as_json:
                    payload["generationConfig"] = {"responseMimeType": "application/json"}
                r = requests.post(url, json=payload, timeout=180,
                                  headers={"x-goog-api-key": GEMINI_KEY,
                                           "Content-Type": "application/json"})
                if r.status_code in (401, 403):
                    raise SystemExit("Gemini API key galat hai: " + r.text[:200])
                if r.status_code != 200:
                    raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
                parts = r.json()["candidates"][0]["content"]["parts"]
                text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
                result = parse_json(text) if as_json else text
                if check:
                    check(result)
                return result
            except SystemExit:
                raise
            except Exception as e:
                last_error = e
                msg = str(e)
                print(f"[round {rnd}][{model_name}] failed: {msg[:160]}")
                if "404" in msg or "400" in msg:
                    dead.add(model_name)
        wait = min(15 * rnd, 60)
        print(f"Models busy, waiting {wait}s...")
        time.sleep(wait)
    raise RuntimeError("Gemini Response Failed") from last_error

def trending_topic():
    if not USE_TRENDING:
        return None
    try:
        r = requests.get("https://trends.google.com/trending/rss?geo=IN", headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        items = re.findall(r"<item>(.*?)</item>", r.text, flags=re.S)
        terms = []
        for it in items:
            m = re.search(r"<title>(.*?)</title>", it, flags=re.S)
            if m:
                terms.append(html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", m.group(1))).strip())
        terms = [t for t in dict.fromkeys(terms) if t][:50]
        if not terms:
            return None
        prompt = (
            "Select one Hindu devotional topic from trending IN searches:\n- " + "\n- ".join(terms) +
            '\nReturn JSON: {"term": "<term_or_empty>", "topic": "<short_description_or_empty>"}'
        )
        data = ask_gemini(prompt, as_json=True, max_rounds=2)
        if data.get("term") and data.get("topic"):
            return f"{data['topic']} (Trending in India: {data['term']})"
    except Exception as e:
        print("Trending Skip:", str(e)[:100])
    return None

def pick_topic():
    if TOPIC:
        return TOPIC
    ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    today = datetime.datetime.now(ist).date()
    special = FESTIVALS.get((today + datetime.timedelta(days=1)).isoformat())
    if special:
        return special + " (Special Festival Katha for Tomorrow)"
    trending = trending_topic()
    if trending:
        return trending
    ordinal = today.toordinal()
    return TOPICS[ordinal % len(TOPICS)]

def generate_outline(n_chapters, topic):
    prompt = f"""
Plan a high-retention viral Hindi devotional YouTube video for "{CHANNEL_NAME}".
Topic: {topic}
Number of chapters: {n_chapters}

Return JSON with:
- "title": High CTR viral title in Hindi with 1 emoji at end (e.g., "सोने से पहले यह कथा जरूर सुनें, बदल जाएगी किस्मत 💥")
- "description": Hindi, 120-150 words with hashtags #HindiKatha #Bhakti
- "tags": list of 12 strings
- "thumbnail_text": 3-5 super catchy Hindi words (Shocking/Curious/Emotional)
- "thumbnail_query": short English stock query
- "chapters": list of {n_chapters} objects each with "heading", "summary", "image_queries" (list of 4 English strings)
"""
    data = ask_gemini(prompt, as_json=True)
    data["chapters"] = data["chapters"][:n_chapters]
    return data

def clean_story(text):
    return re.sub(r"[*#_`>~]+", "", text).strip()

def write_chapters(outline, topic):
    chapters = outline["chapters"]
    n = len(chapters)
    texts = []
    for i, ch in enumerate(chapters):
        extra = ""
        if i == 0:
            extra = f" Start immediately with an intense 2-sentence emotional mystery hook to grab attention. Then greet briefly as {CHANNEL_NAME}."
        elif i == n - 1:
            extra = " End with a heartwarming blessing and request viewers to Like and Subscribe for daily kathas."

        prompt = f"""
Write chapter {i + 1} of {n} in Devanagari Hindi for YouTube story narration.
Topic: {topic} | Chapter Heading: {ch['heading']}
Summary: {ch.get('summary')}
Length: ~{WORDS_PER_CHAPTER} words. Fast pacing, short sentences, high emotion. No markdown.{extra}
"""
        txt = clean_story(ask_gemini(prompt))
        texts.append(txt)
    return texts

async def _edge_save(text, path):
    import edge_tts
    await edge_tts.Communicate(text, VOICE, rate=VOICE_RATE).save(path)

def make_voiceover(text, path):
    try:
        asyncio.run(_edge_save(text, path))
        if os.path.exists(path) and os.path.getsize(path) > 3000:
            return path
    except Exception as e:
        print("Edge TTS fallback to gTTS:", str(e)[:100])
    from gtts import gTTS
    gTTS(text=text, lang="hi", slow=False).save(path)
    return path

def audio_seconds(path):
    clip = AudioFileClip(path)
    d = clip.duration
    clip.close()
    return d

HEADERS = {"User-Agent": "Mozilla/5.0"}
SEEN = set()
_img_counter = [0]

def fetch_pixabay(q):
    try:
        r = requests.get("https://pixabay.com/api/", params={
            "key": PIXABAY_KEY, "q": q, "image_type": "photo",
            "orientation": "horizontal", "safesearch": "true", "per_page": 10
        }, headers=HEADERS, timeout=20)
        hits = r.json().get("hits", [])
        random.shuffle(hits)
        for h in hits:
            url = h.get("largeImageURL")
            if url and url not in SEEN:
                data = requests.get(url, headers=HEADERS, timeout=30).content
                path = f"bg_{_img_counter[0]}.jpg"
                with open(path, "wb") as f:
                    f.write(data)
                SEEN.add(url)
                _img_counter[0] += 1
                return path
    except Exception:
        pass
    return None

def download_chapter_images(queries, need):
    got = []
    for q in queries:
        if len(got) >= need:
            break
        img = fetch_pixabay(q)
        if img:
            got.append(img)
    return got

def font_for(text, size):
    paths = ["font.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()

def cover_crop(img, w=W, h=H):
    img = img.convert("RGB")
    scale = max(w / img.width, h / img.height)
    img = img.resize((int(img.width * scale) + 1, int(img.height * scale) + 1), Image.LANCZOS)
    left = (img.width - w) // 2
    top = (img.height - h) // 2
    return img.crop((left, top, left + w, top + h))

def make_thumbnail(bg_path, text, out_path="thumb.jpg"):
    base = cover_crop(Image.open(bg_path))
    base = ImageEnhance.Color(base).enhance(1.5)
    base = ImageEnhance.Contrast(base).enhance(1.2)
    img = base.convert("RGBA")

    # Dark gradient overlay for extreme readability
    grad = np.zeros((H, W, 4), np.uint8)
    grad[..., :3] = [0, 0, 0]
    grad[..., 3] = np.clip(1.5 - np.arange(W) / (W * 0.65), 0, 1) ** 1.1 * 220
    img = Image.alpha_composite(img, Image.fromarray(grad))
    d = ImageDraw.Draw(img)

    # Big Yellow-White Text
    font = font_for(text, 82)
    words = text.split()
    line1 = " ".join(words[:2]) if len(words) >= 2 else text
    line2 = " ".join(words[2:]) if len(words) > 2 else ""

    y = 180
    d.text((60, y), line1, font=font, fill=(255, 235, 0, 255), stroke_width=10, stroke_fill=(0, 0, 0, 255))
    if line2:
        d.text((60, y + 110), line2, font=font, fill=(255, 255, 255, 255), stroke_width=10, stroke_fill=(0, 0, 0, 255))

    # High CTR Badge
    d.rounded_rectangle([60, 50, 320, 130], radius=15, fill=(220, 20, 20, 255), outline=(255, 255, 255, 255), width=3)
    d.text((85, 65), "खास कथा", font=font_for("खास कथा", 42), fill=(255, 255, 255, 255))

    if os.path.exists("Logo.jpg"):
        logo = Image.open("Logo.jpg").convert("RGBA").resize((120, 120))
        img.paste(logo, (W - 150, H - 150), logo)

    img.convert("RGB").save(out_path, quality=95)
    return out_path

def generate_bgm(path="bgm.wav", loop_sec=20, sr=22050):
    t = np.arange(int(loop_sec * sr)) / sr
    out = 0.15 * np.sin(2 * np.pi * 146.83 * t) + 0.08 * np.sin(2 * np.pi * 220.00 * t)
    stereo = (np.stack([out, out], axis=1) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(stereo.tobytes())
    return path

def build_segments(durations, photos_by_chapter):
    segs = []
    t = 0.0
    for d, photos in zip(durations, photos_by_chapter):
        photos = photos or ["Logo.jpg"]
        n = max(1, int(round(d / SECONDS_PER_IMAGE)))
        per = d / n
        for k in range(n):
            segs.append({
                "start": t + k * per,
                "end": t + (k + 1) * per,
                "path": photos[k % len(photos)]
            })
        t += d
    return segs

def render_video(audio_paths, durations, photos_by_chapter, output_path="final_video.mp4"):
    total = float(sum(durations))
    segs = build_segments(durations, photos_by_chapter)
    starts = [s["start"] for s in segs]

    def make_frame(t):
        i = max(0, min(bisect.bisect_right(starts, t) - 1, len(segs) - 1))
        img = cover_crop(Image.open(segs[i]["path"]))
        return np.array(img)

    video = VideoClip(make_frame, duration=total)
    voice = concatenate_audioclips([AudioFileClip(p) for p in audio_paths])
    bgm_file = generate_bgm()
    bgm = audio_loop(AudioFileClip(bgm_file).volumex(BGM_VOLUME), duration=total)
    
    final_audio = CompositeAudioClip([voice, bgm]).set_duration(total)
    video = video.set_audio(final_audio)
    video.write_videofile(output_path, fps=FPS, codec="libx264", audio_codec="aac", preset="ultrafast")
    return output_path

def upload_youtube(video_path, thumb_path, title, description, tags):
    creds = Credentials(None, refresh_token=YT_REFRESH_TOKEN, token_uri="https://oauth2.googleapis.com/token",
                        client_id=YT_CLIENT_ID, client_secret=YT_CLIENT_SECRET)
    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": title[:100], "description": description[:4500],
            "tags": tags, "categoryId": "22", "defaultLanguage": "hi"
        },
        "status": {"privacyStatus": PRIVACY, "selfDeclaredMadeForKids": False}
    }
    media = MediaFileUpload(video_path, chunksize=8 * 1024 * 1024, resumable=True)
    req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    res = None
    while res is None:
        st, res = req.next_chunk(num_retries=5)
    video_id = res.get("id")
    try:
        youtube.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(thumb_path)).execute()
    except Exception as e:
        print("Thumb upload failed:", e)
    return video_id

if __name__ == "__main__":
    check_secrets()
    topic = pick_topic()
    n_chapters = random.randint(MIN_CHAPTERS, MAX_CHAPTERS)
    outline = generate_outline(n_chapters, topic)
    texts = write_chapters(outline, topic)

    audio_paths, durations = [], []
    for i, txt in enumerate(texts):
        p = make_voiceover(txt, f"v_{i}.mp3")
        audio_paths.append(p)
        durations.append(audio_seconds(p))

    photos_by_chapter = [download_chapter_images(ch["image_queries"], max(1, int(d / SECONDS_PER_IMAGE))) for ch, d in zip(outline["chapters"], durations)]
    
    bg = fetch_pixabay(outline.get("thumbnail_query", "god")) or "Logo.jpg"
    thumb = make_thumbnail(bg, outline.get("thumbnail_text", outline["title"]))

    v_file = render_video(audio_paths, durations, photos_by_chapter)
    upload_youtube(v_file, thumb, outline["title"], outline["description"], outline["tags"])
                          
