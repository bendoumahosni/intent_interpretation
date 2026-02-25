
from pydantic_ai import Agent, RunContext
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any, Literal
import os
from dotenv import load_dotenv
from pinecone import Pinecone
from sentence_transformers import SentenceTransformer
from pydantic_ai.models.openai import OpenAIModel

from pydantic_ai.models.anthropic import AnthropicModel

import json
from pathlib import Path

load_dotenv()

# Embedding model
embedder = SentenceTransformer('all-MiniLM-L6-v2')

# Pinecone
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index(os.getenv("PINECONE_INDEX_NAME", "telecom-catalog1"))

# Chemin catalogue
CATALOG_DIR = Path(__file__).parent / "catalog"

# ============================================================================
# MODELS
# ============================================================================

class OutOfScopeResponse(BaseModel):
    """Réponse pour demandes hors sujet."""
    is_out_of_scope: bool = True
    message: str = Field(description="Message poli expliquant le refus")

class GreetingResponse(BaseModel):
    """Réponse pour salutations."""
    is_greeting: bool = True
    message: str = Field(description="Réponse courtoise à la salutation")

class ServiceIdentified(BaseModel):
    """Service identifié AVEC ses propriétés spécifiques."""
    nom: str
    raison: str
    proprietes: Dict[str, Any] = Field(
        default_factory=dict,
        description="Propriétés SPÉCIFIQUES à ce service uniquement"
    )

class Decomposition(BaseModel):
    """Décomposition de la demande."""
    services_identifies: List[ServiceIdentified]

class ServiceDependency(BaseModel):
    """Dépendance CFSS."""
    name: str
    id: str
    version: str
    href: str

class ServiceCandidate(BaseModel):
    """Candidat service."""
    service_id: str
    name: str
    description: str
    score: float
    dependencies: List[ServiceDependency] = Field(default_factory=list)

class ValidationResponse(BaseModel):
    """Validation utilisateur."""
    validation_type: Literal["total", "partiel", "refus"]
    services_valides: List[str] = Field(default_factory=list)
    services_refuses: List[str] = Field(default_factory=list)
    commentaire: Optional[str] = None

class TMF921Intent(BaseModel):
    """Intent TMF921."""
    name: str
    description: str
    version: str = "1.0"
    priority: str = "1"
    isBundled: bool = False
    context: str = "User request automation"
    characteristic: List[Dict[str, Any]] = Field(default_factory=list)
    expression: Dict[str, Any] = Field(default_factory=dict)

# ============================================================================
# AGENT 0 : CLASSIFICATION
# ============================================================================

classification_agent = Agent(
    model=OpenAIModel('gpt-4o'),
    result_type=str,
    system_prompt="""
Tu es un agent de classification pour un système télécom 5G.

TÂCHE : Comprendre la demande utilisateur  et la Classifier en 3 catégories :
1. "TELECOM" : demande concernant services télécom/réseau/5G/cloud/IoT
2. "GREETING" : salutation simple (bonjour, salut, comment ça va, etc.)
3. "OUT_OF_SCOPE" : hors sujet (cuisine, sport, politique, code Python, etc.)

RÈGLES :
- Réponds UNIQUEMENT par : "TELECOM", "GREETING" ou "OUT_OF_SCOPE"
- RIEN d'autre, juste le mot-clé
- Si doute entre TELECOM et OUT_OF_SCOPE, préfère OUT_OF_SCOPE
"""
)

polite_response_agent = Agent(
    model=OpenAIModel('gpt-4o'),
    result_type=str,
    system_prompt="""
Tu es un assistant poli et professionnel.

TÂCHE : Générer une réponse appropriée selon le contexte.

RÈGLES :
- Pour salutations : réponse chaleureuse, proposer d'aider sur services télécom
- Pour hors sujet : s'excuser poliment, rappeler le domaine d'expertise (télécom/5G/cloud)
- Ton professionnel mais amical
- Réponse courte (2-3 phrases max)
"""
)

# ============================================================================
# AGENT 1 : DÉCOMPOSITION
# ============================================================================

decomposition_agent = Agent(
    model = AnthropicModel(
        'claude-sonnet-4-5')
    ,
    result_type=Decomposition,
    system_prompt="""
Tu es un expert télécom 5G spécialisé dans l'analyse de besoins.

TÂCHE : Identifier TOUS les services ET associer à CHAQUE service SES propriétés spécifiques .

RÈGLE CRITIQUE - PROPRIÉTÉS PAR SERVICE :
- CHAQUE service doit avoir son propre dictionnaire "proprietes"
- N'inclure dans "proprietes" QUE les propriétés DIRECTEMENT liées à CE service
- NE JAMAIS créer de dictionnaire "proprietes" global
- pas  besoins d'extraire des propriétés dont l'utilisateur  n'est pas definit leurs  valeurs . 
- le  type de  slice , le  uses-case, usage , etc n'est pas  inclure dans  ce dictionnaire .

RÈGLES SERVICES :
- Identifier TOUS les services mentionnés ou IMPLICITES
- Un service par fonction distincte
- Types courants :
  * Slices 5G : uRLLC (latence), eMBB (débit), mMTC (IoT)
  * Analytics : vidéo, IoT data, détection
  * Notification : SMS, email, push, alertes
  * Edge computing : traitement local
  * Stockage : cloud, edge storage
  * Sécurité : VPN, firewall, authentification

MAPPING PROPRIÉTÉS → SERVICES :

- Latence, débit, disponibilité → slice 5G concerné
- Zone géographique, nb_caméras → service d'analyse/traitement
- Destinataire, fréquence → service notification
- Capacité stockage → service stockage

IMPORTANT :
- NE PAS dupliquer les services
- NE PAS inventer de propriétés absentes de la demande
- Associer chaque propriété au service le plus pertinent
"""
)

# ============================================================================
# AGENT 2 : REFORMULATION
# ============================================================================

reformulation_agent = Agent(
    model=OpenAIModel('gpt-4o'),
    result_type=str,
    system_prompt="""
Assistant pour clarification de demandes.

TÂCHE : Poser UNE question ciblée UNIQUEMENT pour les services refusés.

RÈGLES CRITIQUES :
- CONCENTRE-TOI UNIQUEMENT sur les services refusés
- NE MENTIONNE PAS les services déjà validés
- Question courte et précise
- Focus sur UN aspect à clarifier
- Exemples concrets si pertinent
- Ton professionnel

IMPORTANT : L'utilisateur a déjà validé certains services. Ta question doit porter 
UNIQUEMENT sur les services qu'il a refusés, pour comprendre pourquoi et proposer 
des alternatives.
"""
)

# ============================================================================
# AGENT 3 : RECOMMANDATION D'ALTERNATIVES (renommé)
# ============================================================================

service_recommendation_agent = Agent(
    model=OpenAIModel('gpt-4o'),
    result_type=List[str],
    system_prompt="""
Conseiller pour proposer des services alternatifs COMPLÉMENTAIRES.

TÂCHE : Proposer 2-3 services alternatifs qui remplacent les services refusés.

RÈGLES CRITIQUES :
- Analyser les services DÉJÀ VALIDÉS pour éviter les doublons
- Proposer des alternatives qui COMPLÈTENT les services validés
- NE PAS proposer de services redondants avec ceux déjà validés
- Analyser l'historique pour comprendre les contraintes
- Compromis réalistes
- Format : liste de noms techniques précis

IMPORTANT : Si l'utilisateur a déjà un slice 5G validé, ne propose pas un autre slice.
Si un service de notification est validé, ne propose pas un autre service de notification similaire.
"""
)

# ============================================================================
# FONCTIONS UTILITAIRES
# ============================================================================

def load_service_full_json(service_id: str) -> Optional[Dict]:
    """Charge JSON complet service."""
    for json_file in CATALOG_DIR.glob("*.json"):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                service = json.load(f)
                if service.get('id') == service_id or service.get('name') == service_id:
                    return service
        except:
            continue
    return None

def extract_dependencies(service_json: Dict) -> List[ServiceDependency]:
    """Extrait dépendances CFSS uniquement."""
    dependencies = []
    
    for rel in service_json.get('serviceSpecRelationship', []):
        if rel.get('relationshipType') == 'dependsOn':
            spec = rel.get('serviceSpec', {})
            
            if spec.get('@referredType') == 'CustomerFacingServiceSpecification':
                dependencies.append(ServiceDependency(
                    name=spec.get('name', 'Unknown'),
                    id=spec.get('id', 'unknown'),
                    version=spec.get('version', '1.0.0'),
                    href=spec.get('href', '')
                ))
    
    return dependencies

def search_services_pinecone(query: str, top_k: int = 3, min_score: float = 0.5) -> List[ServiceCandidate]:
    """Recherche sémantique avec FILTRAGE par score minimum."""
    embedding = embedder.encode(query).tolist()
    results = index.query(
        vector=embedding,
        top_k=top_k * 2,
        include_metadata=True
    )
    
    candidates = []
    for match in results.matches:
        if match.score < min_score:
            continue
        
        meta = match.metadata
        service_id = meta.get("service_id", "unknown")
        
        service_full = load_service_full_json(service_id)
        dependencies = extract_dependencies(service_full) if service_full else []
        
        candidates.append(ServiceCandidate(
            service_id=service_id,
            name=meta.get("name", "Unknown"),
            description=meta.get("description", ""),
            score=round(match.score, 3),
            dependencies=dependencies
        ))
    
    return candidates[:top_k]

# ============================================================================
# WORKFLOW - ÉTAT GLOBAL 
# ============================================================================

class ConversationState:
    """État conversation avec historique complet."""
    def __init__(self):
        self.iteration = 0
        self.max_iterations = 5
        
        # Stocker TOUS les services identifiés
        self.all_services_identified: Dict[str, ServiceIdentified] = {}
        # Clé = nom du service, Valeur = ServiceIdentified avec propriétés
        
        self.candidats_par_service: Dict[str, List[ServiceCandidate]] = {}
        self.services_valides: Dict[str, ServiceCandidate] = {}
        self.historique: List[str] = []
        self.user_request_original: str = ""
    
    def add_to_history(self, message: str):
        self.historique.append(message)
    
    def increment_iteration(self) -> bool:
        """
        Incrémente l'itération.
        Returns: True si max atteint, False sinon
        """
        self.iteration += 1
        return self.iteration >= self.max_iterations
    
    def is_max_iterations_reached(self):
        return self.iteration >= self.max_iterations
    
    def add_identified_services(self, services: List[ServiceIdentified]):
        """
        Ajoute ou met à jour les services identifiés.
        Garde l'historique complet
        """
        for service in services:
            self.all_services_identified[service.nom] = service
    
    def get_all_identified_services(self) -> List[ServiceIdentified]:
        """Retourne tous les services identifiés (historique complet)."""
        return list(self.all_services_identified.values())
    
    def get_validated_service_names(self) -> List[str]:
        """Retourne les noms des services validés."""
        return list(self.services_valides.keys())

# ============================================================================
# FONCTIONS WORKFLOW
# ============================================================================

async def classify_and_route(user_request: str) -> Dict[str, Any]:
    """Étape 0 : Classification de la demande."""
    result = await classification_agent.run(user_request)
    classification = result.data.strip().upper()
    
    if classification == "GREETING":
        response = await polite_response_agent.run(
            f"Réponds à cette salutation : '{user_request}'. Propose ton aide pour services télécom 5G/cloud."
        )
        return {
            "type": "GREETING",
            "message": response.data
        }
    
    elif classification == "OUT_OF_SCOPE":
        response = await polite_response_agent.run(
            f"Explique poliment que tu ne peux pas aider avec : '{user_request}'. Rappelle ton expertise (télécom/5G/cloud)."
        )
        return {
            "type": "OUT_OF_SCOPE",
            "message": response.data
        }
    
    else:
        return {
            "type": "TELECOM",
            "message": "Demande télécom identifiée. Analyse en cours..."
        }

async def decompose_request(user_request: str) -> Decomposition:
    """Phase 1 : Décomposition."""
    result = await decomposition_agent.run(user_request)
    return result.data

async def search_candidates_for_services(decomposition: Decomposition) -> Dict[str, List[ServiceCandidate]]:
    """Phase 2 : Recherche candidats avec filtrage score."""
    candidats_par_service = {}
    
    for service_id in decomposition.services_identifies:
        query = f"{service_id.nom} {service_id.raison}"
        candidates = search_services_pinecone(query, top_k=3, min_score=0.2)
        candidats_par_service[service_id.nom] = candidates
    
    return candidats_par_service

async def reformulate_request(
    services_refuses: List[str], 
    services_valides: List[str],
    historique: List[str]
) -> str:
    """Phase 3 : Reformulation CIBLÉE sur services refusés uniquement."""
    context = f"""
Services DÉJÀ VALIDÉS (à ne pas mentionner) : {', '.join(services_valides)}

Services REFUSÉS (à clarifier) : {', '.join(services_refuses)}

Historique :
{chr(10).join(historique[-3:])}

Pose UNE question UNIQUEMENT sur les services refusés pour comprendre pourquoi 
l'utilisateur les a rejetés et pouvoir proposer des alternatives.
"""
    result = await reformulation_agent.run(context)
    return result.data

async def handle_clarification_with_merge(
    user_clarification: str,
    services_valides_noms: List[str],
    services_refuses: List[str],
    original_request: str
) -> Decomposition:
    """
    Gère la clarification en proposant UNIQUEMENT de nouveaux services.
    
    ✅ CORRECTION : Filtrage strict des services déjà validés.
    """
    targeted_request = f"""
CONTEXTE :
L'utilisateur a déjà VALIDÉ ces services (NE PAS les reproposer) :
{', '.join(services_valides_noms)}

Services REFUSÉS à améliorer :
{', '.join(services_refuses)}

DEMANDE ORIGINALE :
{original_request}

CLARIFICATION DE L'UTILISATEUR :
{user_clarification}

TÂCHE :
Propose UNIQUEMENT des services alternatifs ou améliorés pour les services refusés.
NE REPROPOSE PAS les services déjà validés : {', '.join(services_valides_noms)}
"""
    
    new_decomposition = await decompose_request(targeted_request)
    
    # Filtrer les doublons
    filtered_services = [
        service for service in new_decomposition.services_identifies
        if service.nom not in services_valides_noms
    ]
    
    return Decomposition(services_identifies=filtered_services)

async def recommend_alternatives(
    services_refuses: List[str],
    services_valides: List[str],
    historique: List[str]
) -> List[str]:
    """
    Phase 4 : Recommandation d'alternatives.
    
    ✅ CORRECTION : Prend en compte les services validés.
    """
    context = f"""
Services DÉJÀ VALIDÉS (ne pas reproposer de services similaires) :
{', '.join(services_valides)}

Services REFUSÉS (à remplacer) :
{', '.join(services_refuses)}

Historique :
{chr(10).join(historique)}

Propose 2-3 services alternatifs qui :
1. Remplacent les services refusés
2. Sont COMPLÉMENTAIRES aux services validés
3. Ne dupliquent PAS les fonctionnalités déjà couvertes
"""
    result = await service_recommendation_agent.run(context)
    return result.data

def generate_tmf921_intent(
    state: ConversationState
) -> TMF921Intent:
    """
    Phase 5 : Génération TMF921.
    """
    
    intent_name = f"UserRequest_{len(state.services_valides)}_Services"
    
    # Delivery Expectations
    delivery_expectations = {}
    
    for service_name, candidate in state.services_valides.items():
        target_id = f"T_{candidate.service_id}"
        exp_id = f"E_Delivery_{candidate.service_id}"
        
        delivery_expectations[exp_id] = {
            "@type": "icm:DeliveryExpectation",
            "icm:target": f"ex:{target_id}",
            "icm:targetType": f"cat:{candidate.name}"
        }
        
        # Dépendances CFSS
        for dep in candidate.dependencies:
            dep_target_id = f"T_dep_{dep.id}"
            dep_exp_id = f"E_Delivery_dep_{dep.id}"
            
            delivery_expectations[dep_exp_id] = {
                "@type": "icm:DeliveryExpectation",
                "icm:target": f"ex:{dep_target_id}",
                "icm:targetType": f"cat:{dep.name}",
                "icm:requiredBy": f"ex:{target_id}"
            }
    
    # Property Expectations
    property_expectations = {}
    all_characteristics = []
    
    #  les propriétés
    for service_identified in state.get_all_identified_services():
        candidate = state.services_valides.get(service_identified.nom)
        
        if candidate and service_identified.proprietes:
            target_id = f"T_{candidate.service_id}"
            
            for prop_name, prop_value in service_identified.proprietes.items():
                exp_id = f"E_Property_{prop_name}_{candidate.service_id}"
                constraint = build_constraint(prop_name, prop_value)
                
                property_expectations[exp_id] = {
                    "@type": "icm:PropertyExpectation",
                    "icm:target": f"ex:{target_id}",
                    "icm:constraint": constraint
                }
                
                all_characteristics.append({
                    "name": prop_name,
                    "value": prop_value,
                    "valueType": type(prop_value).__name__,
                    "relatedService": service_identified.nom
                })
    
    # Intent final
    intent = TMF921Intent(
        name=intent_name,
        description=state.user_request_original[:100],
        isBundled=len(state.services_valides) > 1,
        characteristic=[],
        expression={
            "@type": "JsonLdExpression",
            "expressionValue": {
                "@context": {
                    "icm": "http://www.models.tmforum.org/tio/v1.0.0/IntentCommonModel#",
                    "cat": "http://www.operator.com/Catalog#",
                    "ex": "http://www.example.com/intent#",
                    "cem": "http://www.example.com/commonModel#"
                },
                f"ex:{intent_name}": {
                    "@type": "icm:Intent",
                    "icm:intentOwner": "ex:AutomatedAgent",
                    "icm:hasExpectation": {
                        **delivery_expectations,
                        **property_expectations
                    }
                }
            }
        }
    )
    
    return intent

def build_constraint(prop_name: str, prop_value: Any) -> Dict[str, Any]:
    """Construit constraint ICM."""
    
    if isinstance(prop_value, str):
        parsed = parse_value_with_unit(prop_value)
        if parsed:
            value, unit = parsed
            operator = infer_operator(prop_name)
            
            return {
                f"icm:{operator}": {
                    "icm:ValueOf": f"cem:{prop_name}",
                    "icm:value": value,
                    "cem:unit": unit
                }
            }
    
    if isinstance(prop_value, dict) and "min" in prop_value and "max" in prop_value:
        return {
            "icm:between": {
                "icm:ValueOf": f"cem:{prop_name}",
                "icm:min": prop_value["min"],
                "icm:max": prop_value["max"],
                "cem:unit": prop_value.get("unit", "")
            }
        }
    
    if isinstance(prop_value, dict) and ("min" in prop_value or "max" in prop_value):
        operator = "greater" if "min" in prop_value else "smaller"
        value_key = "min" if "min" in prop_value else "max"
        
        return {
            f"icm:{operator}": {
                "icm:ValueOf": f"cem:{prop_name}",
                "icm:value": prop_value[value_key],
                "cem:unit": prop_value.get("unit", "")
            }
        }
    
    return {
        "icm:equals": {
            "icm:ValueOf": f"cem:{prop_name}",
            "icm:value": prop_value
        }
    }

def parse_value_with_unit(value_str: str) -> Optional[tuple]:
    """Parse '10ms', '100Mbps', etc."""
    import re
    
    match = re.match(r'^([0-9.]+)\s*([a-zA-Z%]+)$', value_str.strip())
    if match:
        num_str, unit = match.groups()
        try:
            value = float(num_str) if '.' in num_str else int(num_str)
            return (value, unit)
        except:
            return None
    return None

def infer_operator(prop_name: str) -> str:
    """Infère opérateur selon propriété."""
    prop_lower = prop_name.lower()
    
    if any(k in prop_lower for k in ['latence', 'latency', 'delay', 'jitter']):
        return 'smaller'
    
    if any(k in prop_lower for k in ['debit', 'bandwidth', 'throughput', 'disponibilite', 'availability']):
        return 'greater'
    
    return 'equals'