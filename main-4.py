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
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter, ImageOps
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
SECONDS_PER_IMAGE = 9                  # har photo kitni der dikhe (kam = tez video)
USE_VISION_FILTER = True               # Gemini har photo dekhkar bhagwan/mandir wali hi rakhe
MAKE_SHORTS = False                    # Short nahi chahiye (True karoge to Short bhi banega)
USE_AI_IMAGES = True                   # Cloudflare AI (free) se bhagwan ke chitra banao
AI_SECONDS_PER_IMAGE = 22              # ek AI chitra ~18 second ke liye (dobara alag zoom ke saath dikhta hai)
AI_EXTRA = 1.25                        # kuch kharab nikle to bachne ke liye 30% zyada banao
AI_IMAGE_STEPS = 4                     # zyada = behtar chitra par zyada free limit lagti hai (max 8)
AI_STYLE_DEFAULT = ("traditional Indian devotional digital painting, rich saffron, gold and blue colours, "
                    "soft glowing divine light, highly detailed, respectful, no text, no letters, no watermark")
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
CF_ACCOUNT_ID = (os.environ.get("CF_ACCOUNT_ID") or "").strip()
CF_API_TOKEN = (os.environ.get("CF_API_TOKEN") or "").strip()
TOPIC = (os.environ.get("TOPIC") or "").strip()   # n8n se aa sakta hai (tyohar/grahan)
SLOT = int(os.environ.get("SLOT") or 0)           # aaj ka kaun sa video (0 = pehla, 1 = doosra)
VIDEOS_PER_DAY = max(1, int(os.environ.get("VIDEOS_PER_DAY") or 1))
VINTAGE_SLOTS = (1,)                   # in slot ke video 'purani pandulipi' shaili me (sepia + sajawati frame + gyan)
VINTAGE = SLOT in VINTAGE_SLOTS and VIDEOS_PER_DAY > 1
VOICE_PITCH = "-6Hz" if VINTAGE else "+0Hz"      # gyan wale video me thodi gehri awaaz
MUSIC_LEVEL = 0.30                     # music ki awaaz (awaaz aate hi apne-aap dheemi ho jati hai)
VINTAGE_STYLE = ("antique illuminated manuscript painting, ancient Indian mythological illustration, "
                 "sepia, gold and deep brown tones, detailed ink and watercolor on aged parchment, dramatic mood, "
                 "respectful depiction of Hindu gods, no text, no letters")

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


GYAN_FORMAT = (" [format: GYAN explainer, not only a story. Open with a mystery or a question; explain the deeper "
               "meaning; give 3-5 practical life lessons and simple steps people can try; calm, serious, wise tone. "
               "Title: curiosity hook, use a number when natural (for example '5 sandesh'). Stay truthful: no miracle, "
               "health, wealth or exam-result promises, and no fake statistics like '99% people do not know']")
GYAN_TOPICS = [
    "Mahadev ke 5 jeevan sandesh: Shiv ji ka vairagya aur santulan",
    "Brahma muhurta ka mahatva: subah jaldi uthne ki sadhna aur uski saral vidhi",
    "Shiv aur Shakti: Ardhnarishwar ka gehra arth",
    "Mahamrityunjay mantra ka arth aur jaap ki sahi vidhi",
    "Om Namah Shivaya (panchakshar mantra) ka arth aur rahasya",
    "Kailash parvat ka rahasya aur Shiv ji ka nivas",
    "Ravan ki Shiv bhakti aur ahankar se patan",
    "Adiyogi Shiv: dhyan kya hai aur Shiv ko pehla yogi kyon kehte hain",
    "Ganga ko jataon me dharan karne ka gehra arth",
    "Neelkanth: kadve anubhav ko pachana Shiv se seekhein",
    "Trishul, damru aur naag: Shiv ke prateekon ka arth",
    "Bhagavad Gita ke 5 niyam jo jeevan badal sakte hain",
    "Ramcharitmanas ki 5 seekh jo aaj bhi kaam aati hain",
    "Hanuman ji se seekhne wali 7 baatein: seva, vinay aur shakti",
    "Shri Krishna ki neeti: sahi samay par sahi nirnay kaise len",
    "Sant Kabir ke dohe: jeevan ka sach",
    "Karma ka siddhant: jaisa karenge waisa paayenge ka asli arth",
    "Moksha kya hai? Vedant ka saral gyan",
    "Man ki shanti ke 5 prachin upay: dhyan, jaap, seva, satsang, sanyam",
    "Pitra paksha ka arth aur shraddha ka bhav",
    "Shani dev aur karma ka nyay",
    "Mantra jaap ki sahi vidhi: mala, samay aur niyam",
    "Vrat ka asli arth: upvas, sanyam aur shraddha",
    "Guru ka mahatva: Ved Vyas se Ramakrishna tak",
    "Atma aur sharir: Gita ka gyan",
    "Maa Durga ke nau roop aur nau gun jo jeevan me apnane chahiye",
    "Lakshmi ji kahan nivas karti hain: sanskar aur parishram ka sandesh",
    "Shiv Parvati ka vivah: ek aadarsh sambandh ki seekh",
    "Mahashivratri ki sadhna: jaagran aur upvas ka arth",
    "Satsang aur sangati ka prabhav: Ramayan ke udaharan",
    "Kaal aur samay ka Bhartiya darshan: Mahakal ka arth",
    "Sanskar kya hain: 16 sanskar aur unka mahatva",
    "Ahankar ka tyag: Ganesh ji aur Kartikeya ki parikrama ki seekh",
    "Seva ka mahatva: Shabri, Kevat aur Hanuman ke udaharan",
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


GEMINI_MIN_GAP = 6.5                   # do Gemini call ke beech kam se kam itne second
_gemini_last = [0.0]


def ask_gemini(prompt, as_json=False, check=None, max_rounds=8, images=None):
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
                parts_in = [{"text": prompt}]
                for k, b64 in enumerate(images or []):          # (photo dekhne wale sawal ke liye)
                    parts_in.append({"text": f"Image {k}:"})
                    parts_in.append({"inlineData": {"mimeType": "image/jpeg", "data": b64}})
                payload = {"contents": [{"role": "user", "parts": parts_in}]}
                if as_json:
                    payload["generationConfig"] = {"responseMimeType": "application/json"}
                gap = GEMINI_MIN_GAP - (time.time() - _gemini_last[0])
                if gap > 0:
                    time.sleep(gap)
                _gemini_last[0] = time.time()
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
        if rnd >= max_rounds:
            break
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
    if special and SLOT == 0:
        return special + " (this video is published one day before the festival; say it is coming tomorrow)"
    if special and SLOT != 0:
        return (special + " - this video must NOT retell the main story; focus on the puja vidhi, traditions and "
                "the deeper meaning of the festival; say it is coming tomorrow")
    trending = trending_topic() if SLOT == 0 else None
    if trending:
        return trending
    if VINTAGE:                                      # shaam ka video: gyan / rahasya / sadhna
        pool = GYAN_TOPICS
        if today.weekday() == 0:                     # Somvar: Shiv gyan
            pool = [t for t in GYAN_TOPICS if "Shiv" in t or "Mahadev" in t] or GYAN_TOPICS
        return pool[today.toordinal() % len(pool)] + GYAN_FORMAT
    ordinal = today.toordinal() * VIDEOS_PER_DAY + SLOT
    topic = TOPICS[ordinal % len(TOPICS)]
    if (ordinal // len(TOPICS)) % 2 == 1:
        topic += " (present it from a fresh angle: lesser-known scenes, the lesson, and the meaning)"
    return topic


def generate_outline(n_chapters, topic):
    ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    today = datetime.datetime.now(ist).strftime("%d %B %Y")
    if VINTAGE:
        last_rule = ('The LAST chapter must have the heading "सार और अभ्यास" and its summary must say that it gives '
                     'the key lessons and 2-3 simple practices viewers can try.')
    else:
        last_rule = ('The LAST chapter must have the heading "कथा का फल" and its summary must say that it explains\n'
                     'what the tradition believes about the merit of listening to this katha with devotion.')
    prompt = f"""
You plan videos for a Hindi devotional (bhakti) YouTube channel called "{CHANNEL_NAME}".
Today's date (IST): {today}.
Topic of today's video: {topic}

Plan one long video with exactly {n_chapters} chapters. Keep facts accurate as per
Hindu scriptures and traditions. No superstition, no fear-based claims, no
medical or astrology predictions, and no false promises of money/health/miracles.

Return ONLY valid JSON (no markdown) with these keys:
- "title": a Hindi hook (emotional, curiosity-driven, truthful, max 55 characters, no false promises) followed by " | " and 2-3 English search words naming the deity and story type (example: "यमुना ने क्यों छुए बाल कृष्ण के चरण? | Krishna Leela"). Total max 85 characters.
- "description": Hindi, 100-160 words, hashtags at the end (include #HindiKatha #Bhakti)
- "tags": list of 10-15 strings (Hindi + English)
- "thumbnail_text": ONLY 1 to 3 Hindi words (shorter is better), huge, emotional and curiosity-making, like a film-poster word. It must NOT repeat the title. Examples: "कान्हा का रहस्य", "अनसुनी कथा", "सच्ची भक्ति"
- "thumbnail_badge": 2 Hindi words for a small badge, e.g. "अनसुनी कथा", "सच्ची कथा"
- "thumbnail_query": one short English stock-photo search query for a beautiful
   divine thumbnail background (e.g. "krishna idol golden", "hanuman statue sunset")
- "deity_keywords": list of 4 short English photo-search terms for the MAIN deities /
   characters / holy place of this story (e.g. "lord hanuman", "hanuman statue",
   "shri ram sita", "ram mandir ayodhya"). They must name the deity or holy place.
- "thumbnail_art_prompt": an English prompt (2-3 sentences) for a DRAMATIC cinematic movie-poster scene of the single most exciting or emotional moment of this story: one or two divine characters, large and clearly visible in the middle of the frame (faces in the middle third), intense expressive faces, dynamic pose, vivid saturated colours, golden rim light and glow, epic sky, ultra detailed, absolutely no text or letters in the image
- "art_style": ONE English sentence describing one consistent painting style for every image
   of this video (e.g. "traditional Indian devotional painting, rich saffron and gold, soft divine glow")
- "chapters": list of exactly {n_chapters} objects, each with:
    "heading": Hindi, max 5 words,
    "summary": 1-2 sentences in English about what happens in this chapter,
    "image_queries": list of 5 short English stock-photo search queries for this
       chapter. EVERY query must name the deity/character/temple of the chapter
       (e.g. "lord krishna flute", "shiva temple", "hanuman idol") or a sacred
       item (e.g. "diya aarti", "temple bell"). NEVER generic nature, people or
       random landscapes.
    "image_prompts": list of 6 English prompts (1-2 sentences each) for AI-painted scenes of
       THIS chapter. Clearly name the deity/character, what they are doing, the place and the
       mood (e.g. "Little Krishna playing the flute under a kadamba tree in Vrindavan, golden
       evening light"). Show only gods, saints and sacred places. Make the 6 scenes different.
    "caption_lines": list of 6 very short Hindi on-screen caption lines (max 7 words each), in the order
       they are spoken in THIS chapter; each is a striking key phrase from the narration.

{last_rule}
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
    voice_style = ("calm, serious, wise explanatory voice with real examples" if VINTAGE
                   else "emotional devotional storytelling voice")
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
        elif VINTAGE:
            extra += (" This last chapter is 'सार और अभ्यास': summarise the key lessons simply and give 2-3 "
                      "practical steps viewers can try (only simple habits, no promises of results). Then end with "
                      "a short blessing, and politely request viewers to like, share and subscribe and to come "
                      "back tomorrow for another video.")
        else:
            extra += (" This last chapter is 'कथा का फल': gently explain what the tradition and "
                      "scriptures are believed to say about the merit of listening to this katha with "
                      "devotion - inner peace, devotion, good values and blessings. Use faith-based "
                      "wording such as 'मान्यता है कि' and 'शास्त्रों में कहा गया है'. NEVER promise "
                      "wealth, health cures, miracles, exam or job success, and never use fear. Then end "
                      "with a short prayer and blessing, and politely request viewers to like, share and "
                      "subscribe and to come back tomorrow for another katha.")
        prompt = f"""
You are writing chapter {i + 1} of {n} of one long Hindi devotional narration for a YouTube video.
Video topic: {topic}
Video title: {outline.get('title')}

Full outline:
{outline_text}

The previous chapter ended with: "{tail}"

Write ONLY chapter {i + 1}: "{ch['heading']}" ({ch.get('summary', '')}).
Length: about {WORDS_PER_CHAPTER} words (not less than {WORDS_PER_CHAPTER - 40}).
Language: Hindi in Devanagari script, {voice_style}.
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
    await edge_tts.Communicate(text, VOICE, rate=VOICE_RATE, pitch=VOICE_PITCH).save(path)


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
        "key": PIXABAY_KEY, "q": q, "image_type": "photo", "category": "religion",
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


def fetch_image(hit, headers=None):
    url = hit.get("largeImageURL")
    if not url or url in SEEN:
        return None
    try:
        data = requests.get(url, headers=headers or HEADERS, timeout=60).content
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


COMMONS_HEADERS = {"User-Agent": "BhaktiVideoBot/1.0 (https://github.com/bhgatisong474-cmyk/Bhagti-video-)"}


def commons_images(query, need):
    """Wikimedia Commons (free, bina key): sirf Public Domain / CC0 photo aur chitra
    (jaise Raja Ravi Varma ki painting). Copyright ka koi jhanjhat nahi."""
    got = []
    try:
        r = requests.get(
            "https://commons.wikimedia.org/w/api.php", headers=COMMONS_HEADERS, timeout=30,
            params={"action": "query", "format": "json", "generator": "search",
                    "gsrsearch": query, "gsrnamespace": 6, "gsrlimit": 25,
                    "prop": "imageinfo", "iiprop": "url|extmetadata|size|mime",
                    "iiurlwidth": 1600})
        pages = list((r.json().get("query") or {}).get("pages", {}).values())
        for p in pages:
            if len(got) >= need:
                break
            info = (p.get("imageinfo") or [{}])[0]
            lic = ((info.get("extmetadata") or {}).get("LicenseShortName") or {}).get("value", "").lower()
            if not lic.startswith(("public domain", "pd", "cc0")):
                continue
            if info.get("mime") != "image/jpeg" or info.get("width", 0) < 1000 or info.get("height", 0) < 600:
                continue
            url = info.get("thumburl") or info.get("url")
            if not url or url in SEEN:
                continue
            path = fetch_image({"largeImageURL": url}, headers=COMMONS_HEADERS)
            if path:
                got.append(path)
    except Exception as e:
        print("Commons error:", query, str(e)[:100])
    return got


def _small_b64(path, size=384):
    import base64
    import io
    img = Image.open(path).convert("RGB")
    img.thumbnail((size, size))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=70)
    return base64.b64encode(buf.getvalue()).decode()


def filter_relevant(paths, topic):
    """Gemini har photo dekhkar batata hai kaun si bhagwan/mandir/puja wali hai. Baaki hata do."""
    if not USE_VISION_FILTER or len(paths) == 0:
        return paths
    kept = []
    for i in range(0, len(paths), 10):
        batch = paths[i:i + 10]
        try:
            prompt = (
                f"These are candidate background photos for a Hindu devotional video about: {topic}.\n"
                "Keep an image ONLY if it clearly shows a Hindu deity (idol, statue or painting), a "
                "temple, an aarti/diya/puja scene, or a sacred Hindu symbol. Reject random scenery, "
                "animals, ordinary people or portraits, food, objects, logos, and images with a lot "
                "of text or watermarks. Also reject images with distorted faces or bodies, extra "
                "limbs or fingers, or garbled letters.\n"
                f'Return ONLY JSON like {{"keep": [0, 2, 5]}} using image numbers 0 to {len(batch) - 1}.')

            def check(d):
                if not isinstance(d, dict) or not isinstance(d.get("keep"), list):
                    raise ValueError("galat format")

            data = ask_gemini(prompt, as_json=True, max_rounds=1, check=check,
                              images=[_small_b64(p) for p in batch])
            idx = [k for k in data["keep"] if isinstance(k, int) and 0 <= k < len(batch)]
            kept += [batch[k] for k in idx]
        except Exception as e:
            print("Photo check skip (sab rakhi):", str(e)[:80])
            kept += batch
    if len(kept) < max(3, len(paths) // 5):
        print("Filter bahut sakht nikla, original photos rakhi")
        return paths
    print(f"Bhagwan wali photos: {len(kept)}/{len(paths)}")
    return kept


def download_chapter_images(queries, need, topic="", deity_keywords=None):
    deity_keywords = deity_keywords or []
    queries = list(dict.fromkeys(list(deity_keywords[:3]) + list(queries)))
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
    # teesra round: ab bhi kami ho to bhagwan wale words ke agle page se
    for page in (2, 3):
        if len(got) >= need:
            break
        for q in (list(deity_keywords[:3]) or queries[:3]):
            if len(got) >= need:
                break
            for h in pixabay_hits(q, page=page):
                if len(got) >= need:
                    break
                path = fetch_image(h)
                if path:
                    got.append(path)
            time.sleep(0.4)
    # chautha: Wikimedia Commons (free, public domain) se bhagwan ke chitra
    if len(got) < need * 0.6:
        for q in (list(deity_keywords[:2]) or queries[:2]):
            got += commons_images(q, need - len(got))
            if len(got) >= need:
                break
    return filter_relevant(got, topic)


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
HEAVY_DEVA = [
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Black.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-ExtraBold.ttf",
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


def font_for(text, size, heavy=False):
    is_hindi = any("\u0900" <= c <= "\u097F" for c in text)
    key = (is_hindi, size, heavy)
    if key in _font_cache:
        return _font_cache[key]
    candidates = (HEAVY_DEVA + DEVA_FONTS if heavy else DEVA_FONTS) if is_hindi else LATIN_FONTS
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


def download_thumb_candidates(queries, n=8):
    """Thumbnail ke liye kai achhi photos laao (bhagwan ke chehre/murti wali)."""
    got = []
    for q in dict.fromkeys([q for q in queries if q]):
        if len(got) >= n:
            break
        hits = pixabay_hits(q, page=random.randint(1, 4)) or pixabay_hits(q)
        random.shuffle(hits)                       # roz wahi pehli photo na aaye
        taken = 0
        for h in hits:
            if taken >= 2 or len(got) >= n:
                break
            path = fetch_image(h)
            if path:
                got.append(path)
                taken += 1
        time.sleep(0.4)
    return got


CF_MODEL = "@cf/black-forest-labs/flux-1-schnell"
CF_FALLBACK_MODEL = "@cf/bytedance/stable-diffusion-xl-lightning"
CF_STATE = {"off": False, "fails": 0}


def cf_enabled():
    return USE_AI_IMAGES and bool(CF_ACCOUNT_ID) and bool(CF_API_TOKEN) and not CF_STATE["off"]


def cf_image(prompt, seed=None, steps=None):
    """Cloudflare Workers AI (FLUX.1 schnell, free) se ek chitra. Na bane to None."""
    if not cf_enabled():
        return None
    import base64
    import io
    base = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/"
    flux_payload = {"prompt": prompt[:1900], "steps": int(steps or AI_IMAGE_STEPS)}
    sdxl_payload = {"prompt": prompt[:1900], "num_steps": 4, "width": 1024, "height": 576}
    if seed is not None:
        sdxl_payload["seed"] = int(seed)          # FLUX schnell 'seed' nahi leta (400 deta hai)
    for attempt in range(1, 4):
        use_sdxl = attempt == 3 or CF_STATE.get("flux_bad", False)   # FLUX fail/400 to doosra model
        url = base + (CF_FALLBACK_MODEL if use_sdxl else CF_MODEL)
        payload = sdxl_payload if use_sdxl else flux_payload
        try:
            r = requests.post(url, json=payload, timeout=120,
                              headers={"Authorization": f"Bearer {CF_API_TOKEN}",
                                       "Content-Type": "application/json"})
            low = r.text[:400].lower() if "json" in r.headers.get("content-type", "").lower() else ""
            if r.status_code in (401, 403):
                print("Cloudflare token galat ya ijazat nahi:", r.text[:150])
                CF_STATE["off"] = True
                return None
            if r.status_code == 429 or "daily free allocation" in low or "neurons" in low:
                print("Cloudflare ki aaj ki free seema khatam:", r.text[:150])
                CF_STATE["off"] = True
                return None
            if r.status_code == 400:
                if "/seed" in r.text:
                    sdxl_payload.pop("seed", None)
                if not use_sdxl:
                    CF_STATE["flux_bad"] = True        # bad input: aage seedha doosra model
                raise RuntimeError(f"HTTP 400: {r.text[:150]}")
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:150]}")
            if r.headers.get("content-type", "").startswith("image/"):
                data = r.content
            else:
                b64 = (r.json().get("result") or {}).get("image")
                if not b64:
                    raise RuntimeError("jawab me chitra nahi")
                data = base64.b64decode(b64)
            path = f"ai_{_img_counter[0]}.jpg"
            Image.open(io.BytesIO(data)).convert("RGB").save(path, quality=92)
            _img_counter[0] += 1
            CF_STATE["fails"] = 0
            return path
        except Exception as e:
            print(f"AI chitra attempt {attempt} fail:", str(e)[:150])
            time.sleep(3 * attempt)
    CF_STATE["fails"] += 1
    if CF_STATE["fails"] >= 6:
        print("Cloudflare baar-baar fail, ab Pixabay chalega")
        CF_STATE["off"] = True
    return None


def make_ai_images(prompts, count, style):
    got = []
    if not prompts or count <= 0:
        return got
    for i in range(count):
        path = cf_image(f"{prompts[i % len(prompts)]}. {style}", seed=random.randrange(1, 2 ** 31))
        if path:
            got.append(path)
        elif not cf_enabled():
            break
        time.sleep(0.3)
    return got


def pick_best_thumbnail(paths, topic):
    """Gemini batata hai kaun si photo thumbnail ke liye sabse achhi hai."""
    if not paths:
        return None
    if not USE_VISION_FILTER or len(paths) == 1:
        return paths[0]
    try:
        prompt = (
            "Choose the single best image to use as a YouTube thumbnail for a Hindu "
            f"devotional video about: {topic}.\nBest = the most striking, dramatic and emotional image "
            "with vivid colours and clearly visible divine characters or a deity face, good faces and hands "
            "(reject deformed faces, extra fingers or limbs), no text and no watermark.\n"
            f'Return ONLY JSON like {{"best": 0}} with an image number from 0 to {len(paths) - 1}.')

        def check(d):
            if not isinstance(d, dict) or not isinstance(d.get("best"), int):
                raise ValueError("galat format")
            if not 0 <= d["best"] < len(paths):
                raise ValueError("number galat")

        data = ask_gemini(prompt, as_json=True, max_rounds=1, check=check,
                          images=[_small_b64(p, 512) for p in paths])
        print("Thumbnail photo chuni:", data["best"])
        return paths[data["best"]]
    except Exception as e:
        print("Thumbnail photo-chunav skip:", str(e)[:80])
        return paths[0]


def heavy_text(d, pos, line, font, color, stroke):
    x, y = pos
    d.text((x + 7, y + 9), line, font=font, fill=(0, 0, 0, 210),
           stroke_width=stroke + 6, stroke_fill=(0, 0, 0, 210))                  # parchhai
    d.text((x, y), line, font=font, fill=(110, 0, 0, 255),
           stroke_width=stroke + 7, stroke_fill=(110, 0, 0, 255))                # gehra laal kinara
    d.text((x, y), line, font=font, fill=(10, 4, 0, 255),
           stroke_width=stroke, stroke_fill=(10, 4, 0, 255))                     # kaala kinara
    d.text((x, y), line, font=font, fill=color,
           stroke_width=max(2, int(font.size * 0.03)), stroke_fill=color)        # akshar mote


THUMB_STYLE = ("cinematic epic digital art, ultra detailed, dramatic lighting, vivid saturated colours, "
               "golden rim light and glow, sharp focus, expressive faces, respectful depiction of Hindu gods, "
               "no text, no letters, no watermark")
THUMB_STEPS = 8                        # thumbnail ke liye zyada steps = behtar chitra (sirf 4 chitra)
THUMB_PALETTES = [
    [(255, 232, 0, 255), (255, 255, 255, 255)],
    [(255, 255, 255, 255), (255, 150, 20, 255)],
    [(255, 215, 0, 255), (255, 90, 90, 255)],
    [(120, 235, 255, 255), (255, 232, 0, 255)],
]


def make_poster_thumbnail(bg_path, text, badge="भक्ति कथा", out_path="thumb.jpg"):
    """Poori tasveer + chhota bada likhawat. Likhawat ki jagah aur rang har video me badalte hain."""
    rnd = random.Random(text)                      # ek video ka hamesha ek, alag video ka alag
    variant = rnd.choice(["top", "bottom", "side"])
    pal = rnd.choice(THUMB_PALETTES)
    base = cover_crop(Image.open(bg_path))
    base = ImageEnhance.Color(base).enhance(1.35)
    base = ImageEnhance.Contrast(base).enhance(1.15)
    base = ImageEnhance.Brightness(base).enhance(1.05)
    base = base.filter(ImageFilter.UnsharpMask(radius=2, percent=130, threshold=3))
    img = base.convert("RGBA")

    grad = np.zeros((H, W, 4), np.uint8)
    grad[..., 0], grad[..., 1], grad[..., 2] = 40, 5, 0
    ys, xs = np.arange(H)[:, None], np.arange(W)[None, :]
    if variant == "top":
        a = np.clip(1 - ys / 380.0, 0, 1) ** 1.1 * 215 + 0 * xs
    elif variant == "bottom":
        a = np.clip(1 - (H - ys) / 340.0, 0, 1) ** 1.1 * 225 + 0 * xs
    else:
        a = np.clip(1 - xs / (W * 0.64), 0, 1) ** 1.2 * 215 + 0 * ys
    grad[..., 3] = a.astype(np.uint8)
    img = Image.alpha_composite(img, Image.fromarray(grad))
    img = Image.alpha_composite(img, make_vignette(85))
    d = ImageDraw.Draw(img)

    if variant == "side":
        max_w, max_h, area_top = int(W * 0.56), 450, 135
    elif variant == "top":
        max_w, max_h, area_top = W - 130, 290, 150
    else:
        max_w, max_h, area_top = W - 130, 290, H - 335
    size, lines = 200, [text]
    while size > 56:
        font = font_for(text, size, heavy=True)
        lines = wrap_text(d, text, font, max_w)
        widest = max(d.textlength(l, font=font) for l in lines)
        if len(lines) <= 3 and widest <= max_w and len(lines) * size * 1.2 <= max_h:
            break
        size -= 6
    font = font_for(text, size, heavy=True)
    line_h = int(size * 1.2)
    y = area_top + (max_h - len(lines) * line_h) // 2
    stroke = max(6, size // 12)
    for i, line in enumerate(lines):
        w_line = d.textlength(line, font=font)
        x = 50 if variant == "side" else int((W - w_line) / 2)
        heavy_text(d, (x, y), line, font, pal[i % 2], stroke)
        y += line_h

    draw_star(d, int(W * rnd.uniform(0.45, 0.6)), 62, 30, (255, 255, 255, 235))
    draw_star(d, 70, int(H * rnd.uniform(0.55, 0.7)), 18, (255, 235, 120, 235))

    tf = font_for(badge, 42, heavy=True)
    tw = d.textlength(badge, font=tf)
    d.rounded_rectangle([45, 34, 45 + int(tw) + 56, 108], radius=18, fill=(230, 90, 0, 255),
                        outline=(255, 215, 0, 255), width=4)
    d.text((72, 40), badge, font=tf, fill=(255, 255, 255, 255))

    if variant != "bottom":
        btn = "पूरी कथा सुनें"
        bf = font_for(btn, 40, heavy=True)
        bw = d.textlength(btn, font=bf)
        d.rounded_rectangle([45, H - 102, 45 + int(bw) + 100, H - 36], radius=16, fill=(215, 15, 15, 255),
                            outline=(255, 255, 255, 255), width=3)
        d.polygon([(68, H - 86), (68, H - 54), (94, H - 70)], fill=(255, 255, 255, 255))
        d.text((108, H - 96), btn, font=bf, fill=(255, 255, 255, 255))

    if os.path.exists("Logo.jpg"):
        logo, mask = circle_logo(112)
        lx, ly = W - 85, 85
        d.ellipse([lx - 64, ly - 64, lx + 64, ly + 64], fill=(255, 193, 7, 255))
        img.paste(logo, (lx - 56, ly - 56), mask)

    img.convert("RGB").save(out_path, quality=92)
    print("Thumbnail ready (poster:", variant, ")")
    return out_path


def make_thumbnail(bg_path, text, badge="भक्ति कथा", layout="full", out_path="thumb.jpg"):
    if layout == "poster":
        return make_poster_thumbnail(bg_path, text, badge, out_path)
    """layout 'full': poori tasveer (AI chitra). layout 'split': baayein laal panel + daayein photo."""
    photo = Image.open(bg_path)
    if layout == "split":
        panel = np.zeros((H, W, 3), np.uint8)
        grad_y = np.linspace(0, 1, H)[:, None]
        panel[..., 0] = (190 - 70 * grad_y).astype(np.uint8)
        panel[..., 1] = (35 - 25 * grad_y).astype(np.uint8)
        panel[..., 2] = (0 + 25 * grad_y).astype(np.uint8)
        base = Image.fromarray(panel)
        pw = int(W * 0.66)
        base.paste(cover_crop(photo, pw, H), (W - pw, 0))
    else:
        base = cover_crop(photo)
    base = ImageEnhance.Color(base).enhance(1.5)
    base = ImageEnhance.Contrast(base).enhance(1.2)
    base = ImageEnhance.Brightness(base).enhance(1.1)
    base = base.filter(ImageFilter.UnsharpMask(radius=2, percent=130, threshold=3))
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
                   fill=(255, 220, 110, 34))
    img = Image.alpha_composite(img, rays)

    # baayein taraf laal gradient: likhawat chamke, photo dheere dheere ubhre
    grad = np.zeros((H, W, 4), np.uint8)
    grad[..., 0], grad[..., 1], grad[..., 2] = 150, 22, 0
    xs = np.arange(W)
    if layout == "split":
        a = np.clip((W * 0.62 - xs) / (W * 0.30), 0, 1) * 235          # 0.32W tak poora, 0.62W tak ghulta
    else:
        a = np.clip(1 - xs / (W * 0.72), 0, 1) ** 1.2 * 210
    grad[..., 3] = a[None, :].astype(np.uint8)
    img = Image.alpha_composite(img, Image.fromarray(grad))
    img = Image.alpha_composite(img, make_vignette(90))
    d = ImageDraw.Draw(img)

    # likhawat: badi, mote akshar, 3 line tak
    max_w = int(W * (0.52 if layout == "split" else 0.60))
    size = 160
    lines = [text]
    while size > 58:
        font = font_for(text, size, heavy=True)
        lines = wrap_text(d, text, font, max_w)
        widest = max(d.textlength(l, font=font) for l in lines)
        if len(lines) <= 3 and widest <= max_w and len(lines) * size * 1.22 <= 470:
            break
        size -= 6
    font = font_for(text, size, heavy=True)
    line_h = int(size * 1.22)
    y = 125 + (470 - len(lines) * line_h) // 2
    colors = [(255, 255, 255, 255), (255, 232, 0, 255), (255, 150, 20, 255)]
    stroke = max(6, size // 12)
    for i, line in enumerate(lines):
        heavy_text(d, (50, y), line, font, colors[i % 3], stroke)
        y += line_h

    draw_star(d, 600, 64, 30, (255, 255, 255, 235))
    draw_star(d, 70, 650, 18, (255, 235, 120, 235))
    draw_star(d, 700, 560, 16, (255, 255, 255, 220))

    # upar-baayein kesariya badge
    tf = font_for(badge, 42, heavy=True)
    tw = d.textlength(badge, font=tf)
    d.rounded_rectangle([45, 34, 45 + int(tw) + 56, 108], radius=18, fill=(230, 90, 0, 255),
                        outline=(255, 215, 0, 255), width=4)
    d.text((72, 40), badge, font=tf, fill=(255, 255, 255, 255))

    # niche-baayein laal button
    btn = "पूरी कथा सुनें"
    bf = font_for(btn, 40, heavy=True)
    bw = d.textlength(btn, font=bf)
    d.rounded_rectangle([45, H - 102, 45 + int(bw) + 100, H - 36], radius=16, fill=(215, 15, 15, 255),
                        outline=(255, 255, 255, 255), width=3)
    d.polygon([(68, H - 86), (68, H - 54), (94, H - 70)], fill=(255, 255, 255, 255))
    d.text((108, H - 96), btn, font=bf, fill=(255, 255, 255, 255))

    # logo UPAR-DAAYEIN (neeche-daayein me YouTube ka time likha aata hai)
    if os.path.exists("Logo.jpg"):
        logo, mask = circle_logo(112)
        lx, ly = W - 85, 85
        d.ellipse([lx - 64, ly - 64, lx + 64, ly + 64], fill=(255, 193, 7, 255))
        img.paste(logo, (lx - 56, ly - 56), mask)

    img.convert("RGB").save(out_path, quality=92)
    print("Thumbnail ready (", layout, ")")
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
        big = cover_crop(Image.open(path), int(W * ZMAX), int(H * ZMAX))
        _big_cache[path] = vintage_grade(big) if VINTAGE else big
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


def make_particles(n=55):
    """Halki sunehri dhool/chingari jo upar udti hai - tasveer jeevant lagti hai."""
    rnd = random.Random(11)
    sprites = []
    for s in (8, 14, 24):
        yy, xx = np.mgrid[0:s, 0:s]
        r = np.sqrt((xx - s / 2 + 0.5) ** 2 + (yy - s / 2 + 0.5) ** 2) / (s / 2)
        alpha = (np.clip(1 - r, 0, 1) ** 1.5 * 170).astype(np.uint8)
        sprites.append((Image.new("RGB", (s, s), (255, 214, 120)), Image.fromarray(alpha)))
    parts = [{"x0": rnd.uniform(0, W), "y0": rnd.uniform(0, H + 40), "speed": rnd.uniform(12, 38),
              "amp": rnd.uniform(6, 30), "freq": rnd.uniform(0.3, 1.1), "ph": rnd.uniform(0, 6.28),
              "k": rnd.choice([0, 0, 1, 1, 2])} for _ in range(n)]
    return parts, sprites


def draw_particles(img, t, parts, sprites):
    for p in parts:
        y = (p["y0"] - p["speed"] * t) % (H + 40) - 20
        x = p["x0"] + p["amp"] * math.sin(p["freq"] * t + p["ph"])
        rgb, mask = sprites[p["k"]]
        img.paste(rgb, (int(x), int(y)), mask)


def vintage_grade(img):
    """Purani pandulipi jaisa sepia rang."""
    img = ImageEnhance.Color(img).enhance(0.6)
    sepia = ImageOps.colorize(ImageOps.grayscale(img), black=(38, 22, 8), white=(255, 238, 205))
    return Image.blend(img, sepia, 0.55)


def make_vintage_border():
    """Sajawati bhuri-sunehri frame, kono par gol phool."""
    b = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(b)
    d.rectangle([0, 0, W - 1, H - 1], outline=(70, 40, 12, 255), width=14)
    d.rectangle([14, 14, W - 15, H - 15], outline=(201, 150, 60, 255), width=3)
    d.rectangle([22, 22, W - 23, H - 23], outline=(110, 70, 25, 255), width=2)
    for cx, cy in [(14, 14), (W - 14, 14), (14, H - 14), (W - 14, H - 14)]:
        d.ellipse([cx - 16, cy - 16, cx + 16, cy + 16], fill=(201, 150, 60, 255), outline=(70, 40, 12, 255), width=3)
        d.ellipse([cx - 6, cy - 6, cx + 6, cy + 6], fill=(70, 40, 12, 255))
    return b


CAP_W, CAP_H, CAP_X, CAP_Y = 1120, 118, 80, 30


def make_caption_layer(text):
    """Upar ka parchment patta: chhoti, khaas line (gyan wale video jaisi)."""
    layer = Image.new("RGBA", (CAP_W, CAP_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle([0, 0, CAP_W - 1, CAP_H - 1], radius=22, fill=(232, 210, 160, 238),
                        outline=(110, 70, 20, 255), width=5)
    d.rounded_rectangle([10, 10, CAP_W - 11, CAP_H - 11], radius=16, outline=(150, 100, 40, 255), width=2)
    size = 60
    while size > 30:
        font = font_for(text, size, heavy=True)
        if d.textlength(text, font=font) <= CAP_W - 90:
            break
        size -= 4
    font = font_for(text, size, heavy=True)
    tw = d.textlength(text, font=font)
    d.text(((CAP_W - tw) / 2, (CAP_H - size * 1.2) / 2 - 2), text, font=font, fill=(60, 30, 5, 255))
    return layer.convert("RGB"), layer.split()[3]


def schedule_captions(chapter_starts, durations, captions):
    """Har adhyay ki lines ko adhyay ke samay me barabar baant do (shuru ke 7 second heading ke liye chhodkar)."""
    out = []
    for s, d, lines in zip(chapter_starts, durations, captions or []):
        lines = [str(x).strip() for x in (lines or []) if str(x).strip()]
        if len(lines) < 2 or d < 20:
            continue
        start, end = s + 7.0, s + d - 1.5
        slot = (end - start) / len(lines)
        if slot < 2.0:
            continue
        for i, line in enumerate(lines):
            rgb, mask = make_caption_layer(line)
            out.append((start + i * slot, start + (i + 1) * slot - 0.3, rgb, mask))
    return out


def make_video_clip(segs, total, chapter_starts, headings, captions=None):
    ov_rgb, ov_mask = make_overlay()
    if VINTAGE:
        merged = Image.alpha_composite(Image.merge("RGBA", (*ov_rgb.split(), ov_mask)), make_vintage_border())
        ov_rgb, ov_mask = merged.convert("RGB"), merged.split()[3]
    durs = [(chapter_starts[i + 1] if i + 1 < len(chapter_starts) else total) - s
            for i, s in enumerate(chapter_starts)]
    caps = schedule_captions(chapter_starts, durs, captions) if captions else []
    parts, sprites = make_particles()
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
        draw_particles(img, t, parts, sprites)
        img.paste(ov_rgb, (0, 0), ov_mask)
        for (a, b, rgb, mask) in titles:
            if a <= t <= b:
                k = min(1.0, (t - a) / 0.6, (b - t) / 0.6)
                img.paste(rgb, (0, 0), mask.point(lambda v, k=k: int(v * k)))
        for (a, b, rgb, mask) in caps:
            if a <= t <= b:
                k = min(1.0, (t - a) / 0.5, (b - t) / 0.5)
                img.paste(rgb, (CAP_X, CAP_Y), mask.point(lambda v, k=k: int(v * k)))
        fade = min(1.0, t / 1.2, max(total - t, 0.0) / 1.5)
        if fade < 1.0:
            img = Image.blend(black, img, max(fade, 0.0))
        return np.array(img)

    return VideoClip(make_frame, duration=total)


def mix_audio(audio_paths, bgm_path, total, out_path="mix.m4a"):
    """Awaaz + music: awaaz aate hi music apne-aap dheemi, aur poori awaaz ek jaisi (-16 LUFS)."""
    try:
        n = len(audio_paths)
        cmd = ["ffmpeg", "-y", "-loglevel", "error"]
        for p_ in audio_paths:
            cmd += ["-i", p_]
        cmd += ["-stream_loop", "-1", "-i", bgm_path]
        ins = "".join(f"[{i}:a]" for i in range(n))
        fo = max(total - 3.0, 0.0)
        fc = (f"{ins}concat=n={n}:v=0:a=1,aresample=44100,asplit=2[v1][v2];"
              f"[{n}:a]aresample=44100,volume={MUSIC_LEVEL}[b];"
              "[b][v2]sidechaincompress=threshold=0.02:ratio=10:attack=15:release=700:makeup=1[duck];"
              "[v1][duck]amix=inputs=2:duration=first:dropout_transition=0,"
              f"loudnorm=I=-16:TP=-1.5:LRA=11,aresample=44100,afade=t=out:st={fo:.2f}:d=3[a]")
        cmd += ["-filter_complex", fc, "-map", "[a]", "-t", f"{total:.2f}",
                "-c:a", "aac", "-b:a", "192k", out_path]
        subprocess.run(cmd, check=True, timeout=1800)
        if os.path.exists(out_path) and os.path.getsize(out_path) > 10000:
            print("Audio mix ready (music dheemi + awaaz barabar)")
            return out_path
    except Exception as e:
        print("Audio mix skip, purana tareeka:", str(e)[:150])
    return None


def render_video(audio_paths, durations, photos_by_chapter, headings, bgm_path,
                 output_path="final_video.mp4", captions=None):
    total = float(sum(durations))
    pool = [p for ph in photos_by_chapter for p in ph]
    if not pool:
        pool = ["Logo.jpg"]
    chapter_starts = [sum(durations[:i]) for i in range(len(durations))]
    segs = build_segments(durations, photos_by_chapter, pool)
    video = make_video_clip(segs, total, chapter_starts, headings, captions)

    mixed = mix_audio(audio_paths, bgm_path, total) if bgm_path else None
    voice = concatenate_audioclips([AudioFileClip(p) for p in audio_paths])
    if mixed:
        final_audio = AudioFileClip(mixed)
    elif bgm_path:
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
# 7b. YouTube Short (lambe video ke shuru ke ~50 second, khadi screen me)
# ------------------------------------------------------------------
SHORT_SECONDS = 50


def make_short_overlay(text, out_path="short_overlay.png"):
    SW, SH = 1080, 1920
    layer = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    size = 92
    lines = [text]
    while size > 50:
        font = font_for(text, size, heavy=True)
        lines = wrap_text(d, text, font, 900)
        if len(lines) <= 3:
            break
        size -= 6
    font = font_for(text, size, heavy=True)
    line_h = int(size * 1.25)
    box_h = len(lines) * line_h + 60
    d.rounded_rectangle([40, 120, SW - 40, 120 + box_h], radius=30, fill=(0, 0, 0, 150))
    d.rectangle([40, 130, 54, 110 + box_h], fill=(255, 193, 7, 255))
    colors = [(255, 255, 255, 255), (255, 232, 0, 255), (255, 150, 20, 255)]
    y = 150
    for i, line in enumerate(lines):
        d.text((90, y), line, font=font, fill=colors[i % 3],
               stroke_width=max(4, size // 14), stroke_fill=(10, 4, 0, 255))
        y += line_h
    btn = "पूरी कथा देखें"
    bf = font_for(btn, 56, heavy=True)
    bw = d.textlength(btn, font=bf)
    bx0 = (SW - int(bw) - 120) // 2
    d.rounded_rectangle([bx0, 1640, bx0 + int(bw) + 120, 1740], radius=26, fill=(215, 15, 15, 255),
                        outline=(255, 255, 255, 255), width=4)
    d.polygon([(bx0 + 32, 1665), (bx0 + 32, 1715), (bx0 + 72, 1690)], fill=(255, 255, 255, 255))
    d.text((bx0 + 92, 1652), btn, font=bf, fill=(255, 255, 255, 255))
    layer.save(out_path)
    return out_path


def make_short(video_path, hook_text, out_path="short.mp4", seconds=SHORT_SECONDS):
    """Lambe video ke shuru ke 50 second ko khadi (9:16) screen me badal do: peeche dhundhla
    bada video, beech me asli video, upar hook likhawat."""
    overlay = make_short_overlay(hook_text)
    fade_start = max(seconds - 2, 1)
    flt = ("[0:v]split=2[a][b];"
           "[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:5[bg];"
           "[b]scale=1080:-2[fg];"
           "[bg][fg]overlay=(W-w)/2:(H-h)/2[v1];"
           "[v1][1:v]overlay=0:0:shortest=1[v]")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-t", str(seconds), "-i", video_path,
           "-loop", "1", "-i", overlay, "-filter_complex", flt,
           "-map", "[v]", "-map", "0:a", "-t", str(seconds),
           "-af", f"afade=t=out:st={fade_start}:d=2",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-pix_fmt", "yuv420p",
           "-r", "30", "-c:a", "aac", "-b:a", "160k", "-shortest", out_path]
    subprocess.run(cmd, check=True)
    print("Short ready:", out_path)
    return out_path


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

    if thumb_path:
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
    print("Cloudflare AI:", "ON" if cf_enabled() else "OFF - CF_ACCOUNT_ID / CF_API_TOKEN nahi mile (main.yml me env aur GitHub secrets check karo)")

    topic = pick_topic()
    # gyan wala (vintage) video lamba: 7-10 adhyay. katha wala: MIN_CHAPTERS..MAX_CHAPTERS
    lo, hi = (7, 10) if VINTAGE else (MIN_CHAPTERS, MAX_CHAPTERS)
    n_chapters = random.randint(lo, hi)
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

    topic_desc = outline.get("title") or topic
    style = (outline.get("art_style") or "").strip().rstrip(".")
    style = f"{style}. {AI_STYLE_DEFAULT}" if style else AI_STYLE_DEFAULT
    if VINTAGE:
        style = VINTAGE_STYLE

    photos_by_chapter = []
    for ch, d in zip(chapters, durations):
        need = max(1, int(round(d / SECONDS_PER_IMAGE)))          # is adhyay me kitne photo-segment
        photos = []
        if cf_enabled():                                          # pehle AI se bhagwan ke chitra
            n_ai = max(2, int(round(d / AI_SECONDS_PER_IMAGE)))
            prompts = ch.get("image_prompts") or [f"{q}, devotional painting" for q in ch["image_queries"]]
            made = make_ai_images(prompts, math.ceil(n_ai * AI_EXTRA), style)
            photos = list(made)
        want = math.ceil(need * 0.4) if photos else need           # AI na chale to Pixabay se poora
        if len(photos) < want:
            photos += download_chapter_images(
                ch["image_queries"], want - len(photos), topic=topic_desc,
                deity_keywords=outline.get("deity_keywords"))
        photos_by_chapter.append(photos)
    print("Photos per chapter:", [len(p) for p in photos_by_chapter])

    art_prompt = outline.get("thumbnail_art_prompt") or (
        "Dramatic cinematic movie-poster scene of the most emotional moment of this story, "
        f"{outline.get('thumbnail_query') or topic}, large divine characters in the middle of the frame, "
        "intense expressions, golden rim light, no text or letters")
    thumb_bg = None
    if cf_enabled():
        cands = [p for p in (cf_image(f"{art_prompt}. {THUMB_STYLE}",
                                      seed=random.randrange(1, 2 ** 31), steps=THUMB_STEPS)
                             for _ in range(4)) if p]
        thumb_bg = pick_best_thumbnail(cands, topic_desc) if cands else None
    if not thumb_bg:
        cands = download_thumb_candidates(
            [outline.get("thumbnail_query")] + list(outline.get("deity_keywords") or [])[:3]
            + [q for ch in chapters[:4] for q in list(ch.get("image_queries") or [])[:2]])
        random.shuffle(cands)                      # roz ek hi photo na chune
        thumb_bg = pick_best_thumbnail(cands, topic_desc)
    if not thumb_bg:
        pool = [p for ph in photos_by_chapter for p in ph]
        thumb_bg = pool[0] if pool else "Logo.jpg"
    thumb = make_thumbnail(thumb_bg, outline.get("thumbnail_text") or outline.get("title"),
                           badge=outline.get("thumbnail_badge") or "भक्ति कथा", layout="poster")

    bgm = get_bgm()
    video = render_video(audio_paths, durations, photos_by_chapter, headings, bgm,
                         captions=[c.get("caption_lines") for c in chapters])

    chapter_starts = [sum(durations[:i]) for i in range(len(durations))]
    description = build_description(outline.get("description", ""), headings, chapter_starts)
    long_title = outline.get("title") or "भगवान की सुंदर कथा"
    tags = outline.get("tags") or ["bhakti", "katha"]
    long_id = upload_youtube(video, thumb, long_title, description, tags)

    # Short (abhi band: MAKE_SHORTS = False). Chalu karo to koi gadbad hone par bhi run fail nahi hoga
    try:
        if not MAKE_SHORTS:
            raise RuntimeError("Short band hai (MAKE_SHORTS = False)")
        hook = outline.get("thumbnail_text") or long_title
        short_path = make_short(video, hook)
        short_title = clean(long_title)[:84] + " #Shorts"
        short_desc = (f"{clean(outline.get('thumbnail_text') or '')}\n\n▶ पूरी कथा यहाँ देखें: "
                      f"https://youtu.be/{long_id}\n\n🙏 {CHANNEL_NAME} - रोज़ नई भक्ति कथा\n"
                      "#Shorts #Bhakti #HindiKatha")
        upload_youtube(short_path, None, short_title, short_desc, list(tags) + ["Shorts"])
    except Exception as e:
        print("Short skip (lambe video par koi asar nahi):", str(e)[:200])
