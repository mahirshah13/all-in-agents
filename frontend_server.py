#!/usr/bin/env python3
"""
Frontend server with WebSocket support for real-time game visualization
"""
import asyncio
import json
import time
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
import uvicorn
from pathlib import Path

# Global WebSocket manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self.game_state_history = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients"""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                disconnected.append(connection)
        
        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(conn)

    def add_game_state(self, state: dict):
        """Add game state to history"""
        self.game_state_history.append(state)
        # Keep only last 100 states
        if len(self.game_state_history) > 100:
            self.game_state_history.pop(0)

# Global connection manager
manager = ConnectionManager()

# Create FastAPI app
app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files (CSS, JS)
frontend_dir = Path(__file__).parent / "frontend"
app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

@app.get("/")
async def read_root():
    """Serve the frontend HTML"""
    frontend_path = frontend_dir / "index.html"
    if not frontend_path.exists():
        return {"error": "Frontend not found", "path": str(frontend_path)}
    return FileResponse(frontend_path)

@app.get("/select")
async def select_agents_page():
    """Serve the agent selection page"""
    selection_path = frontend_dir / "agent-selection.html"
    if not selection_path.exists():
        return {"error": "Selection page not found"}
    return FileResponse(selection_path)

@app.get("/style.css")
async def get_style():
    """Serve CSS file"""
    css_path = frontend_dir / "style.css"
    if css_path.exists():
        return FileResponse(css_path, media_type="text/css")
    return {"error": "CSS not found"}

@app.get("/app.js")
async def get_script():
    """Serve JavaScript file"""
    js_path = frontend_dir / "app.js"
    if js_path.exists():
        return FileResponse(js_path, media_type="application/javascript")
    return {"error": "JS not found"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates"""
    await manager.connect(websocket)
    try:
        # Send initial state/history
        if manager.game_state_history:
            # Send last game state
            last_state = manager.game_state_history[-1]
            await websocket.send_json(last_state)
            
            # Also send history if available
            if len(manager.game_state_history) > 1:
                await websocket.send_json({
                    "type": "history",
                    "data": manager.game_state_history[-10:]  # Last 10 states
                })
        else:
            # Send welcome message if no game state
            await websocket.send_json({
                "type": "info",
                "data": {"message": "Connected. Waiting for game to start..."}
            })
        
        # Keep connection alive
        while True:
            try:
                data = await websocket.receive_text()
                message = json.loads(data)
                
                # Handle client requests
                if message.get("type") == "get_state":
                    # Send current state if available
                    if manager.game_state_history:
                        last_state = manager.game_state_history[-1]
                        await websocket.send_json(last_state)
                    else:
                        await websocket.send_json({
                            "type": "info",
                            "data": {"message": "No game state available yet"}
                        })
                else:
                    # Echo back
                    await websocket.send_json({"type": "pong", "data": data})
            except json.JSONDecodeError:
                # Not JSON, just echo
                await websocket.send_json({"type": "pong", "data": data})
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.disconnect(websocket)

@app.get("/api/state")
async def get_current_state():
    """Get current game state"""
    if manager.game_state_history:
        return manager.game_state_history[-1]
    return {"status": "no_game"}

@app.get("/api/history")
async def get_history():
    """Get game state history"""
    return manager.game_state_history

# Store selected agents (shared state)
selected_agents_for_tournament = []

@app.get("/api/available-agents")
async def get_available_agents():
    """Get list of all available agents"""
    return {
        "agents": [
            {"id": "tagbot", "name": "TAGBot", "description": "Tight-Aggressive"},
            {"id": "montecarlo", "name": "Monte Carlo", "description": "Simulation-Based"},
            {"id": "maniac", "name": "Maniac", "description": "Ultra-Aggressive"},
            {"id": "smart_agent", "name": "Smart Agent", "description": "Pot Odds & Position"},
            {"id": "equity", "name": "Equity Calculator", "description": "Equity-Based"},
            {"id": "adaptive", "name": "Adaptive Heuristic", "description": "Stack-Aware Adaptive"}
        ]
    }

@app.get("/api/selected-agents")
async def get_selected_agents():
    """Get currently selected agents"""
    global selected_agents_for_tournament
    if not selected_agents_for_tournament:
        # Return default if none selected
        return {
            "agents": [
                {"id": "tagbot", "name": "TAGBot", "description": "Tight-Aggressive"},
                {"id": "montecarlo", "name": "Monte Carlo", "description": "Simulation-Based"},
                {"id": "maniac", "name": "Maniac", "description": "Ultra-Aggressive"},
                {"id": "smart_agent", "name": "Smart Agent", "description": "Pot Odds & Position"}
            ]
        }
    return {"agents": selected_agents_for_tournament}

class AgentSelection(BaseModel):
    agents: list

@app.post("/api/select-agents")
async def select_agents(selection: AgentSelection):
    """Receive selected agents and store for tournament"""
    global selected_agents_for_tournament
    selected = selection.agents
    if len(selected) != 4:
        return {"success": False, "error": "Must select exactly 4 agents"}
    
    # Map agent IDs to full agent info with URLs
    all_agents = {
        "tagbot": {"id": "tagbot", "name": "TAGBot", "type": "tagbot", "description": "Tight-Aggressive", "url": "http://localhost:8001"},
        "montecarlo": {"id": "montecarlo", "name": "Monte Carlo", "type": "montecarlo", "description": "Simulation-Based", "url": "http://localhost:8002"},
        "maniac": {"id": "maniac", "name": "Maniac", "type": "maniac", "description": "Ultra-Aggressive", "url": "http://localhost:8003"},
        "smart_agent": {"id": "smart_agent", "name": "Smart Agent", "type": "smart", "description": "Pot Odds & Position", "url": "http://localhost:8004"},
        "equity": {"id": "equity", "name": "Equity Calculator", "type": "equity", "description": "Equity-Based", "url": "http://localhost:8005"},
        "adaptive": {"id": "adaptive", "name": "Adaptive Heuristic", "type": "adaptive", "description": "Stack-Aware Adaptive", "url": "http://localhost:8006"}
    }
    
    selected_agents_for_tournament = [all_agents[aid] for aid in selected if aid in all_agents]
    
    # Write to config file for assessment manager to read
    import toml
    config_path = "src/green_agent/agent_card.toml"
    try:
        with open(config_path, 'r') as f:
            config = toml.load(f)
        
        # Update white_agents with selected agents
        config["evaluation"]["white_agents"] = selected_agents_for_tournament
        
        with open(config_path, 'w') as f:
            toml.dump(config, f)
    except Exception as e:
        print(f"Warning: Could not update config file: {e}")
    
    return {"success": True, "message": "Agents selected", "agents": selected_agents_for_tournament}

@app.post("/api/broadcast")
async def receive_broadcast(update: dict):
    """Receive broadcast from assessment manager and forward to WebSocket clients"""
    update_type = update.get("type")
    data = update.get("data", {})
    
    message = {
        "type": update_type,
        "data": data,
        "timestamp": time.time()
    }
    manager.add_game_state(message)
    
    # Broadcast to all connected clients
    if manager.active_connections:
        await manager.broadcast(message)
        print(f"📡 Broadcasted {update_type} to {len(manager.active_connections)} clients")
    else:
        print(f"⚠️  No clients connected to receive {update_type}")
    
    return {"status": "ok", "type": update_type, "clients": len(manager.active_connections)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)

