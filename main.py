import os
import re
import json
import glob
import wave
import math
import time
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
from moviepy.editor import VideoClip, AudioFileClip, CompositeAudioClip
from moviepy.audio.fx.all import audio_loop

# ==================================================================
# SETTINGS (yahan apne hisaab se badlein)
# ==================================================================
CHANNEL_NAME = "Spiritual Bhakti"      # video par dikhne wala channel naam
VOICE = "hi-IN-MadhurNeural"           # female ke liye: hi-IN-SwaraNeural
PRIVACY = "public"                     # testing ke liye "private" kar sakte hain

MIN_MINUTES = 10                       # video ki lambai har baar random:
MAX_MINUTES = 20                       # 10 se 20 minute ke beech
WORDS_PER_MIN = 175                    # Hindi bolne ki speed (shabd/minute)
CHAPTER_WORDS = 400                    # har chapter me kitne shabd

SECONDS_PER_IMAGE = 15                 # har photo kitni der dikhe (kam = zyada photos)
MAX_IMAGES = 160
ZOOM_MAX = 2.15                        # zoom kitna gehra (1.0 = zoom nahi)
FADE = 2.0                             # photo badalte waqt crossfade (second)
TITLE_SECONDS = 10                     # shuru me title kitni der dikhe
BGM_VOLUME = 0.12
FPS = 20
W, H = 1280, 720

GEMINI_MODELS = [
    os.environ.get("GEMINI_MODEL", "gemini-3.8-flash"),
    "gemini-3.8-flash",
    "gemini-flash-latest",
]
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


def no_emoji(s):
    return re.sub(r"[\U00010000-\U0010FFFF\u2600-\u27BF\uFE0F]", "", str(s)).strip()


# ==================================================================
# 1. Gemini: plan + chapter-wise lambi kahani
# ==================================================================
_good_model = None


def parse_json(text):
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    return json.loads(text)


def ask_gemini(client, prompt, as_json=False, min_len=0):
    """503 par ruk kar dobara, model band ho to agla model."""
    global _good_model
    models = list(dict.fromkeys(([_good_model] if _good_model else []) + GEMINI_MODELS))
    last_error = None
    for model_name in models:
        for attempt in range(1, 6):
            try:
                cfg = (types.GenerateContentConfig(response_mime_type="application/json")
                       if as_json else None)
                response = client.models.generate_content(
                    model=model_name, contents=prompt, config=cfg)
                text = (response.text or "").strip()
                result = parse_json(text) if as_json else text
                if not as_json and len(text) < min_len:
                    raise ValueError("text bahut chhota aaya")
                _good_model = model_name
                return result
            except Exception as e:
                last_error = e
                msg = str(e)
                print(f"[{model_name}] attempt {attempt} failed: {msg[:150]}")
                if "404" in msg or "NOT_FOUND" in msg:
                    break
                time.sleep(5 if isinstance(e, ValueError) else min(30 * attempt, 90))
    raise RuntimeError("Gemini se jawab nahi mila") from last_error


def clean_story(text):
    text = re.sub(r"[*#_`>]+", "", text)
    text = re.sub(r"^\s*(अध्याय|चैप्टर|Chapter)\s*\d+.*$", "", text, flags=re.M | re.I)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def generate_content():
    ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    today = datetime.datetime.now(ist).strftime("%d %B %Y")
    minutes = random.randint(MIN_MINUTES, MAX_MINUTES)
    total_words = minutes * WORDS_PER_MIN
    n_chapters = max(3, math.ceil(total_words / CHAPTER_WORDS))
    print(f"Aaj ka target: {minutes} minute | {total_words} shabd | {n_chapters} chapters")

    if TOPIC:
        topic_line = f"Topic for today's video: {TOPIC}."
    else:
        topic_line = (
            "If a major Hindu festival or an eclipse (grahan) falls within the "
            "next 2 days, write about it. Otherwise pick a beautiful story of "
            "a Hindu deity or saint."
        )

    client = genai.Client(api_key=GEMINI_KEY)

    plan_prompt = f"""
You plan videos for a Hindi devotional (bhakti) YouTube channel.
Today's date (IST) is {today}. {topic_line}

Plan one long video of about {minutes} minutes. Keep facts accurate as per Hindu
scriptures and traditions. No superstition, no fear-based claims, no medical or
astrology predictions.

Return ONLY valid JSON (no markdown) with these keys:
- "title": Hindi, catchy, max 90 characters
- "description": Hindi, 120-200 words, hashtags at the end
- "tags": list of 10-15 strings (Hindi + English)
- "thumbnail_text": max 6 Hindi words, punchy
- "image_queries": list of 40 short English search queries for stock photos
   that match the story in order (temple, diya, lotus, deity idol, aarti, river,
   flowers, sunrise, mountains, etc.). Make them varied.
- "chapters": list of exactly {n_chapters} items, each a one-line Hindi summary of
   what happens in that part of the story, in order
"""
    plan = ask_gemini(client, plan_prompt, as_json=True)
    chapters = [str(c) for c in plan.get("chapters", []) if str(c).strip()]
    if len(chapters) < 2:
        raise RuntimeError("Gemini ne chapters nahi diye")
    title = plan.get("title") or "भगवान की सुंदर कथा"
    outline = "\n".join(f"{i + 1}. {c}" for i, c in enumerate(chapters))
    print("Title:", title, "| chapters:", len(chapters))

    parts, tail = [], ""
    for i, summary in enumerate(chapters):
        pos = ("This is the FIRST chapter: begin with a warm devotional greeting and "
               "introduce the story. " if i == 0 else "")
        if i == len(chapters) - 1:
            pos += ("This is the LAST chapter: end with the moral, a blessing, and "
                    "a gentle request to like, share and subscribe. ")
        else:
            pos += "Do NOT conclude the story here; the story continues in the next chapter. "
        chapter_prompt = f"""
You are writing chapter {i + 1} of {len(chapters)} of a long Hindi devotional narration.
Story title: {title}
Full plan:
{outline}

This chapter: {summary}
{"The previous chapter ended with: " + tail if tail else ""}

Write ONLY this chapter as a calm, devotional spoken narration in Hindi (Devanagari),
about {CHAPTER_WORDS} words. {pos}
Plain text only: no headings, no numbering, no markdown, no stage directions.
Continue naturally from the previous chapter. Keep facts accurate.
"""
        try:
            text = clean_story(ask_gemini(client, chapter_prompt, min_len=300))
            parts.append(text)
            tail = text[-300:]
            print(f"Chapter {i + 1}/{len(chapters)} ready ({len(text.split())} words)")
        except Exception as e:
            print(f"Chapter {i + 1} fail hua, chhod rahe hain:", str(e)[:100])
        time.sleep(3)

    story = "\n\n".join(parts)
    if len(story) < 1500:
        raise RuntimeError("Kahani bahut chhoti bani, dobara chalaiye")
    plan["story"] = story
    plan["title"] = title
    return plan


# ==================================================================
# 2. Voiceover (Edge TTS, fail ho to gTTS)
# ==================================================================
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


# ==================================================================
# 3. Pixabay se bahut saari photos
# ==================================================================
def download_images(queries, target):
    paths, seen = [], set()
    headers = {"User-Agent": "Mozilla/5.0"}
    for q in queries:
        if len(paths) >= target:
            break
        try:
            r = requests.get(
                "https://pixabay.com/api/",
                params={
                    "key": PIXABAY_KEY, "q": q, "image_type": "photo",
                    "orientation": "horizontal", "safesearch": "true",
                    "per_page": 12, "min_width": 1280,
                },
                headers=headers, timeout=30,
            ).json()
            taken = 0
            for hit in r.get("hits", []):
                if taken >= 4 or len(paths) >= target:
                    break
                if hit["id"] in seen:
                    continue
                seen.add(hit["id"])
                path = f"bg_{len(paths)}.jpg"
                try:
                    with open(path, "wb") as f:
                        f.write(requests.get(hit["largeImageURL"], headers=headers,
                                             timeout=60).content)
                    Image.open(path).verify()
                    paths.append(path)
                    taken += 1
                except Exception as e:
                    print("Download error:", str(e)[:80])
        except Exception as e:
            print("Pixabay error:", q, str(e)[:100])
        time.sleep(0.6)                      # Pixabay rate limit se bachne ke liye
    if not paths and os.path.exists("Logo.jpg"):
        paths = ["Logo.jpg"]
    print("Images:", len(paths), "/ target", target)
    return paths


# ==================================================================
# 4. Fonts, overlay, title card, thumbnail (Pillow)
# ==================================================================
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


def vignette_layer(strength=120):
    """Kinaron par halka andhera (cinematic look)."""
    ys, xs = np.mgrid[0:H, 0:W]
    r = np.sqrt(((xs - W / 2) / (W / 2)) ** 2 + ((ys - H / 2) / (H / 2)) ** 2)
    a = (np.clip((r - 0.65) / 0.75, 0, 1) ** 1.5 * strength).astype(np.uint8)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    layer.putalpha(Image.fromarray(a))
    return layer


def make_overlay():
    """Vignette + neeche patti (logo, channel naam, SUBSCRIBE) - har frame par same."""
    layer = vignette_layer(120)
    bar = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(bar)
    d.rectangle([0, H - 95, W, H], fill=(0, 0, 0, 150))
    x = 20
    if os.path.exists("Logo.jpg"):
        logo, mask = circle_logo(70)
        bar.paste(logo, (20, H - 83), mask)
        x = 105
    d.text((x, H - 78), CHANNEL_NAME, font=font_for(CHANNEL_NAME, 34), fill=(255, 255, 255, 255))
    bx0, by0, bx1, by1 = W - 290, H - 78, W - 20, H - 18
    d.rounded_rectangle([bx0, by0, bx1, by1], radius=14, fill=(220, 20, 20, 255))
    d.text((bx0 + 32, by0 + 12), "SUBSCRIBE", font=font_for("SUBSCRIBE", 32),
           fill=(255, 255, 255, 255))
    return Image.alpha_composite(layer, bar)


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


def make_title_card(title):
    """Video ke shuru me dikhne wala title (halke se aata aur jaata hai)."""
    title = no_emoji(title)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    font = font_for(title, 64)
    lines = wrap_text(d, title, font, W - 200)[:3]
    line_h = 84
    total = line_h * len(lines)
    y0 = (H - 95 - total) // 2 + 30
    d.rectangle([0, y0 - 40, W, y0 + total + 30], fill=(0, 0, 0, 165))
    d.rectangle([0, y0 - 40, W, y0 - 34], fill=(255, 200, 0, 255))
    d.rectangle([0, y0 + total + 24, W, y0 + total + 30], fill=(255, 200, 0, 255))
    for i, line in enumerate(lines):
        tw = d.textlength(line, font=font)
        d.text(((W - tw) / 2, y0 + i * line_h), line, font=font, fill=(255, 255, 255, 255),
               stroke_width=3, stroke_fill=(0, 0, 0, 255))
    return layer.convert("RGB"), layer.split()[3]


def pick_best_image(paths):
    """Thumbnail ke liye sabse rangeen aur chamakdar photo chunta hai."""
    best, best_score = paths[0], -1.0
    for p in paths[:25]:
        try:
            hsv = Image.open(p).convert("RGB").resize((64, 36)).convert("HSV")
            _, s, v = hsv.split()
            s_m, v_m = np.array(s).mean() / 255, np.array(v).mean() / 255
            score = s_m * (1 - abs(v_m - 0.55) * 1.5)
            if score > best_score:
                best, best_score = p, score
        except Exception:
            continue
    return best


def make_thumbnail(bg_path, text, out_path="thumb.jpg"):
    text = no_emoji(text)
    img = cover_crop(Image.open(bg_path))
    img = ImageEnhance.Color(img).enhance(1.35)
    img = ImageEnhance.Contrast(img).enhance(1.15)
    img = ImageEnhance.Sharpness(img).enhance(1.4).convert("RGBA")

    xs = np.linspace(0, 1, W)                       # bayen taraf gehra gradient
    a = (np.clip(1 - xs / 0.78, 0, 1) ** 1.2 * 225).astype(np.uint8)
    grad = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    grad.putalpha(Image.fromarray(np.tile(a, (H, 1))))
    img = Image.alpha_composite(img, grad)
    img = Image.alpha_composite(img, vignette_layer(140))
    d = ImageDraw.Draw(img)

    # Title: bada, saaf, rang-birange shabd
    max_w = int(W * 0.64)
    for size in range(150, 59, -10):
        font = font_for(text, size)
        lines = wrap_text(d, text, font, max_w)
        if len(lines) <= 3 and all(d.textlength(l, font=font) <= max_w for l in lines):
            break
    lines = lines[:3]
    line_h = int(size * 1.3)
    y = (H - line_h * len(lines)) // 2 + 30
    colors = [(255, 214, 10), (255, 255, 255), (255, 214, 10)]
    for i, line in enumerate(lines):
        d.text((78, y + 7), line, font=font, fill=(0, 0, 0, 200))        # parchhai
        d.text((70, y), line, font=font, fill=colors[i % 3],
               stroke_width=8, stroke_fill=(0, 0, 0, 255))
        y += line_h

    # Upar laal badge me channel naam
    bfont = font_for(CHANNEL_NAME, 38)
    bw = int(d.textlength(CHANNEL_NAME, font=bfont)) + 60
    d.rounded_rectangle([70, 48, 70 + bw, 112], radius=16, fill=(215, 25, 25, 255))
    d.text((100, 56), CHANNEL_NAME, font=bfont, fill=(255, 255, 255, 255))

    # Neeche daayen sunehri ring me logo
    if os.path.exists("Logo.jpg"):
        size_l = 210
        lx, ly = W - size_l - 60, H - size_l - 60
        d.ellipse([lx - 10, ly - 10, lx + size_l + 10, ly + size_l + 10],
                  fill=(255, 200, 0, 255))
        logo, mask = circle_logo(size_l)
        img.paste(logo, (lx, ly), mask)

    d.rectangle([10, 10, W - 10, H - 10], outline=(255, 200, 0, 255), width=6)

    rgb = img.convert("RGB")
    for q in (93, 88, 82, 75):                       # 2MB se chhota rakhne ke liye
        rgb.save(out_path, quality=q)
        if os.path.getsize(out_path) < 1_900_000:
            break
    print("Thumbnail ready")
    return out_path


# ==================================================================
# 5. Background music (automatic, copyright-free)
# ==================================================================
def generate_bgm(path="bgm_gen.wav", loop_sec=24, sr=22050):
    """Tanpura jaisi drone + soft pad + ghanti. Har baar alag swar."""
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
        f 
# ==================================================================
if __name__ == "__main__":
    print("Starting Daily Bhakti Video Automation (Long Video)...")
    check_secrets()

    plan = generate_content()
    title = plan.get("title") or "भगवान की सुंदर कथा"
    story = plan["story"]
    description = (plan.get("description") or "") + (
        f"\n\n🙏 {CHANNEL_NAME} - रोज़ एक नई भक्ति कथा के लिए चैनल को "
        "Subscribe करें और बेल आइकन दबाएँ।"
    )
    tags = plan.get("tags") or ["bhakti", "katha"]
    thumb_text = plan.get("thumbnail_text") or title
    queries = plan.get("image_queries") or ["hindu temple", "diya lamp", "lotus flower"]

    # 1. Voiceover
    make_voiceover(story, "audio.mp3")
    
    # Audio ki lambai ke hisaab se target images tay karna (15 second par 1 image)
    voice_clip = AudioFileClip("audio.mp3")
    duration = voice_clip.duration
    voice_clip.close()
    target_images = max(10, min(MAX_IMAGES, int(duration / SECONDS_PER_IMAGE)))

    # 2. Images
    images = download_images(queries, target_images)
    if not images:
        raise SystemExit("Error: koi image nahi mili (Pixabay key check karein).")

    # 3. Thumbnail & Title Card
    best_img = pick_best_image(images)
    thumb = make_thumbnail(best_img, thumb_text)
    title_img, title_mask = make_title_card(title)
    title_img_path = "title_card.jpg"
    title_img.save(title_img_path)

    # 4. BGM & Video Render
    bgm = (glob.glob("music/*.mp3") + glob.glob("music/*.wav") + glob.glob("bgm*.mp3") or [None])[0]
    if not bgm:
        bgm = generate_bgm()

    # Video clips assemble karna
    clips = []
    # Shuru me title card
    tc = ImageClip(title_img_path).set_duration(TITLE_SECONDS).crossfadein(1).crossfadeout(1)
    clips.append(tc)

    # Baaki images
    per_img_time = max(4.0, (duration - TITLE_SECONDS) / len(images))
    for p in images:
        img_clip = ImageClip(cover_crop(Image.open(p))).set_duration(per_img_time).crossfadein(FADE)
        clips.append(img_clip)

    from moviepy.editor import concatenate_videoclips
    final_video_clip = concatenate_videoclips(clips, method="compose")

    # Audio jodna
    voice = AudioFileClip("audio.mp3")
    if bgm and os.path.exists(bgm):
        bgm_clip = audio_loop(AudioFileClip(bgm).volumex(BGM_VOLUME), duration=voice.duration)
        final_audio = CompositeAudioClip([voice, bgm_clip]).set_duration(voice.duration)
    else:
        final_audio = voice

    final_video_clip = final_video_clip.set_audio(final_audio)
    output_path = "final_video.mp4"
    final_video_clip.write_videofile(
        output_path, fps=FPS, codec="libx264", audio_codec="aac",
        preset="ultrafast", threads=2,
    )
    print("Video rendered successfully!")

    # 5. YouTube Upload
    def clean(s):
        return re.sub(r"[<>]", "", str(s)).strip()

    def cut_bytes(s, limit):
        return s.encode("utf-8")[:limit].decode("utf-8", "ignore")

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
            "description": cut_bytes(clean(description), 4800),
            "tags": clean_tags,
            "categoryId": "22",
            "defaultLanguage": "hi",
        },
        "status": {"privacyStatus": PRIVACY, "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(output_path, chunksize=-1, resumable=True)
    response = youtube.videos().insert(
        part="snippet,status", body=body, media_body=media
    ).execute()
    video_id = response.get("id")
    print("Uploaded! https://youtu.be/" + str(video_id))

    try:
        youtube.thumbnails().set(
            videoId=video_id, media_body=MediaFileUpload(thumb)
        ).execute()
        print("Thumbnail set successfully")
    except Exception as e:
        print("Thumbnail error:", str(e)[:200])
        
