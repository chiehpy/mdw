from fastapi import FastAPI, HTTPException, Header, Request
from pydantic import BaseModel, Field
from typing import Optional
from .salesforce_client import update_serial_in_salesforce
import json
from pathlib import Path
import logging

# ========== LOGGING ==========
logger = logging.getLogger("mdw")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)

app = FastAPI(title="Middleware Técnicos → Salesforce")


# ========== MIDDLEWARE DE LOG GLOBAL ==========
@app.middleware("http")
async def log_requests(request: Request, call_next):
    # Log de entrada
    logger.info(f"👉 {request.method} {request.url.path}")

    # Para debug: loguear headers básicos
    logger.info(f"Headers: {dict(request.headers)}")

    # Si querés ver el body crudo de TODO, descomentá esto (ojo que consume el body):
    # body_bytes = await request.body()
    # logger.info(f"Raw body: {body_bytes.decode('utf-8')}")
    # request = Request(request.scope, receive=lambda: {"type": "http.request", "body": body_bytes})

    response = await call_next(request)

    # Log de salida
    logger.info(f"👈 {request.method} {request.url.path} -> {response.status_code}")
    return response


# ===== Modelos de entrada/salida =====

class ProcessSerialRequest(BaseModel):
    serial: str = Field(..., min_length=1)
    technicianName: str = Field(..., min_length=1)
    role: str = Field(..., min_length=1)


class ProcessSerialResponse(BaseModel):
    ok: bool
    message: str
    salesforce_id: Optional[str] = None
    error_code: Optional[str] = None


# ===== Modelos para LOGIN =====

class LoginRequest(BaseModel):
    username: str
    password: str


class UserInfo(BaseModel):
    username: str
    technicianName: str
    role: str
    email: Optional[str] = None


class LoginResponse(BaseModel):
    ok: bool
    message: str
    user: Optional[UserInfo] = None
    error_code: Optional[str] = None


# API key simple para que solo la app de técnicos pueda llamar
API_KEY = "123"  # luego lo pasamos a .env


# "Base de datos" dummy de usuarios (solo para desarrollo)
USERS_DB_PATH = Path("config/users.json")


def load_users_db() -> dict:
    """
    Carga la base de usuarios desde un archivo JSON.
    Si falla, devuelve un dict vacío.
    """
    try:
        with USERS_DB_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                logger.info(f"USERS_DB cargada con {len(data)} usuarios desde {USERS_DB_PATH}")
                return data
            logger.warning("users.json no contiene un objeto dict en la raíz")
            return {}
    except FileNotFoundError:
        logger.warning(f"Archivo de usuarios no encontrado: {USERS_DB_PATH}")
        return {}
    except json.JSONDecodeError as e:
        logger.error(f"Error parseando users.json: {e}")
        return {}


# Cargamos una vez al iniciar la app
USERS_DB = load_users_db()


# ===== Endpoint LOGIN =====

@app.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    x_api_key: Optional[str] = Header(default=None),
):
    logger.info(f"🔐 /login llamado con username={payload.username}")

    # 1) Validar API key
    if x_api_key != API_KEY:
        logger.warning(f"/login API key inválida: {x_api_key}")
        raise HTTPException(status_code=401, detail="API key inválida")

    # 2) Buscar usuario
    user = USERS_DB.get(payload.username)

    if not user or payload.password != user["password"]:
        logger.warning(
            f"Intento de login fallido para username={payload.username}"
        )
        return LoginResponse(
            ok=False,
            message="Usuario o contraseña incorrectos",
            user=None,
            error_code="INVALID_CREDENTIALS",
        )

    # 3) Login OK → armar objeto user
    user_info = UserInfo(
        username=payload.username,
        technicianName=user["technicianName"],
        role=user["role"],
        email=user.get("email"),
    )

    logger.info(
        f"Login exitoso para username={payload.username}, "
        f"technicianName={user['technicianName']}, role={user['role']}"
    )

    return LoginResponse(
        ok=True,
        message="Login exitoso",
        user=user_info,
        error_code=None,
    )


# ===== Endpoint PROCESS-SERIAL =====

@app.post("/process-serial", response_model=ProcessSerialResponse)
async def process_serial(
    payload: ProcessSerialRequest,
    x_api_key: Optional[str] = Header(default=None),
):
    # 👇 log explícito del JSON que envía la app
    logger.info(f"📦 /process-serial JSON recibido: {payload.dict()}")

    logger.info(
        f"🚚 /process-serial llamado con serial={payload.serial}, "
        f"technicianName={payload.technicianName}, role={payload.role}"
    )

    # 1) Seguridad básica
    if x_api_key != API_KEY:
        logger.warning(f"/process-serial API key inválida: {x_api_key}")
        raise HTTPException(status_code=401, detail="API key inválida")

    # 3) Llamada a la "capa Salesforce"
    try:
        result = await update_serial_in_salesforce(
            serial=payload.serial,
            technicianName=payload.technicianName,
            role=payload.role,
        )
    except Exception as e:
        logger.exception(f"Error interno llamando a Salesforce: {e}")
        return ProcessSerialResponse(
            ok=False,
            message="Error interno llamando a Salesforce",
            error_code="SF_INTERNAL_ERROR",
        )

    # 4) Interpretar el resultado normalizado de salesforce_client
    if result.get("success"):
        logger.info(
            f"/process-serial éxito para serial={payload.serial}, "
            f"salesforce_id={result.get('salesforce_id')}"
        )
        return ProcessSerialResponse(
            ok=True,
            message=result.get(
                "message",
                f"Serial {payload.serial} actualizado correctamente en Salesforce",
            ),
            salesforce_id=result.get("salesforce_id"),
        )

    logger.warning(
        f"/process-serial error para serial={payload.serial}, "
        f"message={result.get('message')}, error_code={result.get('error_code')}"
    )

    return ProcessSerialResponse(
        ok=False,
        message=result.get("message", "Error desconocido en Salesforce"),
        error_code=result.get("error_code"),
    )
