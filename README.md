# 🌍 Travel Copilot — Production README

## 🚀 Overview

Travel Copilot is a modular AI travel assistant that:

- understands user travel requests
- extracts structured trip intent from free text
- routes to MCP tools for travel enrichment
- generates grounded responses with an LLM
- shows **decision trace visibility** so you can inspect exactly **why** a tool was called
- supports both **OpenAI** and **local Ollama models**
- tracks execution with **Langfuse**

This project currently uses a **Python-driven MCP routing flow** for production behavior, while also being prepared for a future **LLM-driven MCP calling architecture**.

---

## ✅ What is implemented now

### Core capabilities

- Streamlit chat UI
- session-aware travel state
- structured parsing of:
  - city
  - trip duration
  - date text
  - budget
  - source currency
  - target currency
- MCP-based enrichment for:
  - weather
  - currency
  - local travel planning MCP
- LLM response generation using LangChain
- prompt loading through Langfuse with fallback prompt support
- Langfuse observability across the user turn
- visual **decision trace** in Streamlit so you can see:
  - where decisions were taken
  - which MCP family was selected
  - which exact tool was called
  - the arguments sent
  - the returned payload
  - what was finally passed into the LLM

---

## 🧱 Current architecture

```text
User
  ↓
Streamlit UI
  ↓
Agent Layer (Python-controlled orchestration)
  ↓
State Manager
  └─ extracts city / trip_days / date_text / budget / currencies
  └─ determines flow_stage
  ↓
Tool Router
  ├─ Weather MCP routing
  ├─ Currency MCP routing
  └─ Travel Planning MCP routing
  ↓
MCP Clients
  ├─ Weather MCP client
  ├─ Currency MCP client
  └─ Travel Planning MCP client
  ↓
Tool Context + Guardrails
  ↓
Prompt Layer (Langfuse or fallback)
  ↓
LLM Layer (OpenAI / Ollama)
  ↓
Final answer
```

---

## 🧠 Important design point

### Current mode: Python-driven MCP routing

Right now, the **LLM does not decide which MCP tool to call**.

Instead:

1. Python parses the user query into structured travel state
2. Python decides whether the conversation is ready for itinerary generation
3. Python decides which MCP family to call
4. Python decides which exact MCP tool to call
5. MCP results are collected
6. only then is the LLM invoked with tool outputs inside `tool_context`

This was done intentionally so the decision-making stays:

- deterministic
- explainable
- observable
- easier to debug
- safer for exception handling

### Planned next mode: LLM-driven MCP routing

A future extension will add a second flow where the model itself proposes MCP tool calls and Python validates/executes them.

---

## 🔍 Decision visibility added

The Streamlit app now exposes a **decision trace** for every assistant turn.

You can visually inspect:

- flow stage before parsing
- flow stage after parsing
- whether tool calls were allowed
- each lookup step
- the MCP family involved
- the exact tool selected
- whether the tool call was skipped
- the reason for selection
- the arguments sent to MCP
- the returned payload
- what the LLM finally received

This is the key learning/debugging feature of the current implementation.

---

## 🧱 Implemented MCP families

### 1. Weather MCP

Used for weather enrichment.

Current router behavior:

- if the query suggests future/range-based weather:
  - `get_weather_byDateTimeRange`
- otherwise:
  - `get_current_weather`

Examples of triggers:

- weather
- rain
- forecast
- temperature
- next week
- tomorrow
- weekend

---

### 2. Currency MCP

Used for budget/currency conversion.

Current router behavior:

- extract amount and source currency
- extract target currency
- if no target currency:
  - skip MCP call
- if same source and target:
  - skip MCP call
- else:
  - try direct `get_latest_rates`
  - if insufficient, try USD bridge fallback using `get_latest_rates`

---

### 3. Travel Planning MCP (local)

Used for trip planning enrichment through your local MCP project.

Current tools integrated:

- `trip_readiness_check_tool`
- `build_trip_summary_tool`
- `estimate_daily_budget_tool`

Available in the MCP server as well:

- `suggest_packing_list_tool`

Current travel-planning routing behavior:

- readiness check
- trip summary
- budget estimate

These are triggered when state reaches `show_itinerary`.

---

## 🧠 Flow stages

The session state uses a high-level flow model.

Typical stages include:

- `choose_place`
- `choose_dates`
- `show_itinerary`

The agent only attempts the main enrichment/tool path when the state reaches:

```text
show_itinerary
```

That means the system first tries to ensure enough trip information is present before spending tool calls.

---

## 📦 Tech stack

| Layer | Tool |
|------|------|
| UI | Streamlit |
| Backend | Python |
| Dependency management | Poetry |
| LLM | OpenAI / Ollama |
| Orchestration | LangChain |
| Observability | Langfuse |
| Tool protocol | MCP |
| Travel planning MCP | Local FastAPI-hosted MCP server |
| Future storage | Postgres / Qdrant |

---

## 📁 Project structure

```text
app/
  chat/
    agent.py
    model_factory.py
    prompt_loader.py
    session_state.py
    state_manager.py
    tool_router.py
  config/
    settings.py
  mcp/
    base.py
    currency_client.py
    travel_planning_client.py
    weather_client.py
  observability/
    tracing.py
  ui/
    rendering.py
    streamlit_app.py

.env
pyproject.toml
poetry.lock
README.md
```

---

## 🧩 Key modules

### `app/chat/agent.py`

Main orchestration layer.

Responsibilities:

- update state from user input
- decide whether tool calls are allowed
- call MCP-backed router helpers
- build `tool_context`
- build `decision_trace`
- add guardrails
- invoke the LLM
- return all debug/visibility payloads to Streamlit

---

### `app/chat/state_manager.py`

Responsible for:

- extracting structured travel information from user text
- updating session state
- determining `flow_stage`

This is the first decision layer in the system.

---

### `app/chat/tool_router.py`

Responsible for:

- deciding which MCP family to use
- deciding which exact MCP tool to call
- building tool arguments
- returning decision metadata alongside tool outputs

This is the second decision layer in the system.

---

### `app/mcp/travel_planning_client.py`

HTTP MCP client for your local travel-planning MCP server.

Responsibilities:

- connect to `http://127.0.0.1:8000/mcp/mcp`
- initialize session
- call tool
- normalize MCP output
- return metadata about called tool and arguments

---

### `app/ui/streamlit_app.py`

Main UI layer.

Responsibilities:

- render chat history
- show assistant answers
- show decision trace
- show tool context
- show session state
- show prompt metadata

---

## 🧠 Observability (Langfuse)

The app uses Langfuse to track the full user turn.

### Typical tracked steps

- root observation for the travel turn
- state parsing/update
- MCP lookups
- prompt fetch
- LLM generation

### Benefits

- see execution at per-step level
- inspect metadata
- inspect prompt usage
- inspect model response generation
- correlate tool calls with final answer quality

---

## ⚙️ Environment setup

Create a `.env` file in the project root.

Example:

```env
OPENAI_API_KEY=

LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_BASE_URL=http://localhost:3000

DEFAULT_MODEL_PROVIDER=openai

OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2
OPENAI_MODEL=gpt-4o-mini
```

You may already have additional environment variables in your codebase. Keep those as needed.

---

## 🐍 Local setup

### 1. Clone the repository

```bash
git clone <your-travel-copilot-repo-url>
cd Travel-copilot-starter
```

### 2. Install dependencies

```bash
poetry install
```

### 3. Activate the Poetry shell if you want

```bash
poetry shell
```

This is optional. You can also use `poetry run ...` directly.

### 4. Create `.env`

Add the variables shown above.

---

## 🐳 Optional local dependencies

### Langfuse

If you want observability enabled locally, make sure Langfuse is running and reachable at the configured base URL.

You typically need:

- Langfuse UI/API
- its backing database

If Langfuse is not available, your fallback prompt path may still allow the app to run depending on your configuration.

### Ollama

If you want local LLM inference:

```bash
ollama serve
```

And ensure the model you configured is installed, for example:

```bash
ollama pull llama3.2
```

---

## 🔌 Running the local travel-planning MCP server

This project depends on your separate local MCP project for travel planning.

From your **travel-planning-mcp** project:

```bash
poetry install
poetry run travel-planning-mcp-http
```

Expected MCP endpoint:

```text
http://127.0.0.1:8000/mcp/mcp
```

This must be running before the Travel Copilot app tries to call the local travel-planning MCP tools.

---

## ▶️ Running the Streamlit app locally

From the Travel Copilot project root:

```bash
PYTHONPATH=. poetry run streamlit run app/ui/streamlit_app.py
```

If you are on Windows PowerShell:

```powershell
$env:PYTHONPATH="."
poetry run streamlit run app/ui/streamlit_app.py
```

If you are already inside a Poetry shell:

```bash
PYTHONPATH=. streamlit run app/ui/streamlit_app.py
```

---

## ✅ Recommended startup order

Start services in this order:

### Option A — OpenAI mode

1. Start Langfuse
2. Start your local travel-planning MCP server
3. Start the Streamlit app

### Option B — Ollama mode

1. Start Ollama
2. Start Langfuse
3. Start your local travel-planning MCP server
4. Start the Streamlit app

---

## 🧪 Example test prompts

### General trip planning

- `Plan a 4-day trip to Dubai next week under 2500 USD and show budget in AED`
- `Plan a 3-day trip to Tokyo under 3000 USD`
- `I want a 5 day trip to Paris next month`

### Currency-focused

- `Convert 100 USD to EUR`
- `Plan a trip under 3000 INR and show budget in USD`

### Weather-focused

- `Weather in Tokyo`
- `Forecast in Dubai next week`
- `What will the weather be in Paris tomorrow`

---

## 👀 What to inspect in the UI

For each assistant message, open these panels:

### How the app decided which MCP tools to call

Use this to inspect:

- state update
- flow gate
- travel readiness lookup
- trip summary lookup
- travel budget lookup
- weather lookup
- currency lookup

### Tool context

Use this to inspect what the LLM actually received.

### Session state

Use this to inspect the structured state used by routing.

### Prompt metadata

Use this to confirm prompt source/debugging.

---

## 🛡️ Current safety/robustness pattern

The system uses a practical fallback model:

- tool calls are attempted by Python before LLM generation
- tool results are passed into `tool_context`
- guardrails are added to instruct the model not to invent data when tools fail
- decision trace records why a call was made or skipped

This keeps the system debuggable and reduces hidden behavior.

---

## 🧪 How to debug MCP decisions

When something looks wrong, inspect the decision trace in this order:

1. `state_update`
   - was city extracted correctly?
   - were trip_days extracted correctly?
   - was budget parsed correctly?
   - was `flow_stage` correct?

2. `flow_gate`
   - did the app enter `show_itinerary`?

3. MCP lookup steps
   - was the right MCP family selected?
   - was the right tool chosen?
   - were the arguments correct?

4. returned payload
   - did MCP return useful data?

5. tool context
   - did the LLM receive the right structured information?

---

## 🔄 Current limitations

- current production path is still Python-driven, not LLM-driven
- packing tool exists in the travel MCP project but is not yet fully integrated into the main orchestration flow
- weather and currency clients may still be slightly inconsistent in error-handling patterns
- current city extraction is rule-based and uses a known-city list
- date interpretation is still relatively lightweight

---

## 🛣️ Planned next enhancements

- LLM-driven MCP tool selection
- MCP registry / planner / executor abstraction
- packing-list integration
- more robust date normalization
- stronger validation and exception handling standardization
- memory/persistence
- optional RAG integration
- richer evaluation and tracing

---

## 👨‍💻 Author

Shourya Mangal
