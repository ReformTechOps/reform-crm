"""
FastAPI entry for the field-rep app (routes.reformchiropractic.app).

Runs as a Docker container on Coolify. Startup lifespan spawns the Redis
cache warmer; shutdown cancels it and closes the Redis connection.
"""
import asyncio
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Allow `from hub.* import ...` when this file is launched as
# `uvicorn field_rep.app:app` from the `execution/` build context.
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI

from . import storage
from .auth import router as auth_router
from .routes.api import router as api_router
from .routes.pages import router as pages_router
from .warm import warm_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    warmer = asyncio.create_task(warm_loop())
    try:
        yield
    finally:
        warmer.cancel()
        try:
            await warmer
        except asyncio.CancelledError:
            pass
        await storage.close()


app = FastAPI(title="Reform Routes", lifespan=lifespan)

app.include_router(auth_router)
app.include_router(pages_router)
app.include_router(api_router)


@app.get("/healthz")
async def healthz():
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "field_rep.app:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
        reload=False,
    )
