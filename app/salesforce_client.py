import os
from typing import Dict, Any

import httpx

# === CONFIGURACIÓN SALESFORCE ===

SF_BASE_URL = "https://enofir--sbxenof.sandbox.my.salesforce.com"
SF_ENDPOINT = f"{SF_BASE_URL}/services/apexrest/enofir/v1/terminal-action"
SF_TOKEN_URL = f"{SF_BASE_URL}/services/oauth2/token"

SF_CLIENT_ID = os.getenv("SF_CLIENT_ID")         # Consumer Key
SF_CLIENT_SECRET = os.getenv("SF_CLIENT_SECRET") # Consumer Secret

# Cache simple de token en memoria
_SF_ACCESS_TOKEN: str | None = None


async def _get_salesforce_token() -> str:
    """
    Pide un access_token a Salesforce usando client_credentials.
    En esta etapa de testeo, pedimos uno nuevo cuando hace falta.
    """
    global _SF_ACCESS_TOKEN

    if not SF_CLIENT_ID or not SF_CLIENT_SECRET:
        raise RuntimeError("Faltan SF_CLIENT_ID / SF_CLIENT_SECRET en variables de entorno")

    data = {
        "grant_type": "client_credentials",
        "client_id": SF_CLIENT_ID,
        "client_secret": SF_CLIENT_SECRET,
    }

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(SF_TOKEN_URL, data=data)

    if resp.status_code != 200:
        raise RuntimeError(f"Error al obtener token de Salesforce: {resp.status_code} - {resp.text}")

    token_json = resp.json()
    access_token = token_json.get("access_token")
    if not access_token:
        raise RuntimeError(f"Respuesta de token sin access_token: {token_json}")

    _SF_ACCESS_TOKEN = access_token
    return access_token


async def _call_salesforce_terminal_action(payload: Dict[str, Any]) -> httpx.Response:
    """
    Llama al endpoint Apex REST usando el token cacheado.
    Si recibe 401, pide un token nuevo y reintenta una vez.
    """
    global _SF_ACCESS_TOKEN

    # 1) Asegurarse de tener token
    if not _SF_ACCESS_TOKEN:
        _SF_ACCESS_TOKEN = await _get_salesforce_token()

    headers = {
        "Authorization": f"Bearer {_SF_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(SF_ENDPOINT, json=payload, headers=headers)

        # Si el token falló (expiró / fue revocado), pedimos otro y reintentamos una vez
        if resp.status_code == 401:
            _SF_ACCESS_TOKEN = await _get_salesforce_token()
            headers["Authorization"] = f"Bearer {_SF_ACCESS_TOKEN}"
            resp = await client.post(SF_ENDPOINT, json=payload, headers=headers)

    return resp


async def update_serial_in_salesforce(serial: str, technicianName: str, role: str) -> Dict[str, Any]:
    """
    Llama al endpoint Apex REST /enofir/v1/terminal-action
    y normaliza la respuesta para el middleware.
    """

    payload = {
        "serialNumber": serial,
        "role": role,                     # "Limpieza" o "Programación"
        "technicianName": technicianName  # Debe matchear el picklist
    }

    response = await _call_salesforce_terminal_action(payload)

    # Intentar parsear JSON
    try:
        sf_resp = response.json()
    except Exception:
        return {
            "success": False,
            "message": f"Salesforce devolvió una respuesta no válida (HTTP {response.status_code})",
            "salesforce_id": None,
            "error_code": "SF_INVALID_JSON"
        }

    # Éxito (tu Apex ya devuelve success=true cuando todo sale bien)
    if response.status_code == 200 and sf_resp.get("success") is True:
        return {
            "success": True,
            "message": sf_resp.get("message", "Acción realizada correctamente."),
            "salesforce_id": sf_resp.get("caseId"),
            "error_code": None,
        }

    # Error (mensaje desde tu Apex o genérico)
    return {
        "success": False,
        "message": sf_resp.get("message", f"Error en Salesforce (HTTP {response.status_code})"),
        "salesforce_id": sf_resp.get("caseId"),
        "error_code": sf_resp.get("error_code") or f"SF_{response.status_code}",
    }
