# ingest_catalog.py
import os
import json
import re
from pathlib import Path
from tqdm import tqdm
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from pinecone import Pinecone, ServerlessSpec
import sys
import unicodedata

load_dotenv()

# Modèle d'embedding local (gratuit et excellent)
embedder = SentenceTransformer('all-MiniLM-L6-v2')

# Initialisation du client Pinecone
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))

index_name = os.getenv("PINECONE_INDEX_NAME", "telecom-catalog11")

# Path absolu sécurisé
CATALOG_DIR = Path(__file__).parent / "catalog1"

# Vérification de l'existence du dossier
if not CATALOG_DIR.exists():
    print(f"❌ ERREUR : Le dossier catalog n'existe pas à {CATALOG_DIR.absolute()}")
    print(f"💡 Créez le dossier et placez-y vos fichiers JSON TMF633")
    sys.exit(1)

# Vérification qu'il contient des fichiers JSON
json_files = list(CATALOG_DIR.glob("*.json"))
if not json_files:
    print(f"❌ ERREUR : Aucun fichier JSON trouvé dans {CATALOG_DIR.absolute()}")
    print(f"💡 Ajoutez vos services au format TMF633 (*.json) dans ce dossier")
    sys.exit(1)

print(f"✅ Dossier catalog trouvé : {CATALOG_DIR.absolute()}")
print(f"📁 {len(json_files)} fichier(s) JSON détecté(s)")


def sanitize_id(text: str) -> str:
    """
    Normaliser les IDs pour Pinecone (ASCII uniquement)
    - Supprime les accents (é → e, à → a)
    - Remplace les tirets spéciaux (–, —) par des tirets normaux (-)
    - Supprime tous les caractères non-ASCII restants
    - Remplace les espaces par des underscores
    """
    if not text:
        return "unknown_service"
    
    # Normalisation Unicode (NFD = décomposition, NFKD = compatible)
    text = unicodedata.normalize('NFKD', text)
    
    # Suppression des accents (catégorie Mn = Mark, Nonspacing)
    text = ''.join(c for c in text if not unicodedata.combining(c))
    
    # Remplacement des tirets spéciaux (–, —) par tiret normal
    text = text.replace('–', '-').replace('—', '-').replace('−', '-')
    
    # Suppression de tous les caractères non-ASCII
    text = text.encode('ascii', 'ignore').decode('ascii')
    
    # Nettoyage final
    text = re.sub(r'[^\w\s-]', '', text)  # Garder uniquement lettres, chiffres, -, _
    text = re.sub(r'\s+', '_', text)       # Espaces → underscores
    text = re.sub(r'_+', '_', text)        # Multiples underscores → 1 seul
    text = text.strip('_-').lower()        # Supprime _ ou - en début/fin
    
    return text or "unknown_service"

def generate_summary(service_json: dict) -> str:
    """
    Texte optimisé pour embedding sémantique :
    - Forte priorité à la description (répétée)
    - Nom du service
    - Caractéristiques : nom + description courte + valeur(s) / plage / ensemble
    """
    # Extraction des champs principaux
    description = (service_json.get("description") or "").strip()
    name = (service_json.get("name") or "").strip()
    parts = []

    # ────────────────────────────────────────────────
    # 1. Description → poids très fort (x2 ou x3)
    # ────────────────────────────────────────────────
    if description:
        parts.append(description)
        parts.append(description)               # double pour renforcer
        # parts.append(description)             # option : x3 si la desc est courte

    # ────────────────────────────────────────────────
    # 2. Nom du service
    # ────────────────────────────────────────────────
    if name:
        parts.append(f"Service : {name}")

    # ────────────────────────────────────────────────
    # 3. Caractéristiques (point central de l'amélioration)
    # ────────────────────────────────────────────────
    char_lines = []

    for char in service_json.get("serviceSpecCharacteristic", []):
        char_name        = char.get("name", "").strip()
        char_desc        = (char.get("description") or "").strip()
        value_type       = char.get("valueType", "").upper()
        configurable     = char.get("configurable", False)

        # On saute les caractéristiques vides ou très techniques sans valeur métier
        if not char_name or not any(v.get("value") for v in char.get("serviceSpecCharacteristicValue", [])):
            continue

        # Préparation du texte de la valeur(s)
        value_strs = []

        for val_item in char.get("serviceSpecCharacteristicValue", []):
            v = val_item.get("value", {}) if isinstance(val_item.get("value"), dict) else {}
            alias = v.get("alias", "").strip()
            raw_value = v.get("value", "")

            # Cas 1 : alias présent → on le préfère (plus lisible)
            if alias:
                disp_value = alias
                if raw_value and str(raw_value) != alias:
                    disp_value += f" ({raw_value})"
            else:
                disp_value = str(raw_value) if raw_value else ""

            # Cas 2 : plage de valeurs
            if "valueFrom" in val_item and "valueTo" in val_item:
                from_v = val_item.get("valueFrom")
                to_v   = val_item.get("valueTo")
                if from_v is not None and to_v is not None:
                    disp_value = f"{from_v} – {to_v}"

            value_strs.append(disp_value)

        # Nettoyage & déduplication
        value_strs = [s.strip() for s in value_strs if s.strip()]
        value_strs = list(dict.fromkeys(value_strs))   # ordre préservé, pas de doublons

        if not value_strs:
            continue

        # Format final de la caractéristique
        values_joined = " | ".join(value_strs)

        # On préfère la description courte si elle existe, sinon le nom
        label = char_desc or char_name

        # Ajout d'un indicateur configurable quand c'est pertinent
        prefix = "configurable • " if configurable else ""

        line = f"{prefix}{label} : {values_joined}"
        char_lines.append(line)

    # Ajout du bloc caractéristiques
    if char_lines:
        parts.append("Caractéristiques principales :")
        parts.extend(char_lines[:25])           # limite arbitraire pour éviter de noyer l'embedding

    # ────────────────────────────────────────────────

    # Fallback minimal
    if len(parts) < 2 and name:
        parts.append(name)

    # ────────────────────────────────────────────────
    # Texte final
    # ────────────────────────────────────────────────
    text = " ".join(parts)
    return text.lower()


def create_index_if_not_exists():
    """Création de l'index Pinecone avec gestion d'erreurs"""
    try:
        existing_indexes = pc.list_indexes().names()
        
        if index_name not in existing_indexes:
            print(f"🔨 Création de l'index '{index_name}' (Serverless AWS)...")
            pc.create_index(
                name=index_name,
                dimension=384,  # Dimension du modèle all-MiniLM-L6-v2
                metric="cosine",
                spec=ServerlessSpec(
                    cloud="aws",
                    region="us-east-1"  # Changez selon votre région préférée
                )
            )
            print(f"✅ Index '{index_name}' créé avec succès")
        else:
            print(f"✅ Index '{index_name}' existe déjà")
    
    except Exception as e:
        print(f"❌ Erreur lors de la création de l'index : {e}")
        sys.exit(1)


def ingest():
    """
    Ingestion avec priorité à la description des services
    """
    # Création de l'index si nécessaire
    create_index_if_not_exists()
    
    # Connexion à l'index
    try:
        index = pc.Index(index_name)
        print(f"✅ Connecté à l'index '{index_name}'")
    except Exception as e:
        print(f"❌ Erreur de connexion à l'index : {e}")
        sys.exit(1)
    
    vectors_to_upsert = []
    skipped_files = []
    services_without_description = []
    
    print(f"\n🔄 Traitement des fichiers JSON...")
    
    for json_file in tqdm(json_files, desc="Parsing JSON"):
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                service = json.load(f)
            
            # Sanitize l'ID avant de l'utiliser
            raw_id = service.get("id") or service.get("name", "")
            service_id = sanitize_id(raw_id)
            
            if not service_id or service_id == "unknown_service":
                print(f"⚠️  Fichier ignoré (ID invalide après sanitization) : {json_file.name}")
                skipped_files.append(json_file.name)
                continue
            
            # Vérification de la présence de la description
            description = service.get("description", "").strip()
            if not description:
                services_without_description.append(service.get("name", service_id))
            
            # Génération du résumé optimisé (basé sur description)
            summary = generate_summary(service)
            
            # Génération de l'embedding
            embedding = embedder.encode(summary).tolist()
            
            # Préparation des métadonnées (limitées à 40KB par vecteur)
            metadata = {
                "service_id": service_id,
                "name": service.get("name", "")[:500],
                "description": description[:2000],  # ✅ Description complète stockée
                "summary": summary[:2000]  # Pour debug si nécessaire
            }
            
            vectors_to_upsert.append((service_id, embedding, metadata))
        
        except json.JSONDecodeError as e:
            print(f"⚠️  Fichier JSON invalide : {json_file.name} ({e})")
            skipped_files.append(json_file.name)
        except Exception as e:
            print(f"⚠️  Erreur lors du traitement de {json_file.name} : {e}")
            skipped_files.append(json_file.name)
    
    if not vectors_to_upsert:
        print("❌ Aucun service valide à indexer")
        sys.exit(1)
    
    # Upsert par batch avec gestion d'erreurs
    print(f"\n📤 Indexation de {len(vectors_to_upsert)} services dans Pinecone...")
    
    batch_size = 100
    success_count = 0
    failed_batches = []
    
    for i in tqdm(range(0, len(vectors_to_upsert), batch_size), desc="Upsert batches"):
        batch = vectors_to_upsert[i:i + batch_size]
        try:
            index.upsert(vectors=batch)
            success_count += len(batch)
        except Exception as e:
            print(f"⚠️  Erreur lors de l'upsert du batch {i//batch_size + 1} : {e}")
            failed_batches.append(i//batch_size + 1)
            
            # Affichage des IDs problématiques pour debug
            print(f"   IDs du batch échoué : {[v[0] for v in batch[:3]]}...")
    
    # Statistiques finales
    print(f"\n{'='*60}")
    print(f"✅ Indexation terminée !")
    print(f"   • Services indexés : {success_count}/{len(json_files)}")
    print(f"   • Fichiers ignorés : {len(skipped_files)}")
    if skipped_files:
        print(f"   • Liste des fichiers ignorés : {', '.join(skipped_files)}")
    if services_without_description:
        print(f"   ⚠️  Services sans description : {len(services_without_description)}")
        print(f"      {', '.join(services_without_description[:5])}")
        if len(services_without_description) > 5:
            print(f"      ... et {len(services_without_description) - 5} autres")
    if failed_batches:
        print(f"   ⚠️  Batches échoués : {failed_batches}")
    print(f"   • Index Pinecone : '{index_name}'")
    print(f"{'='*60}\n")
    
    # Test de recherche pour validation
    if success_count > 0:
        print("🧪 Test de validation (recherche 'service de notification')...")
        try:
            test_embedding = embedder.encode("Slice 5G uRLLC (Ultra-Reliable Low Latency Communication) ").tolist()
            test_results = index.query(
                vector=test_embedding,
                top_k=3,
                include_metadata=True
            )
            
            if test_results.matches:
                print(f"✅ Test réussi ! Top 3 résultats :")
                for match in test_results.matches:
                    print(f"   • {match.metadata['name']} (score: {match.score:.3f})")
                    desc_preview = match.metadata.get('description', '')[:80]
                    if desc_preview:
                        print(f"     → {desc_preview}...")
            else:
                print("⚠️  Aucun résultat trouvé (index peut-être vide)")
        except Exception as e:
            print(f"⚠️  Erreur lors du test : {e}")


if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════════╗
║   Ingestion Catalog TMF633 → Pinecone (Description-Based)   ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    # Vérification des variables d'environnement
    if not os.getenv("PINECONE_API_KEY"):
        print("❌ ERREUR : Variable PINECONE_API_KEY non définie dans .env")
        sys.exit(1)
    
    try:
        ingest()
    except KeyboardInterrupt:
        print("\n⚠️  Ingestion interrompue par l'utilisateur")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Erreur fatale : {e}")
        sys.exit(1)