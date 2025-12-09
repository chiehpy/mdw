from typing import Dict


async def update_serial_in_salesforce(serial: str, username: str, role: str) -> Dict:
    """
    Función dummy: simula una llamada a Salesforce.
    Más adelante acá vamos a hacer la llamada real al endpoint de Salesforce.
    """

    # Caso de prueba: si el serial es "ERROR123", simulamos un error en Salesforce
    if serial == "ERROR123":
        return {
            "success": False,
            "message": "Serial no encontrado en Salesforce",
            "error_code": "SF_RECORD_NOT_FOUND",
        }

    # Caso normal: simulamos éxito
    return {
        "success": True,
        "salesforce_id": "a0BXXXXXXXXXXXXXXX",  # ID falso de ejemplo
    }
