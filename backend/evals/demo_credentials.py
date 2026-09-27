"""Load synthetic demo credentials without putting a reusable password in Git."""

import json
import os
from pathlib import Path

from pydantic import EmailStr, TypeAdapter, ValidationError

CREDENTIALS_PATH = Path(__file__).resolve().parents[1] / ".tmp" / "demo-credentials.json"
EMAIL = TypeAdapter(EmailStr)


def get_demo_credentials(role: str) -> dict[str, str]:
    if role not in {"student", "enterprise"}:
        raise ValueError("Unknown demo role")
    return get_demo_credentials_pair()[role]


def get_demo_credentials_pair() -> dict[str, dict[str, str]]:
    """Validate both identities from one snapshot before any account is seeded."""
    names = ("DEMO_STUDENT_EMAIL", "DEMO_ENTERPRISE_EMAIL", "DEMO_PASSWORD")
    configured = {name: os.getenv(name, "") for name in names}
    if any(value.strip() for value in configured.values()):
        if not all(value.strip() for value in configured.values()):
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
        try:
            values = json.loads(CREDENTIALS_PATH.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            raise RuntimeError("Cannot read local demo credentials JSON") from None

    if not isinstance(values, dict):
        raise RuntimeError("Local demo credentials must be a JSON object")
    password = values.get("password")
    if not isinstance(password, str) or not 12 <= len(password) <= 128:
        raise RuntimeError("Invalid local demo password")

    result = {}
    for role in ("student", "enterprise"):
        try:
            email = str(EMAIL.validate_python(values.get(f"{role}Email")))
        except ValidationError:
            raise RuntimeError("Invalid local demo email") from None
        result[role] = {"email": email, "password": password}
    if result["student"]["email"].lower() == result["enterprise"]["email"].lower():
        raise RuntimeError("Student and enterprise demo emails must be different")
    return result


if __name__ == "__main__":
    try:
        get_demo_credentials_pair()
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from None
    print("Local demo credentials validated; no network request or account change.")
