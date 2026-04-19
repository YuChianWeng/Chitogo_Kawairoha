from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import Base, engine
from app.routers import health, places


@asynccontextmanager
async def lifespan(app: FastAPI):
    import app.models

    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="ChitoGo Place Data Service", version="0.1.0", lifespan=lifespan)

app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(places.router, prefix="/api/v1", tags=["places"])
