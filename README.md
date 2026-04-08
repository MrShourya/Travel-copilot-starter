# 🌍 Travel Copilot — Dynamic MCP Architecture

![Python](https://img.shields.io/badge/Python-3.11-blue)
![Streamlit](https://img.shields.io/badge/UI-Streamlit-red)
![LLM](https://img.shields.io/badge/LLM-OpenAI%20%7C%20Ollama-green)
![Architecture](https://img.shields.io/badge/Pattern-Dynamic%20MCP-orange)
![Status](https://img.shields.io/badge/Status-Active-success)

## 🚀 Overview
Travel Copilot is a Dynamic MCP-based AI system that:
- Understands user queries
- Extracts structured intent
- Dynamically decides which tools to call
- Validates inputs
- Executes MCP tools
- Generates final responses

## 🧠 Dynamic MCP Concept
LLM → decides WHAT to do  
Python → validates  
MCP → executes  

## 🏗️ Architecture
User → UI → Agent → Planner → Validator → MCP → LLM → Response

## 🔄 Execution Flow
1. User Input  
2. Input Understanding  
3. State Extraction  
4. Planner Prompt  
5. Planner Response  
6. Validation  
7. Action Decision  
8. Tool Execution  
9. Loop  
10. Final Output  

## 🔁 Sequence
User → Agent → Planner → Validator → Tool → LLM → UI

## 🧩 Components
- agent.py → loop control  
- planner.py → LLM decisions  
- executor.py → validation + execution  
- tool_catalog.py → tool discovery  
- UI → visualization  

## 🔌 MCP Integration
Expose:
- tool_name  
- description  
- required_args  

System auto-discovers tools.

## ▶️ Run
```
poetry install
poetry shell
PYTHONPATH=. poetry run streamlit run app/ui/streamlit_app.py
```

## 🧪 Example
- Plan a trip to Dubai  
- Weather in Delhi next week  

## ⚠️ Issues
- Token overflow → compress context  
- Missing inputs → validation  
- Wrong args → filter required args  

## 🚀 Future
- Multi-tool execution  
- Memory  
- LangGraph  

## 👨‍💻 Author
Shourya Mangal
