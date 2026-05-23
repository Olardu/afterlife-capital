"""
Ejemplo: enviar email de acceso revocado.

Uso:
    export RESEND_API_KEY="re_xxxxxxxx"
    python examples/send_revoked.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

from emails import send_access_revoked_email

if __name__ == "__main__":
    test_email = "test@example.com"

    print(f"Enviando revoked a {test_email}...")
    result = send_access_revoked_email(email=test_email)
    print(f"OK → message id: {result.get('id')}")
