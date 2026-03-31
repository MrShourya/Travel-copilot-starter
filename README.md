# 🌍 Travel Copilot — Production README

## 🚀 Overview
Travel Copilot is a modular AI system that:
- Understands user travel queries
- Extracts structured intent (city, dates, budget)
- Calls external MCP tools (weather, currency)
- Generates responses via LLM (OpenAI or local)
- Tracks everything with **Langfuse (observability + prompts)**

---

## 🧱 System Architecture

```
User → Streamlit UI
        ↓
    Agent Layer
        ↓
  ┌───────────────┐
  │ State Parsing │ (@observe)
  └───────────────┘
        ↓
  ┌───────────────┐
  │ Tool Router   │ (MCP calls)
  │  - Weather    │
  │  - Currency   │
  └───────────────┘
        ↓
  ┌───────────────┐
  │ Prompt Layer  │ (Langfuse)
  └───────────────┘
        ↓
  ┌───────────────┐
  │ LLM Layer     │ (LangChain)
  └───────────────┘
        ↓
     Response
```

---

## 🧠 Observability (Langfuse)

### Concepts
- **Session** → full user journey
- **Trace** → one user request
- **Observation** → one step

### Pattern Used

```
propagate_attributes → session
@observe → steps
update_current_observation → metadata
CallbackHandler → LLM tracking
```

---

## 📦 Tech Stack

| Layer | Tool |
|------|------|
| UI | Streamlit |
| Backend | Python (Poetry) |
| LLM | OpenAI / Local |
| Orchestration | LangChain |
| Observability | Langfuse |
| Tools | MCP Servers |
| DB (future) | Postgres + Qdrant |

---

## 📁 Project Structure

```
app/
  chat/
    agent.py
    prompts.py
  tools/
    tool_router.py
  observability/
    langfuse_client.py
  ui/
    streamlit_app.py

scripts/
.env
```

---

## ⚙️ Setup

### 1. Install
```bash
poetry install
poetry shell
```

### 2. Environment
```
OPENAI_API_KEY=

LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_BASE_URL=http://localhost:3000
```

---

## 🐳 Langfuse (Docker)

Ensure running:
- Langfuse UI
- Postgres

---

## ▶️ Run

```bash
PYTHONPATH=. poetry run streamlit run app/ui/streamlit_app.py
```

---

## 🔌 MCP Tools

| Tool | Purpose |
|-----|--------|
| Weather MCP | Forecast data |
| Currency MCP | Conversion |

---

## 🤖 LLM Layer

Supports:
- OpenAI (default)
- Local LLM (LLaMA)

Switch handled via provider config.

---

## 🧠 Prompt Management

```
prompt = client.get_prompt("travel_copilot")
compiled = prompt.compile(...)
```

---

## 📊 Langfuse Best Practices

- Use `@observe(name="...")` for all business steps
- Use `metadata` for custom fields
- Use `CallbackHandler` for LLM
- Avoid duplicate generation spans
- Keep one trace per user turn

---

## 🧪 Example Queries

- Plan a 4-day trip to Delhi next week under 30000 INR and show budget in EUR
- Convert 100 USD to EUR
- Weather in Tokyo

---

## 🔄 Future Enhancements

- Agentic workflow
- Local MCP servers
- RAG integration
- Memory/state persistence

---

## 👨‍💻 Author
Shourya Mangal
