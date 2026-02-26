"""
🎬 Générateur de vidéos automatiques - Facts Insolites
-----------------------------------------------------
Dépendances : pip install moviepy pillow requests gTTS
Hébergeable gratuitement sur Render.com ou Railway.app
"""

import os
import json
import textwrap
import requests
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import ImageClip, AudioFileClip, CompositeVideoClip, concatenate_videoclips
from gtts import gTTS
import tempfile


# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920  # Format vertical TikTok / Shorts
FPS = 30
BG_COLOR = (15, 15, 30)        # Fond sombre
ACCENT_COLOR = (255, 200, 0)   # Jaune doré pour le titre
TEXT_COLOR = (255, 255, 255)   # Blanc pour le corps


# ─────────────────────────────────────────────
# ÉTAPE 1 : Générer le contenu avec Gemini API
# ─────────────────────────────────────────────
def generate_fact_with_gemini(api_key: str) -> dict:
    """
    Appelle l'API Gemini (gratuite) pour générer un fait insolite.
    Obtenez votre clé gratuite sur : https://aistudio.google.com/apikey
    """
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    
    prompt = """Génère un fait insolite surprenant en français.
Réponds UNIQUEMENT avec un JSON valide, sans markdown, sans commentaire.
Format exact :
{
  "titre": "Titre accrocheur max 8 mots",
  "fait": "Description du fait insolite en 50-60 mots maximum.",
  "hashtags": "#fait #insolite #science #culture #saviez"
}"""

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.9, "maxOutputTokens": 300}
    }

    response = requests.post(url, json=payload)
    response.raise_for_status()
    
    raw = response.json()["candidates"][0]["content"]["parts"][0]["text"]
    # Nettoyer si markdown présent
    raw = raw.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(raw)


# ─────────────────────────────────────────────
# ÉTAPE 2 : Générer la voix off (gTTS - gratuit)
# ─────────────────────────────────────────────
def generate_voiceover(text: str, output_path: str, lang: str = "fr"):
    """
    Utilise gTTS (Google Text-to-Speech) - 100% gratuit, aucune clé requise.
    """
    tts = gTTS(text=text, lang=lang, slow=False)
    tts.save(output_path)
    print(f"✅ Voix off générée : {output_path}")


# ─────────────────────────────────────────────
# ÉTAPE 3 : Créer le visuel de la vidéo
# ─────────────────────────────────────────────
def create_frame(titre: str, fait: str, hashtags: str) -> Image.Image:
    """
    Crée une image 1080x1920 avec titre, texte et hashtags.
    """
    img = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # ── Dégradé subtil en haut et en bas
    for y in range(300):
        alpha = int(60 * (1 - y / 300))
        draw.line([(0, y), (VIDEO_WIDTH, y)], fill=(50, 50, 100))
    
    # ── Chargement des polices (utilise la police par défaut si non trouvée)
    try:
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 72)
        font_body = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 48)
        font_hash = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 38)
    except:
        font_title = ImageFont.load_default()
        font_body = ImageFont.load_default()
        font_hash = ImageFont.load_default()

    margin = 80
    y_pos = 200

    # ── Ligne décorative
    draw.rectangle([(margin, y_pos), (VIDEO_WIDTH - margin, y_pos + 6)], fill=ACCENT_COLOR)
    y_pos += 50

    # ── Titre (retour à la ligne automatique)
    wrapped_title = textwrap.fill(titre.upper(), width=20)
    for line in wrapped_title.split("\n"):
        bbox = draw.textbbox((0, 0), line, font=font_title)
        w = bbox[2] - bbox[0]
        draw.text(((VIDEO_WIDTH - w) / 2, y_pos), line, font=font_title, fill=ACCENT_COLOR)
        y_pos += 90

    y_pos += 40

    # ── Ligne décorative
    draw.rectangle([(margin, y_pos), (VIDEO_WIDTH - margin, y_pos + 4)], fill=(80, 80, 120))
    y_pos += 60

    # ── Corps du texte
    wrapped_body = textwrap.fill(fait, width=30)
    for line in wrapped_body.split("\n"):
        bbox = draw.textbbox((0, 0), line, font=font_body)
        w = bbox[2] - bbox[0]
        draw.text(((VIDEO_WIDTH - w) / 2, y_pos), line, font=font_body, fill=TEXT_COLOR)
        y_pos += 65

    # ── Hashtags en bas
    hashtag_y = VIDEO_HEIGHT - 150
    bbox = draw.textbbox((0, 0), hashtags, font=font_hash)
    w = bbox[2] - bbox[0]
    draw.text(((VIDEO_WIDTH - w) / 2, hashtag_y), hashtags, font=font_hash, fill=(150, 150, 200))

    return img


# ─────────────────────────────────────────────
# ÉTAPE 4 : Assembler la vidéo finale
# ─────────────────────────────────────────────
def create_video(fact_data: dict, output_path: str = "output_video.mp4"):
    """
    Assemble image + voix off en vidéo MP4 prête pour TikTok/Shorts.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        # Générer l'image
        frame = create_frame(fact_data["titre"], fact_data["fait"], fact_data["hashtags"])
        img_path = os.path.join(tmpdir, "frame.png")
        frame.save(img_path)
        print(f"✅ Image créée")

        # Générer la voix off
        audio_path = os.path.join(tmpdir, "voix.mp3")
        generate_voiceover(fact_data["fait"], audio_path)

        # Charger l'audio pour connaître sa durée
        audio_clip = AudioFileClip(audio_path)
        duration = audio_clip.duration + 1.5  # +1.5s de marge

        # Créer le clip vidéo
        video_clip = ImageClip(img_path, duration=duration)
        video_clip = video_clip.set_audio(audio_clip)
        video_clip = video_clip.set_fps(FPS)

        # Exporter
        video_clip.write_videofile(
            output_path,
            fps=FPS,
            codec="libx264",
            audio_codec="aac",
            verbose=False,
            logger=None
        )

    print(f"\n🎬 Vidéo générée avec succès : {output_path}")
    return output_path


# ─────────────────────────────────────────────
# POINT D'ENTRÉE
# ─────────────────────────────────────────────
if __name__ == "__main__":
    # 🔑 Remplacez par votre clé Gemini (gratuite sur aistudio.google.com)
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "VOTRE_CLE_GEMINI_ICI")

    print("📡 Génération du fait insolite via Gemini...")
    fact = generate_fact_with_gemini(GEMINI_API_KEY)
    
    print(f"\n📝 Fait généré :")
    print(f"   Titre    : {fact['titre']}")
    print(f"   Fait     : {fact['fait']}")
    print(f"   Hashtags : {fact['hashtags']}")

    print("\n🎬 Assemblage de la vidéo...")
    create_video(fact, output_path="video_fact_insolite.mp4")
