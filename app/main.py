from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import Base, engine
import app.models  # noqa: F401
from app.routes import users, auth, analyze


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Satu Survey",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(users.router)
app.include_router(auth.router)
app.include_router(analyze.router)


@app.get("/")
def root():
    return {"message": "Hello World! API is Running. Proceed to /docs"}