"""
Example participating poker agents for testing the evaluation system
"""
import asyncio
import json
import logging
import random
import time
from typing import Dict, Any, List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
import uvicorn
from poker_engine import Action, HandRank


class BasePokerAgent:
    """Base class for poker agents"""
    
    def __init__(self, agent_id: str, agent_name: str):
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.logger = logging.getLogger(f"Agent-{agent_name}")
        self.game_history: List[Dict[str, Any]] = []
    
    async def get_action(self, game_state: Dict[str, Any]) -> Dict[str, Any]:
        """Get action based on game state - to be implemented by subclasses"""
        raise NotImplementedError
    
    def log_action(self, action: str, game_state: Dict[str, Any], reasoning: str = ""):
        """Log action taken by agent"""
        self.logger.info(f"Action: {action}, Reasoning: {reasoning}")
        self.game_history.append({
            "timestamp": time.time(),
            "action": action,
            "game_state": game_state,
            "reasoning": reasoning
        })


class RandomAgent(BasePokerAgent):
    """Random poker agent that makes random decisions"""
    
    def __init__(self, agent_id: str = "random", agent_name: str = "Random Agent"):
        super().__init__(agent_id, agent_name)
        self.fold_probability = 0.3
        self.call_probability = 0.4
        self.raise_probability = 0.3
    
    async def get_action(self, game_state: Dict[str, Any]) -> Dict[str, Any]:
        """Make random action based on probabilities"""
        if not game_state.get("is_your_turn", False):
            return {"action": "fold"}
        
        # Check if we can check
        if game_state.get("your_current_bet", 0) >= game_state.get("current_bet", 0):
            if random.random() < 0.5:
                self.log_action("check", game_state, "Random check")
                return {"action": "check"}
        
        # Make random decision
        rand = random.random()
        
        if rand < self.fold_probability:
            self.log_action("fold", game_state, "Random fold")
            return {"action": "fold"}
        elif rand < self.fold_probability + self.call_probability:
            call_amount = min(
                game_state.get("current_bet", 0) - game_state.get("your_current_bet", 0),
                game_state.get("your_chips", 0)
            )
            self.log_action("call", game_state, f"Random call for {call_amount}")
            return {"action": "call", "amount": call_amount}
        else:
            # Raise
            current_bet = game_state.get("current_bet", 0)
            your_bet = game_state.get("your_current_bet", 0)
            your_chips = game_state.get("your_chips", 0)
            
            if your_chips <= 0:
                self.log_action("fold", game_state, "No chips left")
                return {"action": "fold"}
            
            # Random raise between 2x and 4x current bet
            raise_amount = current_bet * random.uniform(2, 4)
            raise_amount = min(raise_amount, your_chips)
            
            self.log_action("raise", game_state, f"Random raise to {raise_amount}")
            return {"action": "raise", "amount": raise_amount}


class ConservativeAgent(BasePokerAgent):
    """Conservative poker agent that plays tight"""
    
    def __init__(self, agent_id: str = "conservative", agent_name: str = "Conservative Agent"):
        super().__init__(agent_id, agent_name)
    
    async def get_action(self, game_state: Dict[str, Any]) -> Dict[str, Any]:
        """Make conservative decisions"""
        if not game_state.get("is_your_turn", False):
            return {"action": "fold"}
        
        your_cards = game_state.get("your_cards", [])
        community_cards = game_state.get("community_cards", [])
        current_bet = game_state.get("current_bet", 0)
        your_bet = game_state.get("your_current_bet", 0)
        your_chips = game_state.get("your_chips", 0)
        
        # Simple hand strength evaluation
        hand_strength = self._evaluate_hand_strength(your_cards, community_cards)
        
        # Very conservative play
        if hand_strength < 0.3:
            if your_bet >= current_bet:
                self.log_action("check", game_state, f"Hand strength {hand_strength:.2f} - checking")
                return {"action": "check"}
            else:
                self.log_action("fold", game_state, f"Hand strength {hand_strength:.2f} - folding")
                return {"action": "fold"}
        elif hand_strength < 0.6:
            if your_bet >= current_bet:
                self.log_action("check", game_state, f"Hand strength {hand_strength:.2f} - checking")
                return {"action": "check"}
            else:
                call_amount = min(current_bet - your_bet, your_chips)
                self.log_action("call", game_state, f"Hand strength {hand_strength:.2f} - calling {call_amount}")
                return {"action": "call", "amount": call_amount}
        else:
            # Strong hand - raise
            if your_chips <= 0:
                self.log_action("fold", game_state, "No chips left")
                return {"action": "fold"}
            
            raise_amount = current_bet * 2
            raise_amount = min(raise_amount, your_chips)
            
            self.log_action("raise", game_state, f"Hand strength {hand_strength:.2f} - raising to {raise_amount}")
            return {"action": "raise", "amount": raise_amount}
    
    def _evaluate_hand_strength(self, hole_cards: List[str], community_cards: List[str]) -> float:
        """Simple hand strength evaluation (0.0 to 1.0)"""
        # This is a very simplified evaluation
        # In a real implementation, you'd want more sophisticated hand evaluation
        
        if len(hole_cards) < 2:
            return 0.0
        
        # Count high cards
        high_cards = 0
        for card in hole_cards:
            if any(rank in card for rank in ['A', 'K', 'Q', 'J']):
                high_cards += 1
        
        # Check for pairs
        ranks = [card[0] for card in hole_cards]
        has_pair = len(set(ranks)) == 1
        
        # Check for suited cards
        suits = [card[-1] for card in hole_cards]
        is_suited = len(set(suits)) == 1
        
        # Simple scoring
        score = 0.0
        score += high_cards * 0.2
        if has_pair:
            score += 0.3
        if is_suited:
            score += 0.1
        
        return min(score, 1.0)


class AggressiveAgent(BasePokerAgent):
    """Aggressive poker agent that plays loose and aggressive"""
    
    def __init__(self, agent_id: str = "aggressive", agent_name: str = "Aggressive Agent"):
        super().__init__(agent_id, agent_name)
    
    async def get_action(self, game_state: Dict[str, Any]) -> Dict[str, Any]:
        """Make aggressive decisions"""
        if not game_state.get("is_your_turn", False):
            return {"action": "fold"}
        
        your_cards = game_state.get("your_cards", [])
        community_cards = game_state.get("community_cards", [])
        current_bet = game_state.get("current_bet", 0)
        your_bet = game_state.get("your_current_bet", 0)
        your_chips = game_state.get("your_chips", 0)
        
        # Aggressive play - bluff frequently
        hand_strength = self._evaluate_hand_strength(your_cards, community_cards)
        
        # Very aggressive - rarely fold
        if hand_strength < 0.2 and random.random() < 0.8:
            # Bluff
            if your_chips <= 0:
                self.log_action("fold", game_state, "No chips left")
                return {"action": "fold"}
            
            bluff_amount = current_bet * random.uniform(1.5, 3)
            bluff_amount = min(bluff_amount, your_chips)
            
            self.log_action("raise", game_state, f"Bluffing with hand strength {hand_strength:.2f}")
            return {"action": "raise", "amount": bluff_amount}
        elif hand_strength < 0.5:
            if your_bet >= current_bet:
                self.log_action("check", game_state, f"Hand strength {hand_strength:.2f} - checking")
                return {"action": "check"}
            else:
                call_amount = min(current_bet - your_bet, your_chips)
                self.log_action("call", game_state, f"Hand strength {hand_strength:.2f} - calling {call_amount}")
                return {"action": "call", "amount": call_amount}
        else:
            # Strong hand - big raise
            if your_chips <= 0:
                self.log_action("fold", game_state, "No chips left")
                return {"action": "fold"}
            
            raise_amount = current_bet * random.uniform(2, 5)
            raise_amount = min(raise_amount, your_chips)
            
            self.log_action("raise", game_state, f"Hand strength {hand_strength:.2f} - big raise to {raise_amount}")
            return {"action": "raise", "amount": raise_amount}
    
    def _evaluate_hand_strength(self, hole_cards: List[str], community_cards: List[str]) -> float:
        """Simple hand strength evaluation (0.0 to 1.0)"""
        # Same as conservative agent for now
        if len(hole_cards) < 2:
            return 0.0
        
        high_cards = 0
        for card in hole_cards:
            if any(rank in card for rank in ['A', 'K', 'Q', 'J']):
                high_cards += 1
        
        ranks = [card[0] for card in hole_cards]
        has_pair = len(set(ranks)) == 1
        
        suits = [card[-1] for card in hole_cards]
        is_suited = len(set(suits)) == 1
        
        score = 0.0
        score += high_cards * 0.2
        if has_pair:
            score += 0.3
        if is_suited:
            score += 0.1
        
        return min(score, 1.0)


class SmartAgent(BasePokerAgent):
    """Smarter poker agent with better hand evaluation"""
    
    def __init__(self, agent_id: str = "smart", agent_name: str = "Smart Agent"):
        super().__init__(agent_id, agent_name)
    
    async def get_action(self, game_state: Dict[str, Any]) -> Dict[str, Any]:
        """Make smart decisions based on hand strength and position"""
        if not game_state.get("is_your_turn", False):
            return {"action": "fold"}
        
        your_cards = game_state.get("your_cards", [])
        community_cards = game_state.get("community_cards", [])
        current_bet = game_state.get("current_bet", 0)
        your_bet = game_state.get("your_current_bet", 0)
        your_chips = game_state.get("your_chips", 0)
        pot = game_state.get("pot", 0)
        
        # Better hand evaluation
        hand_strength = self._evaluate_hand_strength(your_cards, community_cards)
        
        # Position-based play
        players = game_state.get("players", [])
        your_position = next((i for i, p in enumerate(players) if p.get("name") == self.agent_name), 0)
        is_early_position = your_position < len(players) // 2
        
        # Pot odds consideration
        call_amount = current_bet - your_bet
        pot_odds = call_amount / (pot + call_amount) if (pot + call_amount) > 0 else 0
        
        # Decision logic
        if hand_strength < 0.2:
            if your_bet >= current_bet:
                self.log_action("check", game_state, f"Hand strength {hand_strength:.2f} - checking")
                return {"action": "check"}
            else:
                self.log_action("fold", game_state, f"Hand strength {hand_strength:.2f} - folding")
                return {"action": "fold"}
        elif hand_strength < 0.4:
            if your_bet >= current_bet:
                self.log_action("check", game_state, f"Hand strength {hand_strength:.2f} - checking")
                return {"action": "check"}
            elif pot_odds < 0.3:  # Good pot odds
                call_amount = min(call_amount, your_chips)
                self.log_action("call", game_state, f"Hand strength {hand_strength:.2f} - calling {call_amount}")
                return {"action": "call", "amount": call_amount}
            else:
                self.log_action("fold", game_state, f"Hand strength {hand_strength:.2f} - bad pot odds")
                return {"action": "fold"}
        elif hand_strength < 0.7:
            if your_bet >= current_bet:
                self.log_action("check", game_state, f"Hand strength {hand_strength:.2f} - checking")
                return {"action": "check"}
            else:
                call_amount = min(call_amount, your_chips)
                self.log_action("call", game_state, f"Hand strength {hand_strength:.2f} - calling {call_amount}")
                return {"action": "call", "amount": call_amount}
        else:
            # Strong hand - raise
            if your_chips <= 0:
                self.log_action("fold", game_state, "No chips left")
                return {"action": "fold"}
            
            # Adjust raise size based on position and hand strength
            if is_early_position:
                raise_amount = current_bet * 2.5
            else:
                raise_amount = current_bet * 2
            
            raise_amount = min(raise_amount, your_chips)
            
            self.log_action("raise", game_state, f"Hand strength {hand_strength:.2f} - raising to {raise_amount}")
            return {"action": "raise", "amount": raise_amount}
    
    def _evaluate_hand_strength(self, hole_cards: List[str], community_cards: List[str]) -> float:
        """Better hand strength evaluation"""
        if len(hole_cards) < 2:
            return 0.0
        
        # Convert card strings to rank values
        def card_value(card_str):
            rank = card_str[0]
            if rank == 'A':
                return 14
            elif rank == 'K':
                return 13
            elif rank == 'Q':
                return 12
            elif rank == 'J':
                return 11
            elif rank == 'T':
                return 10
            else:
                return int(rank)
        
        hole_values = [card_value(card) for card in hole_cards]
        hole_values.sort(reverse=True)
        
        # High card strength
        high_card_strength = hole_values[0] / 14.0
        
        # Pair strength
        pair_strength = 0.0
        if hole_values[0] == hole_values[1]:
            pair_strength = hole_values[0] / 14.0
        
        # Suited strength
        suited_strength = 0.0
        if len(set(card[-1] for card in hole_cards)) == 1:
            suited_strength = 0.1
        
        # Connected strength
        connected_strength = 0.0
        if abs(hole_values[0] - hole_values[1]) == 1:
            connected_strength = 0.1
        
        # Combine factors
        total_strength = high_card_strength * 0.4 + pair_strength * 0.4 + suited_strength + connected_strength
        
        return min(total_strength, 1.0)


def create_agent_server(agent: BasePokerAgent, port: int) -> FastAPI:
    """Create a FastAPI server for an agent"""
    app = FastAPI(title=f"Poker Agent - {agent.agent_name}")
    
    @app.post("/")
    async def handle_message(request: dict):
        """Handle incoming A2A messages"""
        try:
            message_type = request.get("message_type")
            data = request.get("data", {})
            
            if message_type == "action_request":
                game_state = data.get("game_state", {})
                action = await agent.get_action(game_state)
                
                return {
                    "message_type": "action_response",
                    "data": action,
                    "timestamp": request.get("timestamp"),
                    "message_id": request.get("message_id")
                }
            elif message_type == "game_start":
                agent.logger.info(f"Game started: {data}")
                return {"success": True}
            elif message_type == "game_end":
                agent.logger.info(f"Game ended: {data}")
                return {"success": True}
            elif message_type == "ping":
                return {
                    "message_type": "pong",
                    "data": {"pong": True},
                    "timestamp": request.get("timestamp"),
                    "message_id": request.get("message_id")
                }
            else:
                return {"error": f"Unknown message type: {message_type}"}
                
        except Exception as e:
            agent.logger.error(f"Error handling message: {e}")
            return {"error": str(e)}
    
    return app


async def run_agent_server(agent: BasePokerAgent, port: int):
    """Run an agent server"""
    app = create_agent_server(agent, port)
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    # Create example agents
    agents = [
        RandomAgent("random", "Random Agent"),
        ConservativeAgent("conservative", "Conservative Agent"),
        AggressiveAgent("aggressive", "Aggressive Agent"),
        SmartAgent("smart", "Smart Agent")
    ]
    
    # Run all agents
    async def run_all_agents():
        tasks = []
        for i, agent in enumerate(agents):
            port = 8001 + i
            agent.logger.info(f"Starting {agent.agent_name} on port {port}")
            tasks.append(run_agent_server(agent, port))
        
        await asyncio.gather(*tasks)
    
    asyncio.run(run_all_agents())
