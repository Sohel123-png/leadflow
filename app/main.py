from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse

from app.ratelimit import rate_limit
from app.routers import auth, leads, users

app = FastAPI(
    title="LeadFlow API",
    description="CRM lead management backend: JWT auth, role-based access, Redis caching, rate limiting.",
    version="1.0.0",
    dependencies=[Depends(rate_limit)],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(leads.router)


@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
