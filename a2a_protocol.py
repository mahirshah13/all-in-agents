"""
A2A (Agent-to-Agent) Protocol Implementation
Handles communication between the evaluation agent and participating poker agents
"""
import asyncio
import json
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum
import httpx
import websockets
from urllib.parse import urlparse


class MessageType(Enum):
    GAME_START = "game_start"
    GAME_STATE = "game_state"
    ACTION_REQUEST = "action_request"
    ACTION_RESPONSE = "action_response"
    GAME_END = "game_end"
    ERROR = "error"
    PING = "ping"
    PONG = "pong"


@dataclass
class A2AMessage:
    message_type: MessageType
    game_id: str
    player_id: str
    data: Dict[str, Any]
    timestamp: float
    message_id: str


class A2AProtocol:
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.logger = logging.getLogger(__name__)
        self.active_connections: Dict[str, websockets.WebSocketServerProtocol] = {}
        
    async def send_message(self, agent_url: str, message: A2AMessage) -> Optional[Dict[str, Any]]:
        """Send a message to an agent and wait for response"""
        try:
            parsed_url = urlparse(agent_url)
            
            if parsed_url.scheme == "ws" or parsed_url.scheme == "wss":
                return await self._send_websocket_message(agent_url, message)
            elif parsed_url.scheme == "http" or parsed_url.scheme == "https":
                return await self._send_http_message(agent_url, message)
            else:
                raise ValueError(f"Unsupported URL scheme: {parsed_url.scheme}")
                
        except Exception as e:
            self.logger.error(f"Failed to send message to {agent_url}: {e}")
            return {"error": str(e)}
    
    async def _send_websocket_message(self, url: str, message: A2AMessage) -> Optional[Dict[str, Any]]:
        """Send message via WebSocket"""
        try:
            async with websockets.connect(url, timeout=self.timeout) as websocket:
                await websocket.send(json.dumps({
                    "message_type": message.message_type.value,
                    "game_id": message.game_id,
                    "player_id": message.player_id,
                    "data": message.data,
                    "timestamp": message.timestamp,
                    "message_id": message.message_id
                }))
                
                # Wait for response
                response = await asyncio.wait_for(websocket.recv(), timeout=self.timeout)
                return json.loads(response)
                
        except asyncio.TimeoutError:
            self.logger.error(f"Timeout waiting for response from {url}")
            return {"error": "Timeout"}
        except Exception as e:
            self.logger.error(f"WebSocket error with {url}: {e}")
            return {"error": str(e)}
    
    async def _send_http_message(self, url: str, message: A2AMessage) -> Optional[Dict[str, Any]]:
        """Send message via HTTP POST"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    url,
                    json={
                        "message_type": message.message_type.value,
                        "game_id": message.game_id,
                        "player_id": message.player_id,
                        "data": message.data,
                        "timestamp": message.timestamp,
                        "message_id": message.message_id
                    }
                )
                response.raise_for_status()
                return response.json()
                
        except httpx.TimeoutException:
            self.logger.error(f"HTTP timeout with {url}")
            return {"error": "Timeout"}
        except Exception as e:
            self.logger.error(f"HTTP error with {url}: {e}")
            return {"error": str(e)}
    
    def create_message(self, message_type: MessageType, game_id: str, 
                      player_id: str, data: Dict[str, Any]) -> A2AMessage:
        """Create a new A2A message"""
        import time
        import uuid
        
        return A2AMessage(
            message_type=message_type,
            game_id=game_id,
            player_id=player_id,
            data=data,
            timestamp=time.time(),
            message_id=str(uuid.uuid4())
        )
    
    async def request_action(self, agent_url: str, game_id: str, player_id: str, 
                           game_state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Request an action from an agent"""
        message = self.create_message(
            MessageType.ACTION_REQUEST,
            game_id,
            player_id,
            {"game_state": game_state}
        )
        
        response = await self.send_message(agent_url, message)
        
        if response and "error" not in response:
            return response.get("data", {})
        
        return None
    
    async def notify_game_start(self, agent_url: str, game_id: str, player_id: str, 
                              game_info: Dict[str, Any]) -> bool:
        """Notify agent that a game is starting"""
        message = self.create_message(
            MessageType.GAME_START,
            game_id,
            player_id,
            game_info
        )
        
        response = await self.send_message(agent_url, message)
        return response is not None and "error" not in response
    
    async def notify_game_end(self, agent_url: str, game_id: str, player_id: str, 
                            final_results: Dict[str, Any]) -> bool:
        """Notify agent that a game has ended"""
        message = self.create_message(
            MessageType.GAME_END,
            game_id,
            player_id,
            final_results
        )
        
        response = await self.send_message(agent_url, message)
        return response is not None and "error" not in response
    
    async def ping_agent(self, agent_url: str) -> bool:
        """Ping an agent to check if it's alive"""
        message = self.create_message(
            MessageType.PING,
            "ping",
            "system",
            {}
        )
        
        response = await self.send_message(agent_url, message)
        return response is not None and response.get("data", {}).get("pong") is True


class A2AServer:
    """A2A Protocol Server for handling incoming messages from agents"""
    
    def __init__(self, host: str = "localhost", port: int = 8765):
        self.host = host
        self.port = port
        self.logger = logging.getLogger(__name__)
        self.message_handlers: Dict[MessageType, callable] = {}
        
    def register_handler(self, message_type: MessageType, handler: callable):
        """Register a message handler"""
        self.message_handlers[message_type] = handler
    
    async def handle_message(self, websocket, path):
        """Handle incoming WebSocket messages"""
        try:
            async for message in websocket:
                data = json.loads(message)
                message_type = MessageType(data["message_type"])
                
                if message_type in self.message_handlers:
                    response = await self.message_handlers[message_type](data)
                    await websocket.send(json.dumps(response))
                else:
                    await websocket.send(json.dumps({
                        "error": f"No handler for message type: {message_type.value}"
                    }))
                    
        except websockets.exceptions.ConnectionClosed:
            self.logger.info("WebSocket connection closed")
        except Exception as e:
            self.logger.error(f"Error handling message: {e}")
            await websocket.send(json.dumps({"error": str(e)}))
    
    async def start_server(self):
        """Start the A2A server"""
        self.logger.info(f"Starting A2A server on {self.host}:{self.port}")
        await websockets.serve(self.handle_message, self.host, self.port)
    
    async def stop_server(self):
        """Stop the A2A server"""
        self.logger.info("Stopping A2A server")


# Example message handlers for the evaluation agent
class EvaluationAgentHandlers:
    """Message handlers for the evaluation agent"""
    
    def __init__(self, evaluation_agent):
        self.evaluation_agent = evaluation_agent
        self.logger = logging.getLogger(__name__)
    
    async def handle_ping(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle ping messages"""
        return {
            "message_type": MessageType.PONG.value,
            "data": {"pong": True},
            "timestamp": data["timestamp"],
            "message_id": data["message_id"]
        }
    
    async def handle_action_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle action responses from agents"""
        try:
            player_id = data["player_id"]
            game_id = data["game_id"]
            action_data = data["data"]
            
            # Process the action in the evaluation agent
            result = await self.evaluation_agent.process_agent_action(
                game_id, player_id, action_data
            )
            
            return {
                "message_type": MessageType.ACTION_RESPONSE.value,
                "data": result,
                "timestamp": data["timestamp"],
                "message_id": data["message_id"]
            }
            
        except Exception as e:
            self.logger.error(f"Error handling action response: {e}")
            return {
                "error": str(e),
                "message_type": MessageType.ERROR.value
            }
