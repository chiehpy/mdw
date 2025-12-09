from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel, Field
from typing import Optional
from .salesforce_client import update_serial_in_salesforce

app = FastAPI(title="Middleware Técnicos → Salesforce")

# ===== Modelos de entrada/salida =====

class ProcessSerialRequest(BaseModel):
    serial: str = Field(..., min_length=1)
    username: str = Field(..., min_length=1)
    role: str = Field(..., min_length=1)


class ProcessSerialResponse(BaseModel):
    ok: bool
    message: str
    salesforce_id: Optional[str] = None
    error_code: Optional[str] = None


# API key simple para que solo la app de técnicos pueda llamar
API_KEY = "CAMBIA_ESTA_CLAVE"  # luego lo pasamos a .env


@app.post("/process-serial", response_model=ProcessSerialResponse)
async def process_serial(
    payload: ProcessSerialRequest,
    x_api_key: Optional[str] = Header(default=None),
):
    # 1) Seguridad básica
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="API key inválida")

    # 2) Validación extra de role (además de que no esté vacío)
    if payload.role not in ("ROL_A", "ROL_B", "ROL_C"):
        return ProcessSerialResponse(
            ok=False,
            message=f"Role desconocido: {payload.role}",
            error_code="INVALID_ROLE",
        )

    # 3) Llamada a la "capa Salesforce" (por ahora dummy)
    try:
        result = await update_serial_in_salesforce(
            serial=payload.serial,
            username=payload.username,
            role=payload.role,
        )
    except Exception:
        # Aquí luego podemos loguear mejor
        return ProcessSerialResponse(
            ok=False,
            message="Error interno llamando a Salesforce",
            error_code="SF_INTERNAL_ERROR",
        )

    # 4) Interpretar el resultado
    if result.get("success"):
        return ProcessSerialResponse(
            ok=True,
            message=f"Serial {payload.serial} actualizado correctamente en Salesforce",
            salesforce_id=result.get("salesforce_id"),
        )

    return ProcessSerialResponse(
        ok=False,
        message=result.get("message", "Error desconocido en Salesforce"),
        error_code=result.get("error_code"),
    )
