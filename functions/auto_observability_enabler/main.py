import base64
import json
import logging
import os
import re
import urllib.request
import functions_framework
import google.auth
from google.auth.transport.requests import Request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("auto_observability_enabler")

def get_auth_token():
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(Request())
    return creds.token

def patch_agent_observability(agent_resource_name, location="eu", project_id=None):
    """
    Wywołuje Discovery Engine API PATCH aby włączyć observabilityConfig.observabilityEnabled: true.
    agent_resource_name ma postać:
    projects/{proj}/locations/{loc}/collections/default_collection/engines/{engine}/assistants/default_assistant/agents/{agent_id}
    """
    token = get_auth_token()
    
    # Określ lokalizację z nazwy zasobu lub domyślnej
    loc_match = re.search(r"locations/([a-zA-Z0-9_\-]+)", agent_resource_name)
    loc = loc_match.group(1) if loc_match else location
    
    api_host = f"{loc}-discoveryengine.googleapis.com" if loc != "global" else "discoveryengine.googleapis.com"
    url = f"https://{api_host}/v1alpha/{agent_resource_name}?updateMask=observabilityConfig"
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    if project_id:
        headers["X-Goog-User-Project"] = project_id
    
    payload = {
        "observabilityConfig": {
            "observabilityEnabled": True
        }
    }
    
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="PATCH")
    try:
        with urllib.request.urlopen(req) as resp:
            logger.info(f"Pomyślnie włączono obserwowalność dla agenta: {agent_resource_name} (Status: {resp.status})")
            return True
    except Exception as e:
        logger.error(f"Błąd podczas włączania obserwowalności dla {agent_resource_name}: {e}")
        raise e

def reconcile_all_agents(project_id, location, engine_id):
    """
    Listuje wszystkich agentów w silniku i włącza obserwowalność na każdym, który ma observabilityEnabled != True.
    """
    token = get_auth_token()
    api_host = f"{location}-discoveryengine.googleapis.com" if location != "global" else "discoveryengine.googleapis.com"
    url = f"https://{api_host}/v1alpha/projects/{project_id}/locations/{location}/collections/default_collection/engines/{engine_id}/assistants/default_assistant/agents"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "X-Goog-User-Project": project_id})
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            agents = data.get("agents", [])
            logger.info(f"Sprawdzam {len(agents)} agentów w silniku {engine_id}...")
            count_patched = 0
            for a in agents:
                a_name = a.get("name")
                obs = a.get("observabilityConfig") or {}
                if not obs.get("observabilityEnabled"):
                    logger.info(f"Agent {a_name} ({a.get('displayName')}) nie ma włączonej obserwowalności. Włączam...")
                    patch_agent_observability(a_name, location=location, project_id=project_id)
                    count_patched += 1
                else:
                    logger.info(f"Agent {a_name} ({a.get('displayName')}) ma już aktywną obserwowalność.")
            logger.info(f"Zakończono weryfikację. Zaktualizowano agentów: {count_patched}")
            return count_patched
    except Exception as e:
        logger.error(f"Błąd podczas listowania agentów: {e}")
        raise e

@functions_framework.cloud_event
def auto_enable_observability(cloud_event):
    """
    Trigger Pub/Sub: odbiera log CreateAgent z Cloud Audit Logs i włącza obserwowalność na agencie.
    """
    try:
        pubsub_message = cloud_event.data.get("message", {})
        data_encoded = pubsub_message.get("data")
        if not data_encoded:
            logger.warning("Brak danych w wiadomości Pub/Sub")
            return
            
        data_str = base64.b64decode(data_encoded).decode("utf-8")
        payload = json.loads(data_str)
        
        # Sprawdź czy to polecenie reconciliacji
        if payload.get("action") == "reconcile":
            proj = payload.get("project_id") or os.environ.get("GCP_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT")
            loc = payload.get("location") or os.environ.get("LOCATION") or "eu"
            eng = payload.get("engine_id") or os.environ.get("ENGINE_ID")
            if proj and eng:
                reconcile_all_agents(proj, loc, eng)
                return
        
        proto_payload = payload.get("protoPayload", {})
        method_name = proto_payload.get("methodName", "")
        
        if "AgentService.CreateAgent" not in method_name:
            logger.info(f"Zignorowano metodę: {method_name}")
            return
            
        # Wyciągnięcie nazwy zasobu agenta z odpowiedzi CreateAgent
        resp = proto_payload.get("response", {})
        agent_name = resp.get("name")
        
        if not agent_name:
            logger.warning("Brak pola 'name' w protoPayload.response.")
            return
            
        project_id = payload.get("resource", {}).get("labels", {}).get("project_id") or os.environ.get("GCP_PROJECT")
        logger.info(f"Wykryto nowego agenta: {agent_name}. Włączam obserwowalność...")
        patch_agent_observability(agent_name, project_id=project_id)
        
    except Exception as e:
        logger.error(f"Nieoczekiwany błąd w funkcji auto_enable_observability: {e}")
        raise e
