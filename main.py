import os
import asyncio
import random
import requests
from google.generativeai import configure, GenerativeModel
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from moviepy.editor import ImageClip, AudioFileClip, TextClip, CompositeVideoClip

# GitHub Secrets से API Keys पढ़ना
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
PIXABAY_KEY = os.environ.get("PIXABAY_API_KEY")
YT_CLIENT_ID = os.environ.get("YOUTUBE_CLIENT_ID")
YT_CLIENT_SECRET = os.environ.get("YOUTUBE_CLIENT_SECRET")
YT_REFRESH_TOKEN = os.environ.get("YOUTUBE_REFRESH_TOKEN")

# Gemini AI कॉन्फ़िगरेशन
configure(api_key=GEMINI_KEY)

# 1. Gemini AI से कहानी और मेटाडेटा बनाना (त्योहारों और ट्रेंड्स के हिसाब से)
def generate_story():
    model = GenerativeModel("gemini-1.5-flash")
    
    prompt = (
        "हिंदी में एक बहुत ही सुंदर, प्रेरणादायक हिंदू पौराणिक/धार्मिक कथा या आने वाले बड़े त्योहार (जैसे दिवाली, छठ पूजा) या ग्रहण पर एक लंबी कथा लिखें जो YouTube दर्शकों को बांधे रखे।\n"
        "फ़ॉर्मेट ऐसा रखें:\n"
        "TITLE: <शीर्षक>\n"
        "DESCRIPTION: <विवरण>\n"
        "TAGS: <टैग्स>\n"
        "STORY: <कथा का मुख्य पाठ>"
    )
    
    response = model.generate_content(prompt)
    print("Gemini Response generated successfully!")
    return response.text

# 2. वॉयसओवर जनरेटर (Edge TTS)
async def make_voiceover(text, output_path="audio.mp3"):
    import edge_tts
    voice = "hi-IN-MadhurNeural"
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)
    print("Voiceover generated successfully!")

# 3. पिक्साबे से इमेज लाना
def get_pixabay_image(query="lord krishna temple"):
    try:
        url = f"https://pixabay.com/api/?key={PIXABAY_KEY}&q={requests.utils.quote(query)}&image_type=photo&safesearch=true"
        response = requests.get(url).json()
        if response.get("hits"):
            image_url = response["hits"][0]["largeImageURL"]
            img_data = requests.get(image_url).content
            with open("bg.jpg", "wb") as f:
                f.write(img_data)
            return "bg.jpg"
    except Exception as e:
        print("Image Fetch Error:", e)
    return None

# 4. बैकग्राउंड म्यूजिक लाना
def get_free_music(query="relaxing"):
    fallback_bgm = "https://cdn.pixabay.com/download/audio/2022/05/27/audio_1808fbf07a.mp3?filename=meditation-spiritual-relaxing-flute-112255.mp3"
    try:
        audio_data = requests.get(fallback_bgm).content
        with open("bgm.mp3", "wb") as f:
            f.write(audio_data)
        return "bgm.mp3"
    except Exception as e:
        print("Music Error:", e)
    return None

# 5. वीडियो रेंडरिंग (MoviePy)
def render_video(image_path, audio_path, bgm_path, output_path="final_video.mp4"):
    voice_audio = AudioFileClip(audio_path)
    video_duration = voice_audio.duration

    img_clip = ImageClip(image_path).set_duration(video_duration)
    clips = [img_clip]

    # लोगो जोड़ना (Logo.jpg यदि हो)
    if os.path.exists("logo.jpg"):
        logo = (ImageClip("logo.jpg")
                .set_duration(video_duration)
                .resize(height=100)
                .set_position(("left", "bottom")))
        clips.append(logo)

    # वॉटरमार्क टेक्स्ट (font.ttf यदि हो)
    if os.path.exists("font.ttf"):
        watermark = TextClip("Spiritual Bhakti", fontsize=24, color="white", font="font.ttf")\
                    .set_duration(video_duration)\
                    .set_position(("left", "bottom"))
        clips.append(watermark)

    final_video = CompositeVideoClip(clips)

    # वॉयसओवर और BGM मिक्स करना
    if bgm_path and os.path.exists(bgm_path):
        bgm = AudioFileClip(bgm_path).volumex(0.10).set_duration(video_duration)
        final_audio = CompositeAudioClip([voice_audio, bgm])
    else:
        final_audio = voice_audio

    final_video = final_video.set_audio(final_audio)
    final_video.write_videofile(output_path, fps=24, codec="libx264", audio_codec="aac")
    print("Video rendered successfully!")

# 6. यूट्यूब ऑटो अपलोड
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
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = request.execute()
    print("Video uploaded to YouTube successfully! ID:", response.get("id"))

if __name__ == "__main__":
    print("Starting Daily Bhakti Video Automation...")
    
    # 1. Gemini से कहानी और डेटा लेना
    content = generate_story()
    
    try:
        title = content.split("TITLE:")[1].split("DESCRIPTION:")[0].strip()
        desc = content.split("DESCRIPTION:")[1].split("TAGS:")[0].strip()
        tags = content.split("TAGS:")[1].split("STORY:")[0].strip()
        story = content.split("STORY:")[1].strip()
    except Exception:
        title = "Bhagwan ki Sundar Katha"
        desc = "Daily spiritual and motivational story."
        tags = "bhakti, katha, krishna"
        story = content

    # 2. वॉयसओवर बनाना
    asyncio.run(make_voiceover(story, "audio.mp3"))

    # 3. इमेज और म्यूजिक डाउनलोड करना
    img = get_pixabay_image("lord krishna divine peaceful")
    bgm = get_free_music()

    # 4. वीडियो रेंडर करना
    if img:
        render_video(img, "audio.mp3", bgm, "final_video.mp4")
        
        # 5. यूट्यूब पर अपलोड करना
        upload_youtube("final_video.mp4", title, desc, tags)
    else:
        print("Error: Background image could not be fetched.")
        
