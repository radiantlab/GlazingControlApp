from __future__ import annotations
import uvicorn
from fastapi import FastAPI
from app.routes import router
from app.state import bootstrap_default_if_empty

def create_app() -> FastAPI:
    # ensure seed data exists for the simulator on first run
    bootstrap_default_if_empty()
    app = FastAPI(title="ECG Control Service", version="0.1.0")
    app.include_router(router)
    return app

app = create_app()

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
