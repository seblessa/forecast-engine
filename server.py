"""Executable entrypoint for the Forecast Engine HTTP service."""

from __future__ import annotations

import os

import uvicorn

from forecast_engine.api.app import app


if __name__ == "__main__":
    uvicorn.run(
        app,
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
    )
