"""
Daily Bhakti Video Automation (poora code, ek hi file)
Gemini script -> Hindi voice -> zoom in/out photos -> BGM -> thumbnail -> YouTube upload
"""
import os, sys, json, re, time, random, glob, math, asyncio, subprocess
from pathlib import Path

# ============ SETTINGS (yahin badalna hai) ============
CHANNEL_NAME = os.environ.get("CHANNEL_NAME", "मेरा चैनल")   # <-- apna asli naam likhiye
PRIVACY = os.environ.get("PRIVACY", "private")               # test ke liye private, baad me public
MIN_MINUTES = int(os.environ.get("MIN_MINUTES", "10"))       # video kam se kam itne minute
MAX_MINUTES = int(os.environ.get("MAX_MINUTES", "20"))       # video zyada se zyada itne minute
VOICE = os.environ.get("VOICE", "hi-IN-MadhurNeural")
MODELS = [m for m in [os.environ.get("GEMINI_MODEL"), "gemini-3.8-flash", "gemini-flash-latest"] if m]
SEC_PER_IMAGE = 7          # har photo kitni der dikhe
ZOOM_AMOUNT = 0.25         # zoom kitna (0.25 = 25%)
BGM_VOLUME = float(os.environ.get("BGM_VOLUME", "0.12"))
W, H, FPS = 1280, 720, 24
# =====================================================

WORK = Path("work")
WORK.mkdir(exist_ok=True)


def log(*a):
    print(*a, flush=True)


def sh(cmd):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("Command fail: %s\n%s" % (" ".join(map(str, cmd))[:300], r.stderr[-1500:]))
    return r.stdout


# ---------------------------------------------------------------- GEMINI
def gemini(prompt, json_mode=False):
    from google import genai
    from google.genai import types
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GEMINI_KEY")
    client = genai.Client(api_key=key)
    last = None
    for model in MODELS:
        for attempt in range(5):
            try:
                cfg = types.GenerateContentConfig(response_mime_type="application/json") if json_mode else None
                r = client.models.generate_content(model=model, contents=prompt, config=cfg)
                if r.text:
                    return r.text
            except Exception as e:
                last = e
                s = str(e)
                if "404" in s or "NOT_FOUND" in s:
                    log("Model nahi mila:", model)
                    break
                wait = 30 * (attempt + 1)
                log("Gemini error (%s), %ss baad dobara: %s" % (model, wait, s[:150]))
                time.sleep(wait)
    raise RuntimeError("Gemini se jawab nahi mila: %s" % last)


def parse_json(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    return json.loads(text)


def clean_text(t):
    t = re.sub(r"[*#_`>\[\]]", "", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def get_outline(topic, minutes, n_sections):
    prompt = (
        "तुम एक भक्ति/धार्मिक YouTube चैनल के लेखक हो। विषय: %s\n"
        "एक लंबे हिंदी वीडियो (लगभग %d मिनट) की रूपरेखा JSON में दो। सिर्फ JSON दो, इस ढाँचे में:\n"
        '{"title": "...", "description": "...", "tags": ["..."], "thumbnail_text": "...", '
        '"sections": [{"heading": "...", "image_query": "..."}]}\n'
        "नियम:\n"
        "- title हिंदी में, आकर्षक, 70 अक्षर से कम, विषय का मुख्य शब्द शुरू में।\n"
        "- description हिंदी में 150-250 शब्द, आख़िर में 8-10 hashtags।\n"
        "- tags 12-15, हिंदी और अंग्रेज़ी मिलाकर।\n"
        "- thumbnail_text 2-4 शब्द, दमदार, हिंदी में।\n"
        "- ठीक %d sections हों। image_query अंग्रेज़ी में 2-4 शब्द (जैसे 'diya temple aarti')।\n"
        "- तथ्य सही हों। अंधविश्वास या डराने वाली बातें नहीं। अगर किसी तिथि या समय का पक्का पता न हो तो मत लिखो।"
        % (topic, minutes, n_sections)
    )
    data = parse_json(gemini(prompt, json_mode=True))
    if not data.get("sections"):
        raise RuntimeError("Outline me sections nahi aaye")
    return data


def get_section_text(topic, outline, idx, words):
    secs = outline["sections"]
    total = len(secs)
    sec = secs[idx]
    extra = ""
    if idx == 0:
        extra = "शुरुआत में दर्शकों का स्वागत करो और विषय का परिचय दो। "
    if idx == total - 1:
        extra += "अंत में सार बताओ और दर्शकों से चैनल %s को सब्सक्राइब, लाइक और शेयर करने को कहो। " % CHANNEL_NAME
    prev = secs[idx - 1]["heading"] if idx > 0 else "कोई नहीं"
    prompt = (
        "वीडियो का विषय: %s\nवीडियो का शीर्षक: %s\n"
        "अब भाग %d/%d लिखो: \"%s\" (पिछला भाग: %s)\n"
        "लगभग %d शब्द, शुद्ध हिंदी (देवनागरी) में, बोलने वाली सहज भाषा में, जैसे कोई कथावाचक सुना रहा हो।\n"
        "%s\n"
        "सिर्फ़ बोला जाने वाला पाठ दो। कोई heading, bullet, markdown, emoji या कोष्ठक नहीं। "
        "तथ्य सही रखो, अंधविश्वास वाली बातें नहीं।"
        % (topic, outline["title"], idx + 1, total, sec["heading"], prev, words, extra)
    )
    return clean_text(gemini(prompt))


# ---------------------------------------------------------------- VOICE
async def _edge(text, out):
    import edge_tts
    await edge_tts.Communicate(text, VOICE, rate="-5%").save(out)


def make_voice(text, out):
    for i in range(3):
        try:
            asyncio.run(_edge(text, out))
            if os.path.getsize(out) > 2000:
                return
        except Exception as e:
            log("Edge TTS fail (%d): %s" % (i + 1, str(e)[:120]))
            time.sleep(5)
    log("gTTS use ho raha hai")
    from gtts import gTTS
    gTTS(text, lang="hi").save(out)


def duration(path):
    out = sh(["ffprobe", "-v", "error", "-show_entries", "format=duration",
              "-of", "default=nw=1:nk=1", path])
    return float(out.strip())


# ---------------------------------------------------------------- FONT / IMAGES
_font_path = None


def find_font():
    global _font_path
    if _font_path:
        return _font_path

    def search():
        pats = ["/usr/share/fonts/**/*.ttf", "/usr/share/fonts/**/*.otf"]
        files = []
        for p in pats:
            files += glob.glob(p, recursive=True)
        for key in ("devanagari", "deva", "hind", "mukta"):
            for f in files:
                low = os.path.basename(f).lower()
                if key in low and "bold" not in low:
                    return f
        return None

    f = search()
    if not f:
        try:
            subprocess.run(["sudo", "apt-get", "install", "-y", "fonts-lohit-deva", "fonts-noto-core"],
                           capture_output=True, timeout=240)
        except Exception:
            pass
        f = search()
    if not f and os.path.exists("font.ttf"):
        f = "font.ttf"
    if not f:
        d = glob.glob("/usr/share/fonts/**/DejaVuSans.ttf", recursive=True)
        f = d[0] if d else None
    _font_path = f
    log("Font:", f)
    return f


def font(size):
    from PIL import ImageFont
    p = find_font()
    return ImageFont.truetype(p, size) if p else ImageFont.load_default()


PALETTES = [((255, 153, 51), (128, 0, 32)), ((255, 200, 80), (90, 20, 10)),
            ((40, 30, 90), (200, 90, 40)), ((20, 60, 80), (240, 170, 60)),
            ((120, 20, 60), (250, 140, 40))]


def make_art(seed):
    """Photo na mile to sundar rangoli/mandala jaisa background."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter
    rnd = random.Random(seed)
    c1, c2 = rnd.choice(PALETTES)
    y = np.linspace(0, 1, H)[:, None, None]
    base = np.array(c1) * (1 - y) + np.array(c2) * y
    arr = np.repeat(base, W, axis=1).astype("uint8")
    img = Image.fromarray(arr).convert("RGBA")
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx = W // 2 + rnd.randint(-250, 250)
    cy = H // 2 + rnd.randint(-80, 80)
    n = rnd.choice([8, 12, 16])
    R = rnd.randint(150, 260)
    for ring in range(3):
        r = R * (1 - ring * 0.28)
        for k in range(n):
            a = 2 * math.pi * k / n + ring * 0.2
            px, py = cx + r * math.cos(a), cy + r * math.sin(a)
            pr = r * 0.38
            d.ellipse([px - pr, py - pr, px + pr, py + pr], outline=(255, 230, 160, 120), width=3)
    d.ellipse([cx - 32, cy - 32, cx + 32, cy + 32], fill=(255, 240, 180, 235))
    glow = layer.filter(ImageFilter.GaussianBlur(14))
    img = Image.alpha_composite(img, glow)
    img = Image.alpha_composite(img, layer)
    return img.convert("RGB")


def cover(img):
    from PIL import Image
    img = img.convert("RGB")
    s = max(W / img.width, H / img.height)
    img = img.resize((int(img.width * s) + 1, int(img.height * s) + 1))
    l, t = (img.width - W) // 2, (img.height - H) // 2
    return img.crop((l, t, l + W, t + H))


def add_logo(img, size=90, pos=(W - 110, 18)):
    from PIL import Image
    for name in ("Logo.jpg", "logo.jpg", "Logo.png", "logo.png"):
        if os.path.exists(name):
            try:
                lg = Image.open(name).convert("RGB").resize((size, size))
                img.paste(lg, pos)
            except Exception:
                pass
            break
    return img


def brand(img):
    """Har photo par channel naam + SUBSCRIBE button."""
    from PIL import Image, ImageDraw
    img = cover(img).convert("RGBA")
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    d.rectangle([0, H - 70, W, H], fill=(0, 0, 0, 150))
    d.text((24, H - 54), CHANNEL_NAME, font=font(32), fill=(255, 255, 255, 255))
    bw = 200
    d.rounded_rectangle([W - bw - 24, H - 58, W - 24, H - 12], radius=10, fill=(220, 0, 0, 255))
    d.text((W - bw - 24 + 24, H - 52), "SUBSCRIBE", font=font(26), fill=(255, 255, 255, 255))
    out = Image.alpha_composite(img, ov).convert("RGB")
    return add_logo(out)


def pexels(query, n):
    key = os.environ.get("PEXELS_API_KEY")
    if not key or n <= 0:
        return []
    import requests
    try:
        r = requests.get("https://api.pexels.com/v1/search",
                         headers={"Authorization": key},
                         params={"query": query, "per_page": min(n, 40), "orientation": "landscape"},
                         timeout=30)
        photos = r.json().get("photos", [])
    except Exception as e:
        log("Pexels error:", str(e)[:100])
        return []
    paths = []
    cache = WORK / "pexels"
    cache.mkdir(exist_ok=True)
    for p in photos[:n]:
        fp = cache / ("%s.jpg" % p["id"])
        try:
            if not fp.exists():
                fp.write_bytes(requests.get(p["src"]["large"], timeout=30).content)
            paths.append(fp)
        except Exception:
            continue
    return paths


def build_images(query, n, tag):
    """n photos taiyar (branding ke saath). Pexels + generated art."""
    from PIL import Image
    srcs = pexels(query, n)
    out = []
    for i in range(n):
        if i < len(srcs):
            img = Image.open(srcs[i])
        else:
            img = make_art("%s-%d-%d" % (tag, i, random.randint(0, 99999)))
        p = WORK / ("img_%s_%03d.jpg" % (tag, i))
        brand(img).save(p, quality=90)
        out.append(p)
    return out


# ---------------------------------------------------------------- THUMBNAIL
def make_thumbnail(text, bg_path, out):
    from PIL import Image, ImageDraw, ImageEnhance
    bg = ImageEnhance.Brightness(cover(Image.open(bg_path))).enhance(0.55)
    d = ImageDraw.Draw(bg)
    words = text.split()
    if len(words) > 2:
        mid = (len(words) + 1) // 2
        lines = [" ".join(words[:mid]), " ".join(words[mid:])]
    else:
        lines = [text]
    size = 150
    while size > 50:
        f = font(size)
        if all(d.textlength(l, font=f) < W - 120 for l in lines):
            break
        size -= 6
    f = font(size)
    total_h = len(lines) * int(size * 1.35)
    y = (H - total_h) // 2 - 20
    for l in lines:
        x = (W - d.textlength(l, font=f)) // 2
        d.text((x, y), l, font=f, fill=(255, 225, 0), stroke_width=7, stroke_fill=(0, 0, 0))
        y += int(size * 1.35)
    d.rectangle([0, H - 80, W, H], fill=(0, 0, 0))
    d.text((24, H - 62), CHANNEL_NAME, font=font(36), fill=(255, 255, 255))
    add_logo(bg, 110, (W - 130, 20))
    bg.save(out, quality=88)


# ---------------------------------------------------------------- MUSIC
def make_bgm(path, seconds=60):
    """Tanpura jaisi halki drone music, code se (copyright ka darr nahi)."""
    import numpy as np, wave
    sr = 22050
    t = np.arange(int(sr * seconds)) / sr
    base = random.choice([130.81, 146.83, 155.56, 164.81, 174.61])
    sig = np.zeros_like(t)
    for ratio, amp in [(1.0, 0.5), (1.5, 0.35), (2.0, 0.4), (3.0, 0.12)]:
        f = round(base * ratio * seconds) / seconds   # seamless loop
        phase = random.random() * 6.28
        trem = 0.8 + 0.2 * np.sin(2 * np.pi * (9 / seconds) * t + phase)
        for h, ha in [(1, 1.0), (2, 0.3), (3, 0.15)]:
            sig += amp * ha * np.sin(2 * np.pi * f * h * t) * trem
    sig = sig / np.max(np.abs(sig)) * 0.5
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((sig * 32767).astype("<i2").tobytes())


def pick_bgm():
    files = glob.glob("music/*.mp3") + glob.glob("music/*.wav")
    if files:
        return random.choice(files)
    if os.path.exists("bgm.mp3"):
        return "bgm.mp3"
    p = WORK / "bgm_generated.wav"
    make_bgm(p)
    return str(p)


# ---------------------------------------------------------------- VIDEO
def make_clip(img, dur, idx, out):
    """Ek photo ko zoom in ya zoom out ke saath clip banao."""
    frames = max(int(dur * FPS), 2)
    step = ZOOM_AMOUNT / frames
    if idx % 2 == 0:
        z = "min(1+%.7f*on,%.3f)" % (step, 1 + ZOOM_AMOUNT)      # zoom in
    else:
        z = "max(%.3f-%.7f*on,1)" % (1 + ZOOM_AMOUNT, step)       # zoom out
    vf = ("scale=2560:1440,zoompan=z='%s':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
          ":d=%d:s=%dx%d:fps=%d,format=yuv420p" % (z, frames, W, H, FPS))
    sh(["ffmpeg", "-y", "-i", img, "-vf", vf, "-frames:v", frames, "-c:v", "libx264",
        "-preset", "veryfast", "-crf", "23", out])


def concat(files, out, audio=False):
    lst = WORK / ("list_%s.txt" % Path(out).stem)
    lst.write_text("".join("file '%s'\n" % Path(f).resolve() for f in files), encoding="utf-8")
    if audio:
        sh(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c:a", "libmp3lame", "-b:a", "128k", out])
    else:
        sh(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out])


# ---------------------------------------------------------------- YOUTUBE
def upload(video, thumb, title, desc, tags):
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    creds = Credentials(None,
                        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
                        token_uri="https://oauth2.googleapis.com/token",
                        client_id=os.environ["YOUTUBE_CLIENT_ID"],
                        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"])
    creds.refresh(Request())
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)

    title = re.sub(r"[<>]", "", title)[:95]
    desc = re.sub(r"[<>]", "", desc)
    desc = desc.encode("utf-8")[:4800].decode("utf-8", errors="ignore")
    clean_tags, total = [], 0
    for t in tags:
        t = re.sub(r"[<>#,]", "", str(t)).strip()[:30]
        if t and total + len(t) < 450:
            clean_tags.append(t)
            total += len(t) + 1
    body = {"snippet": {"title": title, "description": desc, "tags": clean_tags,
                        "categoryId": "22", "defaultLanguage": "hi"},
            "status": {"privacyStatus": PRIVACY, "selfDeclaredMadeForKids": False}}
    media = MediaFileUpload(video, chunksize=8 * 1024 * 1024, resumable=True, mimetype="video/mp4")
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    resp, tries = None, 0
    while resp is None:
        try:
            status, resp = req.next_chunk()
            if status:
                log("Upload: %d%%" % int(status.progress() * 100))
        except Exception as e:
            tries += 1
            if tries > 6:
                raise
            log("Upload error, dobara:", str(e)[:120])
            time.sleep(10 * tries)
    vid = resp["id"]
    log("Video upload ho gaya: https://youtu.be/" + vid)
    try:
        yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(thumb, mimetype="image/jpeg")).execute()
        log("Thumbnail lag gaya")
    except Exception as e:
        log("Thumbnail nahi lag paya (channel verified hona chahiye):", str(e)[:150])
    return vid


# ---------------------------------------------------------------- MAIN
def get_topic():
    for k in ("TOPIC", "VIDEO_TOPIC", "INPUT_TOPIC"):
        if os.environ.get(k, "").strip():
            return os.environ[k].strip()
    if len(sys.argv) > 1 and sys.argv[1].strip():
        return " ".join(sys.argv[1:]).strip()
    return "आज का भक्ति विचार और प्रेरणा"


def check_env():
    missing = []
    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GEMINI_KEY")):
        missing.append("GEMINI_API_KEY")
    for k in ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"):
        if not os.environ.get(k):
            missing.append(k)
    if missing:
        raise SystemExit("Ye secrets khaali hain: " + ", ".join(missing))


def main():
    check_env()
    topic = get_topic()
    minutes = random.randint(MIN_MINUTES, MAX_MINUTES)
    n_sections = max(5, round(minutes / 2))
    words = max(150, int(minutes * 130 / n_sections))
    log("Topic: %s | Target: ~%d min | Sections: %d" % (topic, minutes, n_sections))

    outline = get_outline(topic, minutes, n_sections)
    secs = outline["sections"]
    log("Title:", outline["title"])

    voice_files, clips, first_img = [], [], None
    for i, sec in enumerate(secs):
        log("--- Section %d/%d: %s" % (i + 1, len(secs), sec["heading"]))
        text = get_section_text(topic, outline, i, words)
        vp = str(WORK / ("voice_%02d.mp3" % i))
        make_voice(text, vp)
        dur = duration(vp)
        voice_files.append(vp)
        n_img = max(1, round(dur / SEC_PER_IMAGE))
        imgs = build_images(sec.get("image_query", "temple diya"), n_img, "s%02d" % i)
        if first_img is None:
            first_img = imgs[0]
        per = dur / n_img
        for j, im in enumerate(imgs):
            cp = str(WORK / ("clip_%02d_%03d.mp4" % (i, j)))
            make_clip(str(im), per, j, cp)
            clips.append(cp)
        time.sleep(2)

    log("Video jod rahe hain...")
    concat(clips, WORK / "video_silent.mp4")
    concat(voice_files, WORK / "voice_all.mp3", audio=True)
    bgm = pick_bgm()
    final = "final_video.mp4"
    sh(["ffmpeg", "-y", "-i", WORK / "video_silent.mp4", "-i", WORK / "voice_all.mp3",
        "-stream_loop", "-1", "-i", bgm,
        "-filter_complex",
        "[2:a]volume=%s[b];[1:a][b]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]" % BGM_VOLUME,
        "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
        "-shortest", "-movflags", "+faststart", final])
    log("Final video: %.1f minute" % (duration(final) / 60))

    thumb = "thumbnail.jpg"
    make_thumbnail(outline.get("thumbnail_text") or outline["title"][:20], first_img, thumb)

    upload(final, thumb, outline["title"], outline["description"], outline.get("tags", []))
    log("Sab kaam poora.")


if __name__ == "__main__":
    main()
    
