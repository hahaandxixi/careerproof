from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

class Booking(BaseModel):
    room: str = Field(min_length=1, max_length=20)
    hour: int = Field(ge=0, le=23)

def create_app():
    app = FastAPI(title="Booking exercise")
    bookings = []

    @app.post("/bookings", status_code=201)
    def book(payload: Booking):
        if any(x["room"] == payload.room and x["hour"] == payload.hour for x in bookings):
            raise HTTPException(409, "Slot already booked")
        result = {"id": len(bookings) + 1, **payload.model_dump()}
        bookings.append(result)
        return result

    return app
