# crypto_utils.py
# Helpers de encriptación simétrica (Fernet/AES-128-CBC + HMAC) para
# almacenar API keys en la tabla api_keys (#FIX-008).
#
# La master key se lee de MASTER_ENCRYPTION_KEY en .env. NUNCA debe
# commitearse al repo. Si se pierde, se pierden todas las API keys
# encriptadas y hay que repoblarlas desde el .env actual.
#
# Generar una master key nueva:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

import os

from cryptography.fernet import Fernet, InvalidToken


_ENV_VAR = "MASTER_ENCRYPTION_KEY"


def _get_fernet() -> Fernet:
    """
    Construye un Fernet desde MASTER_ENCRYPTION_KEY del entorno.

    Raises:
        RuntimeError si la variable no está seteada o no es válida.
    """
    key = os.environ.get(_ENV_VAR)
    if not key:
        raise RuntimeError(
            f"{_ENV_VAR} no está en .env. Generala con: "
            "python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\""
        )
    try:
        return Fernet(key.encode("utf-8") if isinstance(key, str) else key)
    except (ValueError, TypeError) as e:
        raise RuntimeError(
            f"{_ENV_VAR} no es una key Fernet válida (debe ser 32 bytes "
            f"base64-encoded url-safe): {e}"
        )


def encrypt(plaintext: str) -> str:
    """Encripta un string con la master key. Retorna ciphertext base64."""
    if plaintext is None:
        raise ValueError("plaintext no puede ser None")
    return _get_fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt(ciphertext: str) -> str:
    """
    Desencripta un ciphertext producido por encrypt().

    Raises:
        InvalidToken si el ciphertext fue manipulado o usa otra key.
        RuntimeError si la master key no está configurada.
    """
    if ciphertext is None:
        raise ValueError("ciphertext no puede ser None")
    try:
        return _get_fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        raise


def mask(plaintext: str) -> str:
    """
    Retorna una representación enmascarada para mostrar en UI:
    primeros 4 + '****' + últimos 4. Para keys cortas, todo asteriscos.
    """
    if plaintext is None:
        return ""
    n = len(plaintext)
    if n <= 8:
        return "*" * n
    return f"{plaintext[:4]}****{plaintext[-4:]}"
