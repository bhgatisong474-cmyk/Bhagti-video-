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
# SETTINGS (yahan apne hisaab se badlein)
# ------------------------------------------------------------------
CHANNEL_NAME = "Spiritual Bhakti"      # video par dikhne wala channel naam
GEMINI_MODELS = [
    os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
    "gemini-2.5-flash",
    "gemini-1.5-flash",
    "gemini-flash-latest",
]
VOICE = "hi-IN-MadhurNeural"           # female ke liye: hi-IN-SwaraNeural
USE_TRENDING = True                    # Google Trends (India) se bhakti topic dhoondhna
VOICE_RATE = "+18%"                    # awaaz ki raftaar (High Retention & Engaging)
PRIVACY = "public"
MIN_CHAPTERS = 6                       # har video me itne se
MAX_CHAPTERS = 10                      # itne adhyay (random). 1 adhyay ~ 2 minute
WORDS_PER_CHAPTER = 280
SECONDS_PER_IMAGE = 6                  # har photo kitni der dikhe (fast pacing)
ZMAX = 1.25                            # zoom ki hadd
FADE = 0.9                             # photo badalne ka dissolve (second)
BGM_VOLUME = 0.12
FPS = 24
W, H = 1280, 720

GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
PIXABAY_KEY = os.environ.get("PIXABAY_API_KEY")
YT_CLIENT_ID = os.environ.get("YOUTUBE_CLIENT_ID")
YT_CLIENT_SECRET = os.environ.get("YOUTUBE_CLIENT_SECRET")
YT_REFRESH_TOKEN = os.environ.get("YOUTUBE_REFRESH_TOKEN")
TOPIC = (os.environ.get("TOPIC") or "").strip()   # n8n se aa sakta hai (tyohar/grahan)

# Roz ka topic is list se chalta hai (n8n se topic aaye to wo pehle).
TOPICS = [
    "Hanuman ji ka Sanjeevani buti lana",
    "Prahlad aur Narasimha avatar ki katha",
    "Dhruv ki tapasya",
    "Sudama aur Shri Krishna ki mitrata",
    "Shabri ke jhoothe ber aur Shri Ram",
    "Savitri aur Satyavan ki katha",
    "Ganesh ji ki mata-pita ki parikrama",
    "Markandeya aur Shiv ji ki kripa",
    "Gajendra Moksha ki katha",
    "Meerabai ki Krishna bhakti",
    "Sant Tulsidas aur Ramcharitmanas ki rachna",
    "Sant Kabir ke dohe aur unki shiksha",
    "Bhagirath aur Ganga avataran",
    "Samudra manthan ki katha",
    "Vaman avatar aur Raja Bali",
    "Ahilya uddhar ki katha",
    "Hanuman ji ka Lanka dahan",
    "Shri Krishna ki Govardhan leela",
    "Mata Sita aur Ashok Vatika me Hanuman ji se mulakat",
    "Kevat aur Shri Ram ki Ganga paar ki katha",
    "Bharat ka tyag aur Charan Paduka",
    "Mahabharat: Karna ka daan",
    "Bhagavad Gita: Karm yog ka sandesh",
    "Bhagavad Gita: Arjun ka moh aur Shri Krishna ka gyan",
    "Eklavya ki gurubhakti",
    "Shravan Kumar ki matri-pitri bhakti",
    "Nachiketa aur Yamraj ka samvad",
    "Mata Durga aur Mahishasur mardini",
    "Navdurga ke nau roop",
    "Ganesh-Lakshmi puja ka mahatva",
    "Jatayu ka balidan",
    "Hanuman ji aur Shani dev ki katha",
    "Shri Krishna ka janm aur Vasudev ka Yamuna paar karna",
    "Makhan chor Krishna ki bal leelayein",
    "Kaliya naag mardan",
    "Radha Krishna ka prem aur bhakti",
    "Ambarish aur Sudarshan chakra ki katha",
    "Rukmini ki bhakti aur Shri Krishna ka vivah",
    "Shiv Parvati vivah ki katha",
    "Shiv ji ne vish piya: Neelkanth ki katha",
    "Ardhnarishwar swaroop ka rahasya",
    "Sant Surdas ki Krishna bhakti",
    "Sant Ravidas ki katha",
    "Narsi Mehta ki bhakti",
    "Sant Tukaram aur Vitthal bhakti",
    "Raja Harishchandra ki satyavadita",
    "Dadhichi ka asthi daan",
    "Hanuman Chalisa ka arth aur mahatva",
    "Gayatri Mantra ka arth aur mahatva",
    "Mahamrityunjay Mantra ka arth aur mahatva",
    "Tulsi mata aur Shaligram ki katha",
    "Mata Anasuya ki pativrata shakti",
    "Ram Setu nirman aur gilahri ka yogdan",
    "Vibhishan ki Ram sharan",
    "Shri Ram aur Hanuman ji ka pehla milan",
    "Lakshman ki bhratri bhakti",
    "Satyanarayan katha ka mahatva",
    "Ekadashi vrat ka mahatva aur katha",
    "Pradosh vrat ki katha",
    "Hanuman ji ke janm ki katha",
    "Bhakt Pundalik aur Vitthal ji",
]

FESTIVALS = {
    "2026-10-20": "Dussehra (Vijayadashami): Shri Ram ki Ravan par vijay ki katha",
    "2026-10-29": "Karwa Chauth ki katha aur mahatva",
    "2026-11-06": "Dhanteras: Bhagwan Dhanvantari aur Dhanteras ki katha",
    "2026-11-08": "Diwali: Lakshmi Puja aur Shri Ram ke Ayodhya lautne ki katha",
    "2026-11-10": "Govardhan Puja: Shri Krishna ne Govardhan parvat uthaya",
    "2026-11-11": "Bhai Dooj: Yamraj aur Yamuna ki katha",
    "2026-11-13": "Chhath Puja: Surya dev, Chhathi maiya aur char din ke vrat ki katha",
    "2026-11-20": "Dev Uthani Ekadashi: Bhagwan Vishnu ka yog nidra se jaagna",
    "2026-11-21": "Tulsi Vivah: Tulsi mata aur Shaligram ki katha",
    "2026-11-24": "Kartik Purnima aur Dev Deepawali ka mahatva",
    "2026-12-20": "Gita Jayanti: Bhagavad Gita ka janm aur sandesh",
    "2027-01-14": "Makar Sankranti: Surya dev ka Uttarayan me pravesh",
    "2027-01-15": "Makar Sankranti: Bhishma Pitamah aur Uttarayan ki pratiksha",
    "2027-03-06": "Maha Shivratri: Shiv ji ki katha aur mahatva",
    "2027-03-21": "Holika Dahan: Prahlad, Holika aur Narasimha avatar ki katha",
    "2027-03-22": "Holi: Radha Krishna ki Holi leela",
    "2027-04-15": "Ram Navami: Shri Ram ke janm ki katha",
    "2027-04-20": "Hanuman Jayanti: Hanuman ji ke janm ki katha",
    "2027-05-09": "Akshaya Tritiya ka mahatva aur katha",
    "2027-07-18": "Guru Purnima: Ved Vyas aur guru ka mahatva",
    "2027-08-02": "Surya Grahan: Rahu-Ketu aur Samudra manthan ki katha",
    "2027-08-17": "Raksha Bandhan: Draupadi aur Shri Krishna ki katha",
    "2027-08-24": "Krishna Janmashtami: Shri Krishna ke janm ki katha",
    "2027-09-04": "Ganesh Chaturthi: Ganesh ji ke janm ki katha",
    "2027-09-30": "Sharad Navratri: Maa Durga ke nau roop",
    "2027-10-09": "Dussehra: Shri Ram ki Ravan par vijay ki katha",
    "2027-10-18": "Karwa Chauth ki katha aur mahatva",
    "2027-10-29": "Diwali: Lakshmi Puja aur Shri Ram ke Ayodhya lautne ki katha",
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
                r = requests.post(url, json=payload, timeout=300,
                                  headers={"x-goog-api-key": GEMINI_KEY,
                                           "Content-Type": "application/json"})
                if r.status_code in (401, 403):
                    raise SystemExit("Gemini API key galat ya band hai: " + r.text[:200])
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
                print(f"[round {rnd}][{model_name}] failed: {msg[:160].replace(chr(10), ' ')}")
                if "HTTP 404" in msg or "HTTP 400" in msg:
                    dead.add(model_name)
        wait = min(30 * rnd, 120)
        print(f"Sab models busy/fail, {wait}s ruk kar dobara...")
        time.sleep(wait)
    raise RuntimeError("Gemini se jawab nahi mila") from last_error

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
        terms = [t for t in dict.fromkeys(terms) if t][:60]
        if not terms:
            return None
        prompt = (
            "Below are today's trending Google searches in India:\n- " + "\n- ".join(terms) +
            "\n\nChoose AT MOST ONE that is about Hindu devotion and suitable for a calm "
            "devotional story video: a festival, deity, temple, saint, mantra, or katha. "
            'Return ONLY JSON: {"term": "<exact term or empty string>", '
            '"topic": "<short English description of the devotional video topic, or empty string>"}'
        )
        data = ask_gemini(prompt, as_json=True, max_rounds=2)
        if data.get("term") and data.get("topic"):
            return f"{data['topic']} (Trending in India today: {data['term']})"
    except Exception as e:
        print("Trending skip:", str(e)[:150])
    return None

def pick_topic():
    if TOPIC:
        return TOPIC
    ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    today = datetime.datetime.now(ist).date()
    special = FESTIVALS.get((today + datetime.timedelta(days=1)).isoformat())
    if special:
        return special + " (published one day before festival)"
    trending = trending_topic()
    if trending:
        return trending
    ordinal = today.toordinal()
    return TOPICS[ordinal % len(TOPICS)]

def generate_outline(n_chapters, topic):
    ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    today = datetime.datetime.now(ist).strftime("%d %B %Y")
    prompt = f"""
You plan high-CTR viral videos for a Hindi devotional YouTube channel called "{CHANNEL_NAME}".
Today's date: {today}. Topic: {topic}
Plan exactly {n_chapters} chapters.
Return ONLY valid JSON with keys:
- "title": Hindi, emotional & high curiosity, max 70 chars, 1 emoji at end (e.g. "रात में यह कथा सुनकर सोएँ, मन को शांति मिलेगी ✨")
- "description": Hindi, 100-160 words with hashtags #HindiKatha #Bhakti
- "tags": list of 10-15 strings
- "thumbnail_text": 3-5 punchy Hindi words (high CTR)
- "thumbnail_query": short English stock query
- "thumbnail_art_prompt": English prompt for 16:9 cinematic painting, main character on right, golden light
- "chapters": list of {n_chapters} objects with "heading", "summary", "image_queries" (list of 5 English queries)
"""
    def check(data):
        if len(data.get("chapters", [])) < 3:
            raise ValueError("chapters kam aaye")
    data = ask_gemini(prompt, as_json=True, check=check)
    data["chapters"] = data["chapters"][:n_chapters]
    return data

def clean_story(text):
    text = re.sub(r"[*#_`>~]+", "", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()

def write_chapters(outline, topic):
    chapters = outline["chapters"]
    n = len(chapters)
    outline_text = "\n".join(f"{i + 1}. {c['heading']} - {c.get('summary', '')}" for i, c in enumerate(chapters))
    texts = []
    for i, ch in enumerate(chapters):
        extra = ""
        if i == 0:
            extra += f" VERY IMPORTANT: begin DIRECTLY with a high-retention emotional hook (2-3 short dramatic sentences). No greeting in the first lines. Then greet viewers as {CHANNEL_NAME}."
        if i == n - 1:
            extra += " End with a short prayer, blessing, and a polite reminder to Like, Share and Subscribe."
        prompt = f"""
Write chapter {i + 1} of {n} for a Hindi devotional video.
Topic: {topic} | Title: {outline.get('title')}
Chapter Heading: {ch['heading']} ({ch.get('summary', '')})
Length: ~{WORDS_PER_CHAPTER} words. Fast pacing, emotional storytelling, vivid scenes, short sentences. Plain text only.{extra}
"""
        def check(txt):
            if len(clean_story(txt)) < 500:
                raise ValueError("chapter chhota hai")
        txt = clean_story(ask_gemini(prompt, check=check))
        texts.append(txt)
    return texts

async def _edge_save(text, path):
    import edge_tts
    await edge_tts.Communicate(text, VOICE, rate=VOICE_RATE).save(path)

def make_voiceover(text, path):
    for attempt in range(1, 4):
        try:
            asyncio.run(_edge_save(text, path))
            if os.path.exists(path) and os.path.getsize(path) > 5000:
                return path
        except Exception as e:
            print(f"Edge TTS attempt {attempt} failed:", str(e)[:100])
            time.sleep(3 * attempt)
    from gtts import gTTS
    gTTS(text=text, lang="hi", slow=False).save(path)
    return path

def audio_seconds(path):
    clip = AudioFileClip(path)
    d = clip.duration
    clip.close()
    return d

SEEN = set()
HEADERS = {"User-Agent": "Mozilla/5.0"}
_img_counter = [0]

def pixabay_hits(q, min_size=True, page=1):
    params = {"key": PIXABAY_KEY, "q": q, "image_type": "photo", "orientation": "horizontal", "safesearch": "true", "per_page": 20, "page": page}
    if min_size:
        params.update({"min_width": 1280, "min_height": 720})
    try:
        r = requests.get("https://pixabay.com/api/", params=params, headers=HEADERS, timeout=30)
        return r.json().get("hits", [])
    except Exception:
        return []

def fetch_image(hit):
    url = hit.get("largeImageURL")
    if not url or url in SEEN:
        return None
    try:
        data = requests.get(url, headers=HEADERS, timeout=60).content
        path = f"bg_{_img_counter[0]}.jpg"
        with open(path, "wb") as f:
            f.write(data)
        Image.open(path).verify()
        SEEN.add(url)
        _img_counter[0] += 1
        return path
    except Exception:
        return None

def download_chapter_images(queries, need):
    got = []
    for q in queries:
        if len(got) >= need:
            break
        for h in pixabay_hits(q):
            if len(got) >= need:
                break
            p = fetch_image(h)
            if p:
                got.append(p)
    return got

def download_thumb_image(query):
    for h in pixabay_hits(query):
        p = fetch_image(h)
        if p:
            return p
    return None

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

def circle_logo(size):
    logo = Image.open("Logo.jpg").convert("RGBA").resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size - 1, size - 1], fill=255)
    return logo, mask

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

def make_vignette(strength=150):
    yy, xx = np.mgrid[0:H, 0:W]
    r = np.sqrt(((xx / W) - 0.5) ** 2 + ((yy / H) - 0.5) ** 2) / 0.7071
    alpha = (np.clip((r - 0.5) / 0.5, 0, 1) ** 1.6 * strength).astype(np.uint8)
    arr = np.zeros((H, W, 4), np.uint8)
    arr[..., 3] = alpha
    return Image.fromarray(arr)

def make_overlay():
    bar = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(bar)
    d.rectangle([0, H - 95, W, H], fill=(0, 0, 0, 150))
    d.rectangle([0, H - 97, W, H - 95], fill=(255, 193, 7, 255))
    x = 20
    if os.path.exists("Logo.jpg"):
        logo, mask = circle_logo(70)
        bar.paste(logo, (20, H - 83), mask)
        d.ellipse([18, H - 85, 92, H - 11], outline=(255, 193, 7, 255), width=3)
        x = 105
    d.text((x, H - 78), CHANNEL_NAME, font=font_for(CHANNEL_NAME, 34), fill=(255, 255, 255, 255))
    bx0, by0, bx1, by1 = W - 290, H - 78, W - 20, H - 18
    d.rounded_rectangle([bx0, by0, bx1, by1], radius=14, fill=(220, 20, 20, 255))
    d.text((bx0 + 32, by0 + 12), "SUBSCRIBE", font=font_for("SUBSCRIBE", 32), fill=(255, 255, 255, 255))
    combined = Image.alpha_composite(make_vignette(), bar)
    return combined.convert("RGB"), combined.split()[3]

def make_title_layer(heading):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    font = font_for(heading, 52)
    tw = d.textlength(heading, font=font)
    x0, y0, bh = 50, 45, 104
    d.rounded_rectangle([x0, y0, x0 + int(tw) + 90, y0 + bh], radius=16, fill=(0, 0, 0, 165))
    d.rectangle([x0, y0 + 8, x0 + 8, y0 + bh - 8], fill=(255, 193, 7, 255))
    d.text((x0 + 36, y0 + 20), heading, font=font, fill=(255, 255, 255, 255))
    return layer.convert("RGB"), layer.split()[3]

def make_thumbnail(bg_path, text, out_path="thumb.jpg"):
    base = cover_crop(Image.open(bg_path))
    base = ImageEnhance.Color(base).enhance(1.45)
    base = ImageEnhance.Contrast(base).enhance(1.18)
    base = ImageEnhance.Brightness(base).enhance(1.06)
    img = base.convert("RGBA")

    grad = np.zeros((H, W, 4), np.uint8)
    grad[..., 0], grad[..., 1], grad[..., 2] = 150, 28, 0
    a = np.clip(1 - np.arange(W) / (W * 0.72), 0, 1) ** 1.2 * 205
    grad[..., 3] = a[None, :].astype(np.uint8)
    img = Image.alpha_composite(img, Image.fromarray(grad))
    img = Image.alpha_composite(img, make_vignette(95))
    d = ImageDraw.Draw(img)

    max_w = int(W * 0.60)
    size = 150
    lines = [text]
    while size > 58:
        font = font_for(text, size)
        lines = wrap_text(d, text, font, max_w)
        widest = max(d.textlength(l, font=font) for l in lines)
        if len(lines) <= 3 and widest <= max_w and len(lines) * size * 1.25 <= 480:
            break
        size -= 6
    font = font_for(text, size)
    line_h = int(size * 1.25)
    y = 118 + (480 - len(lines) * line_h) // 2
    colors = [(255, 232, 0, 255), (255, 255, 255, 255), (255, 150, 20, 255)]
    stroke = max(6, size // 12)
    for i, line in enumerate(lines):
        d.text((56, y), line, font=font, fill=colors[i % 3], stroke_width=stroke, stroke_fill=(15, 5, 0, 255))
        y += line_h

    tag = "भक्ति कथा"
    tf = font_for(tag, 42)
    tw = d.textlength(tag, font=tf)
    d.rounded_rectangle([50, 38, 50 + int(tw) + 54, 108], radius=18, fill=(230, 90, 0, 255), outline=(255, 215, 0, 255), width=3)
    d.text((77, 44), tag, font=tf, fill=(255, 255, 255, 255))

    btn = "पूरी कथा सुनें"
    bf = font_for(btn, 40)
    bw = d.textlength(btn, font=bf)
    d.rounded_rectangle([50, H - 100, 50 + int(bw) + 100, H - 36], radius=16, fill=(215, 15, 15, 255), outline=(255, 255, 255, 255), width=3)
    d.text((112, H - 94), btn, font=bf, fill=(255, 255, 255, 255))

    if os.path.exists("Logo.jpg"):
        logo, mask = circle_logo(150)
        lx, ly = W - 125, H - 125
        d.ellipse([lx - 90, ly - 90, lx + 90, ly + 90], fill=(255, 193, 7, 255))
        img.paste(logo, (lx - 75, ly - 75), mask)

    img.convert("RGB").save(out_path, quality=92)
    return out_path

def generate_bgm(path="bgm_gen.wav", loop_sec=24, sr=22050):
    root = random.choice([130.81, 146.83, 164.81, 196.00])
    n = int(loop_sec * sr)
    t = np.arange(n) / sr
    out = 0.12 * np.sin(2 * np.pi * root * t)
    stereo = (np.stack([out, out], axis=1) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(stereo.tobytes())
    return path

EFFECTS = [
    ((1.0, 0.0, 0.0), (ZMAX, 0.0, 0.0)),
    ((ZMAX, 0.0, 0.0), (1.0, 0.0, 0.0)),
]

def build_segments(durations, photos_by_chapter, pool):
    segs = []
    t = 0.0
    for d, photos in zip(durations, photos_by_chapter):
        photos = photos or pool
        n = max(1, int(round(d / SECONDS_PER_IMAGE)))
        per = d / n
        for k in range(n):
            segs.append({
                "start": t + k * per,
                "end": t + (k + 1) * per if k < n - 1 else t + d,
                "path": photos[k % len(photos)],
                "eff": EFFECTS[k % len(EFFECTS)],
            })
        t += d
    return segs

def make_video_clip(segs, total, chapter_starts, headings):
    ov_rgb, ov_mask = make_overlay()
    starts = [s["start"] for s in segs]

    def make_frame(t):
        i = max(0, min(bisect.bisect_right(starts, t) - 1, len(segs) - 1))
        img = cover_crop(Image.open(segs[i]["path"]))
        img.paste(ov_rgb, (0, 0), ov_mask)
        return np.array(img)

    return VideoClip(make_frame, duration=total)

def render_video(audio_paths, durations, photos_by_chapter, headings, bgm_path, output_path="final_video.mp4"):
    total = float(sum(durations))
    pool = [p for ph in photos_by_chapter for p in ph] or ["Logo.jpg"]
    chapter_starts = [sum(durations[:i]) for i in range(len(durations))]
    segs = build_segments(durations, photos_by_chapter, pool)
    video = make_video_clip(segs, total, chapter_starts, headings)

    voice = concatenate_audioclips([AudioFileClip(p) for p in audio_paths])
    bgm = audio_loop(AudioFileClip(bgm_path).volumex(BGM_VOLUME), duration=total)
    final_audio = CompositeAudioClip([voice, bgm]).set_duration(total)

    video = video.set_audio(final_audio)
    video.write_videofile(output_path, fps=FPS, codec="libx264", audio_codec="aac", preset="veryfast", audio_bitrate="192k")
    return output_path

def upload_youtube(video_path, thumb_path, title, description, tags):
    creds = Credentials(None, refresh_token=YT_REFRESH_TOKEN, token_uri="https://oauth2.googleapis.com/token", client_id=YT_CLIENT_ID, client_secret=YT_CLIENT_SECRET)
    youtube = build("youtube", "v3", credentials=creds)
    body = {
        "snippet": {"title": title[:100], "description": description[:4800], "tags": tags, "categoryId": "22", "defaultLanguage": "hi"},
        "status": {"privacyStatus": PRIVACY, "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(video_path, chunksize=8 * 1024 * 1024, resumable=True)
    res = None
    req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    while res is None:
        _, res = req.next_chunk(num_retries=5)
    video_id = res.get("id")
    try:
        youtube.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(thumb_path)).execute()
    except Exception as e:
        print("Thumbnail set error:", e)
    return video_id

if __name__ == "__main__":
    check_secrets()
    topic = pick_topic()
    n_chapters = random.randint(MIN_CHAPTERS, MAX_CHAPTERS)
    outline = generate_outline(n_chapters, topic)
    texts = write_chapters(outline, topic)
    headings = [c["heading"] for c in outline["chapters"]]

    audio_paths, durations = [], []
    for i, txt in enumerate(texts):
        p = make_voiceover(txt, f"voice_{i}.mp3")
        audio_paths.append(p)
        durations.append(audio_seconds(p))

    photos_by_chapter = [download_chapter_images(ch["image_queries"], max(1, int(d / SECONDS_PER_IMAGE))) for ch, d in zip(outline["chapters"], durations)]
    
    thumb_bg = download_thumb_image(outline.get("thumbnail_query") or outline["chapters"][0]["image_queries"][0]) or "Logo.jpg"
    thumb = make_thumbnail(thumb_bg, outline.get("thumbnail_text") or outline.get("title"))

    bgm = generate_bgm()
    video = render_video(audio_paths, durations, photos_by_chapter, headings, bgm)
    
    chapter_starts = [sum(durations[:i]) for i in range(len(durations))]
    desc = f"{outline.get('description', '')}\n\n📌 Chapters:\n" + "\n".join([f"{int(s)//60}:{int(s)%60:02d} {h}" for s, h in zip(chapter_starts, headings)])
    upload_youtube(video, thumb, outline.get("title"), desc, outline.get("tags", ["bhakti"]))
