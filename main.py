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
    os.environ.get("GEMINI_MODEL", "gemini-3.8-flash"),
    "gemini-3.8-flash",
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
]
VOICE = "hi-IN-MadhurNeural"           # female ke liye: hi-IN-SwaraNeural
USE_TRENDING = True                    # Google Trends (India) se bhakti topic dhoondhna
VOICE_RATE = "+12%"                    # awaaz ki raftaar (+0% normal, +20% bahut tez)
PRIVACY = "public"
MIN_CHAPTERS = 6                       # har video me itne se
MAX_CHAPTERS = 10                      # itne adhyay (random). 1 adhyay ~ 2 minute
WORDS_PER_CHAPTER = 280
SECONDS_PER_IMAGE = 7                  # har photo kitni der dikhe (kam = tez video)
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


# Tyohar / grahan: "tyohar ki tarikh": "topic". Video us se EK DIN PEHLE ban-ta hai.
# (Kuch tarikhen alag panchang me +-1 din alag hoti hain, isliye dono din ke topic alag rakhe hain.)
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
    "2027-08-02": ("Surya Grahan (partial in India): Rahu-Ketu aur Samudra manthan ki katha, "
                   "grahan se jude dharmik vishwas, without fear or superstition"),
    "2027-08-17": "Raksha Bandhan: Draupadi aur Shri Krishna ki katha",
    "2027-08-24": "Krishna Janmashtami: Shri Krishna ke janm ki katha",
    "2027-08-25": "Krishna Janmashtami: Shri Krishna ki bal leelayein aur Dahi Handi",
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


# ------------------------------------------------------------------
# 1. Gemini: outline (title, description, tags, adhyay) + har adhyay ki katha
# ------------------------------------------------------------------
def parse_json(text):
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    return json.loads(text)


def ask_gemini(prompt, as_json=False, check=None, max_rounds=8):
    """Gemini se jawab (seedha REST API, SDK ki zaroorat nahi).
    Ek model par 503 (high demand) aaye to turant agla model, har round ke baad
    thoda ruk kar. Jo model 404 de use chhod dete hain."""
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
    """Google Trends (India) ki aaj ki trending list me se koi bhakti wala topic. Na mile to None."""
    if not USE_TRENDING:
        return None
    try:
        r = requests.get("https://trends.google.com/trending/rss?geo=IN", headers=HEADERS, timeout=30)
        items = re.findall(r"<item>(.*?)</item>", r.text, flags=re.S)
        terms = []
        for it in items:
            m = re.search(r"<title>(.*?)</title>", it, flags=re.S)
            if m:
                terms.append(html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", m.group(1))).strip())
        terms = [t for t in dict.fromkeys(terms) if t][:60]
        if not terms:
            print("Trending list khaali mili")
            return None
        print("Trending (top):", terms[:8])
        prompt = (
            "Below are today's trending Google searches in India:\n- " + "\n- ".join(terms) +
            "\n\nChoose AT MOST ONE that is clearly about Hindu devotion and is suitable for a calm "
            "devotional story video: a festival, deity, temple/pilgrimage, saint, mantra, vrat or katha. "
            "Ignore politics, crime, accidents, deaths, celebrities, movies, sports, scams and anything "
            "sensitive or controversial. If none fits, leave it empty.\n"
            'Return ONLY JSON: {"term": "<exact term or empty string>", '
            '"topic": "<short English description of the devotional video topic, or empty string>"}'
        )
        def check(d):
            if not isinstance(d, dict) or "term" not in d:
                raise ValueError("galat format")

        data = ask_gemini(prompt, as_json=True, max_rounds=2, check=check)
        if data.get("term") and data.get("topic"):
            print("Trending bhakti topic mila:", data["term"])
            return f"{data['topic']} (it is trending in India today: {data['term']})"
        print("Aaj trending me koi bhakti topic nahi")
    except Exception as e:
        print("Trending skip:", str(e)[:150])
    return None


def pick_topic():
    if TOPIC:
        return TOPIC + " (this video is published one day before; mention it is coming tomorrow)"
    ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    today = datetime.datetime.now(ist).date()
    special = FESTIVALS.get((today + datetime.timedelta(days=1)).isoformat())
    if special:
        return special + " (this video is published one day before the festival; say it is coming tomorrow)"
    trending = trending_topic()
    if trending:
        return trending
    ordinal = today.toordinal()
    topic = TOPICS[ordinal % len(TOPICS)]
    if (ordinal // len(TOPICS)) % 2 == 1:
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
medical or astrology predictions, and no false promises of money/health/miracles.

Return ONLY valid JSON (no markdown) with these keys:
- "title": Hindi, emotional and curiosity-driven, max 70 characters, one emoji at the
   end, truthful. Example style: "रात में यह कथा सुनकर सोएँ, मन को शांति मिलेगी ✨"
- "description": Hindi, 100-160 words, hashtags at the end (include #HindiKatha #Bhakti)
- "tags": list of 10-15 strings (Hindi + English)
- "thumbnail_text": 4-7 Hindi words, big, punchy and emotional (like a film poster line)
- "thumbnail_query": one short English stock-photo search query for a beautiful
   divine thumbnail background (e.g. "krishna idol golden", "hanuman statue sunset")
- "thumbnail_art_prompt": an English prompt (2-3 sentences) to paint a vibrant, ultra
   detailed, cinematic 16:9 devotional digital painting for this story: the main
   character on the RIGHT side of the frame, glowing golden light, rich saffron and
   blue colours, empty space on the LEFT, absolutely no text or letters in the image
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
            extra += (" VERY IMPORTANT: begin DIRECTLY with a gripping hook - 2 or 3 short, "
                      "dramatic sentences (a question or the most emotional moment of the story) "
                      "so the viewer cannot stop listening. No greeting in the first lines. "
                      f"After the hook, greet the viewers in one short line and name the channel {CHANNEL_NAME}.")
        if i < n - 1:
            extra += " End the chapter with a small curiosity hook that makes the viewer want the next chapter."
        else:
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
Language: Hindi in Devanagari script, emotional devotional storytelling voice.
Style: SHORT sentences, vivid scenes, some dialogue, no long lectures - it must never feel boring.
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
    await edge_tts.Communicate(text, VOICE, rate=VOICE_RATE).save(path)


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
    try:                                           # gTTS ko ffmpeg se thoda tez karo
        fast = path.replace(".mp3", "_fast.mp3")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", path,
                        "-filter:a", "atempo=1.12", fast], check=True)
        os.replace(fast, path)
    except Exception as e:
        print("gTTS speed-up skip:", str(e)[:100])
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


def pixabay_hits(q, min_size=True, page=1):
    params = {
        "key": PIXABAY_KEY, "q": q, "image_type": "photo",
        "orientation": "horizontal", "safesearch": "true", "per_page": 20, "page": page,
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
    # teesra round: ab bhi kami ho to in queries ke agle page se
    for page in (2, 3):
        if len(got) >= need:
            break
        for q in queries:
            if len(got) >= need:
                break
            for h in pixabay_hits(q, page=page):
                if len(got) >= need:
                    break
                path = fetch_image(h)
                if path:
                    got.append(path)
            time.sleep(0.4)
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
# 5. Thumbnail (chatak, badi likhawat, AI chitra)
# ------------------------------------------------------------------
IMAGE_MODELS = ["gemini-3.8-flash-image", "gemini-2.5-flash-image", "gemini-flash-image-latest"]


def generate_ai_image(prompt, out_path="thumb_ai.png"):
    """Gemini se thumbnail ka chitra banwao. Na ban sake to None (tab Pixabay chalega)."""
    import base64
    import io
    for model_name in IMAGE_MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
        try:
            r = requests.post(
                url, timeout=180,
                headers={"x-goog-api-key": GEMINI_KEY, "Content-Type": "application/json"},
                json={"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                      "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]}})
            if r.status_code != 200:
                print(f"AI image [{model_name}] HTTP {r.status_code}: {r.text[:120]!r}")
                continue
            for part in r.json()["candidates"][0]["content"]["parts"]:
                inline = part.get("inlineData") or part.get("inline_data")
                if inline and inline.get("data"):
                    img = Image.open(io.BytesIO(base64.b64decode(inline["data"])))
                    img.convert("RGB").save(out_path)
                    print("AI thumbnail image ready:", model_name)
                    return out_path
            print(f"AI image [{model_name}]: jawab me chitra nahi mila")
        except Exception as e:
            print(f"AI image [{model_name}] error:", str(e)[:120])
    return None


def draw_star(d, x, y, r, fill):
    pts = [(x, y - r), (x + r * 0.22, y - r * 0.22), (x + r, y), (x + r * 0.22, y + r * 0.22),
           (x, y + r), (x - r * 0.22, y + r * 0.22), (x - r, y), (x - r * 0.22, y - r * 0.22)]
    d.polygon(pts, fill=fill)


def make_thumbnail(bg_path, text, out_path="thumb.jpg"):
    base = cover_crop(Image.open(bg_path))
    base = ImageEnhance.Color(base).enhance(1.45)
    base = ImageEnhance.Contrast(base).enhance(1.18)
    base = ImageEnhance.Brightness(base).enhance(1.06)
    img = base.convert("RGBA")

    # sunehri kirnen (sunburst)
    rays = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    rd = ImageDraw.Draw(rays)
    cx, cy, n_rays = int(W * 0.74), int(H * 0.42), 20
    for i in range(n_rays):
        a0 = 2 * math.pi * i / n_rays
        a1 = a0 + math.pi / n_rays
        rd.polygon([(cx, cy),
                    (cx + math.cos(a0) * 1700, cy + math.sin(a0) * 1700),
                    (cx + math.cos(a1) * 1700, cy + math.sin(a1) * 1700)],
                   fill=(255, 220, 110, 42))
    img = Image.alpha_composite(img, rays)

    # baayein taraf garam (laal-narangi) gradient, taaki likhawat chamke
    grad = np.zeros((H, W, 4), np.uint8)
    grad[..., 0], grad[..., 1], grad[..., 2] = 150, 28, 0
    a = np.clip(1 - np.arange(W) / (W * 0.72), 0, 1) ** 1.2 * 205
    grad[..., 3] = a[None, :].astype(np.uint8)
    img = Image.alpha_composite(img, Image.fromarray(grad))
    img = Image.alpha_composite(img, make_vignette(95))
    d = ImageDraw.Draw(img)

    # likhawat badi se badi, 3 line tak
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
        d.text((62, y + 8), line, font=font, fill=(0, 0, 0, 200),
               stroke_width=stroke + 6, stroke_fill=(0, 0, 0, 200))              # parchhai
        d.text((56, y), line, font=font, fill=(110, 0, 0, 255),
               stroke_width=stroke + 6, stroke_fill=(110, 0, 0, 255))            # gehra laal kinara
        d.text((56, y), line, font=font, fill=colors[i % 3],
               stroke_width=stroke, stroke_fill=(15, 5, 0, 255))                 # kaala kinara
        y += line_h

    # chamak (sparkle)
    draw_star(d, 560, 70, 30, (255, 255, 255, 235))
    draw_star(d, 90, 640, 20, (255, 235, 120, 235))
    draw_star(d, 640, 600, 16, (255, 255, 255, 220))

    # upar-baayein kesariya tag aur niche laal button
    tag = "भक्ति कथा"
    tf = font_for(tag, 42)
    tw = d.textlength(tag, font=tf)
    d.rounded_rectangle([50, 38, 50 + int(tw) + 54, 108], radius=18, fill=(230, 90, 0, 255),
                        outline=(255, 215, 0, 255), width=3)
    d.text((77, 44), tag, font=tf, fill=(255, 255, 255, 255))

    btn = "पूरी कथा सुनें"
    bf = font_for(btn, 40)
    bw = d.textlength(btn, font=bf)
    d.rounded_rectangle([50, H - 100, 50 + int(bw) + 100, H - 36], radius=16, fill=(215, 15, 15, 255),
                        outline=(255, 255, 255, 255), width=3)
    d.polygon([(72, H - 84), (72, H - 52), (98, H - 68)], fill=(255, 255, 255, 255))
    d.text((112, H - 94), btn, font=bf, fill=(255, 255, 255, 255))

    # logo (sunehri ring ke saath)
    if os.path.exists("Logo.jpg"):
        logo, mask = circle_logo(150)
        lx, ly = W - 125, H - 125
        d.ellipse([lx - 90, ly - 90, lx + 90, ly + 90], fill=(255, 193, 7, 255))
        img.paste(logo, (lx - 75, ly - 75), mask)

    img.convert("RGB").save(out_path, quality=92)
    print("Thumbnail ready")
    return out_path


# ------------------------------------------------------------------
# 6. Background music (automatic, copyright-free)
# ------------------------------------------------------------------
def generate_bgm(path="bgm_gen.wav", loop_sec=24, sr=22050):
    """Tanpura jaisi drone + soft pad + ghanti. Har baar alag swar (root note)."""
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

    for cycle in range(4):
        base = cycle * 6.0
        for i, f in enumerate([root * 1.5, root * 2, root * 2, root]):
            add_tone(string(f), base + i * 1.5, 7.0, 2.2, 0.22)

    for start in (6.0, 18.0):
        add_tone([(root * 4 * r, a) for r, a in [(1, 1), (2.76, .4), (5.4, .2)]],
                 start, 8.0, 2.5, 0.06)

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
    files = glob.glob("music/*.mp3") + glob.glob("music/*.wav") + glob.glob("bgm*.mp3")
    if files:
        choice = random.choice(files)
        print("BGM (file):", choice)
        return choice
    print("BGM (generated)")
    return generate_bgm()


# ------------------------------------------------------------------
# 7. Video render: zoom in/out + pan + dissolve + adhyay heading
# ------------------------------------------------------------------
# (shuru: zoom, x, y) -> (ant: zoom, x, y); x,y -1..1 = photo ke andar ghoomna
EFFECTS = [
    ((1.0, 0.0, 0.0), (ZMAX, 0.0, 0.0)),        # zoom in
    ((ZMAX, 0.0, 0.0), (1.0, 0.0, 0.0)),        # zoom out
    ((1.18, -1.0, 0.0), (1.18, 1.0, 0.0)),      # baayein se daayein pan
    ((1.18, 1.0, 0.0), (1.18, -1.0, 0.0)),      # daayein se baayein pan
    ((1.0, 0.0, 0.0), (ZMAX, 0.9, -0.6)),       # zoom in, kone ki taraf
    ((ZMAX, -0.7, 0.6), (1.0, 0.0, 0.0)),       # zoom out, kone se
]
_big_cache = {}


def get_big(path):
    if path not in _big_cache:
        if len(_big_cache) >= 4:
            _big_cache.pop(next(iter(_big_cache)))
        _big_cache[path] = cover_crop(Image.open(path), int(W * ZMAX), int(H * ZMAX))
    return _big_cache[path]


def view(big, eff, p):
    (z0, x0, y0), (z1, x1, y1) = eff
    p = p * p * (3 - 2 * p)                      # smooth shuru/ant
    z = z0 + (z1 - z0) * p
    ox = x0 + (x1 - x0) * p
    oy = y0 + (y1 - y0) * p
    cw, ch = big.width / z, big.height / z
    cx = big.width / 2 + ox * (big.width - cw) / 2
    cy = big.height / 2 + oy * (big.height - ch) / 2
    return big.resize((W, H), Image.BICUBIC,
                      box=(cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2))


def build_segments(durations, photos_by_chapter, pool):
    segs = []
    t = 0.0
    eff_i = random.randrange(len(EFFECTS))
    for d, photos in zip(durations, photos_by_chapter):
        photos = photos or pool
        n = max(1, int(round(d / SECONDS_PER_IMAGE)))
        per = d / n
        for k in range(n):
            segs.append({
                "start": t + k * per,
                "end": t + (k + 1) * per if k < n - 1 else t + d,
                "path": photos[k % len(photos)],
                "eff": EFFECTS[eff_i % len(EFFECTS)],
            })
            eff_i += 1
        t += d
    return segs


def make_video_clip(segs, total, chapter_starts, headings):
    ov_rgb, ov_mask = make_overlay()
    titles = []
    for s, h in zip(chapter_starts, headings):
        rgb, mask = make_title_layer(h)
        titles.append((s + 1.0, s + 6.5, rgb, mask))
    starts = [s["start"] for s in segs]
    black = Image.new("RGB", (W, H), (0, 0, 0))

    def make_frame(t):
        i = max(0, min(bisect.bisect_right(starts, t) - 1, len(segs) - 1))
        s = segs[i]
        span = max(s["end"] - s["start"], 1e-6)
        p = min(max((t - s["start"]) / span, 0.0), 1.0)
        img = view(get_big(s["path"]), s["eff"], p)
        if i + 1 < len(segs):
            left = s["end"] - t
            if left < FADE:
                nxt = segs[i + 1]
                nimg = view(get_big(nxt["path"]), nxt["eff"], 0.0)
                img = Image.blend(img, nimg, min(max(1 - left / FADE, 0.0), 1.0))
        img.paste(ov_rgb, (0, 0), ov_mask)
        for (a, b, rgb, mask) in titles:
            if a <= t <= b:
                k = min(1.0, (t - a) / 0.6, (b - t) / 0.6)
                img.paste(rgb, (0, 0), mask.point(lambda v, k=k: int(v * k)))
        fade = min(1.0, t / 1.2, max(total - t, 0.0) / 1.5)
        if fade < 1.0:
            img = Image.blend(black, img, max(fade, 0.0))
        return np.array(img)

    return VideoClip(make_frame, duration=total)


def render_video(audio_paths, durations, photos_by_chapter, headings, bgm_path,
                 output_path="final_video.mp4"):
    total = float(sum(durations))
    pool = [p for ph in photos_by_chapter for p in ph]
    if not pool:
        pool = ["Logo.jpg"]
    chapter_starts = [sum(durations[:i]) for i in range(len(durations))]
    segs = build_segments(durations, photos_by_chapter, pool)
    video = make_video_clip(segs, total, chapter_starts, headings)

    voice = concatenate_audioclips([AudioFileClip(p) for p in audio_paths])
    if bgm_path:
        bgm = audio_loop(AudioFileClip(bgm_path).volumex(BGM_VOLUME), duration=total)
        try:
            bgm = audio_fadeout(bgm, 3)
        except Exception as e:
            print("fadeout skip:", e)
        final_audio = CompositeAudioClip([voice, bgm]).set_duration(total)
    else:
        final_audio = voice

    video = video.set_audio(final_audio)
    video.write_videofile(
        output_path, fps=FPS, codec="libx264", audio_codec="aac",
        preset="veryfast", threads=4, audio_bitrate="192k",
        ffmpeg_params=["-crf", "24", "-pix_fmt", "yuv420p"],
    )
    print("Video rendered, minutes:", round(total / 60, 1), "| photos:", len(segs))
    return output_path


# ------------------------------------------------------------------
# 8. YouTube upload
# ------------------------------------------------------------------
def clean(s):
    return re.sub(r"[<>]", "", str(s)).strip()


def cut_bytes(s, limit):
    return s.encode("utf-8")[:limit].decode("utf-8", "ignore")


def fmt_time(sec):
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def build_description(base, headings, starts):
    lines = [clean(base), "", "📌 अध्याय (Chapters):"]
    for h, s in zip(headings, starts):
        lines.append(f"{fmt_time(s)} {clean(h)}")
    lines += ["", f"🙏 {CHANNEL_NAME} - रोज़ एक नई भक्ति कथा के लिए चैनल को "
                  "Subscribe करें और बेल आइकन दबाएँ।"]
    return "\n".join(lines)


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
            "description": cut_bytes(description, 4800),          # YouTube limit bytes me
            "tags": clean_tags,
            "categoryId": "22",
            "defaultLanguage": "hi",
            "defaultAudioLanguage": "hi",
        },
        "status": {"privacyStatus": PRIVACY, "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(video_path, chunksize=8 * 1024 * 1024, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        status, response = request.next_chunk(num_retries=5)
        if status:
            print(f"Upload {int(status.progress() * 100)}%")
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

    topic = pick_topic()
    n_chapters = random.randint(MIN_CHAPTERS, MAX_CHAPTERS)
    print("Topic:", topic, "| chapters:", n_chapters)

    outline = generate_outline(n_chapters, topic)
    chapters = outline["chapters"]
    texts = write_chapters(outline, topic)
    headings = [clean(c["heading"]) for c in chapters]

    audio_paths, durations = [], []
    for i, txt in enumerate(texts):
        path = make_voiceover(txt, f"voice_{i}.mp3")
        audio_paths.append(path)
        durations.append(audio_seconds(path))
    print("Voice length (minutes):", round(sum(durations) / 60, 1))

    photos_by_chapter = []
    for ch, d in zip(chapters, durations):
        need = max(1, int(round(d / SECONDS_PER_IMAGE)))
        photos_by_chapter.append(download_chapter_images(ch["image_queries"], need))
    print("Photos per chapter:", [len(p) for p in photos_by_chapter])

    art_prompt = outline.get("thumbnail_art_prompt") or (
        "Vibrant ultra detailed cinematic 16:9 devotional digital painting, "
        f"{outline.get('thumbnail_query') or topic}, main character on the right, "
        "glowing golden light, empty space on the left, no text or letters")
    thumb_bg = generate_ai_image(art_prompt)
    if not thumb_bg:
        thumb_bg = download_thumb_image(outline.get("thumbnail_query") or chapters[0]["image_queries"][0])
    if not thumb_bg:
        pool = [p for ph in photos_by_chapter for p in ph]
        thumb_bg = pool[0] if pool else "Logo.jpg"
    thumb = make_thumbnail(thumb_bg, outline.get("thumbnail_text") or outline.get("title"))

    bgm = get_bgm()
    video = render_video(audio_paths, durations, photos_by_chapter, headings, bgm)

    chapter_starts = [sum(durations[:i]) for i in range(len(durations))]
    description = build_description(outline.get("description", ""), headings, chapter_starts)
    upload_youtube(video, thumb, outline.get("title") or "भगवान की सुंदर कथा",
                   description, outline.get("tags") or ["bhakti", "katha"])
