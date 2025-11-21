from __future__ import annotations
from dotenv import load_dotenv
load_dotenv()  # Load .env file before importing app modules

import time
import logging
import json
from typing import Callable
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from app.routes import router
from app.state import bootstrap_default_if_empty

# Configure logging to show all INFO level logs from our modules
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(name)s: %(message)s'
)
# Ensure our app modules log at INFO level
logging.getLogger("app").setLevel(logging.INFO)
logging.getLogger("app.adapter").setLevel(logging.INFO)
logging.getLogger("app.service").setLevel(logging.INFO)

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log detailed request and response information."""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.time()
        
        # Get client IP
        client_ip = request.client.host if request.client else "unknown"
        
        # Skip body reading for OPTIONS (CORS preflight) - let CORS middleware handle it
        body = None
        body_bytes = b""
        if request.method == "OPTIONS":
            # OPTIONS requests are handled by CORS middleware, just log and pass through
            logger.debug(f"OPTIONS request: {request.url.path} from {client_ip}")
            response = await call_next(request)
            process_time = time.time() - start_time
            logger.debug(
                f"OPTIONS response: {request.url.path} | "
                f"Status: {response.status_code} | "
                f"Time: {process_time:.3f}s"
            )
            return response
        
        # Get request body for POST/PATCH/PUT requests
        if request.method in ("POST", "PATCH", "PUT"):
            try:
                body_bytes = await request.body()
                if body_bytes:
                    body = json.loads(body_bytes)
            except json.JSONDecodeError:
                body = "<non-json body>"
            except Exception as e:
                body = f"<error reading body: {e}>"
            
            # Recreate request with body for downstream handlers
            async def receive():
                return {"type": "http.request", "body": body_bytes}
            request._receive = receive
        
        # Log request
        query_params = dict(request.query_params) if request.query_params else None
        logger.info(
            f"Request: {request.method} {request.url.path} | "
            f"IP: {client_ip} | "
            f"Query: {query_params} | "
            f"Body: {body if body else 'N/A'}"
        )
        
        # Process request
        response = await call_next(request)
        
        # Calculate response time
        process_time = time.time() - start_time
        
        # Log response
        logger.info(
            f"Response: {request.method} {request.url.path} | "
            f"Status: {response.status_code} | "
            f"Time: {process_time:.3f}s"
        )
        
        return response


def create_app() -> FastAPI:
    bootstrap_default_if_empty()
    app = FastAPI(title="ECG Control Service", version="0.1.0")

    # Request logging middleware (add first so it wraps everything)
    app.add_middleware(LoggingMiddleware)
    
    # CORS for local web dev
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)
    return app


app = create_app()

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
