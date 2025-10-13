"""
Poker Evaluation Agent - Main orchestrator for evaluating poker-playing agents
"""
import asyncio
import json
import logging
import time
import uuid
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from collections import defaultdict
import statistics

from poker_engine import PokerEngine, Action, GameState
from a2a_protocol import A2AProtocol, A2AServer, MessageType, EvaluationAgentHandlers


@dataclass
class AgentConfig:
    id: str
    name: str
    url: str
    timeout: int = 30
    max_actions_per_hand: int = 50


@dataclass
class GameConfig:
    small_blind: int = 10
    big_blind: int = 20
    starting_chips: int = 1000
    max_hands: int = 100
    hand_timeout: int = 300  # 5 minutes per hand


@dataclass
class AgentMetrics:
    agent_id: str
    agent_name: str
    games_played: int = 0
    hands_played: int = 0
    hands_won: int = 0
    total_chips_won: int = 0
    total_chips_lost: int = 0
    net_chips: int = 0
    vpip: float = 0.0  # Voluntarily Put money In Pot
    pfr: float = 0.0   # Pre-Flop Raise
    aggression_factor: float = 0.0
    showdown_percentage: float = 0.0
    win_rate: float = 0.0
    average_hand_strength: float = 0.0
    bluffs_successful: int = 0
    bluffs_attempted: int = 0
    fold_percentage: float = 0.0
    call_percentage: float = 0.0
    raise_percentage: float = 0.0
    all_in_percentage: float = 0.0
    response_times: List[float] = None
    average_response_time: float = 0.0
    errors: int = 0
    timeouts: int = 0
    
    def __post_init__(self):
        if self.response_times is None:
            self.response_times = []


class EvaluationAgent:
    def __init__(self, game_config: GameConfig = None):
        self.game_config = game_config or GameConfig()
        self.poker_engine = PokerEngine(
            small_blind=self.game_config.small_blind,
            big_blind=self.game_config.big_blind
        )
        self.a2a_protocol = A2AProtocol()
        self.a2a_server = A2AServer()
        self.agents: Dict[str, AgentConfig] = {}
        self.metrics: Dict[str, AgentMetrics] = {}
        self.active_games: Dict[str, Dict[str, Any]] = {}
        self.logger = logging.getLogger(__name__)
        
        # Set up message handlers
        self.handlers = EvaluationAgentHandlers(self)
        self.a2a_server.register_handler(MessageType.PING, self.handlers.handle_ping)
        self.a2a_server.register_handler(MessageType.ACTION_RESPONSE, self.handlers.handle_action_response)
    
    def register_agent(self, agent_config: AgentConfig):
        """Register a new agent for evaluation"""
        self.agents[agent_config.id] = agent_config
        self.metrics[agent_config.id] = AgentMetrics(
            agent_id=agent_config.id,
            agent_name=agent_config.name
        )
        self.logger.info(f"Registered agent: {agent_config.name} at {agent_config.url}")
    
    def unregister_agent(self, agent_id: str):
        """Unregister an agent"""
        if agent_id in self.agents:
            del self.agents[agent_id]
            del self.metrics[agent_id]
            self.logger.info(f"Unregistered agent: {agent_id}")
    
    async def start_evaluation_server(self):
        """Start the A2A server for receiving messages"""
        await self.a2a_server.start_server()
        self.logger.info("Evaluation agent server started")
    
    async def run_single_game(self, agent_urls: List[str], game_id: str = None) -> Dict[str, Any]:
        """Run a single poker game with the specified agents"""
        if game_id is None:
            game_id = str(uuid.uuid4())
        
        # Validate agents
        valid_agents = []
        for url in agent_urls:
            agent = next((a for a in self.agents.values() if a.url == url), None)
            if agent:
                valid_agents.append(agent)
            else:
                self.logger.warning(f"Agent with URL {url} not registered")
        
        if len(valid_agents) < 2:
            return {"error": "Need at least 2 valid agents to play"}
        
        # Check agent availability
        available_agents = []
        for agent in valid_agents:
            if await self.a2a_protocol.ping_agent(agent.url):
                available_agents.append(agent)
            else:
                self.logger.warning(f"Agent {agent.name} is not responding")
        
        if len(available_agents) < 2:
            return {"error": "Not enough available agents"}
        
        # Start new game
        player_ids = [agent.id for agent in available_agents]
        player_names = [agent.name for agent in available_agents]
        
        game_state = self.poker_engine.start_new_hand(
            player_ids, player_names, self.game_config.starting_chips
        )
        
        # Store game info
        self.active_games[game_id] = {
            "game_state": game_state,
            "agents": available_agents,
            "start_time": time.time(),
            "hand_number": 1,
            "actions_taken": 0
        }
        
        # Notify agents of game start
        for agent in available_agents:
            await self.a2a_protocol.notify_game_start(
                agent.url, game_id, agent.id, {
                    "game_id": game_id,
                    "player_id": agent.id,
                    "starting_chips": self.game_config.starting_chips,
                    "small_blind": self.game_config.small_blind,
                    "big_blind": self.game_config.big_blind
                }
            )
        
        # Play the hand
        result = await self._play_hand(game_id)
        
        # Clean up
        if game_id in self.active_games:
            del self.active_games[game_id]
        
        return result
    
    async def _play_hand(self, game_id: str) -> Dict[str, Any]:
        """Play a single poker hand"""
        game_info = self.active_games[game_id]
        game_state = game_info["game_state"]
        agents = game_info["agents"]
        
        hand_start_time = time.time()
        actions_taken = 0
        max_actions = max(agent.max_actions_per_hand for agent in agents)
        
        while (game_state.round != "showdown" and 
               len([p for p in game_state.players if p.is_active]) > 1 and
               actions_taken < max_actions):
            
            current_player = game_state.players[game_state.current_player]
            if not current_player.is_active or current_player.chips <= 0:
                self.poker_engine._next_player()
                continue
            
            # Get agent for current player
            agent = next((a for a in agents if a.id == current_player.id), None)
            if not agent:
                self.logger.error(f"No agent found for player {current_player.id}")
                break
            
            # Request action from agent
            action_start_time = time.time()
            try:
                game_state_for_player = self.poker_engine.get_game_state_for_player(current_player.id)
                action_data = await self.a2a_protocol.request_action(
                    agent.url, game_id, current_player.id, game_state_for_player
                )
                action_end_time = time.time()
                
                if action_data is None:
                    self.logger.warning(f"Agent {agent.name} failed to respond, folding")
                    action_data = {"action": "fold"}
                    self.metrics[agent.id].timeouts += 1
                else:
                    response_time = action_end_time - action_start_time
                    self.metrics[agent.id].response_times.append(response_time)
                    self.metrics[agent.id].average_response_time = statistics.mean(self.metrics[agent.id].response_times)
                
            except Exception as e:
                self.logger.error(f"Error requesting action from {agent.name}: {e}")
                action_data = {"action": "fold"}
                self.metrics[agent.id].errors += 1
            
            # Process the action
            try:
                action = Action(action_data.get("action", "fold"))
                amount = action_data.get("amount", 0)
                
                result = self.poker_engine.process_action(current_player.id, action, amount)
                
                if result.get("success"):
                    actions_taken += 1
                    self._update_metrics_from_action(agent.id, action, game_state)
                else:
                    self.logger.warning(f"Invalid action from {agent.name}: {result.get('error')}")
                
            except ValueError as e:
                self.logger.warning(f"Invalid action from {agent.name}: {e}")
            
            # Check for timeout
            if time.time() - hand_start_time > self.game_config.hand_timeout:
                self.logger.warning(f"Hand timeout reached for game {game_id}")
                break
        
        # Determine final results
        final_results = self._calculate_final_results(game_id)
        
        # Notify agents of game end
        for agent in agents:
            await self.a2a_protocol.notify_game_end(
                agent.url, game_id, agent.id, final_results
            )
        
        return final_results
    
    def _update_metrics_from_action(self, agent_id: str, action: Action, game_state: GameState):
        """Update agent metrics based on action taken"""
        metrics = self.metrics[agent_id]
        
        if action == Action.FOLD:
            metrics.fold_percentage += 1
        elif action == Action.CALL:
            metrics.call_percentage += 1
        elif action == Action.RAISE:
            metrics.raise_percentage += 1
        elif action == Action.ALL_IN:
            metrics.all_in_percentage += 1
        
        # Update VPIP and PFR for preflop actions
        if game_state.round == "preflop":
            if action in [Action.CALL, Action.RAISE, Action.ALL_IN]:
                metrics.vpip += 1
            if action in [Action.RAISE, Action.ALL_IN]:
                metrics.pfr += 1
    
    def _calculate_final_results(self, game_id: str) -> Dict[str, Any]:
        """Calculate final results of a game"""
        game_info = self.active_games[game_id]
        game_state = game_info["game_state"]
        agents = game_info["agents"]
        
        # Update metrics
        for agent in agents:
            metrics = self.metrics[agent.id]
            player = next((p for p in game_state.players if p.id == agent.id), None)
            
            if player:
                metrics.games_played += 1
                metrics.hands_played += 1
                
                if player.is_active and player.chips > 0:
                    metrics.hands_won += 1
                
                chip_change = player.chips - self.game_config.starting_chips
                if chip_change > 0:
                    metrics.total_chips_won += chip_change
                else:
                    metrics.total_chips_lost += abs(chip_change)
                
                metrics.net_chips += chip_change
                metrics.win_rate = metrics.hands_won / max(metrics.hands_played, 1)
        
        # Calculate final standings
        standings = []
        for player in sorted(game_state.players, key=lambda p: p.chips, reverse=True):
            agent = next((a for a in agents if a.id == player.id), None)
            standings.append({
                "player_id": player.id,
                "player_name": player.name,
                "final_chips": player.chips,
                "chip_change": player.chips - self.game_config.starting_chips
            })
        
        return {
            "game_id": game_id,
            "final_pot": game_state.pot,
            "community_cards": [str(card) for card in game_state.community_cards],
            "standings": standings,
            "hand_number": game_info["hand_number"],
            "actions_taken": game_info["actions_taken"]
        }
    
    async def run_tournament(self, agent_urls: List[str], num_games: int = 10) -> Dict[str, Any]:
        """Run a tournament with multiple games"""
        tournament_id = str(uuid.uuid4())
        tournament_results = {
            "tournament_id": tournament_id,
            "games": [],
            "final_standings": {},
            "agent_metrics": {}
        }
        
        self.logger.info(f"Starting tournament {tournament_id} with {len(agent_urls)} agents")
        
        for game_num in range(num_games):
            self.logger.info(f"Playing game {game_num + 1}/{num_games}")
            
            game_result = await self.run_single_game(agent_urls, f"{tournament_id}_game_{game_num}")
            tournament_results["games"].append(game_result)
            
            # Small delay between games
            await asyncio.sleep(1)
        
        # Calculate final tournament standings
        tournament_results["final_standings"] = self._calculate_tournament_standings()
        tournament_results["agent_metrics"] = {aid: asdict(metrics) for aid, metrics in self.metrics.items()}
        
        return tournament_results
    
    def _calculate_tournament_standings(self) -> List[Dict[str, Any]]:
        """Calculate final tournament standings"""
        standings = []
        for agent_id, metrics in self.metrics.items():
            standings.append({
                "agent_id": agent_id,
                "agent_name": metrics.agent_name,
                "net_chips": metrics.net_chips,
                "win_rate": metrics.win_rate,
                "games_played": metrics.games_played,
                "average_response_time": metrics.average_response_time,
                "errors": metrics.errors,
                "timeouts": metrics.timeouts
            })
        
        return sorted(standings, key=lambda x: x["net_chips"], reverse=True)
    
    async def process_agent_action(self, game_id: str, player_id: str, action_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process an action response from an agent"""
        if game_id not in self.active_games:
            return {"error": "Game not found"}
        
        # This method can be used for real-time action processing
        # For now, we'll just return success
        return {"success": True, "action_processed": True}
    
    def get_agent_metrics(self, agent_id: str = None) -> Dict[str, Any]:
        """Get metrics for a specific agent or all agents"""
        if agent_id:
            if agent_id in self.metrics:
                return asdict(self.metrics[agent_id])
            else:
                return {"error": "Agent not found"}
        else:
            return {aid: asdict(metrics) for aid, metrics in self.metrics.items()}
    
    def reset_metrics(self, agent_id: str = None):
        """Reset metrics for a specific agent or all agents"""
        if agent_id:
            if agent_id in self.metrics:
                self.metrics[agent_id] = AgentMetrics(
                    agent_id=agent_id,
                    agent_name=self.metrics[agent_id].agent_name
                )
        else:
            for aid, metrics in self.metrics.items():
                self.metrics[aid] = AgentMetrics(
                    agent_id=aid,
                    agent_name=metrics.agent_name
                )
