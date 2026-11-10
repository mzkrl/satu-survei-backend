from fastapi import FastAPI

from app.routes import (
    users,
    auth
)

app = FastAPI(
    title="Satu Survey",
    version="1.0.0"
)

app.include_router(users.router)
app.include_router(auth.router)

@app.get("/")
def root():
    return {"message": "Hello World! API is Running. Proceed to /docs"}