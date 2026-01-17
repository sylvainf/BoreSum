import os
import sys
import shutil
import subprocess
import asyncio
from openai import AsyncOpenAI  # CHANGEMENT : Import Async

# Configuration API (Albert / OpenAI Standard)
API_KEY = os.getenv("ALBERT_API_KEY")
BASE_URL = "https://albert.api.etalab.gouv.fr/v1"

# CHANGEMENT : Client Asynchrone
client = AsyncOpenAI(api_key=API_KEY, base_url=BASE_URL)

MODELS = {
    "mistral": "mistralai/Mistral-Small-3.2-24B-Instruct-2506",
    "gpt": "openai/gpt-oss-120b"
}

TRANSCRIPTION_MODEL = "openai/whisper-large-v3"

DEFAULT_SUMMARY_PROMPT = """Tu es un assistant expert en rédaction de comptes rendus de réunions professionnelles.
Ton objectif est de produire une synthèse fidèle et structurée basée sur la transcription fournie.
Règles strictes :
1. N'invente AUCUNE information qui ne figure pas explicitement dans le texte.
2. Pas de métadonnées inventées : Ne crée pas de liste de participants, d'horaires, de lieux ou d'échéances si elles ne sont pas clairement dites.
3. Style : Utilise un ton professionnel, neutre et impersonnel ("Il a été discuté...", "Le point sur..."). Évite le style "minutes" avec des tirets pour chaque phrase.
4. Structure : Organise le compte rendu par thèmes ou sujets abordés, avec des titres Markdown clairs.
5. Contenu : Synthétise les échanges en allant à l'essentiel, tout en conservant les décisions prises et les points de blocage éventuels.
6. Format : Produis uniquement le corps du document en Markdown.

Interdictions :
- Ne commence pas par "Voici le compte rendu".
- Ne fais pas de section "Participants" ou "Ordre du jour" si ce n'est pas dans le texte."""

async def log_message(msg, websocket=None):
    """Envoie un log via print et websocket si disponible"""
    print(msg)
    if websocket:
        await websocket.send_text(msg)
        # Petite pause pour laisser l'event loop respirer
        await asyncio.sleep(0.01)

async def check_and_compress_audio(file_path):
    """Vérifie taille > 15Mo et compresse si besoin via ffmpeg (Non-bloquant)."""
    SIZE_LIMIT_MB = 15
    if not os.path.exists(file_path): return file_path, False
    
    # On délègue l'I/O bloquant à un thread pour ne pas bloquer FastAPI
    file_size_mb = await asyncio.to_thread(os.path.getsize, file_path)
    file_size_mb = file_size_mb / (1024 * 1024)

    if file_size_mb <= SIZE_LIMIT_MB:
        return file_path, False

    print(f"Fichier lourd ({file_size_mb:.2f} Mo). Compression...")
    if not shutil.which("ffmpeg"):
        return file_path, False

    base, _ = os.path.splitext(file_path)
    output_path = f"{base}.small.mp3"
    
    def run_ffmpeg():
        cmd = ["ffmpeg", "-y", "-i", file_path, "-acodec", "libmp3lame", "-b:a", "32k", "-ac", "1", "-ar", "32000", output_path]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # CHANGEMENT CRITIQUE : Exécution dans un thread séparé
    await asyncio.to_thread(run_ffmpeg)
    
    return output_path, True

async def transcribe_audio(file_path, language="fr", websocket=None, whisper_prompt=None):
    """Transcrit l'audio via API (Asynchrone)."""
    await log_message(f"🎙️ Début de la transcription (Langue: {language})...", websocket)
    
    # Appel asynchrone à la compression
    file_to_send, is_temp = await check_and_compress_audio(file_path)
    
    if is_temp: await log_message("🗜️ Compression audio terminée.", websocket)

    try:
        # Ouverture du fichier dans un contexte thread-safe ou lecture directe
        # AsyncOpenAI gère bien les fichiers ouverts, mais l'ouverture elle-même est synchrone (rapide)
        with open(file_to_send, "rb") as audio_file:
            args = {
                "model": TRANSCRIPTION_MODEL,
                "file": audio_file,
                "language": language, 
                "response_format": "text"
            }
            
            if whisper_prompt and whisper_prompt.strip():
                short_prompt = whisper_prompt[:1000] 
                args["prompt"] = short_prompt
                await log_message(f"💡 Whisper Prompt utilisé : {short_prompt[:50]}...", websocket)

            # CHANGEMENT : Await sur l'appel API
            transcript = await client.audio.transcriptions.create(**args)
            
        await log_message("✅ Transcription terminée.", websocket)
        return transcript
    finally:
        if is_temp and os.path.exists(file_to_send):
            # Suppression asynchrone (via thread)
            await asyncio.to_thread(os.remove, file_to_send)

async def generate_compte_rendu(text, model_key="mistral", custom_prompt=None, websocket=None):
    """Génère le résumé avec le modèle et prompt choisis (Asynchrone)."""
    selected_model = MODELS.get(model_key, MODELS["mistral"])
    await log_message(f"🧠 Génération du résumé avec {selected_model}...", websocket)

    system_instruction = custom_prompt if custom_prompt and custom_prompt.strip() else DEFAULT_SUMMARY_PROMPT

    try:
        # CHANGEMENT : Await sur l'appel API
        response = await client.chat.completions.create(
            model=selected_model,
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": f"Voici le texte à synthétiser :\n\n{text}"}
            ],
            temperature=0.2,
            max_tokens=4096
        )
        return response.choices[0].message.content
    except Exception as e:
        await log_message(f"❌ Erreur IA : {e}", websocket)
        raise e

