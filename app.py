import os
import shutil
import uuid
import uvicorn
import asyncio
from fastapi import FastAPI, UploadFile, File, Form, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

import audio2reu

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Gestionnaire de connexions WebSocket
class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        self.active_connections[client_id] = websocket

    def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]

    async def send_log(self, message: str, client_id: str):
        if client_id in self.active_connections:
            await self.active_connections[client_id].send_text(message)

manager = ConnectionManager()

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """Affiche la page d'accueil avec un ID unique et le prompt par défaut"""
    return templates.TemplateResponse("index.html", {
        "request": request, 
        "uid": str(uuid.uuid4()),
        "default_prompt": audio2reu.DEFAULT_SUMMARY_PROMPT
    })

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    """Gère la connexion WebSocket pour les logs temps réel"""
    await manager.connect(websocket, client_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(client_id)

@app.post("/process", response_class=HTMLResponse)
async def process_data(
    request: Request,
    client_id: str = Form(...),
    inputType: str = Form(...), # 'audio' ou 'text'
    file: UploadFile = File(None),
    rawText: str = Form(None),
    language: str = Form("fr"),
    model: str = Form("mistral"),
    customPrompt: str = Form(None),
    whisperPrompt: str = Form(None) # Nouveau champ
):
    """Endpoint unique pour traiter Audio OU Texte avec logs WebSocket"""
    
    # Adaptateur WebSocket pour audio2reu
    class WebSocketAdapter:
        async def send_text(self, msg: str):
            await manager.send_log(msg, client_id)
            # Pause pour laisser l'event loop respirer et envoyer le message
            await asyncio.sleep(0.01)

    ws_adapter = WebSocketAdapter()
    
    transcript = ""
    
    try:
        # Étape 1 : Obtenir le texte
        if inputType == "audio":
            if not file or not file.filename:
                return "Erreur: Aucun fichier audio fourni."
            
            ext = os.path.splitext(file.filename)[1]
            #temp_filename = f"temp_{uuid.uuid4()}{ext}"
            temp_filename = os.path.join("/tmp", f"temp_{uuid.uuid4()}{ext}")

            
            with open(temp_filename, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            try:
                transcript = await audio2reu.transcribe_audio(
                    temp_filename, 
                    language=language, 
                    websocket=ws_adapter,
                    whisper_prompt=whisperPrompt
                )
            finally:
                if os.path.exists(temp_filename):
                    os.remove(temp_filename)
        else:
            # Mode Texte Direct
            if not rawText:
                return "Erreur: Aucun texte fourni."
            transcript = rawText
            await ws_adapter.send_text("📝 Texte brut reçu directement.")

        # Étape 2 : Résumé
        summary = await audio2reu.generate_compte_rendu(
            transcript, 
            model_key=model, 
            custom_prompt=customPrompt, 
            websocket=ws_adapter
        )
        
        await ws_adapter.send_text("🚀 Traitement terminé ! Affichage du résultat...")

        return templates.TemplateResponse("result.html", {
            "request": request,
            "filename": file.filename if file else "Texte brut",
            "transcript": transcript,
            "summary": summary
        })

    except Exception as e:
        error_msg = f"❌ ERREUR SERVEUR : {str(e)}"
        print(error_msg)
        await ws_adapter.send_text(error_msg)
        return f"Une erreur est survenue : {str(e)}"

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

