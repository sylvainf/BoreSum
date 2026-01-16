# BoreResum - an LLM based audio summary tool

A web application that transcribes meeting recordings and generates structured minutes using Large Language Models (LLMs).

**Default Provider:** This project is pre-configured to use **Albert**, the public AI inference platform provided by **DINUM (Etalab)** for the French administration.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-Async-green) ![Provider](https://img.shields.io/badge/Provider-DINUM%20%2F%20Etalab-blueviolet) ![Docker](https://img.shields.io/badge/Docker-Ready-blue)

## 📋 Overview

This tool automates the tedious process of writing meeting minutes. It accepts audio files (or raw text), processes them through a speech-to-text engine, and uses generative AI to create a professional summary.

This project uses a **fully asynchronous architecture** with **WebSockets** and **Background Tasks**, ensuring that long audio files (30min+) are processed without browser timeouts or server blocking.

## ✨ Key Features

-   **Start-of-the-Art Infrastructure:** By default, runs on the **DINUM Etalab** inference platform, ensuring data sovereignty and high performance for French public agents.
-   **Audio Transcription:** Uses **Whisper Large v3** for high-accuracy speech-to-text (multilingual support).
-   **Intelligent Summarization:** Generates structured minutes using **Mistral Small** or **GPT-OSS 120B**.
-   **Real-Time Feedback:** **WebSockets** provide live logs to the user (e.g., "Compressing audio...", "Transcribing...", "Generating summary...").
-   **Non-Blocking Core:** Heavy I/O tasks (FFmpeg compression, API calls) are handled asynchronously, preventing the server from freezing.
-   **Multi-Provider Support:** While optimized for Etalab, the system uses the standard OpenAI API format and can be configured to use OpenAI, Groq, or LocalAI.

## 🛠️ How It Works

1.  **Upload:** The user uploads an audio file via the web interface.
2.  **Handshake:** The server accepts the file, starts a background task, and responds immediately to the HTTP request to avoid timeout.
3.  **WebSocket:** The browser connects to a WebSocket channel to listen for progress updates.
4.  **Processing:**
    -   **Compression:** If the file is large, `ffmpeg` resample and compresses it (running in a non-blocking thread).
    -   **Transcription:** The API sends the audio to the Whisper model asynchronously.
    -   **Summarization:** The transcript is sent to the LLM with a specialized system prompt.
5.  **Result:** The final HTML report is pushed through the WebSocket and rendered instantly in the browser.

## ⚙️ Prerequisites

-   **Python 3.10+**
-   **FFmpeg** (Required for audio processing)
-   **API Key:** You need an API Key for **Albert (Etalab)**.
    -   *If you are a French public agent, you can request access via the [DINUM portal](https://albert.api.etalab.gouv.fr).*
    -   *Alternatively, you can use an OpenAI API Key.*

## 🚀 Installation & Local Run


1.  **Install FFmpeg and other requirement (see Dockerfile)**

2.  **Set Environment Variables**
    ```bash
    export ALBERT_API_KEY="your_etalab_api_key"
    ```

5.  **Run the application**
    ```bash
    python app.py
    ```
    Access the interface at `http://localhost:8000`.

## 🐳 Deployment with Docker

A `Dockerfile` is provided for easy deployment.

### Build and run the Image
```bash
docker build -t meeting-summarizer .

docker run -d \
  -p 8000:8000 \
  -e ALBERT_API_KEY="your_actual_api_key" \
  --name my-summarizer \
  meeting-summarizer

```

The application will be available at http://YOUR_SERVER_IP:8000.


