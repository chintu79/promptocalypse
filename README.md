# 🔓 Promptocalypse — AI Jailbreak Arena

A real-time web competition platform where participants act as red-teamers to extract hidden secret keys from progressively defended LLM chatbots using prompt injection techniques.

## Tech Stack

| Layer      | Technology                          |
| ---------- | ----------------------------------- |
| Frontend   | React 19 + Vite + TypeScript        |
| Backend    | FastAPI (Python 3.10+) + Uvicorn    |
| Database   | SQLite 3.37+ (WAL mode)            |
| LLM        | Groq Cloud — `llama-3.1-8b-instant` |
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
# Edit .env with your Groq API key (or OLLAMA_ENDPOINTS for local LLM)

# Start backend bound to all network interfaces (allows LAN access)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
# Opens at http://localhost:5173 (and exposes to your LAN IP)
# API requests are automatically proxied to the backend
```

## Running on a Local Network (LAN)

To play the game with multiple people on your local network (e.g. at an office or hackathon):
1. Ensure you run the backend using `--host 0.0.0.0` as shown above.
2. Ensure you run the frontend using `npm run dev` (we already configure `vite --host` in package.json).
3. Find your machine's LAN IP (e.g. `192.168.1.x`).
4. Other devices on the same Wi-Fi can play by visiting `http://<YOUR_LAN_IP>:5173`.

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
