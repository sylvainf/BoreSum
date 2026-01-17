FROM python:3.9-alpine

RUN apk add --no-cache ffmpeg
# Dossier de travail dans le conteneur
WORKDIR /app

# Copie des fichiers de dépendances (si vous en avez un, sinon on installe direct)
# Ici on installe directement pour faire simple
RUN pip install --no-cache-dir fastapi "uvicorn[standard]" python-multipart jinja2 openai requests

# Copie de tout le code dans le conteneur
COPY . /app

# Exposition du port 8000
EXPOSE 8000

# Commande de lancement
CMD ["python", "app.py"]

