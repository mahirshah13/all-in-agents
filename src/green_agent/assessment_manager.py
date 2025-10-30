#!/usr/bin/env python3
"""
Poker Assessment Manager - Green Agent
Coordinates poker evaluations and manages white agents
"""
import asyncio
import logging
import json
import random
import time
import uuid
import toml
import httpx
import os
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict

from a2a import types
from a2a.client import ClientFactory, ClientConfig, A2ACardResolver, A2AClient
from a2a.server.agent_execution import AgentExecutor
from a2a.server.context import ServerCallContext
from a2a.server.events import EventQueue
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
import uvicorn

from poker_engine import PokerEngine, Action, GameState
from src.my_util.my_a2a import get_agent_card, wait_agent_ready, send_message


@dataclass
class WhiteAgentConfig:
    """Configuration for a white agent"""
    id: str
    name: str
    type: str
    url: str
    config: Optional[Dict[str, Any]] = None


@dataclass
class GameResult:
    """Result of a single poker game"""
    game_id: str
    participants: List[str]
    winner: str
    final_chips: Dict[str, int]
    hands_played: int
    duration: float
    game_log: List[Dict[str, Any]]


@dataclass
class EvaluationResult:
    """Result of evaluating an agent"""
    agent_id: str
    agent_name: str
    agent_type: str
    games_played: int
    total_hands: int
    hands_won: int
    win_rate: float
    net_chips: int
    average_response_time: float
    performance_score: float


class PokerAssessmentManager(AgentExecutor):
    """
    Green Agent - Poker Assessment Manager
    Coordinates evaluations and manages white agents
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__()
        self.config = config
        self.logger = logging.getLogger(__name__)

        # Load configuration and override with environment variables
        self.agent_config = config["agent"]
        self.evaluation_config = self._load_evaluation_config(config["evaluation"])
        self.poker_rules = self._load_poker_rules(config["poker_rules"])
        self.metrics_config = config["metrics"]
        self.output_config = config["output"]

        # Initialize white agents from config
        self.white_agents: Dict[str, WhiteAgentConfig] = {}
        for agent_data in self.evaluation_config["white_agents"]:
            self.white_agents[agent_data["id"]] = WhiteAgentConfig(
                id=agent_data["id"],
                name=agent_data["name"],
                type=agent_data["type"],
                url=agent_data["url"],
                config=agent_data.get("config", {})
            )

        # Initialize evaluation results
        self.evaluation_results: Dict[str, EvaluationResult] = {}
        self.poker_engine = PokerEngine(
            small_blind=self.poker_rules["small_blind"],
            big_blind=self.poker_rules["big_blind"]
        )
        self.active_games: Dict[str, Dict[str, Any]] = {}

        # A2A client for communicating with white agents
        self.client_config = ClientConfig()
        self.client_factory = ClientFactory(self.client_config)
        # Note: A2ACardResolver will be initialized when needed with proper httpx client

        # Event queue for handling A2A events
        self.event_queue = EventQueue()
        
        # Context management for maintaining conversation history with each agent
        self.agent_contexts: Dict[str, str] = {}
        
        # Log configuration values being used
        self.logger.info(f"Configuration loaded:")
        self.logger.info(f"  - Games per agent: {self.evaluation_config.get('games_per_agent', 10)}")
        self.logger.info(f"  - Tournament games: {self.evaluation_config.get('tournament_games', 5)}")
        self.logger.info(f"  - Small blind: {self.poker_rules.get('small_blind', 10)}")
        self.logger.info(f"  - Big blind: {self.poker_rules.get('big_blind', 20)}")
        self.logger.info(f"  - Starting chips: {self.poker_rules.get('starting_chips', 1000)}")
        self.logger.info(f"  - Max players: {self.poker_rules.get('max_players', 4)}")

    def _load_evaluation_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Load evaluation configuration with environment variable overrides"""
        evaluation_config = config.copy()
        
        # Override with environment variables if they exist
        if os.getenv("EVALUATION_GAMES_PER_AGENT"):
            evaluation_config["games_per_agent"] = int(os.getenv("EVALUATION_GAMES_PER_AGENT"))
        
        if os.getenv("EVALUATION_TOURNAMENT_GAMES"):
            evaluation_config["tournament_games"] = int(os.getenv("EVALUATION_TOURNAMENT_GAMES"))
        
        if os.getenv("EVALUATION_TIMEOUT"):
            evaluation_config["evaluation_timeout"] = int(os.getenv("EVALUATION_TIMEOUT"))
        
        return evaluation_config

    def _load_poker_rules(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Load poker rules configuration with environment variable overrides"""
        poker_rules = config.copy()
        
        # Override with environment variables if they exist
        if os.getenv("POKER_SMALL_BLIND"):
            poker_rules["small_blind"] = int(os.getenv("POKER_SMALL_BLIND"))
        
        if os.getenv("POKER_BIG_BLIND"):
            poker_rules["big_blind"] = int(os.getenv("POKER_BIG_BLIND"))
        
        if os.getenv("POKER_STARTING_CHIPS"):
            poker_rules["starting_chips"] = int(os.getenv("POKER_STARTING_CHIPS"))
        
        if os.getenv("POKER_MAX_PLAYERS"):
            poker_rules["max_players"] = int(os.getenv("POKER_MAX_PLAYERS"))
        
        return poker_rules

    async def execute(self, context: ServerCallContext, event_queue: EventQueue) -> None:
        """Execute the assessment manager's main logic"""
        try:
            # Parse the incoming message
            message_text = ""
            for part in context.request.message.parts:
                if hasattr(part, 'text'):
                    message_text += part.text
            
            # Parse as JSON if possible
            try:
                task_data = json.loads(message_text)
                task_type = task_data.get("task_type", "evaluation")
            except json.JSONDecodeError:
                task_type = "evaluation"
                task_data = {"task_type": "evaluation"}
            
            if task_type == "evaluation":
                await self._run_a2a_evaluation(task_data)
            elif task_type == "tournament":
                await self._run_a2a_tournament(task_data)
            else:
                self.logger.error(f"Unknown task type: {task_type}")
                
        except Exception as e:
            self.logger.error(f"Error in assessment manager execution: {e}")

    async def cancel(self, context: ServerCallContext, event_queue: EventQueue) -> None:
        """Cancel any active evaluations"""
        self.logger.info("Cancelling active evaluations...")
        self.active_games.clear()
        self.evaluation_results.clear()

    def print_status(self, message: str, status: str = "INFO"):
        """Print status message with tau-bench style formatting"""
        if status == "SUCCESS":
            print(f"✅ {message}")
        elif status == "ERROR":
            print(f"❌ {message}")
        elif status == "WARNING":
            print(f"⚠️  {message}")
        else:
            print(f"ℹ️  {message}")

    def print_agent_communication(self, from_agent: str, to_agent: str, message: str):
        """Print agent communication in tau-bench style"""
        print(f"@@@ {from_agent}: Sending message to {to_agent}... -->")
        print()
        print(message)
        print()

    def print_agent_response(self, agent_name: str, response: str):
        """Print agent response in tau-bench style"""
        print(f"@@@ {agent_name} response:")
        print(response)
        print()

    def _create_poker_task_description(self) -> str:
        """Create poker task description for white agents"""
        return f"""# Poker Agent Evaluation Task

You are being evaluated as a poker-playing agent. Your task is to play Texas Hold'em poker games and make optimal decisions based on the game state.

## Game Rules:
- Texas Hold'em poker with small blind: {self.poker_rules['small_blind']}, big blind: {self.poker_rules['big_blind']}
- Starting chips: 1000 per player
- Standard poker hand rankings apply
- You can fold, call, or raise on each betting round

## Your Role:
- Make optimal poker decisions based on your cards and game state
- Respond with JSON format: {{"action": "fold/call/raise", "amount": <bet_amount>}}
- Consider pot odds, position, and opponent behavior
- Play strategically to maximize your chip count

## Evaluation Criteria:
- Win rate (percentage of hands won)
- Net chip gain/loss
- Strategic decision making
- Response time

## Expected Input Format:
When the green agent sends you a game state, you will receive:
- game_state: Current game phase and pot information
- player_cards: Your hole cards (e.g., ["As", "Kh"])
- community_cards: Community cards (flop, turn, river)
- pot_size: Current pot size
- current_bet: Current bet amount
- player_position: Your position (button, early, etc.)

## Expected Output Format:
Respond with JSON:
{{
  "action": "fold|call|raise",
  "amount": 60,
  "confidence": 0.8,
  "reasoning": "Strong starting hand, raising to build pot"
}}

Please respond with your poker decisions in the specified JSON format."""

    async def _run_a2a_evaluation(self, task_data: Dict[str, Any]):
        """Run evaluation using A2A communication with white agents"""
        self.print_status("Starting A2A-based poker evaluation...")
        
        # Give context to white agents via A2A
        await self._give_context_to_white_agents_a2a()
        
        # Run tournament with real poker games
        await self._run_tournament_a2a()
        
        # Show final results
        self._print_final_report()

    async def _run_a2a_tournament(self, task_data: Dict[str, Any]):
        """Run tournament using A2A communication with white agents"""
        self.print_status("Starting A2A-based poker tournament...")
        
        # Send tournament task description via A2A
        tournament_description = self._create_tournament_task_description()
        await self._send_message_to_all_agents_a2a("Tournament Participants", tournament_description)
        
        # Run tournament via A2A
        await self._run_tournament_a2a()
        
        # Show final results
        self._print_final_report()

    async def _give_context_to_white_agents_a2a(self):
        """Give context to white agents via A2A communication"""
        self.print_status("Giving context to white agents via A2A...")
        
        # Create poker task description
        task_description = self._create_poker_task_description()
        
        for agent_id, agent in self.white_agents.items():            
            # Send message via A2A
            try:
                response = await self._send_message_to_agent_a2a(agent, task_description)
                self.print_agent_response(agent.name, response)
            except Exception as e:
                self.print_status(f"Failed to communicate with {agent.name}: {e}", "ERROR")
                raise e  # Don't simulate, fail if can't communicate
            
            # Small delay between agents
            await asyncio.sleep(0.5)

    async def _send_message_to_agent_a2a(self, agent: WhiteAgentConfig, message: str) -> str:
        """Send message to agent via A2A protocol using my_a2a utilities"""
        try:
            # Wait for agent to be ready
            if not await wait_agent_ready(agent.url, timeout=10):
                raise Exception(f"Agent {agent.name} not ready after timeout")

            # Get or create context ID for this agent to maintain conversation history
            if agent.id not in self.agent_contexts:
                import uuid
                self.agent_contexts[agent.id] = str(uuid.uuid4())
            
            context_id = self.agent_contexts[agent.id]
            
            self.print_agent_communication("Green Agent", agent.name, message)
            
            # Send message using A2A protocol with persistent context
            response = await send_message(agent.url, message, context_id=context_id)

            # Extract response text from A2A response
            response_text = self._extract_text_from_a2a_response(response)
            
            return response_text
                
        except Exception as e:
            self.logger.error(f"Failed to send A2A message to {agent.name}: {e}")
            raise

    def _extract_text_from_a2a_response(self, response) -> str:
        """Extract text content from A2A response object"""
        try:
            # Handle different A2A response formats
            if hasattr(response, 'result') and response.result:
                # Standard A2A response with result
                if hasattr(response.result, 'message') and response.result.message:
                    return self._extract_text_from_message(response.result.message)
                elif hasattr(response.result, 'text'):
                    return response.result.text
                else:
                    return str(response.result)
            elif hasattr(response, 'message') and response.message:
                # Direct message in response
                return self._extract_text_from_message(response.message)
            elif hasattr(response, 'text'):
                # Direct text in response
                return response.text
            else:
                # Fallback: try to extract text from string representation using regex
                response_str = str(response)
                import re
                # Look for text='...' pattern in the response string, handling escaped quotes
                text_match = re.search(r"text='((?:[^'\\]|\\.)*)'", response_str)
                if text_match:
                    # Unescape the text
                    text = text_match.group(1)
                    text = text.replace("\\'", "'")
                    text = text.replace("\\n", "\n")
                    text = text.replace("\\t", "\t")
                    return text
                else:
                    return response_str
        except Exception as e:
            self.logger.error(f"Error extracting text from A2A response: {e}")
            return str(response)

    def _extract_text_from_message(self, message) -> str:
        """Extract text from A2A message object"""
        try:
            if hasattr(message, 'parts') and message.parts:
                text_parts = []
                for part in message.parts:
                    if hasattr(part, 'text'):
                        text_parts.append(part.text)
                    elif hasattr(part, 'content'):
                        text_parts.append(part.content)
                    elif hasattr(part, 'root') and hasattr(part.root, 'text'):
                        text_parts.append(part.root.text)
                return ''.join(text_parts)
            elif hasattr(message, 'text'):
                return message.text
            elif hasattr(message, 'content'):
                return message.content
            else:
                return str(message)
        except Exception as e:
            self.logger.error(f"Error extracting text from message: {e}")
            return str(message)

    async def _send_message_to_all_agents_a2a(self, target: str, message: str):
        """Send message to all agents via A2A communication"""
        self.print_agent_communication("Green agent", target, message)
        
        for agent_id, agent in self.white_agents.items():
            try:
                response = await self._send_message_to_agent_a2a(agent, message)
                self.print_agent_response(agent.name, response)
            except Exception as e:
                self.print_status(f"Failed to communicate with {agent.name}: {e}", "ERROR")
                raise e  # Don't simulate, fail if can't communicate

    async def _run_tournament_a2a(self):
        """Run tournament between all agents via A2A"""
        self.print_status("Starting A2A tournament...")
        
        agent_ids = list(self.white_agents.keys())
        num_games = self.evaluation_config["tournament_games"]
        
        # Initialize tournament stats
        tournament_stats = {aid: {"wins": 0, "total_chips": 0, "hands_won": 0, "total_hands": 0} for aid in agent_ids}
        
        for game_num in range(num_games):
            self.print_status(f"Tournament Game {game_num + 1}/{num_games}")
            
            # Run actual poker game with A2A communication
            game_result = await self._run_poker_game_a2a(agent_ids)
            
            if game_result:
                winner = game_result["winner"]
                tournament_stats[winner]["wins"] += 1
                tournament_stats[winner]["total_chips"] += game_result["final_chips"][winner]
                tournament_stats[winner]["hands_won"] += game_result["hands_won"][winner]
                tournament_stats[winner]["total_hands"] += game_result["total_hands"]
                
                # Update other players' stats
                for aid in agent_ids:
                    if aid != winner:
                        tournament_stats[aid]["total_chips"] += game_result["final_chips"][aid]
                        tournament_stats[aid]["hands_won"] += game_result["hands_won"][aid]
                        tournament_stats[aid]["total_hands"] += game_result["total_hands"]
                
                self.print_status(f"Game {game_num + 1} completed - Winner: {self.white_agents[winner].name}")
        
        # Update evaluation results
        for aid in agent_ids:
            stats = tournament_stats[aid]
            agent = self.white_agents[aid]
            
            self.evaluation_results[aid] = EvaluationResult(
                agent_id=aid,
                agent_name=agent.name,
                agent_type=agent.type,
                games_played=num_games,
                total_hands=stats["total_hands"],
                hands_won=stats["hands_won"],
                win_rate=stats["hands_won"] / stats["total_hands"] if stats["total_hands"] > 0 else 0,
                net_chips=stats["total_chips"] - (num_games * self.poker_rules.get("starting_chips", 1000)),  # Starting chips per game
                average_response_time=0.0,  # TODO: Track actual response times
                performance_score=self._calculate_performance_score(stats["hands_won"], stats["total_hands"], stats["total_chips"] - (num_games * self.poker_rules.get("starting_chips", 1000)))
            )
        
        # Show tournament results
        self.print_status("Tournament completed!", "SUCCESS")
        print("\n🏆 Final Tournament Rankings:")
        rankings = sorted(tournament_stats.items(), key=lambda x: (x[1]["wins"], x[1]["total_chips"]), reverse=True)
        for i, (aid, stats) in enumerate(rankings, 1):
            agent_name = self.white_agents[aid].name
            win_rate = stats["wins"] / num_games
            print(f"  {i}. {agent_name} - {stats['wins']} wins, {stats['total_chips']} chips ({win_rate:.1%} win rate)")

    async def _run_poker_game_a2a(self, agent_ids: List[str]) -> Optional[Dict[str, Any]]:
        """Run a real poker game using A2A communication with agents"""
        try:
            # Track game stats
            hands_won = {aid: 0 for aid in agent_ids}
            total_hands = 0
            game_log = []
            
            # Play multiple hands until one player is eliminated or max hands reached
            max_hands = self.evaluation_config.get("games_per_agent", 10)
            for hand_num in range(max_hands):
                self.print_status(f"Playing hand {hand_num + 1}")
                
                # Start new hand with all agents
                agent_names = [self.white_agents[aid].name for aid in agent_ids]
                starting_chips = self.poker_rules.get("starting_chips", 1000)
                self.poker_engine.start_new_hand(agent_ids, agent_names, starting_chips)
                total_hands += 1
                
                # Play the hand
                hand_result = await self._play_hand_a2a(agent_ids)
                
                if hand_result:
                    winner = hand_result["winner"]
                    hands_won[winner] += 1
                    game_log.append(hand_result)
                    
                    self.print_status(f"Hand {hand_num + 1} winner: {self.white_agents[winner].name}")
                
                # Check if any player is eliminated (simplified check)
                if self.poker_engine.game_state:
                    active_players = [p for p in self.poker_engine.game_state.players if p.chips > 0]
                    if len(active_players) < 2:
                        break
            
            # Determine game winner based on final chips
            if self.poker_engine.game_state:
                final_chips = {p.id: p.chips for p in self.poker_engine.game_state.players}
                winner = max(final_chips.keys(), key=lambda x: final_chips[x])
            else:
                final_chips = {aid: 1000 for aid in agent_ids}  # Default fallback
                winner = agent_ids[0]
            
            return {
                "winner": winner,
                "final_chips": final_chips,
                "hands_won": hands_won,
                "total_hands": total_hands,
                "game_log": game_log
            }
            
        except Exception as e:
            self.logger.error(f"Error running poker game: {e}")
            return None

    async def _play_hand_a2a(self, agent_ids: List[str]) -> Optional[Dict[str, Any]]:
        """Play a single poker hand using A2A communication"""
        try:
            if not self.poker_engine.game_state:
                return None
                
            hand_log = []
            
            # Play through betting rounds
            while self.poker_engine.game_state.round != "showdown":
                current_player = self.poker_engine.game_state.players[self.poker_engine.game_state.current_player]
                
                if current_player.id in agent_ids:
                    # Get decision from agent via A2A and execute it
                    decision_result = await self._get_agent_decision_a2a(current_player.id, self.poker_engine.game_state)
                    
                    if decision_result:
                        # Log the decision
                        hand_log.append({
                            "player": current_player.id,
                            "decision": decision_result["decision"],
                            "action_executed": decision_result["action_executed"],
                            "amount": decision_result["amount"],
                            "engine_result": decision_result["engine_result"]
                        })
                        
                        self.print_status(f"Player {current_player.id}: {decision_result['action_executed']} (amount: {decision_result['amount']})")
                    else:
                        # Default to fold if no decision
                        self.poker_engine.process_action(current_player.id, Action.FOLD, 0)
                        hand_log.append({
                            "player": current_player.id,
                            "decision": {"action": "fold", "reasoning": "No response"},
                            "action_executed": "fold",
                            "amount": 0
                        })
                        self.print_status(f"Player {current_player.id}: fold (no response)")
                else:
                    # Skip non-agent players (shouldn't happen in this setup)
                    self.poker_engine.process_action(current_player.id, Action.FOLD, 0)
                    hand_log.append({
                        "player": current_player.id,
                        "decision": {"action": "fold", "reasoning": "Non-agent player"},
                        "action_executed": "fold",
                        "amount": 0
                    })
            
            # Determine hand winner
            # The poker engine should have determined the winner through _determine_winner
            # For now, use the player with most chips as fallback
            winner = max(self.poker_engine.game_state.players, key=lambda p: p.chips).id
            
            return {
                "winner": winner,
                "hand_log": hand_log,
                "final_state": {
                    "pot": self.poker_engine.game_state.pot,
                    "community_cards": [str(card) for card in self.poker_engine.game_state.community_cards],
                    "players": [{"id": p.id, "chips": p.chips, "cards": [str(card) for card in p.cards]} for p in self.poker_engine.game_state.players]
                }
            }
            
        except Exception as e:
            self.logger.error(f"Error playing hand: {e}")
            return None

    async def _get_agent_decision_a2a(self, agent_id: str, game_state) -> Optional[Dict[str, Any]]:
        """Get poker decision from agent via A2A communication and execute it"""
        try:
            agent = self.white_agents[agent_id]

            # Find the current player
            current_player = None
            for player in game_state.players:
                if player.id == agent_id:
                    current_player = player
                    break

            if not current_player:
                return None

            # Prepare game data for agent
            game_data = {
                "game_state": {
                    "round": game_state.round,
                    "pot": game_state.pot,
                    "current_bet": game_state.current_bet,
                    "community_cards": [str(card) for card in game_state.community_cards]
                },
                "player_cards": [str(card) for card in current_player.cards],
                "community_cards": [str(card) for card in game_state.community_cards],
                "pot_size": game_state.pot,
                "current_bet": game_state.current_bet,
                "player_position": current_player.position,
                "action_required": "fold_call_raise"
            }

            # Send game state to agent using A2A protocol
            response = await self._send_message_to_agent_a2a(agent, json.dumps(game_data))

            # Parse agent response - handle A2A protocol response format
            try:
                # Extract JSON from the response text, handling markdown code blocks
                json_text = self._extract_json_from_response(response)
                self.logger.info(f"Extracted JSON text: {repr(json_text)}")
                decision = json.loads(json_text)

                # Execute the decision using poker engine
                action = Action(decision["action"])
                amount = decision.get("amount", 0)

                # Process the action in the poker engine
                result = self.poker_engine.process_action(agent_id, action, amount)

                # Return the decision with engine result
                return {
                    "decision": decision,
                    "engine_result": result,
                    "action_executed": action.value,
                    "amount": amount
                }

            except json.JSONDecodeError as e:
                self.logger.error(f"Invalid JSON response from {agent.name}: {response}")
                self.logger.error(f"JSON decode error: {e}")
                # Default to fold on invalid response
                result = self.poker_engine.process_action(agent_id, Action.FOLD, 0)
                return {
                    "decision": {"action": "fold", "amount": 0, "reasoning": "Invalid response"},
                    "engine_result": result,
                    "action_executed": "fold",
                    "amount": 0
                }
            except ValueError as ve:
                self.logger.error(f"Invalid action from {agent.name}: {ve}")
                # Default to fold on invalid action
                result = self.poker_engine.process_action(agent_id, Action.FOLD, 0)
                return {
                    "decision": {"action": "fold", "amount": 0, "reasoning": f"Invalid action: {ve}"},
                    "engine_result": result,
                    "action_executed": "fold",
                    "amount": 0
                }

        except Exception as e:
            self.logger.error(f"Error getting decision from {agent_id}: {e}")
            # Default to fold on error
            try:
                result = self.poker_engine.process_action(agent_id, Action.FOLD, 0)
                return {
                    "decision": {"action": "fold", "amount": 0, "reasoning": f"Error: {e}"},
                    "engine_result": result,
                    "action_executed": "fold",
                    "amount": 0
                }
            except:
                return None

    def _extract_json_from_response(self, response_text: str) -> str:
        """Extract JSON from A2A response, handling markdown code blocks and other formatting"""
        import re
        
        # First, try to find JSON wrapped in markdown code blocks
        json_pattern = r'```(?:json)?\s*(\{.*?\})\s*```'
        match = re.search(json_pattern, response_text, re.DOTALL)
        if match:
            return match.group(1).strip()
        
        # If no markdown blocks, look for JSON object directly
        json_pattern = r'\{[^{}]*"action"[^{}]*\}'
        match = re.search(json_pattern, response_text, re.DOTALL)
        if match:
            return match.group(0).strip()
        
        # If still no JSON found, try to find any JSON-like structure
        json_pattern = r'\{.*?\}'
        match = re.search(json_pattern, response_text, re.DOTALL)
        if match:
            return match.group(0).strip()
        
        # If all else fails, return the original response
        return response_text.strip()

    def _create_tournament_task_description(self) -> str:
        """Create tournament task description"""
        participants = [agent.name for agent in self.white_agents.values()]
        return f"""# Poker Tournament Task

You are participating in a poker tournament with the following agents:
{', '.join(participants)}

## Tournament Format:
- Multiple games with random player selection
- Each game: 2-{self.poker_rules['max_players']} players
- Standard Texas Hold'em rules
- Winner determined by most chips at end of hand

## Your Objective:
- Win as many games as possible
- Accumulate the most chips across all games
- Demonstrate superior poker strategy

## Scoring:
- Tournament ranking based on total wins and chip count
- Performance metrics tracked for each agent

Good luck!"""

    def _calculate_performance_score(self, hands_won: int, total_hands: int, net_chips: int) -> float:
        """Calculate performance score based on multiple metrics"""
        if total_hands == 0:
            return 0.0
        
        win_rate = hands_won / total_hands
        chip_score = max(0, min(1, (net_chips + 1000) / 2000))  # Normalize chip score
        
        # Weighted combination
        performance_score = (win_rate * 0.6 + chip_score * 0.4) * 100
        return round(performance_score, 1)

    def _print_final_report(self):
        """Print final evaluation report"""
        print("\n" + "="*80)
        print("POKER AGENT EVALUATION REPORT")
        print("="*80)
        
        if not self.evaluation_results:
            print("No agents evaluated.")
            return
        
        # Sort by performance score
        sorted_results = sorted(
            self.evaluation_results.values(),
            key=lambda x: x.performance_score,
            reverse=True
        )
        
        print(f"{'Rank':<4} {'Agent Name':<20} {'Type':<10} {'Win Rate':<10} {'Net Chips':<12} {'Score':<8}")
        print("-" * 80)
        
        for i, result in enumerate(sorted_results, 1):
            print(f"{i:<4} {result.agent_name:<20} {result.agent_type:<10} "
                  f"{result.win_rate:.2%} {result.net_chips:>+8} {result.performance_score:.1f}")
        
        print("="*80)



async def start_green_agent():
    """Standalone function to start the green agent A2A server and run evaluation"""
    print("🃏 Poker Agentify - A2A-based Poker Agent Evaluation")
    print("=" * 60)
    print("Green Agent: Assessment Manager (A2A Server)")
    print("White Agents: Poker Playing Agents")
    print("Starting A2A-based evaluation system...")
    print("=" * 60)
    
    # Load configuration
    config_path = "src/green_agent/agent_card.toml"
    try:
        with open(config_path, 'r') as f:
            config = toml.load(f)
    except Exception as e:
        print(f"❌ Error loading config from {config_path}: {e}")
        return
    
    # Create assessment manager (executor)
    assessment_manager = PokerAssessmentManager(config)
    
    # Create agent card
    agent_card = types.AgentCard(
        name=config["agent"]["name"],
        description=config["agent"]["description"],
        version=config["agent"]["version"],
        url=config["communication"]["endpoint"],
        capabilities=types.AgentCapabilities(
            evaluation=True,
            agent_management=True,
            game_coordination=True,
            metrics_collection=True,
            tournament_management=True
        ),
        skills=[
            types.AgentSkill(
                id="poker_evaluation",
                name="poker_evaluation",
                description="Evaluate poker-playing agents",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
                tags=["poker", "evaluation", "assessment"]
            ),
            types.AgentSkill(
                id="tournament_management",
                name="tournament_management",
                description="Manage poker tournaments between agents",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
                tags=["poker", "tournament", "management"]
            )
        ],
        transports=["http"],
        default_input_modes=["text"],
        default_output_modes=["text"]
    )
    
    # Create request handler with executor and task store
    request_handler = DefaultRequestHandler(
        agent_executor=assessment_manager,
        task_store=InMemoryTaskStore(),
    )
    
    # Create A2A application
    app = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler,
    )
    
    try:
        # Start the A2A server and run evaluation
        print(f"🚀 Starting A2A server on {config['communication']['endpoint']}")
        print("📡 Server will be available for A2A communication")
        print("🔄 Starting evaluation task...")
        print("=" * 60)
        
        # Start server
        port = int(config["communication"]["endpoint"].split(":")[-1])
        server_config = uvicorn.Config(
            app=app,
            host="0.0.0.0",
            port=port,
            log_level="info"
        )
        server = uvicorn.Server(server_config)
        
        # Run the A2A-based evaluation in background
        evaluation_task = asyncio.create_task(assessment_manager._run_a2a_evaluation({"task_type": "evaluation"}))
        
        # Start server
        await server.serve()
        
    except KeyboardInterrupt:
        print("\n🛑 Evaluation interrupted by user")
    except Exception as e:
        print(f"❌ Error during evaluation: {e}")
        raise
