import os
import shutil
import uuid
import uvicorn
import asyncio
import json
from fastapi import FastAPI, UploadFile, File, Form, Request, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
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
    
    async def send_json(self, data: dict, client_id: str):
        if client_id in self.active_connections:
            await self.active_connections[client_id].send_text(json.dumps(data))

manager = ConnectionManager()

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request, 
        "uid": str(uuid.uuid4()),
        "default_prompt": audio2reu.DEFAULT_SUMMARY_PROMPT
    })

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await manager.connect(websocket, client_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(client_id)

# Fonction de traitement de fond (Background Task)
async def process_background_task(
    client_id: str,
    inputType: str,
    temp_filename: str,
    rawText: str,
    language: str,
    model: str,
    customPrompt: str,
    whisperPrompt: str,
    original_filename: str,
    request: Request
):
    # Adaptateur pour que audio2reu puisse envoyer des logs au bon client
    class WebSocketAdapter:
        async def send_text(self, msg: str):
            await manager.send_log(msg, client_id)
            
    ws_adapter = WebSocketAdapter()
    transcript = ""
    
    try:
        # Étape 1 : Obtenir le texte
        if inputType == "audio":
            try:
                transcript = await audio2reu.transcribe_audio(
                    temp_filename, 
                    language=language, 
                    websocket=ws_adapter,
                    whisper_prompt=whisperPrompt
                )
            finally:
                # Nettoyage du fichier temporaire
                if temp_filename and os.path.exists(temp_filename):
                    await asyncio.to_thread(os.remove, temp_filename)
        else:
            transcript = rawText
            await ws_adapter.send_text("📝 Texte brut reçu directement.")

        # Étape 2 : Résumé
        summary = await audio2reu.generate_compte_rendu(
            transcript, 
            model_key=model, 
            custom_prompt=customPrompt, 
            websocket=ws_adapter
        )
        
        await ws_adapter.send_text("🚀 Traitement terminé ! Envoi du résultat...")

        # Génération du HTML final
        result_html = templates.TemplateResponse("result.html", {
            "request": request,
            "filename": original_filename,
            "transcript": transcript,
            "summary": summary
        }).body.decode("utf-8")

        # Envoi du résultat via WebSocket (format JSON spécial)
        await manager.send_json({
            "type": "result",
            "html": result_html
        }, client_id)

    except Exception as e:
        error_msg = f"❌ ERREUR SERVEUR : {str(e)}"
        print(error_msg)
        await ws_adapter.send_text(error_msg)

@app.post("/process")
async def process_data(
    request: Request,
    background_tasks: BackgroundTasks, # Injection des tâches de fond
    client_id: str = Form(...),
    inputType: str = Form(...),
    file: UploadFile = File(None),
    rawText: str = Form(None),
    language: str = Form("fr"),
    model: str = Form("mistral"),
    customPrompt: str = Form(None),
    whisperPrompt: str = Form(None)
):
    """
    Endpoint asynchrone : Sauvegarde le fichier et lance le traitement en arrière-plan.
    Retourne immédiatement 202 Accepted.
    """
    temp_filename = None
    original_filename = "Texte brut"

    if inputType == "audio":
        if not file or not file.filename:
            return JSONResponse({"error": "Aucun fichier fourni"}, status_code=400)
        
        original_filename = file.filename
        ext = os.path.splitext(file.filename)[1]
        temp_filename = os.path.join("/tmp", f"temp_{uuid.uuid4()}{ext}")
        
        # Sauvegarde le fichier (Bloquant ou quasi, mais rapide)
        # On utilise shutil dans un thread pour être sûr
        try:
            with open(temp_filename, "wb") as buffer:
                # Lecture en mémoire pour uploadfile, puis écriture
                # Pour les gros fichiers, copyfileobj est mieux
                await asyncio.to_thread(shutil.copyfileobj, file.file, buffer)
        except Exception as e:
             return JSONResponse({"error": f"Erreur upload: {str(e)}"}, status_code=500)

    elif not rawText:
        return JSONResponse({"error": "Aucun texte fourni"}, status_code=400)

    # Lancement de la tâche de fond
    background_tasks.add_task(
        process_background_task,
        client_id, inputType, temp_filename, rawText, language, 
        model, customPrompt, whisperPrompt, original_filename, request
    )

    return JSONResponse({"status": "processing_started", "message": "Traitement lancé en arrière-plan"})

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

