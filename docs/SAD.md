System Architecture Document (SAD)

System Name: AI Jailbreak Arena
Document Version: 1.0
Target Execution Environment: Central Host (Laptop/VPS) + Groq LPUs (llama-3.1-8b-instant)

1. Architectural Overview & Design Principles

The AI Jailbreak Arena architecture provides a low-latency, tamper-resistant environment for ~100 concurrent participants competing in prompt injection challenges.

┌────────────────────────────────────────────────────────────────────────┐
│                            PARTICIPANT TIER                            │
│                                                                        │
│   [ React / Vite Single Page App (Browser-Based Arena Client) ]        │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ HTTPS / JSON API
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                             EDGE / INGRESS                             │
│                                                                        │
│   [ Cloudflare Tunnel / Local Network Listener (:8000) ]               │
│   - TLS Termination & Public Expiry                                    │
│   - Layer 7 Anti-DDoS & IP Isolation                                   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                          APPLICATION TIER                              │
│                                                                        │
│   [ FastAPI Core Gateway (Uvicorn 4-Worker Cluster) ]                  │
│   ├── Shared SQLite Sliding-Window Rate Limiter (3s Cooldown)          │
│   ├── Level 2 Ingress Security Filter (Regex Word Denylist)           │
│   ├── Level Context Assembler (Stateful Injections)                   │
│   ├── Outbound Inference Client (Async HTTP Pool)                      │
│   ├── Level 3 Egress Sanitizer (Leak Blocker & Redactor)               │
│   └── Telemetry & Efficiency Scoring Engine                            │
└───────────────────────┬────────────────────────┬───────────────────────┘
                        │                        │
       Async SQLite I/O │                        │ HTTPS Keep-Alive Pool
                        ▼                        ▼
┌──────────────────────────────┐  ┌──────────────────────────────────────┐
│       PERSISTENCE TIER       │  │        EXTERNAL INFERENCE TIER        │
│                              │  │                                      │
│  [ Embedded SQLite3 DB ]     │  │  [ Groq LPU Cloud Platform ]         │
│  - WAL Mode Enabled          │  │  - Model: llama-3.1-8b-instant       │
│  - Users, Logs, Submissions  │  │  - Pay-As-You-Go Quota (1000+ RPM)   │
│  - Real-Time Dynamic Views   │  │  - max_tokens: 150, temp: 0.2        │
└──────────────────────────────┘  └──────────────────────────────────────┘

Core Design Principles

Zero-Trust Client Boundary: No secret flags, system instructions, or validation criteria are exposed in browser bundles, DOM properties, or network payloads.

Stateless Gateway Processing: Challenge state resides strictly in persistent storage, preventing session de-synchronization across concurrent worker processes.

Budget and Egress Protection: All LLM queries enforce static token ceilings (max_tokens: 150) and response timeouts ($8\text{s}$) to prevent resource exhaustion and unbounded billing.

2. Component Specifications

2.1 Presentation Tier (Client Frontend)

Framework: React / Vite Single Page Application (SPA).

Network Strategy: Single-shot REST requests (POST /api/chat, POST /api/submit-key). No persistent WebSockets are required, keeping client overhead minimal.

Client Guardrails:

Client-side UI disables submit actions for 3 seconds post-submission with an animated progress bar.

Inputs are hard-capped at 1,000 characters before network dispatch.

2.2 Ingress & Security Layer

Deployment Options:

Option A (Campus LAN): Direct binding on 0.0.0.0:8000 via local Wi-Fi router subnet (192.168.x.x).

Option B (Remote / Zero-Configuration Port Forwarding): cloudflared tunnel creating an encrypted virtual bridge to the host machine without public port exposure or port-forwarding requirements.

Per-Host Throttling: The FastAPI backend stores the sliding-window timestamp ledger in the shared `rate_limits` SQLite table tracking user_id, so every worker process enforces the same cooldown.

Requests arriving within $< 3.0\text{s}$ of the prior request yield HTTP 429 Too Many Requests.

2.3 Application Tier (FastAPI Gateway)

Runtime: Python 3.10+ running Uvicorn with 4 asynchronous worker processes.

Pipeline Execution Lifecycle (/api/chat):

Authentication Check: Validate user_id against active DB records.

Level Progression Check: Confirm the user has not completed the arena or submitted invalid level indices.

Ingress Filtering (Level 2 Only): Run non-capturing regex check against prohibited keywords (password, key, flag, secret, reveal). Short-circuit execution if matched.

Dynamic Context Building: Select system prompt associated with user's verified level.

Inference Dispatch: Asynchronous non-blocking HTTP call to Groq LPU endpoint using shared client session pool.

Egress Sanitization (Level 3 Only): Check model reply string for target tokens (FLAG{, cipher_master). Replace with redaction notice if present.

Telemetry Persistence: Atomically increment user counters (total_prompts, total_chars) and insert raw prompt log.

2.4 Inference Tier (Groq Cloud)

Model Configuration: llama-3.1-8b-instant.

Execution Parameters:

temperature: 0.2 (reduces erratic hallucination; preserves deterministic vulnerability behavior).

max_tokens: 150.

top_p: 0.9.

Capacity & Quotas: Under Groq Pay-As-You-Go, the account operates under a 1,000+ RPM allowance.

100 participants hitting a 3-second cooldown produce an absolute theoretical maximum of:

$$\text{Max Throughput} = \frac{100 \text{ concurrent users}}{3 \text{ seconds}} \approx 33.3 \text{ requests per second} = 2,000 \text{ RPM}$$

In real-world testing, participant typing and reading latency keeps average traffic between $200\text{--}350 \text{ RPM}$, comfortably within Groq limits.

3. Data Architecture & Storage Strategy

The system utilizes an embedded SQLite3 database running with Write-Ahead Logging (WAL) enabled to support high-throughput concurrent writes from asynchronous workers.

3.1 Entity-Relationship Model

┌──────────────────────────────────────┐
│                users                 │
├──────────────────────────────────────┤
│ id: TEXT [PK]                        │
│ username: TEXT [UNIQUE]              │
│ current_level: INTEGER               │
│ start_time: TIMESTAMP                │
│ completed_at: TIMESTAMP [NULL]       │
│ total_prompts: INTEGER               │
│ total_chars: INTEGER                 │
│ failed_attempts: INTEGER             │
│ final_score: REAL                    │
└──────────────────┬───────────────────┘
                   │
                   │ 1:N
                   │
          ┌────────┴────────────┐
          ▼                     ▼
┌─────────────────────────┐  ┌─────────────────────────┐
│      prompt_ledger      │  │       submissions       │
├─────────────────────────┤  ├─────────────────────────┤
│ id: INTEGER [PK]        │  │ id: INTEGER [PK]        │
│ user_id: TEXT [FK]      │  │ user_id: TEXT [FK]      │
│ level: INTEGER          │  │ level: INTEGER          │
│ prompt_text: TEXT       │  │ submitted_key: TEXT     │
│ response_text: TEXT     │  │ is_correct: BOOLEAN     │
│ char_count: INTEGER     │  │ submitted_at: TIMESTAMP │
│ is_blocked: BOOLEAN     │  └─────────────────────────┘
│ created_at: TIMESTAMP   │
└─────────────────────────┘

3.2 Concurrency & Performance Optimizations

Execute the following PRAGMAs during database initialization to avoid file-level locking bottlenecks:

SQLPRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 10000;
PRAGMA cache_size = -64000; -- 64MB In-Memory Cache

4. Operational Telemetry & Scoring Subsystem

4.1 Real-Time Score Calculation

When a participant submits the correct key for Level 3, the database transaction locks the record and executes the final evaluation pipeline:

[ Correct Level 3 Key Validated ]
               │
               ▼
[ Extract: start_time, completed_at, total_prompts, failed_attempts ]
               │
               ├─► Elapsed Minutes = Floor((Completed - Start) / 60)
               ├─► Deductions(Prompts) = Max(0, total_prompts - 3) * 15
               ├─► Deductions(Time) = Elapsed Minutes * 2
               ├─► Deductions(Fails) = failed_attempts * 25
               │
               ▼
[ Final Score = Max(0, 1000 - Deductions(Prompts) - Deductions(Time) - Deductions(Fails)) ]
               │
               ▼
[ Write Final Score & Update Leaderboard Cache ]

4.2 Leaderboard Sorting Pipeline

The leaderboard ranking query uses a multi-tier tie-breaking structure:

SQLSELECT 
    username, 
    current_level, 
    final_score, 
    total_prompts, 
    total_chars, 
    completed_at 
FROM users 
ORDER BY 
    final_score DESC, 
    current_level DESC, 
    total_prompts ASC, 
    total_chars ASC,
    completed_at ASC 
LIMIT 50;

5. Failure Modes & Mitigations

Failure ModeImpactArchitectural MitigationAPI Timeout / Model DropUser receives broken state; prompt count still increments.Backend wraps external calls in try/except with an 8-second timeout. If the call fails, prompt and character counters are rolled back, and an HTTP 502 Bad Gateway is returned without penalty.Input Fuzzing ScriptsBrute-force tool attempts dictionary attacks on the API.Enforce a strict 3-second sliding window per user_id. Offending IPs with excessive attempts can be dropped via Cloudflare WAF or local firewall.Simultaneous Level SolvesRace conditions updating progress states.All progression transitions execute within isolated transactions using atomic SQL UPDATE operations.Local Host Network SaturationServer laptop exhausts network connection pool.Host server operates with high file-descriptor limits (ulimit -n 65535) and pooled HTTP keep-alive connections via httpx.AsyncClient(limits=Limits(max_keepalive_connections=100, max_connections=250)).

6. Hardware Resource Consumption Analysis

For a deployment running on an 8-core CPU with 24 GB RAM hosting 100 concurrent participants:

Memory Footprint:

4 Uvicorn Workers: ~200 MB – 350 MB RAM

SQLite WAL Buffer: ~64 MB RAM

Cloudflare Tunnel Daemon: ~30 MB RAM

Total Allocated System Memory: $< 500\text{ MB}$ (Leaving $> 23\text{ GB}$ free).

CPU Utilization:

Typical I/O wait state bound by network round-trips to Groq API (~300–600ms latency).

System load factor is estimated at $< 15\%$ total CPU capacity.

Network Bandwidth:

Average payload: 1.5 KB request + 1.2 KB response.

At 50 req/sec peak: $\approx 135 \text{ KB/s}$ outbound/inbound bandwidth (negligible impact on broadband links).