from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
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

# The Next.js frontend runs on a different origin during development and in
# production (https://n3level.id -> https://api.n3level.id). Without this
# middleware the browser blocks every cross-origin request.
def _parse_cors_origins(raw: str) -> list[str]:
    origins: list[str] = []
    for value in raw.split(","):
        # Browsers send the Origin header without a trailing slash, so
        # normalize misconfigured values such as "https://n3level.id/".
        origin = value.strip().rstrip("/")
        if origin and origin not in origins:
            origins.append(origin)
    return origins


_cors_origins = _parse_cors_origins(settings.CORS_ORIGINS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

app.include_router(users.router)
app.include_router(auth.router)
app.include_router(analyze.router)


@app.get("/")
def root():
    return {"message": "Hello World! API is Running. Proceed to /docs"}