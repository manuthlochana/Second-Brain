import os
import time
import uuid
import logging
import asyncio
from typing import Dict, Any, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, BackgroundTasks, Depends, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from dotenv import load_dotenv

import agent_engine
import graph_engine
# import database # Reserved for direct DB checks if needed

# --- Configuration & Logging ---

load_dotenv()

# Setup structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("CEO_BRAIN")

API_KEY_NAME = "X-API-Key"
API_KEY = os.getenv("API_KEY", "secret-key") # Default for dev if not set

api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

# --- Data Models ---

class WebIngestRequest(BaseModel):
    user_input: str = Field(..., min_length=1, description="Raw input text from user")
    source: str = Field("web", description="Source channel (web, mobile, etc)")

class WebhookIngestRequest(BaseModel):
    message: Dict[str, Any] = Field(..., description="Raw webhook payload")
    platform: str = Field(..., description="telegram or whatsapp")

class APIResponse(BaseModel):
    status: str
    message: str
    correlation_id: str

# --- WebSocket Manager ---

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("WebSocket client connected.")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info("WebSocket client disconnected.")

    async def broadcast(self, message: Dict[str, Any]):
        """Sends a JSON message to all connected clients."""
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to WS: {e}")
                # We might remove the dead connection here

manager = ConnectionManager()

# --- Security & Middleware ---

async def verify_api_key(api_key: str = Depends(api_key_header)):
    if not api_key or api_key != API_KEY:
        logger.warning(f"Unauthorized access attempt with key: {api_key}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )
    return api_key

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: could initialize DB connection pools here
    logger.info("🧠 CEO Brain API Starting up...")
    yield
    # Shutdown
    logger.info("🧠 CEO Brain API Shutting down...")

app = FastAPI(
    title="CEO Brain API",
    description="Enterprise-grade Autonomous AI System Backend",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration
origins = [
    "http://localhost:3000",
    "http://localhost:3001",
    "*" # Restrict in production
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    correlation_id = str(uuid.uuid4())
    request.state.correlation_id = correlation_id
    logger.info(f"Request started: {request.method} {request.url} [ID: {correlation_id}]")
    
    start_time = time.time()
    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Process-Time"] = str(process_time)
        logger.info(f"Request finished: {response.status_code} [ID: {correlation_id}] - {process_time:.4f}s")
        return response
    except Exception as e:
        logger.error(f"Request failed [ID: {correlation_id}]: {e}")
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal Server Error", "correlation_id": correlation_id}
        )

# --- Background Processor ---

async def process_brain_task(user_input: str, correlation_id: str):
    """
    Runs the heavy Reasoning Core in the background.
    Emits WS updates.
    """
    try:
        logger.info(f"[{correlation_id}] Starting Brain Processing for: '{user_input[:20]}...'")
        
        # 1. Notify Frontend: Thinking
        await manager.broadcast({
            "status": "THINKING",
            "message": "Analyzing intent...",
            "correlation_id": correlation_id
        })
        
        # 2. Run Agent Engine (Synchronous for now, or wrapped in threadpool if strictly blocking)
        # agent_engine.run_agent uses DB calls which are synchronous SQLAlchemy usually.
        # To avoid blocking the async loop, we should run this in a thread.
        
        response_text = await asyncio.to_thread(agent_engine.run_agent, user_input)
        
        # 3. Notify Frontend: Success
        await manager.broadcast({
            "status": "DONE",
            "message": "Response generated.",
            "response": response_text,
            "correlation_id": correlation_id
        })
        
        logger.info(f"[{correlation_id}] Brain Processing Completed.")
        
    except Exception as e:
        logger.error(f"[{correlation_id}] Brain Processing Failed: {e}")
        await manager.broadcast({
            "status": "ERROR",
            "message": "Something went wrong in the core.",
            "error": str(e),
            "correlation_id": correlation_id
        })

# --- Endpoints ---

@app.get("/")
async def root():
    return {"status": "online", "system": "CEO Brain v1.0"}

@app.post("/ingest/web", response_model=APIResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest_web(
    request: WebIngestRequest, 
    background_tasks: BackgroundTasks,
    request_obj: Request, 
    api_key: str = Depends(verify_api_key)
):
    """
    Main ingestion point for the Web Dashboard.
    Accepted immediately. Logic runs in background.
    """
    correlation_id = request_obj.state.correlation_id
    
    # Enqueue background task
    background_tasks.add_task(process_brain_task, request.user_input, correlation_id)
    
    return APIResponse(
        status="accepted",
        message="Inputs received. Processing started.",
        correlation_id=correlation_id
    )

@app.post("/ingest/webhook")
async def ingest_webhook(request: WebhookIngestRequest, background_tasks: BackgroundTasks, request_obj: Request):
    """
    Webhook for Telegram/WhatsApp.
    (Authenticaton usually logic specific to provider here)
    """
    correlation_id = request_obj.state.correlation_id
    # Placeholder Logic: Extract text from specific payloads
    message_text = "Audio or Text placeholder" 
    
    logger.info(f"Webhook received from {request.platform}")
    
    # background_tasks.add_task(process_brain_task, message_text, correlation_id)
    
    return {"status": "received"}

@app.post("/ingest/voice")
async def ingest_voice(request: Request):
    """
    Handle audio file uploads.
    """
    # Use python-multipart to handle UploadFile
    return {"status": "not_implemented_yet"}

@app.get("/graph/data")
async def get_graph_data(api_key: str = Depends(verify_api_key)):
    """
    Returns the full knowledge graph for visualization.
    """
    return graph_engine.graph_engine.get_full_graph()

@app.post("/graph/inference")
async def trigger_inference(background_tasks: BackgroundTasks, api_key: str = Depends(verify_api_key)):
    """
    Manually triggers the graph inference engine.
    """
    background_tasks.add_task(graph_engine.graph_engine.run_inference)
    return {"status": "inference_started"}

@app.post("/proactive/trigger", dependencies=[Depends(verify_api_key)])
async def proactive_trigger(background_tasks: BackgroundTasks, request: Request):
    """
    Protected endpoint for the Scheduler to trigger proactive checks.
    """
    correlation_id = request.state.correlation_id
    logger.info(f"[{correlation_id}] Proactive Trigger Received.")
    
    # We can define a simplified input for the agent to just "check tasks"
    background_tasks.add_task(process_brain_task, "System: Check for urgent tasks and proactive notifications.", correlation_id)
    
    return {"status": "triggered", "correlation_id": correlation_id}


@app.post("/chat/stream")
async def chat_stream(request: WebIngestRequest, api_key: str = Depends(verify_api_key)):
    """
    Streaming Endpoint for Real-time Chat.
    Yields chunks: "THINKING: ..." or "TOKEN: ..."
    """
    async def event_generator():
        try:
            # We use the new async streaming agent
            async for chunk in agent_engine.astream_agent(request.user_input):
                # Format as Server-Sent Event or just raw chunks
                # For simplicity, we just yield the text chunk + newline
                yield f"{chunk}\n"
        except Exception as e:
            logger.error(f"Stream Error: {e}")
            yield f"TOKEN: [System Error: {str(e)}]\n"

    return StreamingResponse(event_generator(), media_type="text/plain")

@app.get("/health")
async def health_check():
    """
    Heartbeat for Database and System.
    """
    import database
    db_status = "DB_CONNECTED" if database.check_connection() else "DB_OFFLINE"
    return {"status": "online", "database": db_status, "system": "CEO Brain"}

@app.websocket("/ws/status")
async def websocket_endpoint(websocket: WebSocket):
    """
    Real-time status updates for the dashboard.
    """
    await manager.connect(websocket)
    try:
        while True:
            # Keep alive / listen for client messages if any
            data = await websocket.receive_text()
            # We can handle "ping" here
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WS Error: {e}")
        manager.disconnect(websocket)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
