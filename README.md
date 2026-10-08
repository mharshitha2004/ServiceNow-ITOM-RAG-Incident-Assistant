<div align="center">

# ServiceNow ITOM AI Assistant

**A RAG documentation assistant and an agentic incident assistant for ServiceNow IT Operations Management**

Ask questions about MID Server, Discovery, CMDB, Service Mapping, Event Management and Asset Management, and get answers grounded in ServiceNow's own documentation. If the documented answer doesn't solve your problem, the assistant creates a real ServiceNow incident on your behalf, with your screenshot or log file attached.

[**Live Demo**](https://itom-three.vercel.app) · [API Docs](https://itom-assistant-backend.onrender.com/docs)

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-1C3C3C?logo=langchain&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js_16-000000?logo=nextdotjs&logoColor=white)
![MongoDB](https://img.shields.io/badge/MongoDB-47A248?logo=mongodb&logoColor=white)
![Pinecone](https://img.shields.io/badge/Pinecone-000000?logo=pinecone&logoColor=white)
![Gemini](https://img.shields.io/badge/Google_Gemini-8E75B2?logo=googlegemini&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)

</div>

> **Note:** The backend runs on Render's free tier and sleeps after 15 minutes of inactivity. The first request after a pause can take about a minute while it wakes up; the site shows a "Waking up the server" message meanwhile.

---

## Table of Contents

- [Why I built this](#why-i-built-this)
- [Features](#features)
- [Architecture](#architecture)
- [How it works](#how-it-works)
- [Tech stack](#tech-stack)
- [Project structure](#project-structure)
- [Getting started](#getting-started)
- [Building the knowledge base](#building-the-knowledge-base)
- [API reference](#api-reference)
- [Deployment](#deployment)
- [Security](#security)
- [Roadmap](#roadmap)
- [Author](#author)

---

## Why I built this

I worked as a technical support engineer on ServiceNow's ITOM module (MID Server, Discovery, CMDB, Event Management). Two patterns kept repeating:

1. **Many cases were already answered in the documentation**, but the docs run to thousands of pages, so people raised cases instead of searching.
2. **Cases that really needed an engineer often arrived without evidence**: no logs, no screenshot, and the wrong priority. The first exchange was spent just collecting information.

This project is a **documentation-first** assistant. Every question goes to the documentation before anything else. An incident is raised only if the documented answer doesn't help and the user agrees. When one is created, it already contains the problem description, the troubleshooting that was tried, an AI summary of the evidence, and the original files.

---

## Features

### 📘 Documentation Assistant
- Answers ITOM questions using **only** ServiceNow content: about **37,000 indexed chunks** from the official ITOM and Platform documentation, the public docs site, and public Community articles.
- **Two-stage retrieval**: vector search finds candidates, then a cross-encoder reranker picks the most relevant ones.
- **Context expansion** pulls in the chunks around each match, so multi-step procedures aren't cut off halfway.
- **Screenshot support**: paste or attach an error screenshot. Gemini reads it, and the extracted error details are added to the search.
- Works without an account. Logged-in users get their chat history saved.

### 🛠️ Incident Assistant (LangGraph + MCP)
- **Troubleshoots first**: every problem report goes through the documentation pipeline before an incident is offered.
- **Human-in-the-loop**: the agent pauses and asks whether the answer helped, whether to create an incident, and which priority to use.
- **Creates real incidents** in a ServiceNow instance through a custom **MCP server**.
- **P3/P4 only**: P1 and P2 incidents are blocked and must go through the normal human process. This rule is enforced in four separate places in the code.
- **Raised under your own ServiceNow account**: your ServiceNow username is checked when you register, and only you can view or close your incidents.
- **Workload-based assignment**: each incident goes to the member of the ITOM assignment group with the fewest open assistant-created incidents.
- **Evidence handling**: screenshots and `.txt` logs are analysed by Gemini and summarised in the incident, and all files (including `.zip` archives) are attached to the incident record.
- **Full lifecycle**: create incidents, check their status (including the latest work notes), close them with resolution notes, or reopen them.
- **Follow-up questions**: in the same chat, ask "who is the assignee?", "any update?" or "close it" and the agent knows which incident you mean.
- **Crash-safe incident creation**: each conversation's ID is stored in the incident's `correlation_id`, so a retry after a server restart returns the same incident instead of creating a duplicate. Interrupted steps are offered as a **Retry** button.

### 👤 Accounts and history
- Email/password accounts with bcrypt hashing and a JWT stored in an **httpOnly cookie**.
- Saved conversations in a collapsible sidebar. Paused incident conversations can be **resumed exactly where you left off**.
- Profile page for your name, email, ServiceNow username, password and avatar. Light and dark themes.

---

## Architecture

![Architecture: Next.js frontend, FastAPI backend with RAG pipeline, LangGraph agent and in-process MCP server, plus Pinecone, Gemini, MongoDB and ServiceNow](docs/architecture.png)

---

## How it works

### Retrieval-augmented generation

![RAG pipeline: embed, Pinecone top 30, rerank top 6, expand to 24, Gemini](docs/rag-pipeline.png)

| Stage | What happens |
|---|---|
| **Search** | The question is embedded with `all-MiniLM-L6-v2` and the 30 closest chunks are fetched from Pinecone. This stage casts a wide net. |
| **Rerank** | Pinecone's hosted `bge-reranker-v2-m3` cross-encoder scores each of the 30 chunks against the question, and the best 6 are kept. This stage picks the most relevant ones. |
| **Expand** | Documentation is mostly numbered procedures, and a 1,000-character chunk often holds only the first few steps. Neighbouring chunks from the same document are added, with priority for chunks that continue the top matches or a sentence cut off mid-way. The result is capped at 24 chunks and put back into reading order. |
| **Generate** | Gemini answers using **only** the supplied context. The prompt requires it to say when something isn't in the docs. LangChain retries with exponential backoff and falls back to a second model if the first fails. |

### Incident agent

![Incident agent: classify, troubleshoot, satisfied?, create incident?, priority, validate, create or blocked](docs/incident-agent.png)

⏸ marks a node that calls LangGraph's `interrupt()`. The graph pauses there and saves its state to MongoDB (`MongoDBSaver`), and the API returns `done: false` with quick-reply options. The user's next message resumes the graph with `Command(resume=answer)`. Because the state lives in MongoDB, a paused conversation survives server restarts and redeploys. If the server dies in the middle of a step, the checkpoint shows a pending step with no open question, and the conversation offers **Retry**, which re-runs that step safely.

### MCP tools (ServiceNow integration)

| Tool | ServiceNow API | Purpose |
|---|---|---|
| `create_incident` | `POST /api/now/table/incident` | Creates a P3/P4 incident and sets the caller, assignment group and assignee. Idempotent: an existing incident with the same `correlation_id` is returned instead of a duplicate |
| `lookup_servicenow_user` | `GET /api/now/table/sys_user` | Checks a username and returns its `sys_id` |
| `get_incident_status` | Table API + `sys_journal_field` | Returns status, assignee and latest work notes and comments |
| `close_incident` | `PATCH /api/now/table/incident/{sys_id}` | Resolves an incident with notes and a valid close code |
| `reopen_incident` | `PATCH /api/now/table/incident/{sys_id}` | Moves an incident back to In Progress with a work note |
| `attach_incident_file` | `POST /api/now/attachment/file` | Attaches a screenshot, log or archive (skips a file already attached) |

**ServiceNow behaviours the tools account for:**
- **Priority**: ServiceNow calculates priority from impact and urgency, so the tool sends the right impact/urgency pair (P3 = 2/2, P4 = 3/3) instead of setting priority directly.
- **Close codes**: the valid close code is looked up from `sys_choice` rather than hard-coded, because a value that doesn't match an existing choice is silently dropped.
- **Assignment**: open incidents per group member are counted with the Aggregate (Stats) API. If the configured group can't be found, a warning is logged instead of failing silently.
- **Idempotency**: the conversation's thread ID is stored in the standard `correlation_id` field and checked before creating, with the returned value verified (ServiceNow ignores invalid query terms by default).

---

## Tech stack

| Layer | Technologies |
|---|---|
| **Frontend** | Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS v4, shadcn/ui (Base UI), lucide-react, react-markdown + remark-gfm |
| **Backend** | FastAPI, Uvicorn, Pydantic |
| **AI / RAG** | LangChain (LCEL), LangGraph, Google Gemini, `all-MiniLM-L6-v2` via fastembed (ONNX Runtime), Pinecone + Pinecone Inference reranker |
| **Tooling protocol** | Model Context Protocol (MCP) server and client (in-process transport; the server also runs standalone over stdio) |
| **Data** | MongoDB Atlas (users, conversations, GridFS images, LangGraph checkpoints), Pinecone |
| **Auth** | bcrypt, PyJWT (HS256), httpOnly cookies |
| **Ingestion** | PyMuPDF, BeautifulSoup, LangChain text splitters |
| **Deployment** | Docker, Render (backend, via `render.yaml` Blueprint), Vercel (frontend) |

---

## Project structure

```
.
├── render.yaml                              # Render Blueprint for the backend service
├── Servicenow-ITOM Assistant - Backend/
│   ├── main.py                              # FastAPI app and all endpoints
│   ├── rag.py                               # Prompt, Gemini chain (retry + fallback), answer_question()
│   ├── retrieve.py                          # Embed, Pinecone search, rerank, context expansion
│   ├── auth.py                              # bcrypt, JWT, cookie settings, user CRUD
│   ├── db.py                                # MongoDB client, collections, GridFS helpers
│   ├── conversations.py                     # Chat history, scoped to the owning user
│   ├── agent/
│   │   ├── graph.py                         # LangGraph state, nodes, routing, checkpointer
│   │   └── mcp_client.py                    # In-process MCP client + sync wrappers
│   ├── mcp_server/
│   │   └── server.py                        # MCP server exposing the six ServiceNow tools
│   ├── ingestion/
│   │   ├── embeddings.py                    # Shared embedding model, ONNX via fastembed (ingestion and queries)
│   │   ├── pdf_ingest.py                    # Add a PDF to the index without overwriting
│   │   ├── scrape_servicenow_sources.py     # Crawler for docs + Community content
│   │   └── ingest_specific_urls.py          # Ingest a hand-picked URL list
│   ├── chunks/                              # Local chunk copies (used for context expansion)
│   ├── extract_pdf.py, chunk_pdf.py, validate_chunks.py,
│   │   remove_duplicates.py, embed_and_upload.py   # Original 5-step PDF pipeline
│   ├── verify_embeddings.py                 # Proves fastembed vectors match the original model
│   ├── Dockerfile, .dockerignore, prefetch_models.py
│   └── requirements.txt, requirements-ingestion.txt
└── service-now-itom-ai-assistant-frontend/
    ├── app/                                 # Routes: /, /documentation, /incident, /login, /register, /profile
    ├── components/                          # Chat UIs, history sidebar, navbar, profile, landing page
    └── lib/                                 # Typed API clients, auth/theme contexts, attachment hooks
```

---

## Getting started

### Prerequisites

- Python 3.12 and Node.js 20+ with **pnpm**
- A **MongoDB** database (Atlas free tier or local)
- A **Pinecone** account with a serverless index: **dimension 384**, metric **cosine**
- A **Google Gemini** API key ([Google AI Studio](https://aistudio.google.com))
- A **ServiceNow** instance (a free [Personal Developer Instance](https://developer.servicenow.com) works) with:
  - an integration user with permission to read and write incidents, users and attachments
  - an assignment group (default name: `IT Operations Management L1 team`; set `ITOM_ASSIGNMENT_GROUP_NAME` to your group's exact name) with at least one member

### 1. Clone

```bash
git clone https://github.com/harshitha2004-ml/Servicenow_ITOM.git
cd Servicenow_ITOM
```

### 2. Backend

```bash
cd "Servicenow-ITOM Assistant - Backend"
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Create a `.env` file in the backend folder:

```env
# Vector DB
PINECONE_API_KEY=your-pinecone-key
PINECONE_INDEX_NAME=servicenow-itom-docs

# Database
MONGODB_URI=mongodb+srv://user:password@cluster.mongodb.net
MONGODB_DB_NAME=itom_assistant

# Auth
JWT_SECRET_KEY=a-long-random-string

# LLM
GEMINI_API_KEY=your-gemini-key
GEMINI_FALLBACK_MODELS=gemini-3.6-flash

# ServiceNow (used only by the MCP server)
SERVICENOW_INSTANCE_URL=https://devXXXXX.service-now.com
SERVICENOW_USERNAME=integration.user
SERVICENOW_PASSWORD=your-password
ITOM_ASSIGNMENT_GROUP_NAME=IT Operations Management L1 team
ASSISTANT_CONTACT_TYPE=virtual_agent
# INCIDENT_CLOSE_CODE=          # optional; auto-detected from sys_choice if unset

# Deployment (leave unset for local development)
# ENVIRONMENT=production
# FRONTEND_ORIGINS=https://your-app.vercel.app
```

Run the API:

```bash
uvicorn main:app --reload --port 8000
```

Interactive API docs are available at **http://localhost:8000/docs**. You don't need to start the MCP server yourself: the backend loads it in-process. To use the same tools from another MCP client (e.g. Claude Desktop or the MCP Inspector), run `python mcp_server/server.py`, which serves them over stdio.

### 3. Frontend

```bash
cd service-now-itom-ai-assistant-frontend
pnpm install
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
pnpm dev
```

Open **http://localhost:3000**.

---

## Building the knowledge base

The index is built only from **public** ServiceNow content. The login-protected Support KB is deliberately excluded. The ingestion scripts run locally and need the extra packages:

```bash
pip install -r requirements.txt -r requirements-ingestion.txt
```

| Source | Script | Chunks |
|---|---|---|
| ITOM product documentation PDF (5,303 pages) | `extract_pdf.py` → `chunk_pdf.py` → `validate_chunks.py` → `remove_duplicates.py` → `embed_and_upload.py` | 14,505 |
| Platform documentation PDF | `ingestion/pdf_ingest.py --pdf <file> --source-slug platform-guide` | 13,607 |
| Docs site + Community articles (ITOM, CMDB, SAM/HAM) | `ingestion/scrape_servicenow_sources.py` | 8,304 |
| Curated high-value threads | `ingestion/ingest_specific_urls.py` | 882 |

**Chunking settings**: 1,000 characters with 150 overlap (`RecursiveCharacterTextSplitter`). Duplicates are removed after normalising whitespace and letter case.

**Vector IDs**: every source uses its own ID prefix (`platform-guide-000042`, `community-<slug>-<hash>-0003`). Pinecone overwrites a vector when a new one reuses its ID, so the prefixes stop a new ingestion run from replacing existing vectors.

Each script supports `--dry-run`, which shows the chunks it would create without writing to Pinecone. Every script also saves a local copy of its chunks under `chunks/`, which the retriever uses for context expansion.

---

## API reference

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/health` | — | Health check (used by Render and keep-alive pings) |
| `POST` | `/ask` | optional | Ask a documentation question (JSON) |
| `POST` | `/ask/multimodal` | optional | Ask with an attached screenshot (multipart) |
| `POST` | `/incident/start` | required | Start an incident conversation (optionally with an image, `.txt` or `.zip`) |
| `POST` | `/incident/reply` | required | Answer the agent's current question: `{thread_id, answer}` |
| `POST` | `/auth/register` | — | Create an account (checks the ServiceNow username) |
| `POST` | `/auth/login` · `/auth/logout` | — | Start or end a session (httpOnly cookie) |
| `GET` | `/auth/me` | required | Get the current user |
| `PATCH` | `/auth/profile` | required | Update name, email or ServiceNow username |
| `POST` | `/auth/password` | required | Change password |
| `POST` `GET` `DELETE` | `/auth/avatar` | required | Upload, view or remove a profile photo |
| `GET` | `/conversations?kind=documentation\|incident` | required | List saved conversations |
| `GET` `DELETE` | `/conversations/{id}` | required | Open (including any paused incident step or Retry) or delete a conversation |
| `GET` | `/images/{id}` | required | Get an attached image (owner only) |

**Example: an incident turn that is waiting for the user's answer:**

```json
{
  "thread_id": "3f9c...",
  "done": false,
  "message": "Select incident priority (P3 or P4).",
  "awaiting": "priority",
  "options": ["P3", "P4"],
  "conversation_id": "a71b..."
}
```

---

## Deployment

| Component | Platform | Notes |
|---|---|---|
| Frontend | **Vercel** | Root directory set to the frontend folder; `NEXT_PUBLIC_API_URL` points to the backend |
| Backend | **Render** (Docker, free tier) | Configured by `render.yaml`; secrets entered in the Render dashboard |
| Database | **MongoDB Atlas** | Free tier |
| Vectors + reranker | **Pinecone** | Serverless index + Pinecone Inference |

**Fitting the backend into Render's 512 MB free tier:**
- **Embeddings run on ONNX Runtime (fastembed)** instead of PyTorch. It is the same `all-MiniLM-L6-v2` model and produces the same vectors (`verify_embeddings.py` shows cosine similarity 1.000000), using about 300 MB less RAM, so the existing Pinecone index needed no re-ingestion.
- **The MCP server runs in-process** instead of starting a new Python process for every tool call (about 50 MB each).
- **Neighbour-chunk lookup reads from disk** by byte offset instead of holding every chunk in memory: 63 MB down to 5 MB.
- The **reranker runs on Pinecone's servers**, models and clients **load on first use**, and the embedding model is **downloaded at Docker build time** (`prefetch_models.py`).
- `MALLOC_ARENA_MAX=2` and a single Uvicorn worker keep memory steady.

**Cold starts:** `GET /health` answers without touching any database, so it serves as Render's health check and as a target for a free keep-alive ping every 10 minutes.

**Cross-site cookies:** in production the frontend and backend are on different domains. For the session cookie to be sent, the backend needs `ENVIRONMENT=production` (which switches the cookie to `SameSite=None; Secure`) and your Vercel URL in `FRONTEND_ORIGINS`.

---

## Security

- Passwords are hashed with **bcrypt**. Sessions are **JWTs in httpOnly cookies**, which JavaScript cannot read.
- Each incident's caller is taken from the logged-in account, never from chat text. Status, close and reopen queries are filtered by the caller's `sys_id`.
- Every conversation and image query is filtered by `user_id`. Other users' data returns **404**, so you can't tell whether it exists.
- Incident threads can only be resumed by their owner.
- Uploads are restricted to an allowed list of file types with size limits (10 MB for images, 20 MB for logs and archives). SVG is rejected. Images are served with `X-Content-Type-Options: nosniff`.
- The AI can only create **P3/P4** incidents. This is checked in four places: the graph routing, the node that creates the incident, the MCP client, and the MCP server.
- ServiceNow credentials are only available to the MCP server process and are never sent to the browser.
- `.env` files are git-ignored. **Never commit credentials.**

---

## Roadmap

- [ ] Show source citations (document, page, URL) with each answer
- [ ] Measure answer quality with a fixed question set (RAGAS, hit-rate/MRR)
- [ ] Hybrid search (BM25 + dense) to better match exact table names and error codes
- [ ] Stream answers to the UI as they are generated
- [ ] Use an LLM to classify user intent, keeping the keyword rules as a fast path
- [ ] Rewrite follow-up questions using the conversation so far
- [ ] Store incident uploads in GridFS so they survive a restart before Retry
- [ ] Automated tests (pytest) and LangSmith tracing

---

## Author

**Mandadi Harshitha Reddy**: B.Tech CSE (Gold Medallist), ServiceNow CSA and CAD certified, former Associate Technical Support Engineer on ServiceNow ITOM.

If you found this project interesting, consider giving it a ⭐

---

<sub>This is an independent portfolio project and is not affiliated with or endorsed by ServiceNow. "ServiceNow" is a trademark of ServiceNow, Inc. All indexed content is publicly available documentation and community material.</sub>
