# intent_interpretation
A repository for an interpretation application based on agentic AI that translates a user intent expressed in natural language (NL) into a structured TMF921 request
# 🤖 Agent Intent TMF921 - API Architecture
## Composants

1. **Frontend (React + Vite)**
   - Interface utilisateur 
   - Communication avec le backend via API REST

2. **Backend (FastAPI + Python)**
   - API REST pour toutes les opérations
   - Orchestration des agents IA (GPT-4o, Claude)
   - Recherche sémantique via Pinecone
   - Génération des Intents TMF921( les modeles de l'API Groq)

3. **Data Layer**
   - **Pinecone** : Base de données vectorielle pour la recherche sémantique

##  Technologies utilisées

### Backend
- **FastAPI** : Framework web Python
- **Pydantic AI** : Framework pour agents IA
- **OpenAI GPT-4o** : Modèle de langage pour classification et reformulation
- **Anthropic Claude Sonnet 4.5** : Modèle de langage pour décomposition
- **Pinecone** : Base de données vectorielle
- **Sentence Transformers** : Embeddings sémantiques
- **Groq** : modele  pour le mapping des propriétés

### Frontend
- **React 18** : Bibliothèque UI
- **Vite** : Build tool moderne
- **Material-UI (MUI)** : Composants UI
- **Emotion** : CSS-in-JS

##  Installation

# 1. Créer l'environnement
conda create -n agent-intent python=3.10 -y
conda activate agent-intent

# 2. Installer les dépendances
pip install -r requirements.txt


##  Configuration

### Fichier `.env`  :  ajouter les keys des APIs  

##  Structure des fichiers backend

```
backend/
├── api.py                      # API REST FastAPI 
├── agent.py                    # Logique métier
├── ingest_catalog.py           # recherche vectorielle (pinecone) 
├── requirements.txt            # Dépendances
├── .env.example               # Template configuration
├── .env                       # Configuration réelle (à créer)
└── catalog/                   # Catalogue TMF633 (JSON)

## Lancement 

### Avec Uvicorn 
uvicorn api:app --port 8000  --reload
