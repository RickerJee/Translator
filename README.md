# 🌐 Realtime Translator

A cross-platform real-time speech translation application built with **React** (frontend) and **FastAPI** (backend). Speak in one language and get an instant translation with text-to-speech playback.

## ✨ Features

| Feature | Details |
|---|---|
| 🎙 Speech-to-Text | [Faster-Whisper](https://github.com/SYSTRAN/faster-whisper) – fast, accurate, runs on CPU or GPU |
| 🤖 Translation | LLM via OpenAI-compatible API (GPT-4o-mini, any local model, etc.) |
| 🔊 Text-to-Speech | [Azure Cognitive Services Neural Voices](https://azure.microsoft.com/en-us/products/ai-services/text-to-speech) |
| ⚡ Real-time | WebSocket streaming – transcription + translation appears as you speak |
| 📱 Cross-platform | Responsive React UI works on iPhone, Android, Windows, macOS, Linux |
| 🌍 18 languages | EN, ZH, ZH-TW, JA, KO, FR, DE, ES, PT, RU, AR, HI, IT, NL, PL, TR, VI, TH |

## 🏗 Architecture

```
Browser (React + WebSocket)
        │
        ▼  ws://host/ws/translate
FastAPI WebSocket endpoint
        │
        ├── Faster-Whisper  → transcript
        ├── OpenAI LLM      → translation
        └── Azure TTS       → MP3 audio (base64 → browser plays)
```

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Node.js 20+
- FFmpeg (`brew install ffmpeg` / `apt install ffmpeg`)

### 1. Backend

```bash
cd backend
cp .env.example .env          # fill in your API keys
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev                    # opens http://localhost:5173
```

### 3. Docker Compose (all-in-one)

```bash
cp backend/.env.example backend/.env   # fill in your keys
docker compose up --build
# → Frontend: http://localhost
# → Backend API: http://localhost:8000
```

## ⚙️ Configuration

Copy `backend/.env.example` to `backend/.env` and set:

```ini
# Whisper model size: tiny | base | small | medium | large-v3
WHISPER_MODEL=base
WHISPER_DEVICE=cpu          # use 'cuda' for GPU acceleration

# OpenAI-compatible LLM
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini

# Azure Text-to-Speech (optional – TTS is disabled if not set)
AZURE_SPEECH_KEY=your_key
AZURE_SPEECH_REGION=eastus
```

### Using a local LLM (e.g. Ollama)

```ini
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_API_KEY=ollama
OPENAI_MODEL=llama3
```

## 📡 WebSocket Protocol

Connect to `ws://host/ws/translate`.

### Client → Server

```jsonc
// Configure session
{ "type": "config", "source_lang": "en", "target_lang": "zh", "enable_tts": true }

// Force-process buffered audio
{ "type": "flush" }

// Audio data – send raw binary Int16 mono 16 kHz PCM chunks
```

### Server → Client

```jsonc
// Intermediate transcript
{ "type": "transcript", "text": "Hello world", "lang": "en" }

// Final translation (+ optional base64 MP3)
{ "type": "translation", "text": "你好世界", "lang": "zh", "source_text": "Hello world",
  "audio": "<base64 mp3>", "audio_format": "mp3" }

// Error
{ "type": "error", "message": "..." }
```

## 📂 Project Structure

```
Translator/
├── backend/
│   ├── main.py          # FastAPI app + WebSocket endpoint
│   ├── transcriber.py   # Faster-Whisper wrapper
│   ├── translator.py    # LLM translation
│   ├── tts.py           # Azure TTS
│   ├── requirements.txt
│   ├── .env.example
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── components/
│   │   │   ├── TranslatorPanel.jsx
│   │   │   └── LanguageSelector.jsx
│   │   └── hooks/
│   │       ├── useTranslatorWS.js
│   │       └── useAudioRecorder.js
│   ├── Dockerfile
│   ├── nginx.conf
│   └── package.json
└── docker-compose.yml
```

## 📜 License

MIT
