"""Load synthetic demo credentials without putting a reusable password in Git."""

import json
import os
from pathlib import Path

CREDENTIALS_PATH = Path(__file__).resolve().parents[1] / ".tmp" / "demo-credentials.json"


def get_demo_credentials(role: str) -> dict[str, str]:
    if role not in {"student", "enterprise"}:
        raise ValueError("Unknown demo role")

    names = ("DEMO_STUDENT_EMAIL", "DEMO_ENTERPRISE_EMAIL", "DEMO_PASSWORD")
    configured = {name: os.getenv(name, "").strip() for name in names}
    if any(configured.values()):
        if not all(configured.values()):
            raise RuntimeError("Set all three DEMO_* environment variables together")
        values = {
            "studentEmail": configured["DEMO_STUDENT_EMAIL"],
            "enterpriseEmail": configured["DEMO_ENTERPRISE_EMAIL"],
            "password": configured["DEMO_PASSWORD"],
        }
    else:
        if not CREDENTIALS_PATH.is_file():
            raise RuntimeError(
                "Local demo credentials missing. Run Start-Demo.ps1 to create them."
            )
        values = json.loads(CREDENTIALS_PATH.read_text(encoding="utf-8"))

    email = values.get(f"{role}Email")
    password = values.get("password")
    if not isinstance(email, str) or "@" not in email:
        raise RuntimeError("Invalid local demo email")
    if not isinstance(password, str) or len(password) < 12:
        raise RuntimeError("Invalid local demo password")
    return {"email": email, "password": password}
