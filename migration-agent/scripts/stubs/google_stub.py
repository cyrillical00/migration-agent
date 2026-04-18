"""Minimal Google API stub for local development."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(title="Google API Stub")


@app.get("/admin/directory/v1/users")
async def list_users() -> JSONResponse:
    return JSONResponse({"users": []})


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "google-stub"})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8002)
