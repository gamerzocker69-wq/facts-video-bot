from flask import Flask, request, jsonify, send_file
import os
import uuid
import json
import requests
from gtts import gTTS
import subprocess
import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont
import textwrap
import io

app = Flask(__name__)
OUTPUT_DIR = "/tmp/videos"
os.makedirs(OUTPUT_DIR, exist_ok=True)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
UNSPLASH_ACCESS_KEY = os.environ.get("UNSPLASH_ACCESS_KEY", "")

FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()


def generate_fact(groq_key):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {groq_key}",
        "Content-Type": "application/json"
    }
    prompt = """Genere un fait insolite detaille en francais pour une video d environ 1 minute. Reponds UNIQUEMENT en JSON valide, sans markdown : {"titre": "Titre accrocheur max 8 mots", "intro": "Phrase d accroche courte et percutante de 15 mots.", "fait": "Explication detaillee et fascinante du fait en 100-120 mots avec des details, des chiffres, des exemples concrets.", "conclusion": "Phrase de conclusion surprenante de 15 mots.", "hashtags": "#fait #insolite #culture #science #saviez", "mot_cle_image": "mot cle en anglais pour chercher une image liee au sujet exemple ocean space forest animal"}"""

    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.9,
        "max_tokens": 600
    }

    r = requests.post(url, headers=headers, json=payload)
    response_json = r.json()

    if "choices" not in response_json:
        raise Exception("Groq error: " + str(response_json))

    raw = response_json["choices"][0]["message"]["content"]
    raw = raw.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(raw)


def get_unsplash_image(keyword, access_key):
    url = "https://api.unsplash.com/photos/random"
    params = {
        "query": keyword,
        "orientation": "portrait",
        "client_id": access_key
    }
    r = requests.get(url, params=params)
    data = r.json()

    if "urls" not in data:
        return None

    img_url = data["urls"]["regular"]
    img_data = requests.get(img_url).content
    img = Image.open(io.BytesIO(img_data)).convert("RGB")
    img = img.resize((1080, 1920), Image.LANCZOS)
    return img


def add_overlay_text(img, fact_data):
    overlay = Image.new("RGBA", (1080, 1920), (0, 0, 0, 160))
    img = img.convert("RGBA")
    img = Image.alpha_composite(img, overlay)
    img = img.convert("RGB")
    draw = ImageDraw.Draw(img)

    try:
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 68)
        font_body = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 42)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 36)
    except:
        font_title = ImageFont.load_default()
        font_body = ImageFont.load_default()
        font_small = ImageFont.load_default()

    margin = 70
    y = 180

    wrapped = textwrap.fill(fact_data["titre"].upper(), width=22)
    for line in wrapped.split("\n"):
        bbox = draw.textbbox((0, 0), line, font=font_title)
        w = bbox[2] - bbox[0]
        draw.text(((1080 - w) / 2, y), line, font=font_title, fill=(255, 210, 0))
        y += 85

    y += 20
    draw.rectangle([(margin, y), (1080 - margin, y + 4)], fill=(255, 210, 0))
    y += 30

    wrapped = textwrap.fill(fact_data["intro"], width=32)
    for line in wrapped.split("\n"):
        bbox = draw.textbbox((0, 0), line, font=font_body)
        w = bbox[2] - bbox[0]
        draw.text(((1080 - w) / 2, y), line, font=font_body, fill=(220, 220, 255))
        y += 58

    y += 20

    wrapped = textwrap.fill(fact_data["fait"], width=34)
    for line in wrapped.split("\n"):
        bbox = draw.textbbox((0, 0), line, font=font_small)
        w = bbox[2] - bbox[0]
        draw.text(((1080 - w) / 2, y), line, font=font_small, fill=(255, 255, 255))
        y += 50

    bbox = draw.textbbox((0, 0), fact_data["hashtags"], font=font_small)
    w = bbox[2] - bbox[0]
    draw.text(((1080 - w) / 2, 1800), fact_data["hashtags"], font=font_small, fill=(150, 180, 255))

    return img


def create_video(image_path, audio_path, output_path):
    cmd = [
        FFMPEG_PATH, "-y",
        "-loop", "1",
        "-i", image_path,
        "-i", audio_path,
        "-c:v", "libx264",
        "-tune", "stillimage",
        "-c:a", "aac",
        "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-shortest",
        output_path
    ]
    subprocess.run(cmd, check=True, capture_output=True)


@app.route("/", methods=["GET"])
def index():
    return jsonify({"status": "ok"})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "message": "Serveur operationnel"})


@app.route("/generate-auto", methods=["POST"])
def generate_auto():
    try:
        video_id = str(uuid.uuid4())[:8]

        fact = generate_fact(GROQ_API_KEY)

        texte_audio = fact["intro"] + " " + fact["fait"] + " " + fact["conclusion"]
        audio_path = os.path.join(OUTPUT_DIR, "audio_" + video_id + ".mp3")
        tts = gTTS(text=texte_audio, lang="fr", slow=False)
        tts.save(audio_path)

        keyword = fact.get("mot_cle_image", "nature")
        img = get_unsplash_image(keyword, UNSPLASH_ACCESS_KEY)

        if img is None:
            img = Image.new("RGB", (1080, 1920), (15, 15, 30))

        img = add_overlay_text(img, fact)
        image_path = os.path.join(OUTPUT_DIR, "image_" + video_id + ".jpg")
        img.save(image_path, "JPEG", quality=90)

        video_path = os.path.join(OUTPUT_DIR, "video_" + video_id + ".mp4")
        create_video(image_path, audio_path, video_path)

        return jsonify({
            "success": True,
            "fact": fact,
            "video_url": request.host_url + "download/" + video_id,
            "video_id": video_id
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/download/<video_id>", methods=["GET"])
def download(video_id):
    video_path = os.path.join(OUTPUT_DIR, "video_" + video_id + ".mp4")
    if os.path.exists(video_path):
        return send_file(video_path, mimetype="video/mp4")

    audio_path = os.path.join(OUTPUT_DIR, "audio_" + video_id + ".mp3")
    if os.path.exists(audio_path):
        return send_file(audio_path, mimetype="audio/mpeg")

    return jsonify({"error": "Fichier non trouve"}), 404


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
