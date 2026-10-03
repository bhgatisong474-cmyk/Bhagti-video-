import os
import requests
import asyncio
import edge_tts
from google.generativeai import configure, GenerativeModel
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from moviepy.editor import ImageClip, AudioFileClip, TextClip, CompositeVideoClip, CompositeAudioClip

# GitHub Secrets से API Keys पढ़ना
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
PIXABAY_KEY = os.environ.get("PIXABAY_API_KEY")
YT_CLIENT_ID = os.environ.get("YOUTUBE_CLIENT_ID")
YT_CLIENT_SECRET = os.environ.get("YOUTUBE_CLIENT_SECRET")
YT_REFRESH_TOKEN = os.environ.get("YOUTUBE_REFRESH_TOKEN")

configure(api_key=GEMINI_KEY)

# 1. Gemini AI से कहानी और मेटाडेटा बनाना
def generate_story():
    model = GenerativeModel("gemini-1.5-flash")
    prompt = (
        "हिंदी में एक बहुत ही सुंदर और प्रेरणादायक हिंदू पौराणिक/धार्मिक कथा लिखें। "
        "फॉर्मेट ऐसा रखें:\n"
        "TITLE: <शीर्षक>\n"
        "DESCRIPTION: <विवरण>\n"
        "TAGS: <टैग्स>\n"
        "STORY: <पुरी कहानी>"
    )
    return model.generate_content(prompt).text

# 2. HD वॉइसओवर (edge-tts)
async def make_voiceover(text, output="audio.mp3"):
    communicate = edge_tts.Communicate(text, "hi-IN-MadhurNeural")
    await communicate.save(output)

# 3. Pixabay API से टॉपिक के हिसाब से HD इमेज लाना
def get_pixabay_image(query="god krishna india"):
    url = f"https://pixabay.com/api/?key={PIXABAY_KEY}&q={query}&image_type=photo&orientation=horizontal"
    try:
        r = requests.get(url).json()
        if r.get("hits"):
            img_url = r["hits"][0]["largeImageURL"]
            img_data = requests.get(img_url).content
            with open("bg.jpg", "wb") as f:
                f.write(img_data)
            return "bg.jpg"
    except Exception as e:
        print("Image Fetch Error:", e)
    return None

# 4. Pixabay Audio API Key से बढ़िया बैकग्राउंड म्यूज़िक ऑटो-सर्च करके लाना
def get_pixabay_bgm(query="indian flute devotional"):
    # Pixabay API से म्यूज़िक ढूँढना
    url = f"https://pixabay.com/api/docs/#api_search_audio?key={PIXABAY_KEY}&q={query}"
    
    # बैकअप भक्ति बांसुरी धुन (अगर सर्च में दिक्कत आए तो यह लोड होगा)
    fallback_bgm_url = "https://cdn.pixabay.com/download/audio/2022/05/27/audio_1808fbf07a.mp3"
    
    try:
        # Pixabay API कॉल करके ऑडियो फ़ाइल उठाना
        api_search = f"https://pixabay.com/api/?key={PIXABAY_KEY}&q={query}&media=audio"
        res = requests.get(api_search).json()
        
        if res.get("hits") and len(res["hits"]) > 0:
            audio_url = res["hits"][0].get("audio", fallback_bgm_url)
        else:
            audio_url = fallback_bgm_url

        audio_data = requests.get(audio_url).content
        with open("bgm.mp3", "wb") as f:
            f.write(audio_data)
        return "bgm.mp3"
    except Exception as e:
        print("BGM Fetch Error, using fallback:", e)
        try:
            audio_data = requests.get(fallback_bgm_url).content
            with open("bgm.mp3", "wb") as f:
                f.write(audio_data)
            return "bgm.mp3"
        except:
            return None

# 5. वीडियो एडिटिंग (Font + BGM Mix + Auto Text Watermark)
def render_video(image_path, audio_path, bgm_path, output_path="final_video.mp4"):
    voice_audio = AudioFileClip(audio_path)
    video_duration = voice_audio.duration

    # बैकग्राउंड इमेज क्लिप
    img_clip = ImageClip(image_path).set_duration(video_duration)

    # ऑटोमैटिक टेक्स्ट वॉटरमार्क (Font.ttf के साथ)
    font_file = "font.ttf" if os.path.exists("font.ttf") else None
    watermark = TextClip("spiritual_bhaktee", fontsize=30, color='white', font=font_file, opacity=0.5)
    watermark = watermark.set_position(('right', 'top')).set_duration(video_duration)

    # वीडियो और वॉटरमार्क मिक्स
    final_video = CompositeVideoClip([img_clip, watermark])

    # वॉइसओवर और BGM मिक्स (BGM की आवाज़ हल्की 12% रखी गई है)
    if bgm_path and os.path.exists(bgm_path):
        bgm = AudioFileClip(bgm_path).volumex(0.12).set_duration(video_duration)
        final_audio = CompositeAudioClip([voice_audio, bgm])
    else:
        final_audio = voice_audio

    final_video = final_video.set_audio(final_audio)
    final_video.write_videofile(output_path, fps=24, codec="libx264", audio_codec="aac")

# 6. YouTube Auto Upload
def upload_youtube(video_path, title, description, tags):
    creds = Credentials(
        None,
        refresh_token=YT_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=YT_CLIENT_ID,
        client_secret=YT_CLIENT_SECRET
    )
    youtube = build("youtube", "v3", credentials=creds)
    body = {
        "snippet": {
            "title": title[:100],
            "description": description,
            "tags": [t.strip() for t in tags.split(",") if t.strip()],
            "categoryId": "22"
        },
        "status": {"privacyStatus": "public"}
    }
    media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
    youtube.videos().insert(part="snippet,status", body=body, media_body=media).execute()

if __name__ == "__main__":
    content = generate_story()
    
    title = content.split("TITLE:")[1].split("DESCRIPTION:")[0].strip() if "TITLE:" in content else "पौराणिक कथा"
    desc = content.split("DESCRIPTION:")[1].split("TAGS:")[0].strip() if "DESCRIPTION:" in content else "भक्ति कथा"
    tags = content.split("TAGS:")[1].split("STORY:")[0].strip() if "TAGS:" in content else "bhakti,kahani"
    story = content.split("STORY:")[1].strip() if "STORY:" in content else content

    # 1. वॉइसओवर बनाना
    asyncio.run(make_voiceover(story, "audio.mp3"))
    
    # 2. इमेज और BGM Pixabay API से लाना
    img = get_pixabay_image()
    bgm = get_pixabay_bgm()
    
    # 3. वीडियो रेंडर करना
    render_video(img, "audio.mp3", bgm, "final_video.mp4")
    
    # 4. यूट्यूब पर अपलोड करना
    upload_youtube("final_video.mp4", title, desc, tags)
    print("Video Created and Uploaded Successfully!")
