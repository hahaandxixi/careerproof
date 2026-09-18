from fastapi import APIRouter

router = APIRouter()


@router.post("/items")
def create_item(payload: dict) -> dict:
    if not payload.get("name"):
        return {"error": "name required"}
    item = save_item(payload["name"])
    return {"item": item}


def save_item(name: str) -> dict[str, str]:
    return {"name": name}
