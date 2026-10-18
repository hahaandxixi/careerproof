from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="Campus activity exercise")
events = {1: {"id": 1, "title": "Python study group", "capacity": 2}}
registrations = []

class Signup(BaseModel):
    event_id: int = Field(ge=1)
    student_code: str = Field(min_length=3, max_length=16)

@app.get("/events")
def list_events():
    return list(events.values())

@app.post("/registrations", status_code=201)
def register(payload: Signup):
    event = events.get(payload.event_id)
    if event is None:
        raise HTTPException(404, "Unknown event")
    if any(r["event_id"] == payload.event_id and
           r["student_code"] == payload.student_code for r in registrations):
        raise HTTPException(409, "Already registered")
    if sum(r["event_id"] == payload.event_id for r in registrations) >= event["capacity"]:
        raise HTTPException(409, "No remaining places")
    record = {"id": len(registrations) + 1, **payload.model_dump()}
    registrations.append(record)
    return record
