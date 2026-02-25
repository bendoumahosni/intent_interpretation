
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
import asyncio
import os
from dotenv import load_dotenv

# Import depuis agent.py
from agent import (
    classify_and_route,
    decompose_request,
    search_candidates_for_services,
    generate_tmf921_intent,
    reformulate_request,
    handle_clarification_with_merge,
    recommend_alternatives,
    ConversationState,
    ServiceIdentified,
    Decomposition,
    ServiceCandidate,
    TMF921Intent
)

load_dotenv()

# ============================================================================
# FASTAPI APP
# ============================================================================

app = FastAPI(
    title="Agent Intent TMF921 API",
    description="API pour la génération automatique d'Intent TMF921 depuis langage naturel",
    version="1.0.0"
)

# Configuration CORS 
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En production, spécifier les domaines autorisés
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# MODELS D'ENTRÉE/SORTIE
# ============================================================================

class ClassifyRequest(BaseModel):
    user_input: str = Field(..., description="Demande utilisateur en langage naturel")

class ClassifyResponse(BaseModel):
    type: str = Field(..., description="TELECOM, GREETING ou OUT_OF_SCOPE")
    message: str = Field(..., description="Message de réponse")

class DecomposeRequest(BaseModel):
    user_input: str = Field(..., description="Demande utilisateur à décomposer")

class DecomposeResponse(BaseModel):
    services_identifies: List[Dict[str, Any]]
    candidates: Dict[str, List[Dict[str, Any]]]

class ValidateServicesRequest(BaseModel):
    selected_services: Dict[str, str] = Field(
        ..., 
        description="Mapping service_name -> service_id des services validés"
    )
    pending_services: List[Dict[str, Any]] = Field(
        ..., 
        description="Liste des services identifiés (avec nom, raison, proprietes)"
    )

class ClarificationRequest(BaseModel):
    user_clarification: str
    services_valides_noms: List[str]
    services_refuses: List[str]
    original_request: str
    # ✅ NOUVEAU : on passe aussi les données déjà validées pour les fusionner
    services_valides_data: Optional[Dict[str, Dict[str, Any]]] = Field(
        default=None,
        description="Données complètes des services déjà validés (ServiceCandidate)"
    )
    services_identifies_precedents: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Services identifiés lors de la décomposition initiale"
    )

class AlternativesRequest(BaseModel):
    services_refuses: List[str]
    services_valides: List[str]
    historique: List[str]

class GenerateIntentRequest(BaseModel):
    services_valides: Dict[str, Dict[str, Any]]  # service_name -> ServiceCandidate
    services_identifies: List[Dict[str, Any]]  # Liste complète des ServiceIdentified
    user_request_original: str

class GenerateIntentResponse(BaseModel):
    intent: Dict[str, Any]

# ============================================================================
# ENDPOINTS
# ============================================================================

@app.get("/")
async def root():
    """Endpoint racine avec informations sur l'API"""
    return {
        "message": "Agent Intent TMF921 API",
        "version": "1.0.0",
        "endpoints": {
            "classification": "/api/classify",
            "decomposition": "/api/decompose",
            "validation": "/api/validate",
            "clarification": "/api/clarify",
            "alternatives": "/api/alternatives",
            "intent_generation": "/api/generate-intent"
        }
    }

@app.post("/api/classify", response_model=ClassifyResponse)
async def classify(request: ClassifyRequest):
    """
    Classifier la demande utilisateur (TELECOM, GREETING, OUT_OF_SCOPE)
    """
    try:
        result = await classify_and_route(request.user_input)
        return ClassifyResponse(
            type=result["type"],
            message=result["message"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/decompose", response_model=DecomposeResponse)
async def decompose(request: DecomposeRequest):
    """
    Décomposer la demande en services identifiés et rechercher les candidats.
    
    Retourne:
    - services_identifies: Liste des services détectés avec leurs propriétés
    - candidates: Dictionnaire des candidats (avec dépendances complètes) pour chaque service
    """
    try:
        # Décomposition
        decomposition = await decompose_request(request.user_input)
        
        if not decomposition.services_identifies:
            raise HTTPException(
                status_code=400, 
                detail="Aucun service identifié. Veuillez reformuler."
            )
        
        # Recherche des candidats
        candidates = await search_candidates_for_services(decomposition)
        
        # Conversion en dict pour la réponse
        services_dict = [s.model_dump() for s in decomposition.services_identifies]
        
        
        candidates_dict = {
            service_name: [c.model_dump() for c in candidats_list]
            for service_name, candidats_list in candidates.items()
        }
        
        return DecomposeResponse(
            services_identifies=services_dict,
            candidates=candidates_dict
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/validate")
async def validate_services(request: ValidateServicesRequest):
    """
    Valider les services sélectionnés par l'utilisateur
    """
    try:
        return {
            "status": "success",
            "validated_services": list(request.selected_services.keys()),
            "count": len(request.selected_services)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/clarify")
async def clarify(request: ClarificationRequest):
    """
    Gérer la clarification utilisateur et retourner la liste FUSIONNÉE :
    services déjà validés + nouveaux services issus de la clarification.
    
    ✅ CORRECTION PRINCIPALE :
    - Les services déjà validés sont conservés tels quels dans la réponse.
    - Les nouveaux services issus de la clarification sont ajoutés.
    - Les services refusés sont remplacés.
    - Le frontend n'a plus besoin de gérer cette fusion côté client.
    """
    try:
        # 1. Obtenir les nouveaux services depuis la clarification
        new_decomposition = await handle_clarification_with_merge(
            user_clarification=request.user_clarification,
            services_valides_noms=request.services_valides_noms,
            services_refuses=request.services_refuses,
            original_request=request.original_request
        )
        
        # 2. Recherche des candidats pour les NOUVEAUX services uniquement
        new_candidates = await search_candidates_for_services(new_decomposition)
        
        # 3. ✅ FUSION : reconstruire la liste complète des services identifiés
        #    = services précédents validés + nouveaux services de la clarification
        merged_services_identifies = []
        merged_candidates = {}

        # a) Réintégrer les services précédemment identifiés ET validés
        if request.services_identifies_precedents:
            for svc_data in request.services_identifies_precedents:
                svc_nom = svc_data.get("nom", "")
                # On ne garde que ceux qui avaient été validés
                if svc_nom in request.services_valides_noms:
                    merged_services_identifies.append(svc_data)
                    # Réinjecter leurs candidats depuis les données validées
                    if request.services_valides_data and svc_nom in request.services_valides_data:
                        candidate_data = request.services_valides_data[svc_nom]
                        merged_candidates[svc_nom] = [candidate_data]

        # b) Ajouter les nouveaux services issus de la clarification
        for new_svc in new_decomposition.services_identifies:
            # Éviter les doublons avec les services déjà validés
            if new_svc.nom not in request.services_valides_noms:
                merged_services_identifies.append(new_svc.model_dump())
                merged_candidates[new_svc.nom] = [
                    c.model_dump() for c in new_candidates.get(new_svc.nom, [])
                ]

        return {
            "services_identifies": merged_services_identifies,
            "candidates": merged_candidates,
            # Indicateur pour le frontend : quels services sont pré-validés
            "pre_validated_services": request.services_valides_noms
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/alternatives")
async def get_alternatives(request: AlternativesRequest):
    """
    Recommander des services alternatifs
    """
    try:
        alternatives = await recommend_alternatives(
            services_refuses=request.services_refuses,
            services_valides=request.services_valides,
            historique=request.historique
        )
        
        return {
            "alternatives": alternatives
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/generate-intent", response_model=GenerateIntentResponse)
async def generate_intent(request: GenerateIntentRequest):
    """
    Générer l'Intent TMF921 final
    """
    try:
        # Reconstruction de l'état de conversation
        state = ConversationState()
        state.user_request_original = request.user_request_original
        
        # Reconstruction des services validés
        for service_name, candidate_data in request.services_valides.items():
            candidate = ServiceCandidate(**candidate_data)
            state.services_valides[service_name] = candidate
        
        # Reconstruction des services identifiés
        for service_data in request.services_identifies:
            service = ServiceIdentified(**service_data)
            state.add_identified_services([service])
        
        # Génération de l'intent
        intent = generate_tmf921_intent(state)
        
        return GenerateIntentResponse(
            intent=intent.model_dump()
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """Endpoint de santé pour vérifier que l'API fonctionne"""
    return {
        "status": "healthy",
        "pinecone_configured": bool(os.getenv("PINECONE_API_KEY")),
        "openai_configured": bool(os.getenv("OPENAI_API_KEY")),
        "anthropic_configured": bool(os.getenv("ANTHROPIC_API_KEY"))
    }

# ============================================================================
# LANCEMENT
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
