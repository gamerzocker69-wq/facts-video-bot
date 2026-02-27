from flask import Flask, request, jsonify, send_file
import os
import uuid
import json
import requests
from gtts import gTTS
import subprocess
from PIL import Image, ImageDraw, ImageFont
import textwrap
import io

app = Flask(__name__)
OUTPUT_DIR = "/tmp/videos"
os.makedirs(OUTPUT_DIR, exist_ok=True)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
UNSPLASH_ACCESS_KEY = os.environ.get("UNSPLASH_ACCESS_KEY", "")


def generate_fact(groq_key):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {groq_key}",
        "Content-Type": "application/json"
    }
    prompt = """Génère un fait insolite détaillé en français pour une vidéo d'environ 1 minute.
Réponds UNIQUEMENT en JSON valide, sans markdown :
{
  "titre": "Titre accrocheur max 8 mots",
  "intro": "Phrase d'accroche courte et percutante de 15 mots.",
  "fait": "Explication détaillée et fascinante du fait en 100-120 mots. Donne des détails, des chiffres, des exemples concrets pour captiver l'audience.",
  "conclusion": "Phrase de conclusion surprenante de 15 mots.",
  "hashtags": "#fait #insolite #culture #science #saviez",
  "mot_cle_image": "mot clé en anglais pour chercher une image liée au sujet (ex: ocean, space, forest, animal)"
}"""

    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.9,
        "max_tokens": 600
    }

    r = requests.post(url, headers=headers, json=payload)
    response_json = r.json()

    if "choices" not in response_json:
        raise Exception(f"Groq error: {response_json}")

    raw = response_json["choices"][0]["message"]["content"]
    raw = raw.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(raw)


def get_unsplash_image(keyword, access_key, width=1080, height=1920):
    url = f"https://api.unsplash.com/photos/random"
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
    img = img.resize((width, height), Image.LANCZOS)
    return img


def add_overlay_text(img, fact_data):
    draw = ImageDraw.Draw(img)
    width, height = img.size

    # Overlay sombre pour lisibilité
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 160))
    img = img.convert("RGBA")
    img = Image.alpha_composite(img, overlay)
    img = img.convert("RGB")
    draw = ImageDraw.Draw(img)

    # Polices
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

    # Titre
    wrapped = textwrap.fill(fact_data["titre"].upper(), width=22)
    for line in wrapped.split("\n"):
        bbox = draw.textbbox((0, 0), line, font=font_title)
        w = bbox[2] - bbox[0]
        draw.text(((width - w) / 2, y), line, font=font_title, fill=(255, 210, 0))
        y += 85

    y += 20
    draw.rectangle([(margin, y), (width - margin, y + 4)], fill=(255, 210, 0))
    y += 30

    # Intro
    wrapped = textwrap.fill(fact_data["intro"], width=32)
    for line in wrapped.split("\n"):
        bbox = draw.textbbox((0, 0), line, font=font_body)
        w = bbox[2] - bbox[0]
        draw.text(((width - w) / 2, y), line, font=font_body, fill=(220, 220, 255))
        y += 58

    y += 20

    # Fait principal
    wrapped = textwrap.fill(fact_data["fait"], width=34)
    for line in wrapped.split("\n"):
        bbox = draw.textbbox((0, 0), line, font=font_small)
        w = bbox[2] - bbox[0]
        draw.text(((width - w) / 2, y), line, font=font_small, fill=(255, 255, 255))
        y += 50

    # Hashtags en bas
    bbox = draw.textbbox((0, 0), fact_data["hashtags"], font=font_small)
    w = bbox[2] - bbox[0]
    draw.text(((width - w) / 2, height - 120), fact_data["hashtags"], font=font_small, fill=(150, 180, 255))

    return img


def create_video_from_audio_image(image_path, audio_path, output_path):
    cmd = [
        "ffmpeg", "-y",
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

        # 1. Générer le fait
        fact = generate_fact(GROQ_API_KEY)

        # 2. Voix off (intro + fait + conclusion)
        texte_audio = f"{fact['intro']} {fact['fait']} {fact['conclusion']}"
        audio_path = os.path.join(OUTPUT_DIR, f"audio_{video_id}.mp3")
        tts = gTTS(text=texte_audio, lang="fr", slow=False)
        tts.save(audio_path)

        # 3. Image Unsplash
        keyword = fact.get("mot_cle_image", "nature")
        img = get_unsplash_image(keyword, UNSPLASH_ACCESS_KEY)

        if img is None:
            img = Image.new("RGB", (1080, 1920), (15, 15, 30))

        # 4. Ajouter le texte sur l'image
        img = add_overlay_text(img, fact)
        image_path = os.path.join(OUTPUT_DIR, f"image_{video_id}.jpg")
        img.save(image_path, "JPEG", quality=90)

        # 5. Assembler la vidéo
        video_path = os.path.join(OUTPUT_DIR, f"video_{video_id}.mp4")
        create_video_from_audio_image(image_path, audio_path, video_path)

        return jsonify({
            "success": True,
            "fact": fact,
            "video_url": f"{request.host_url}download/{video_id}",
            "video_id": video_id
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/download/<video_id>", methods=["GET"])
def download(video_id):
    # Cherche d'abord la vidéo, sinon l'audio
    for ext in ["mp4", "mp3"]:
        path = os.path.join(OUTPUT_DIR, f"video_{video_id}.{ext}" if ext == "mp4" else f"audio_{video_id}.{ext}")
        if os.path.exists(path):
            mime = "video/mp4" if ext == "mp4" else "audio/mpeg"
            return send_file(path, mimetype=mime)

    return jsonify({"error": "Fichier non trouve"}), 404


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)²
