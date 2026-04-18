"""Minimal MS Graph stub for local development.

Returns canned 200 responses so the agent can start without real Graph access.
Extend per test case as connector implementations land in Step 2.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(title="MS Graph Stub")


@app.get("/v1.0/users")
async def list_users() -> JSONResponse:
    return JSONResponse(
        {
            "value": [
                {
                    "id": "stub-user-001",
                    "userPrincipalName": "alice@contoso.com",
                    "displayName": "Alice",
                    "mail": "alice@contoso.com",
                }
            ]
        }
    )


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "graph-stub"})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
