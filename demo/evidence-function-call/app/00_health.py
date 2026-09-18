from fastapi import FastAPI

app = FastAPI(title="Synthetic Tool Retrieval API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
