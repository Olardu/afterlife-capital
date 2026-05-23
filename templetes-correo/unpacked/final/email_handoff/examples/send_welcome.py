"""
Ejemplo: enviar email de bienvenida.

Uso:
    export RESEND_API_KEY="re_xxxxxxxx"
    python examples/send_welcome.py
"""
import sys
from pathlib import Path

# Permitir importar emails.py desde python/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

from emails import send_welcome_email

if __name__ == "__main__":
    # Cambiá estos valores antes de correr
    test_email = "test@example.com"
    test_role = "VIEWER"   # o "ADMIN"

    print(f"Enviando welcome a {test_email} (role={test_role})...")
    result = send_welcome_email(email=test_email, role=test_role)
    print(f"OK → message id: {result.get('id')}")
