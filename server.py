from flask import Flask, request, jsonify, send_file
import os
import uuid
import json
import requests
from gtts import gTTS

app = Flask(__name__)
OUTPUT_DIR = "/tmp/videos"
os.makedirs(OUTPUT_DIR, exist_ok=True)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")


@app.route("/", methods=["GET"])
def index():
    return jsonify({"status": "ok"})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "message": "Serveur operationnel"})


@app.route("/generate-auto", methods=["POST"])
def generate_auto():
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-8b:generateContent?key={GEMINI_API_KEY}"
        prompt = """Génère un fait insolite en français. Réponds UNIQUEMENT en JSON :
{"titre": "Titre max 8 mots", "fait": "Description 50-60 mots.", "hashtags": "#fait #insolite #culture"}"""

        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        r = requests.post(url, json=payload)
        response_json = r.json()

        if "candidates" not in response_json:
            return jsonify({"error": "Gemini error", "details": response_json}), 500

        raw = response_json["candidates"][0]["content"]["parts"][0]["text"]
        raw = raw.strip().replace("```json", "").replace("```", "").strip()
        fact = json.loads(raw)

        video_id = str(uuid.uuid4())[:8]
        audio_path = os.path.join(OUTPUT_DIR, f"audio_{video_id}.mp3")
        tts = gTTS(text=fact["fait"], lang="fr", slow=False)
        tts.save(audio_path)

        return jsonify({
            "success": True,
            "fact": fact,
            "audio_url": f"{request.host_url}download/{video_id}",
            "video_id": video_id
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/download/<video_id>", methods=["GET"])
def download(video_id):
    path = os.path.join(OUTPUT_DIR, f"audio_{video_id}.mp3")
    if not os.path.exists(path):
        return jsonify({"error": "Fichier non trouve"}), 404
    return send_file(path, mimetype="audio/mpeg")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
