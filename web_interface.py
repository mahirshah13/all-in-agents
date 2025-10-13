"""
Web Interface for Poker Evaluation Agent
Provides a dashboard for monitoring games and viewing results
"""
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import asyncio
import json
import logging
from datetime import datetime

from evaluation_agent import EvaluationAgent, AgentConfig, GameConfig
from a2a_protocol import A2AServer


class WebInterface:
    def __init__(self, evaluation_agent: EvaluationAgent):
        self.evaluation_agent = evaluation_agent
        self.app = FastAPI(title="Poker Evaluation Agent", version="1.0.0")
        self.logger = logging.getLogger(__name__)
        self.connected_clients: List[WebSocket] = []
        
        # Add CORS middleware
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        # Set up routes
        self._setup_routes()
        
        # Set up templates
        self.templates = Jinja2Templates(directory="templates")
    
    def _setup_routes(self):
        """Set up FastAPI routes"""
        
        @self.app.get("/", response_class=HTMLResponse)
        async def dashboard():
            return self._get_dashboard_html()
        
        @self.app.get("/api/agents")
        async def get_agents():
            """Get list of registered agents"""
            return {
                "agents": [
                    {
                        "id": agent.id,
                        "name": agent.name,
                        "url": agent.url,
                        "timeout": agent.timeout
                    }
                    for agent in self.evaluation_agent.agents.values()
                ]
            }
        
        @self.app.post("/api/agents")
        async def register_agent(agent_data: dict):
            """Register a new agent"""
            try:
                agent_config = AgentConfig(
                    id=agent_data["id"],
                    name=agent_data["name"],
                    url=agent_data["url"],
                    timeout=agent_data.get("timeout", 30)
                )
                self.evaluation_agent.register_agent(agent_config)
                await self._broadcast_update("agent_registered", {"agent": agent_data})
                return {"success": True, "message": "Agent registered successfully"}
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))
        
        @self.app.delete("/api/agents/{agent_id}")
        async def unregister_agent(agent_id: str):
            """Unregister an agent"""
            if agent_id not in self.evaluation_agent.agents:
                raise HTTPException(status_code=404, detail="Agent not found")
            
            self.evaluation_agent.unregister_agent(agent_id)
            await self._broadcast_update("agent_unregistered", {"agent_id": agent_id})
            return {"success": True, "message": "Agent unregistered successfully"}
        
        @self.app.get("/api/metrics")
        async def get_metrics(agent_id: Optional[str] = None):
            """Get agent metrics"""
            return self.evaluation_agent.get_agent_metrics(agent_id)
        
        @self.app.post("/api/games/start")
        async def start_game(game_data: dict):
            """Start a new game"""
            try:
                agent_urls = game_data.get("agent_urls", [])
                if len(agent_urls) < 2:
                    raise HTTPException(status_code=400, detail="Need at least 2 agents")
                
                # Start game in background
                asyncio.create_task(self._run_game_and_notify(game_data))
                
                return {"success": True, "message": "Game started"}
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))
        
        @self.app.post("/api/tournaments/start")
        async def start_tournament(tournament_data: dict):
            """Start a new tournament"""
            try:
                agent_urls = tournament_data.get("agent_urls", [])
                num_games = tournament_data.get("num_games", 10)
                
                if len(agent_urls) < 2:
                    raise HTTPException(status_code=400, detail="Need at least 2 agents")
                
                # Start tournament in background
                asyncio.create_task(self._run_tournament_and_notify(tournament_data))
                
                return {"success": True, "message": "Tournament started"}
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))
        
        @self.app.get("/api/games/active")
        async def get_active_games():
            """Get list of active games"""
            return {
                "active_games": [
                    {
                        "game_id": game_id,
                        "agents": [agent.name for agent in game_info["agents"]],
                        "start_time": game_info["start_time"],
                        "hand_number": game_info["hand_number"]
                    }
                    for game_id, game_info in self.evaluation_agent.active_games.items()
                ]
            }
        
        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket endpoint for real-time updates"""
            await websocket.accept()
            self.connected_clients.append(websocket)
            
            try:
                while True:
                    # Keep connection alive
                    await websocket.receive_text()
            except WebSocketDisconnect:
                self.connected_clients.remove(websocket)
    
    async def _run_game_and_notify(self, game_data: dict):
        """Run a game and notify clients of updates"""
        try:
            agent_urls = game_data["agent_urls"]
            result = await self.evaluation_agent.run_single_game(agent_urls)
            
            await self._broadcast_update("game_completed", {
                "result": result,
                "timestamp": datetime.now().isoformat()
            })
        except Exception as e:
            await self._broadcast_update("game_error", {
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            })
    
    async def _run_tournament_and_notify(self, tournament_data: dict):
        """Run a tournament and notify clients of updates"""
        try:
            agent_urls = tournament_data["agent_urls"]
            num_games = tournament_data.get("num_games", 10)
            
            await self._broadcast_update("tournament_started", {
                "num_games": num_games,
                "agents": agent_urls,
                "timestamp": datetime.now().isoformat()
            })
            
            result = await self.evaluation_agent.run_tournament(agent_urls, num_games)
            
            await self._broadcast_update("tournament_completed", {
                "result": result,
                "timestamp": datetime.now().isoformat()
            })
        except Exception as e:
            await self._broadcast_update("tournament_error", {
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            })
    
    async def _broadcast_update(self, event_type: str, data: Dict[str, Any]):
        """Broadcast update to all connected clients"""
        message = {
            "type": event_type,
            "data": data,
            "timestamp": datetime.now().isoformat()
        }
        
        disconnected_clients = []
        for client in self.connected_clients:
            try:
                await client.send_text(json.dumps(message))
            except:
                disconnected_clients.append(client)
        
        # Remove disconnected clients
        for client in disconnected_clients:
            self.connected_clients.remove(client)
    
    def _get_dashboard_html(self) -> str:
        """Get the dashboard HTML"""
        return """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Poker Evaluation Agent Dashboard</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    margin: 0;
                    padding: 20px;
                    background-color: #f5f5f5;
                }
                .container {
                    max-width: 1200px;
                    margin: 0 auto;
                    background: white;
                    padding: 20px;
                    border-radius: 8px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                }
                .header {
                    text-align: center;
                    margin-bottom: 30px;
                    padding-bottom: 20px;
                    border-bottom: 2px solid #e0e0e0;
                }
                .section {
                    margin-bottom: 30px;
                }
                .section h2 {
                    color: #333;
                    margin-bottom: 15px;
                }
                .form-group {
                    margin-bottom: 15px;
                }
                .form-group label {
                    display: block;
                    margin-bottom: 5px;
                    font-weight: bold;
                }
                .form-group input, .form-group select {
                    width: 100%;
                    padding: 8px;
                    border: 1px solid #ddd;
                    border-radius: 4px;
                    box-sizing: border-box;
                }
                .btn {
                    background-color: #007bff;
                    color: white;
                    padding: 10px 20px;
                    border: none;
                    border-radius: 4px;
                    cursor: pointer;
                    margin-right: 10px;
                }
                .btn:hover {
                    background-color: #0056b3;
                }
                .btn-danger {
                    background-color: #dc3545;
                }
                .btn-danger:hover {
                    background-color: #c82333;
                }
                .table {
                    width: 100%;
                    border-collapse: collapse;
                    margin-top: 15px;
                }
                .table th, .table td {
                    padding: 12px;
                    text-align: left;
                    border-bottom: 1px solid #ddd;
                }
                .table th {
                    background-color: #f8f9fa;
                    font-weight: bold;
                }
                .status {
                    padding: 4px 8px;
                    border-radius: 4px;
                    font-size: 12px;
                    font-weight: bold;
                }
                .status.active {
                    background-color: #d4edda;
                    color: #155724;
                }
                .status.inactive {
                    background-color: #f8d7da;
                    color: #721c24;
                }
                .metrics-grid {
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                    gap: 20px;
                    margin-top: 20px;
                }
                .metric-card {
                    background: #f8f9fa;
                    padding: 15px;
                    border-radius: 8px;
                    text-align: center;
                }
                .metric-value {
                    font-size: 24px;
                    font-weight: bold;
                    color: #007bff;
                }
                .metric-label {
                    font-size: 14px;
                    color: #666;
                    margin-top: 5px;
                }
                .log {
                    background: #f8f9fa;
                    border: 1px solid #e0e0e0;
                    border-radius: 4px;
                    padding: 15px;
                    height: 300px;
                    overflow-y: auto;
                    font-family: monospace;
                    font-size: 12px;
                }
                .log-entry {
                    margin-bottom: 5px;
                    padding: 2px 0;
                }
                .log-entry.info {
                    color: #007bff;
                }
                .log-entry.success {
                    color: #28a745;
                }
                .log-entry.error {
                    color: #dc3545;
                }
                .log-entry.warning {
                    color: #ffc107;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🃏 Poker Evaluation Agent Dashboard</h1>
                    <p>Monitor and evaluate poker-playing agents using the A2A protocol</p>
                </div>
                
                <div class="section">
                    <h2>Agent Management</h2>
                    <div class="form-group">
                        <label for="agentId">Agent ID:</label>
                        <input type="text" id="agentId" placeholder="unique-agent-id">
                    </div>
                    <div class="form-group">
                        <label for="agentName">Agent Name:</label>
                        <input type="text" id="agentName" placeholder="Agent Name">
                    </div>
                    <div class="form-group">
                        <label for="agentUrl">Agent URL:</label>
                        <input type="text" id="agentUrl" placeholder="http://localhost:8000 or ws://localhost:8000">
                    </div>
                    <button class="btn" onclick="registerAgent()">Register Agent</button>
                    <button class="btn btn-danger" onclick="refreshAgents()">Refresh</button>
                </div>
                
                <div class="section">
                    <h2>Registered Agents</h2>
                    <table class="table" id="agentsTable">
                        <thead>
                            <tr>
                                <th>ID</th>
                                <th>Name</th>
                                <th>URL</th>
                                <th>Status</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody id="agentsTableBody">
                        </tbody>
                    </table>
                </div>
                
                <div class="section">
                    <h2>Game Control</h2>
                    <div class="form-group">
                        <label for="gameAgents">Select Agents for Game:</label>
                        <select id="gameAgents" multiple style="height: 100px;">
                        </select>
                    </div>
                    <button class="btn" onclick="startGame()">Start Game</button>
                    <button class="btn" onclick="startTournament()">Start Tournament</button>
                </div>
                
                <div class="section">
                    <h2>Agent Metrics</h2>
                    <div class="metrics-grid" id="metricsGrid">
                    </div>
                </div>
                
                <div class="section">
                    <h2>Live Log</h2>
                    <div class="log" id="logContainer">
                    </div>
                </div>
            </div>
            
            <script>
                let ws = null;
                let agents = [];
                
                // Initialize WebSocket connection
                function initWebSocket() {
                    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                    const wsUrl = `${protocol}//${window.location.host}/ws`;
                    
                    ws = new WebSocket(wsUrl);
                    
                    ws.onopen = function() {
                        addLogEntry('WebSocket connected', 'success');
                    };
                    
                    ws.onmessage = function(event) {
                        const message = JSON.parse(event.data);
                        handleWebSocketMessage(message);
                    };
                    
                    ws.onclose = function() {
                        addLogEntry('WebSocket disconnected', 'warning');
                        setTimeout(initWebSocket, 5000);
                    };
                    
                    ws.onerror = function(error) {
                        addLogEntry('WebSocket error: ' + error, 'error');
                    };
                }
                
                function handleWebSocketMessage(message) {
                    addLogEntry(`Received: ${message.type}`, 'info');
                    
                    if (message.type === 'agent_registered') {
                        refreshAgents();
                    } else if (message.type === 'agent_unregistered') {
                        refreshAgents();
                    } else if (message.type === 'game_completed') {
                        addLogEntry('Game completed: ' + JSON.stringify(message.data.result), 'success');
                        refreshMetrics();
                    } else if (message.type === 'tournament_completed') {
                        addLogEntry('Tournament completed: ' + JSON.stringify(message.data.result), 'success');
                        refreshMetrics();
                    }
                }
                
                function addLogEntry(message, type = 'info') {
                    const logContainer = document.getElementById('logContainer');
                    const entry = document.createElement('div');
                    entry.className = `log-entry ${type}`;
                    entry.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
                    logContainer.appendChild(entry);
                    logContainer.scrollTop = logContainer.scrollHeight;
                }
                
                async function registerAgent() {
                    const agentId = document.getElementById('agentId').value;
                    const agentName = document.getElementById('agentName').value;
                    const agentUrl = document.getElementById('agentUrl').value;
                    
                    if (!agentId || !agentName || !agentUrl) {
                        alert('Please fill in all fields');
                        return;
                    }
                    
                    try {
                        const response = await fetch('/api/agents', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                            },
                            body: JSON.stringify({
                                id: agentId,
                                name: agentName,
                                url: agentUrl
                            })
                        });
                        
                        const result = await response.json();
                        if (result.success) {
                            addLogEntry(`Agent registered: ${agentName}`, 'success');
                            document.getElementById('agentId').value = '';
                            document.getElementById('agentName').value = '';
                            document.getElementById('agentUrl').value = '';
                            refreshAgents();
                        } else {
                            addLogEntry(`Failed to register agent: ${result.message}`, 'error');
                        }
                    } catch (error) {
                        addLogEntry(`Error registering agent: ${error}`, 'error');
                    }
                }
                
                async function refreshAgents() {
                    try {
                        const response = await fetch('/api/agents');
                        const data = await response.json();
                        agents = data.agents;
                        
                        const tableBody = document.getElementById('agentsTableBody');
                        tableBody.innerHTML = '';
                        
                        const gameAgentsSelect = document.getElementById('gameAgents');
                        gameAgentsSelect.innerHTML = '';
                        
                        agents.forEach(agent => {
                            const row = document.createElement('tr');
                            row.innerHTML = `
                                <td>${agent.id}</td>
                                <td>${agent.name}</td>
                                <td>${agent.url}</td>
                                <td><span class="status active">Active</span></td>
                                <td>
                                    <button class="btn btn-danger" onclick="unregisterAgent('${agent.id}')">Remove</button>
                                </td>
                            `;
                            tableBody.appendChild(row);
                            
                            const option = document.createElement('option');
                            option.value = agent.url;
                            option.textContent = `${agent.name} (${agent.id})`;
                            gameAgentsSelect.appendChild(option);
                        });
                    } catch (error) {
                        addLogEntry(`Error refreshing agents: ${error}`, 'error');
                    }
                }
                
                async function unregisterAgent(agentId) {
                    if (!confirm('Are you sure you want to remove this agent?')) {
                        return;
                    }
                    
                    try {
                        const response = await fetch(`/api/agents/${agentId}`, {
                            method: 'DELETE'
                        });
                        
                        const result = await response.json();
                        if (result.success) {
                            addLogEntry(`Agent unregistered: ${agentId}`, 'success');
                            refreshAgents();
                        } else {
                            addLogEntry(`Failed to unregister agent: ${result.message}`, 'error');
                        }
                    } catch (error) {
                        addLogEntry(`Error unregistering agent: ${error}`, 'error');
                    }
                }
                
                async function startGame() {
                    const selectedAgents = Array.from(document.getElementById('gameAgents').selectedOptions)
                        .map(option => option.value);
                    
                    if (selectedAgents.length < 2) {
                        alert('Please select at least 2 agents');
                        return;
                    }
                    
                    try {
                        const response = await fetch('/api/games/start', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                            },
                            body: JSON.stringify({
                                agent_urls: selectedAgents
                            })
                        });
                        
                        const result = await response.json();
                        if (result.success) {
                            addLogEntry('Game started', 'success');
                        } else {
                            addLogEntry(`Failed to start game: ${result.message}`, 'error');
                        }
                    } catch (error) {
                        addLogEntry(`Error starting game: ${error}`, 'error');
                    }
                }
                
                async function startTournament() {
                    const selectedAgents = Array.from(document.getElementById('gameAgents').selectedOptions)
                        .map(option => option.value);
                    
                    if (selectedAgents.length < 2) {
                        alert('Please select at least 2 agents');
                        return;
                    }
                    
                    const numGames = prompt('Number of games:', '10');
                    if (!numGames || isNaN(numGames)) {
                        return;
                    }
                    
                    try {
                        const response = await fetch('/api/tournaments/start', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                            },
                            body: JSON.stringify({
                                agent_urls: selectedAgents,
                                num_games: parseInt(numGames)
                            })
                        });
                        
                        const result = await response.json();
                        if (result.success) {
                            addLogEntry(`Tournament started with ${numGames} games`, 'success');
                        } else {
                            addLogEntry(`Failed to start tournament: ${result.message}`, 'error');
                        }
                    } catch (error) {
                        addLogEntry(`Error starting tournament: ${error}`, 'error');
                    }
                }
                
                async function refreshMetrics() {
                    try {
                        const response = await fetch('/api/metrics');
                        const metrics = await response.json();
                        
                        const metricsGrid = document.getElementById('metricsGrid');
                        metricsGrid.innerHTML = '';
                        
                        Object.values(metrics).forEach(metric => {
                            const card = document.createElement('div');
                            card.className = 'metric-card';
                            card.innerHTML = `
                                <div class="metric-value">${metric.win_rate ? (metric.win_rate * 100).toFixed(1) : 0}%</div>
                                <div class="metric-label">Win Rate</div>
                            `;
                            metricsGrid.appendChild(card);
                            
                            const card2 = document.createElement('div');
                            card2.className = 'metric-card';
                            card2.innerHTML = `
                                <div class="metric-value">${metric.net_chips || 0}</div>
                                <div class="metric-label">Net Chips</div>
                            `;
                            metricsGrid.appendChild(card2);
                            
                            const card3 = document.createElement('div');
                            card3.className = 'metric-card';
                            card3.innerHTML = `
                                <div class="metric-value">${metric.games_played || 0}</div>
                                <div class="metric-label">Games Played</div>
                            `;
                            metricsGrid.appendChild(card3);
                            
                            const card4 = document.createElement('div');
                            card4.className = 'metric-card';
                            card4.innerHTML = `
                                <div class="metric-value">${metric.average_response_time ? metric.average_response_time.toFixed(3) : 0}s</div>
                                <div class="metric-label">Avg Response Time</div>
                            `;
                            metricsGrid.appendChild(card4);
                        });
                    } catch (error) {
                        addLogEntry(`Error refreshing metrics: ${error}`, 'error');
                    }
                }
                
                // Initialize on page load
                window.onload = function() {
                    initWebSocket();
                    refreshAgents();
                    refreshMetrics();
                    
                    // Refresh metrics every 5 seconds
                    setInterval(refreshMetrics, 5000);
                };
            </script>
        </body>
        </html>
        """
