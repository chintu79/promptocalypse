# 🔓 Promptocalypse — AI Jailbreak Arena

A real-time web competition platform where participants act as red-teamers to extract hidden secret keys from progressively defended LLM chatbots using prompt injection techniques.

## Tech Stack

| Layer      | Technology                          |
| ---------- | ----------------------------------- |
| Frontend   | React 19 + Vite + TypeScript        |
| Backend    | FastAPI (Python 3.10+) + Uvicorn    |
| Database   | SQLite 3.37+ (WAL mode)            |
| LLM        | Groq Cloud (e.g. `qwen/qwen3.8-27b`) or OpenRouter (e.g. `meta-llama/llama-3.1-8b-instruct`) |
| Tunnel     | Cloudflare Tunnel (optional)        |

## Project Structure

```
promptocalypse/
├── backend/                 # FastAPI backend
│   ├── app/
│   │   ├── main.py          # App entry point
│   │   ├── config.py        # Settings & env vars
│   │   ├── database.py      # SQLite setup & migrations
│   │   ├── models.py        # Pydantic request/response models
│   │   └── routes/
│   │       ├── auth.py      # Registration & session
│   │       ├── chat.py      # Prompt execution pipeline
│   │       └── game.py      # Key submission & leaderboard
│   ├── requirements.txt
│   └── .env.example
├── frontend/                # React SPA
│   ├── src/
│   │   ├── api/client.ts    # API client functions
│   │   ├── components/      # UI components
│   │   ├── types/index.ts   # TypeScript interfaces
│   │   ├── App.tsx          # Root component
│   │   └── main.tsx         # Entry point
│   ├── package.json
│   └── vite.config.ts
├── docs/                    # Specification documents
│   ├── PRD.md
│   ├── FEATURES.md
│   ├── SAD.md
│   ├── TECH-SPEC.md
│   └── UI-UX.md
└── README.md
```

## Quick Start

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your Groq or OpenRouter API key
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
# Opens at http://localhost:3000
# API requests proxy to http://localhost:8000
```

## Game Design

Three levels of progressively defended LLM chatbots:

| Level | Bot                  | Defense                  | Key                        |
| ----- | -------------------- | ------------------------ | -------------------------- |
| 1     | The Trusting Clerk   | System prompt only       | `FLAG{alpha_912}`          |
| 2     | The Strict Gatekeeper| Ingress keyword filter   | `FLAG{gatekeeper_bypassed}`|
| 3     | The Cryptic Sentry   | Egress leak filter       | `FLAG{cipher_master_2026}` |

## API Endpoints

| Method | Endpoint             | Description                    |
| ------ | -------------------- | ------------------------------ |
| POST   | `/api/auth/register` | Register or recover session    |
| POST   | `/api/chat`          | Send prompt to LLM             |
| POST   | `/api/submit-key`    | Submit a flag for verification |
| GET    | `/api/leaderboard`   | Fetch top 50 rankings          |
| GET    | `/api/user/state`    | Get current user state         |
| GET    | `/api/health`        | Health & readiness diagnostic probe (DB + LLM provider) |
| GET    | `/health`            | Health check                   |

## Contributing

See the task assignments below and pick your area. All endpoints return `TODO` stubs — implement the business logic following the spec docs in `docs/`.

## License

MIT
