"""
🌐 Serveur API Flask - Génération de vidéos
-------------------------------------------
Ce serveur reçoit les données de Make.com et retourne une vidéo MP4.
À héberger gratuitement sur Render.com
"""

import os
import uuid
import threading
from flask import Flask, request, jsonify, send_file
from generate_video import generate_fact_with_gemini, create_video

app = Flask(__name__)

# Dossier pour stocker temporairement les vidéos
OUTPUT_DIR = "/tmp/videos"
os.makedirs(OUTPUT_DIR, exist_ok=True)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")


@app.route("/health", methods=["GET"])
def health():
    """Endpoint de vérification - Render l'utilise pour savoir si le service est actif."""
    return jsonify({"status": "ok", "message": "Serveur vidéo opérationnel ✅"})


@app.route("/generate", methods=["POST"])
def generate():
    """
    Reçoit un fact_data et génère une vidéo MP4.
    Body JSON attendu :
    {
        "titre": "...",
        "fait": "...",
        "hashtags": "..."
    }
    """
    data = request.get_json()
    
    if not data:
        return jsonify({"error": "Body JSON manquant"}), 400

    required = ["titre", "fait", "hashtags"]
    for field in required:
        if field not in data:
            return jsonify({"error": f"Champ manquant : {field}"}), 400

    # Générer un nom de fichier unique
    video_id = str(uuid.uuid4())[:8]
    output_path = os.path.join(OUTPUT_DIR, f"video_{video_id}.mp4")

    try:
        create_video(data, output_path=output_path)
        
        # Retourner l'URL de téléchargement
        base_url = request.host_url.rstrip("/")
        video_url = f"{base_url}/download/{video_id}"
        
        return jsonify({
            "success": True,
            "video_url": video_url,
            "video_id": video_id,
            "titre": data["titre"]
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/generate-auto", methods=["POST"])
def generate_auto():
    """
    Version tout-en-un : génère le fact ET la vidéo.
    Utile si vous appelez depuis Make sans passer par le module Gemini séparé.
    Ne nécessite aucun body JSON.
    """
    if not GEMINI_API_KEY:
        return jsonify({"error": "GEMINI_API_KEY non configurée"}), 500

    try:
        fact_data = generate_fact_with_gemini(GEMINI_API_KEY)
        
        video_id = str(uuid.uuid4())[:8]
        output_path = os.path.join(OUTPUT_DIR, f"video_{video_id}.mp4")
        
        create_video(fact_data, output_path=output_path)
        
        base_url = request.host_url.rstrip("/")
        video_url = f"{base_url}/download/{video_id}"
        
        return jsonify({
            "success": True,
            "video_url": video_url,
            "video_id": video_id,
            "fact": fact_data
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/download/<video_id>", methods=["GET"])
def download(video_id):
    """Télécharge la vidéo générée."""
    video_path = os.path.join(OUTPUT_DIR, f"video_{video_id}.mp4")
    
    if not os.path.exists(video_path):
        return jsonify({"error": "Vidéo non trouvée ou expirée"}), 404
    
    return send_file(
        video_path,
        mimetype="video/mp4",
        as_attachment=True,
        download_name=f"fact_insolite_{video_id}.mp4"
    )


# Nettoyage automatique des vieilles vidéos (évite de saturer /tmp)
def cleanup_old_videos():
    import time
    while True:
        time.sleep(3600)  # toutes les heures
        now = time.time()
        for f in os.listdir(OUTPUT_DIR):
            fpath = os.path.join(OUTPUT_DIR, f)
            if os.path.isfile(fpath) and now - os.path.getmtime(fpath) > 7200:
                os.remove(fpath)

threading.Thread(target=cleanup_old_videos, daemon=True).start()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
