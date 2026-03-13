# intent_interpretation
A repository for an interpretation application based on agentic AI that translates a user intent expressed in natural language (NL) into a structured TMF921 request

# 🤖 Agent Intent TMF921 - API Architecture

## Components

1. **Frontend (React + Vite)**
   - User interface
   - Communication with the backend via REST API

2. **Backend (FastAPI + Python)**
   - REST API for all operations
   - Orchestration of AI agents (GPT-4o, Claude)
   - Semantic search using Pinecone
   - Generation of TMF921 Intents (using Groq API models)

3. **Data Layer**
   - **Pinecone**: Vector database for semantic search

## Technologies Used

### Backend
- **FastAPI**: Python web framework
- **Pydantic AI**: Framework for AI agents
- **OpenAI GPT-4o**: Language model for classification and reformulation
- **Anthropic Claude Sonnet 4.5**: Language model for decomposition
- **Pinecone**: Vector database
- **Sentence Transformers**: Semantic embeddings
- **Groq**: Model used for property mapping

### Frontend
- **React 18**: UI library
- **Vite**: Modern build tool
- **Material-UI (MUI)**: UI components
- **Emotion**: CSS-in-JS

## Installation

# 1. Create the environment
conda create -n agent-intent python=3.10 -y
conda activate agent-intent

# 2. Install dependencies
pip install -r requirements.txt


## Configuration

### `.env` file: add the API keys

## Backend File Structure
backend/
├── api.py # FastAPI REST API
├── agent.py # Business logic
├── ingest_catalog.py # Vector search (Pinecone)
├── requirements.txt # Dependencies
├── .env.example # Configuration template
├── .env # Actual configuration (to create)
└── catalog/ # TMF633 Catalog (JSON)


## Run

### Using Uvicorn
uvicorn api:app --port 8000 --reload
