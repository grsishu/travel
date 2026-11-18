import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from app.config import settings
from app.db import engine, Base
from app.routers import (
    auth, onboarding, kyc, wallet, rates, qr, payments, webhooks, admin
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create DB tables if not exist
    Base.metadata.create_all(bind=engine)
    # Ensure upload directory exists
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    yield

app = FastAPI(
    title=settings.APP_NAME,
    description="GPay-style Full-Stack Cross-Border QR Payment PWA for Indian Travellers",
    version="1.0.0",
    lifespan=lifespan
)

# CORS lock-down
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static and Templates
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Mount Routers
app.include_router(auth.router)
app.include_router(onboarding.router)
app.include_router(kyc.router)
app.include_router(wallet.router)
app.include_router(rates.router)
app.include_router(qr.router)
app.include_router(payments.router)
app.include_router(webhooks.router)
app.include_router(admin.router)

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_file = os.path.join(TEMPLATES_DIR, "index.html")
    with open(index_file, "r", encoding="utf-8") as f:
        return f.read()

@app.get("/admin", response_class=HTMLResponse)
async def serve_admin():
    admin_file = os.path.join(TEMPLATES_DIR, "admin.html")
    with open(admin_file, "r", encoding="utf-8") as f:
        return f.read()

@app.get("/merchant-qr", response_class=HTMLResponse)
async def serve_qr_generator():
    qr_file = os.path.join(TEMPLATES_DIR, "qr_generator.html")
    with open(qr_file, "r", encoding="utf-8") as f:
        return f.read()

@app.get("/manifest.json")
async def serve_manifest():
    return FileResponse(os.path.join(STATIC_DIR, "manifest.json"), media_type="application/manifest+json")

@app.get("/sw.js")
async def serve_service_worker():
    return FileResponse(os.path.join(STATIC_DIR, "sw.js"), media_type="application/javascript")

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "test_mode": settings.TEST_MODE,
        "settlement_provider": settings.SETTLEMENT_PROVIDER,
        "otp_provider": settings.OTP_PROVIDER
    }

