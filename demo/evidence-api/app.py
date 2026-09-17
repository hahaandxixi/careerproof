from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Course Task API")


class Course(BaseModel):
    id: int
    title: str


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/courses", response_model=list[Course])
def list_courses() -> list[Course]:
    return [Course(id=1, title="Python Web Development")]

