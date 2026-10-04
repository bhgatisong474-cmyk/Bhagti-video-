import os
import re
import json
import glob
import math
import wave
import time
import bisect
import random
import asyncio
import datetime
import requests
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
from google import genai
from google.genai import types
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
    os.environ.get("GEMINI_MODEL", "gemini-3.8-flash"),
    "gemini-3.8-flash",
    "gemini-flash-latest",
]
VOICE = "hi-IN-MadhurNeural"           # female ke liye: hi-IN-SwaraNeural
PRIVACY = "public"
MIN_CHAPTERS = 5                       # har video me itne se
MAX_CHAPTERS = 9                       # itne adhyay (random). 1 adhyay ~ 2 minute
WORDS_PER_CHAPTER = 250
SECONDS_PER_IMAGE = 11                 # har photo kitni der dikhe
ZMAX = 1.2                             # zoom ki hadd
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


def check_secrets():
    missing = [n for n, v in [
        ("GEMINI_API_KEY", GEMINI_KEY), ("PIXABAY_API_KEY", PIXABAY_KEY),
        ("YOUTUBE_CLIENT_ID", YT_CLIENT_ID), ("YOUTUBE_CLIENT_SECRET", YT_CLIENT_SECRET),
        ("YOUTUBE_REFRESH_TOKEN", YT_REFRESH_TOKEN)] if not v]
    if missing:
        raise SystemExit("Ye secrets khaali hain: " + ", ".join(missing))


# ------------------------------------------------------------------
# 1. Gemini: outline (title, description, tags, adhyay) + har adhyay ki katha
# ------------------------------------------------------------------
def parse_json(text):
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    return json.loads(text)


def ask_gemini(prompt, as_json=False, check=None):
    """Gemini se jawab. 503 par ruk kar dobara, model band ho to agla model."""
    client = genai.Client(api_key=GEMINI_KEY)
    last_error = None
    for model_name in dict.fromkeys(GEMINI_MODELS):
        for attempt in range(1, 6):
            try:
                kwargs = {}
                if as_json:
                    kwargs["config"] = types.GenerateContentConfig(
                        response_mime_type="application/json")
                response = client.models.generate_content(
                    model=model_name, contents=prompt, **kwargs)
                result = parse_json(response.text) if as_json else (response.text or "").strip()
                if check:
                    check(result)
                return result
            except Exception as e:
                last_error = e
                msg = str(e)
                print(f"[{model_name}] attempt {attempt} failed: {msg[:150]}")
                if "404" in msg or "NOT_FOUND" in msg:
                    break
                if isinstance(e, ValueError):
                    time.sleep(5)
                else:
                    time.sleep(min(30 * attempt, 90))
    raise RuntimeError("Gemini se jawab nahi mila") from last_error


def pick_topic():
    if TOPIC:
        return TOPIC + " (this video is published one day before; mention it is coming tomorrow)"
    ordinal = datetime.date.today().toordinal()
    topic = TOPICS[ordinal % len(TOPICS)]
    cycle = ordinal // len(TOPICS)
    if cycle % 2 == 1:
        topic += " (present it from a fresh angle: lesser-known scenes, the lesson, and the meaning)"
    return topic


def generate_outline(n_chapters, topic):
    ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    today = datetime.datetime.now(ist).strftime("%d %B %Y")
    prompt = f"""
You plan videos for a Hindi devotional (bhakti) YouTube channel called "{CHANNEL_NAME}".
Today's date (IST): {today}.
Topic of today's video: {topic}

Plan one long video with exactly {n_chapters} chapters. Keep facts accurate as per
Hindu scriptures and traditions. No superstition, no fear-based claims, no
medical or astrology predictions.

Return ONLY valid JSON (no markdown) with these keys:
- "title": Hindi, catchy, max 90 characters
- "description": Hindi, 100-160 words, hashtags at the end
- "tags": list of 10-15 strings (Hindi + English)
- "thumbnail_text": max 5 Hindi words, punchy and emotional
- "thumbnail_query": one short English stock-photo search query for a beautiful
   divine thumbnail background (e.g. "krishna idol golden", "hanuman statue sunset")
- "chapters": list of exactly {n_chapters} objects, each with:
    "heading": Hindi, max 5 words,
    "summary": 1-2 sentences in English about what happens in this chapter,
    "image_queries": list of 5 short English stock-photo search queries that
       fit this chapter (e.g. "temple sunrise", "diya lamp night", "lotus flower",
       "river ganga aarti", "krishna idol")
"""

    def check(data):
        chapters = data.get("chapters") or []
        if len(chapters) < 3:
            raise ValueError("chapters kam aaye")
        for c in chapters:
            if not c.get("heading") or not c.get("image_queries"):
                raise ValueError("chapter adhoora")

    data = ask_gemini(prompt, as_json=True, check=check)
    data["chapters"] = data["chapters"][:n_chapters]
    print("Outline ready:", data.get("title"), "| chapters:", len(data["chapters"]))
    return data


def clean_story(text):
    text = re.sub(r"[*#_`>~]+", "", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def write_chapters(outline, topic):
    chapters = outline["chapters"]
    n = len(chapters)
    outline_text = "\n".join(
        f"{i + 1}. {c['heading']} - {c.get('summary', '')}" for i, c in enumerate(chapters))
    texts = []
    for i, ch in enumerate(chapters):
        tail = texts[-1][-500:] if texts else ""
        extra = ""
        if i == 0:
            extra += (f" Begin with a warm devotional greeting and welcome the viewers to the "
                      f"channel {CHANNEL_NAME}, then a short introduction to the topic.")
        if i == n - 1:
            extra += (" End with a short prayer and blessing, and politely request viewers to "
                      "like, share and subscribe and to come back tomorrow for another katha.")
        prompt = f"""
You are writing chapter {i + 1} of {n} of one long Hindi devotional narration for a YouTube video.
Video topic: {topic}
Video title: {outline.get('title')}

Full outline:
{outline_text}

The previous chapter ended with: "{tail}"

Write ONLY chapter {i + 1}: "{ch['heading']}" ({ch.get('summary', '')}).
Length: about {WORDS_PER_CHAPTER} words (not less than {WORDS_PER_CHAPTER - 40}).
Language: Hindi in Devanagari script, calm, emotional, devotional storytelling voice.
Rules: plain text only - no markdown, no headings, no bullet points, no stage
directions. Do not repeat earlier chapters. Keep facts accurate as per the
scriptures. Continue smoothly from the previous chapter.{extra}
"""

        def check(txt):
            if len(clean_story(txt)) < 600:
                raise ValueError("chapter bahut chhota aaya")

        txt = clean_story(ask_gemini(prompt, check=check))
        texts.append(txt)
        print(f"Chapter {i + 1}/{n} ready ({len(txt)} chars)")
    return texts


# ------------------------------------------------------------------
# 2. Voiceover (Edge TTS, fail ho to gTTS)
# ------------------------------------------------------------------
async def _edge_save(text, path):
    import edge_tts
    await edge_tts.Communicate(text, VOICE, rate="-5%").save(path)


def make_voiceover(text, path):
    for attempt in range(1, 4):
        try:
            asyncio.run(_edge_save(text, path))
            if os.path.exists(path) and os.path.getsize(path) > 5000:
                return path
            raise RuntimeError("audio khaali hai")
        except Exception as e:
            print(f"Edge TTS attempt {attempt} failed:", str(e)[:150])
            time.sleep(5 * attempt)
    print("Edge TTS fail hua, gTTS use kar rahe hain...")
    from gtts import gTTS
    gTTS(text=text, lang="hi", slow=False).save(path)
    return path


def audio_seconds(path):
    clip = AudioFileClip(path)
    d = clip.duration
    try:
        clip.close()
    except Exception:
        pass
    return d


# ------------------------------------------------------------------
# 3. Pixabay se photos
# ------------------------------------------------------------------
SEEN = set()
HEADERS = {"User-Agent": "Mozilla/5.0"}
_img_counter = [0]


def pixabay_hits(q, min_size=True):
    params = {
        "key": PIXABAY_KEY, "q": q, "image_type": "photo",
        "orientation": "horizontal", "safesearch": "true", "per_page": 20,
    }
    if min_size:
        params.update({"min_width": 1280, "min_height": 720})
    try:
        r = requests.get("https://pixabay.com/api/", params=params,
                         headers=HEADERS, timeout=30)
        if r.status_code == 429:
            time.sleep(30)
            r = requests.get("https://pixabay.com/api/", params=params,
                             headers=HEADERS, timeout=30)
        return r.json().get("hits", [])
    except Exception as e:
        print("Pixabay error:", q, str(e)[:100])
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
        Image.open(path).verify()                  # kharab image pakadne ke liye
        SEEN.add(url)
        _img_counter[0] += 1
        return path
    except Exception as e:
        print("Image download error:", str(e)[:100])
        return None


def download_chapter_images(queries, need):
    got = []
    qhits = {}
    per_query = max(1, math.ceil(need / max(1, len(queries))))
    # pehla round: har query se thodi-thodi photo
    for q in queries:
        if len(got) >= need:
            break
        hits = pixabay_hits(q) or pixabay_hits(q, min_size=False)
        random.shuffle(hits)
        qhits[q] = hits
        taken = 0
        for h in hits:
            if taken >= per_query or len(got) >= need:
                break
            path = fetch_image(h)
            if path:
                got.append(path)
                taken += 1
        time.sleep(0.4)
    # doosra round: kami ho to bachi hui photos se poora karo
    for q, hits in qhits.items():
        for h in hits:
            if len(got) >= need:
                break
            path = fetch_image(h)
            if path:
                got.append(path)
    return got


def download_thumb_image(query):
    hits = pixabay_hits(query)
    for h in hits[:6]:
        path = fetch_image(h)
        if path:
            return path
    return None


# ------------------------------------------------------------------
# 4. Fonts aur design helpers (Pillow)
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
    """Vignette + neeche ki patti (logo, channel naam, SUBSCRIBE). Har frame par same."""
    bar = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(bar)
    d.rectangle([0, H - 95, W, H], fill=(0, 0, 0, 150))
    d.rectangle([0, H - 97, W, H - 95], fill=(255, 193, 7, 255))     # sunehri line
    x = 20
    if os.path.exists("Logo.jpg"):
        logo, mask = circle_logo(70)
        bar.paste(logo, (20, H - 83), mask)
        d.ellipse([18, H - 85, 92, H - 11], outline=(255, 193, 7, 255), width=3)
        x = 105
    d.text((x, H - 78), CHANNEL_NAME, font=font_for(CHANNEL_NAME, 34),
           fill=(255, 255, 255, 255))
    bx0, by0, bx1, by1 = W - 290, H - 78, W - 20, H - 18
    d.rounded_rectangle([bx0, by0, bx1, by1], radius=14, fill=(220, 20, 20, 255))
    d.text((bx0 + 32, by0 + 12), "SUBSCRIBE", font=font_for("SUBSCRIBE", 32),
           fill=(255, 255, 255, 255))
    combined = Image.alpha_composite(make_vignette(), bar)
    return combined.convert("RGB"), combined.split()[3]


def make_title_layer(heading):
    """Har adhyay ke shuru me upar-baayein dikhne wala sunehra heading box."""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    font = font_for(heading, 52)
    tw = d.textlength(heading, font=font)
    x0, y0, bh = 50, 45, 104
    d.rounded_rectangle([x0, y0, x0 + int(tw) + 90, y0 + bh], radius=16, fill=(0, 0, 0, 165))
    d.rectangle([x0, y0 + 8, x0 + 8, y0 + bh - 8], fill=(255, 193, 7, 255))
    d.text((x0 + 36, y0 + 20), heading, font=font, fill=(255, 255, 255, 255))
    return layer.convert("RGB"), layer.split()[3]


# ------------------------------------------------------------------
# 5. Thumbnail (artistic)
# ------------------------------------------------------------------
def make_thumbnail(bg_path, text, out_path="thumb.jpg"):
    base = cover_crop(Image.open(bg_path))
    base = ImageEnhance.Color(base).enhance(1.35)
    base = ImageEnhance.Contrast(base).enhance(1.15)
    base = ImageEnhance.Brightness(base).enhance(0.95)
    img = base.convert("RGBA")

    # baayein taraf gehra gradient taaki likha saaf dikhe
    grad = np.zeros((H, W, 4), np.uint8)
    a = np.clip(1 - np.arange(W) / (W * 0.78), 0, 1) ** 1.1 * 225
    grad[..., 3] = a[None, :].astype(np.uint8)
    img = Image.alpha_composite(img, Image.fromarray(grad))
    img = Image.alpha_composite(img, make_vignette(130))
    d = ImageDraw.Draw(img)

    # text ko box me fit karna
    max_w = int(W * 0.60)
    size = 135
    lines = [text]
    while size > 56:
        font = font_for(text, size)
        lines = wrap_text(d, text, font, max_w)
        widest = max(d.textlength(l, font=font) for l in lines)
        if len(lines) <= 3 and widest <= max_w:
            break
