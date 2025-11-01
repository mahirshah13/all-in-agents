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
class AgentMetrics:
    """Detailed metrics for an agent's playing style"""
    # Basic action counts
    folds: int = 0
    calls: int = 0
    raises: int = 0
    bets: int = 0
    checks: int = 0
    
    # Hand participation
    hands_participated: int = 0  # Hands where player put money in (VPIP)
    hands_voluntarily_played: int = 0  # Hands not in blind positions
    
    # Preflop actions
    preflop_raises: int = 0
    preflop_actions: int = 0
    
    # 3-bet situations
    faced_3bet: int = 0
    folded_to_3bet: int = 0
    
    # Position tracking
    positions: List[int] = None  # List of positions played
    hands_by_position: Dict[str, int] = None  # Hands played by position
    wins_by_position: Dict[str, int] = None  # Wins by position
    
    # Showdown tracking
    showdown_winnings: int = 0  # Chips won at showdown
    non_showdown_winnings: int = 0  # Chips won without showdown
    
    def __post_init__(self):
        if self.positions is None:
            self.positions = []
        if self.hands_by_position is None:
            self.hands_by_position = {}
        if self.wins_by_position is None:
            self.wins_by_position = {}
    
    def calculate_af(self) -> float:
        """Aggression Factor: (raises + bets) / calls"""
        if self.calls == 0:
            return float('inf') if (self.raises + self.bets) > 0 else 0.0
        return (self.raises + self.bets) / self.calls
    
    def calculate_vpip(self) -> float:
        """VPIP: Percentage of hands voluntarily put money in pot"""
        if self.hands_participated == 0:
            return 0.0
        return (self.hands_voluntarily_played / self.hands_participated) * 100
    
    def calculate_pfr(self) -> float:
        """Preflop Raise: Percentage of preflop raises"""
        if self.preflop_actions == 0:
            return 0.0
        return (self.preflop_raises / self.preflop_actions) * 100
    
    def calculate_fold_to_3bet(self) -> float:
        """Fold to 3-Bet percentage"""
        if self.faced_3bet == 0:
            return 0.0
        return (self.folded_to_3bet / self.faced_3bet) * 100
    
    def get_positional_win_rate(self) -> Dict[str, float]:
        """Win rate by position"""
        win_rates = {}
        for position in self.hands_by_position:
            hands = self.hands_by_position.get(position, 0)
            wins = self.wins_by_position.get(position, 0)
            win_rates[position] = (wins / hands * 100) if hands > 0 else 0.0
        return win_rates
    
    def get_showdown_ratio(self) -> float:
        """Ratio of showdown winnings to total winnings"""
        total = self.showdown_winnings + self.non_showdown_winnings
        if total == 0:
            return 0.0
        return self.showdown_winnings / total


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
    metrics: Optional[AgentMetrics] = None
    
    def __post_init__(self):
        if self.metrics is None:
            self.metrics = AgentMetrics()


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
        self.agent_metrics: Dict[str, AgentMetrics] = {}
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
        
        # State management for white agents
        # Track whether each agent has been initialized (task description sent)
        self.agent_initialized: Dict[str, bool] = {}
        # Track current tournament/session ID for state management
        self.current_tournament_id: Optional[str] = None
        # Track agent memory/summaries across tournaments (optional)
        self.agent_memory: Dict[str, List[str]] = {}
        
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
        
        # Reset all agent states before starting (fresh tournament)
        await self.reset_all_agent_states(clear_memory=False)
        
        # Generate new tournament ID
        import uuid
        self.current_tournament_id = str(uuid.uuid4())
        self.logger.info(f"Starting tournament {self.current_tournament_id[:8]}...")
        
        # Initialize agents (send task description)
        await self._give_context_to_white_agents_a2a()
        
        # Run tournament with real poker games
        await self._run_tournament_a2a()
        
        # Show final results
        self._print_final_report()
        
        # Optional: Reset states after tournament (for next tournament)
        # Comment out if you want agents to remember across tournaments
        # await self.reset_all_agent_states(clear_memory=False)

    async def _run_a2a_tournament(self, task_data: Dict[str, Any]):
        """Run tournament using A2A communication with white agents"""
        self.print_status("Starting A2A-based poker tournament...")
        
        # Reset all agent states before starting (fresh tournament)
        await self.reset_all_agent_states(clear_memory=False)
        
        # Generate new tournament ID
        import uuid
        self.current_tournament_id = str(uuid.uuid4())
        self.logger.info(f"Starting tournament {self.current_tournament_id[:8]}...")
        
        # Initialize agents with task description
        await self._give_context_to_white_agents_a2a()
        
        # Send tournament-specific description via A2A (as additional context)
        tournament_description = self._create_tournament_task_description()
        await self._send_message_to_all_agents_a2a("Tournament Participants", tournament_description)
        
        # Run tournament via A2A
        await self._run_tournament_a2a()
        
        # Show final results
        self._print_final_report()
        
        # Optional: Reset states after tournament (for next tournament)
        # Comment out if you want agents to remember across tournaments
        # await self.reset_all_agent_states(clear_memory=False)

    async def initialize_agent_state(self, agent_id: str, send_task_description: bool = True):
        """Initialize state for a specific agent (only sends task description if needed)"""
        agent = self.white_agents.get(agent_id)
        if not agent:
            self.logger.error(f"Agent {agent_id} not found")
            return
        
        # Create or get context ID for this agent
        if agent_id not in self.agent_contexts:
            import uuid
            self.agent_contexts[agent_id] = str(uuid.uuid4())
        
        # Send task description only if not already initialized or if explicitly requested
        if send_task_description and not self.agent_initialized.get(agent_id, False):
            task_description = self._create_poker_task_description()
            try:
                response = await self._send_message_to_agent_a2a(agent, task_description)
                self.agent_initialized[agent_id] = True
                context_id = self.agent_contexts[agent_id]
                self.logger.info(f"Initialized agent {agent.name} with context ID {context_id}")
                print(f"   ✅ {agent.name}: Initialized with context ID {context_id[:16]}...")
            except Exception as e:
                self.logger.error(f"Failed to initialize {agent.name}: {e}")
                raise
    
    async def reset_agent_state(self, agent_id: str, clear_memory: bool = False):
        """Reset state for a specific agent between tournaments"""
        agent = self.white_agents.get(agent_id)
        if not agent:
            self.logger.error(f"Agent {agent_id} not found")
            return
        
        # Generate new context ID to start fresh conversation
        import uuid
        old_context_id = self.agent_contexts.get(agent_id)
        new_context_id = str(uuid.uuid4())
        self.agent_contexts[agent_id] = new_context_id
        
        # Mark as not initialized so task description will be sent again
        self.agent_initialized[agent_id] = False
        
        # Optionally clear memory
        if clear_memory and agent_id in self.agent_memory:
            self.agent_memory[agent_id] = []
        
        if old_context_id:
            self.logger.info(f"Reset state for agent {agent.name} (old context: {old_context_id[:8]}..., new: {new_context_id[:8]}...)")
            print(f"   🔄 {agent.name}: Context ID reset ({old_context_id[:8]}... → {new_context_id[:8]}...)")
        else:
            self.logger.info(f"Created new context for agent {agent.name}: {new_context_id[:8]}...")
            print(f"   ✅ {agent.name}: New context ID created ({new_context_id[:8]}...)")
    
    async def reset_all_agent_states(self, clear_memory: bool = False):
        """Reset state for all agents (e.g., before a new tournament)"""
        self.print_status("Resetting all agent states for new tournament...", "INFO")
        print("🔄 State Management: Generating new context IDs for all agents...")
        for agent_id in self.white_agents.keys():
            await self.reset_agent_state(agent_id, clear_memory=clear_memory)
        self.print_status(f"All {len(self.white_agents)} agents reset with new context IDs", "SUCCESS")
    
    async def share_tournament_summary(self, agent_id: str, summary: str):
        """Share tournament summary with an agent for learning (optional)"""
        agent = self.white_agents.get(agent_id)
        if not agent:
            self.logger.error(f"Agent {agent_id} not found")
            return
        
        # Store in memory
        if agent_id not in self.agent_memory:
            self.agent_memory[agent_id] = []
        self.agent_memory[agent_id].append(summary)
        
        # Optionally send to agent via A2A for learning
        # Uncomment if you want agents to receive tournament summaries
        # try:
        #     summary_message = f"Tournament Summary:\n{summary}"
        #     await self._send_message_to_agent_a2a(agent, summary_message)
        # except Exception as e:
        #     self.logger.warning(f"Failed to share summary with {agent.name}: {e}")
    
    async def _give_context_to_white_agents_a2a(self):
        """Give context to white agents via A2A communication (only sends if not already initialized)"""
        self.print_status("Initializing white agents via A2A...")
        
        for agent_id, agent in self.white_agents.items():
            # Initialize agent state (only sends task description if not already sent)
            try:
                await self.initialize_agent_state(agent_id, send_task_description=True)
            except Exception as e:
                self.print_status(f"Failed to initialize {agent.name}: {e}", "ERROR")
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
        if self.current_tournament_id:
            self.logger.info(f"Tournament ID: {self.current_tournament_id[:8]}...")
        
        agent_ids = list(self.white_agents.keys())
        num_games = self.evaluation_config["tournament_games"]
        
        # Initialize tournament stats
        tournament_stats = {aid: {"wins": 0, "total_chips": 0, "hands_won": 0, "total_hands": 0} for aid in agent_ids}
        
        for game_num in range(num_games):
            # Reset agent states between tournaments to give fresh context
            if game_num > 0:  # Don't reset before first game (already done in _run_a2a_evaluation)
                import uuid
                # Generate new tournament ID for each tournament
                self.current_tournament_id = str(uuid.uuid4())
                print(f"🏆 New Tournament ID: {self.current_tournament_id[:16]}...")
                
                print("\n" + "="*70)
                print("🔄 Resetting agent states for next tournament...")
                await self.reset_all_agent_states(clear_memory=False)
                
                # Re-initialize agents with task description for new tournament
                await self._give_context_to_white_agents_a2a()
                
            print("\n" + "="*70)
            print(f"🏆 TOURNAMENT GAME {game_num + 1} of {num_games}")
            print("="*70)
            
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
            
            # Get metrics for this agent
            agent_metrics = self.agent_metrics.get(aid, AgentMetrics())
            
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
                performance_score=self._calculate_performance_score(stats["hands_won"], stats["total_hands"], stats["total_chips"] - (num_games * self.poker_rules.get("starting_chips", 1000))),
                metrics=agent_metrics
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
                print("\n" + "="*70)
                print(f"🃏 HAND {hand_num + 1} of {max_hands}")
                print("="*70)
                
                # Start new hand with all agents (preserve chips between hands)
                agent_names = [self.white_agents[aid].name for aid in agent_ids]
                starting_chips = self.poker_rules.get("starting_chips", 1000)
                preserve_chips = (hand_num > 0)  # Preserve chips after first hand
                self.poker_engine.start_new_hand(agent_ids, agent_names, starting_chips, preserve_chips=preserve_chips)
                total_hands += 1
                
                # Show dealer and blind positions
                game_state = self.poker_engine.game_state
                dealer_pos = game_state.dealer_position
                sb_pos = (dealer_pos + 1) % len(game_state.players)
                bb_pos = (dealer_pos + 2) % len(game_state.players)
                
                dealer_name = self.white_agents[game_state.players[dealer_pos].id].name
                sb_name = self.white_agents[game_state.players[sb_pos].id].name
                bb_name = self.white_agents[game_state.players[bb_pos].id].name
                
                print(f"\n🎰 Positions:")
                print(f"   🃏 Dealer: {dealer_name}")
                print(f"   🔹 Small Blind: {sb_name} (💰{self.poker_rules['small_blind']})")
                print(f"   🔸 Big Blind: {bb_name} (💰{self.poker_rules['big_blind']})")
                
                # Show starting chip counts
                print("\n💰 Starting Chips:")
                for player in game_state.players:
                    agent = self.white_agents.get(player.id)
                    name = agent.name if agent else player.name
                    print(f"   {name}: {player.chips} chips")
                
                # Play the hand
                hand_result = await self._play_hand_a2a(agent_ids)
                
                if hand_result:
                    winner = hand_result["winner"]
                    hands_won[winner] += 1
                    game_log.append(hand_result)
                    
                    winner_name = self.white_agents[winner].name
                    print(f"\n✅ Hand {hand_num + 1} Complete - Winner: {winner_name}")
                    print("="*70)
                
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
            last_round = None
            
            # Play through betting rounds
            while self.poker_engine.game_state.round != "showdown":
                game_state = self.poker_engine.game_state
                
                # Show new betting round header
                if game_state.round != last_round:
                    last_round = game_state.round
                    print(f"\n📋 {game_state.round.upper()} - Pot: 💰{game_state.pot}")
                    
                    # Show community cards if any
                    if game_state.community_cards:
                        cards_str = " ".join([str(card) for card in game_state.community_cards])
                        print(f"   Community Cards: {cards_str}")
                    else:
                        print(f"   Community Cards: (none yet)")
                    
                    # Show current bet
                    if game_state.current_bet > 0:
                        print(f"   Current Bet: 💰{game_state.current_bet}")
                    print()
                
                current_player = game_state.players[game_state.current_player]
                agent = self.white_agents.get(current_player.id)
                agent_name = agent.name if agent else current_player.name
                
                if current_player.id in agent_ids:
                    # Show player's turn with their cards
                    player_cards_str = " ".join([str(card) for card in current_player.cards])
                    print(f"🎯 {agent_name}'s Turn (Cards: {player_cards_str}, Chips: 💰{current_player.chips})")
                    
                    # Get decision from agent via A2A and execute it
                    decision_result = await self._get_agent_decision_a2a(current_player.id, game_state)
                    
                    if decision_result:
                        # Log the decision
                        hand_log.append({
                            "player": current_player.id,
                            "decision": decision_result["decision"],
                            "action_executed": decision_result["action_executed"],
                            "amount": decision_result["amount"],
                            "engine_result": decision_result["engine_result"]
                        })
                        
                        action = decision_result['action_executed']
                        amount = decision_result['amount']
                        reasoning = decision_result.get('decision', {}).get('reasoning', '')
                        
                        # Track action for metrics
                        self._track_action(current_player.id, action, game_state.round, amount)
                        
                        # Show action with emoji
                        action_emoji = {"fold": "❌", "call": "✅", "raise": "🚀", "check": "✓", "all_in": "🔥"}
                        emoji = action_emoji.get(action, "🎲")
                        
                        print(f"   {emoji} {agent_name}: {action.upper()}", end="")
                        if amount > 0:
                            print(f" 💰{amount}", end="")
                        if reasoning:
                            print(f" - {reasoning}")
                        else:
                            print()
                    else:
                        # Default to fold if no decision
                        self.poker_engine.process_action(current_player.id, Action.FOLD, 0)
                        hand_log.append({
                            "player": current_player.id,
                            "decision": {"action": "fold", "reasoning": "No response"},
                            "action_executed": "fold",
                            "amount": 0
                        })
                        print(f"   ❌ {agent_name}: FOLD (no response)")
                else:
                    # Skip non-agent players (shouldn't happen in this setup)
                    self.poker_engine.process_action(current_player.id, Action.FOLD, 0)
                    hand_log.append({
                        "player": current_player.id,
                        "decision": {"action": "fold", "reasoning": "Non-agent player"},
                        "action_executed": "fold",
                        "amount": 0
                    })
                    print(f"   ❌ {agent_name}: FOLD (non-agent)")
            
            # Show showdown
            print(f"\n🎴 SHOWDOWN")
            print("-" * 70)
            
            # Show all players' cards
            for player in self.poker_engine.game_state.players:
                if player.is_active:
                    agent = self.white_agents.get(player.id)
                    agent_name = agent.name if agent else player.name
                    cards_str = " ".join([str(card) for card in player.cards])
                    print(f"   {agent_name}: {cards_str} (Chips: 💰{player.chips})")
            
            # Determine hand winner
            # The poker engine should have determined the winner through _determine_winner
            # For now, use the player with most chips as fallback
            winner = max(self.poker_engine.game_state.players, key=lambda p: p.chips).id
            winner_agent = self.white_agents.get(winner)
            winner_name = winner_agent.name if winner_agent else winner
            
            print(f"\n🏆 Winner: {winner_name}")
            print(f"💰 Final Pot: {self.poker_engine.game_state.pot}")
            
            # Track results for all players
            starting_chips = self.poker_rules.get("starting_chips", 1000)
            for player in self.poker_engine.game_state.players:
                if player.id in agent_ids:
                    winnings = player.chips - starting_chips
                    is_winner = (player.id == winner)
                    at_showdown = self.poker_engine.game_state.round == "showdown" and len([p for p in self.poker_engine.game_state.players if p.is_active]) > 1
                    in_blind = (player.position <= 2)  # Dealer, SB, BB
                    put_money_in = player.total_bet > 0
                    
                    # Track hand participation
                    self._track_hand_participation(player.id, put_money_in, in_blind)
                    
                    # Track hand result
                    if is_winner:
                        self._track_hand_result(player.id, True, player.position, winnings, at_showdown)
                    
                    # Track all players' positions even if they didn't win
                    if put_money_in:
                        if player.id not in self.agent_metrics:
                            self.agent_metrics[player.id] = AgentMetrics()
                        metrics = self.agent_metrics[player.id]
                        position_name = self._get_position_name(player.position)
                        if position_name not in metrics.hands_by_position:
                            metrics.hands_by_position[position_name] = 0
                        metrics.hands_by_position[position_name] += 1
            
            # Show final chip counts
            print(f"\n💰 Final Chips:")
            for player in self.poker_engine.game_state.players:
                agent = self.white_agents.get(player.id)
                agent_name = agent.name if agent else player.name
                change = player.chips - starting_chips
                change_str = f"(+{change})" if change > 0 else f"({change})" if change < 0 else ""
                print(f"   {agent_name}: 💰{player.chips} {change_str}")
            
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
    
    def _track_action(self, agent_id: str, action: str, round_name: str, amount: int = 0):
        """Track an action for metrics calculation"""
        if agent_id not in self.agent_metrics:
            self.agent_metrics[agent_id] = AgentMetrics()
        
        metrics = self.agent_metrics[agent_id]
        
        # Track basic actions
        if action == "fold":
            metrics.folds += 1
        elif action == "call":
            metrics.calls += 1
        elif action == "raise":
            metrics.raises += 1
            if round_name == "preflop":
                metrics.preflop_raises += 1
        elif action == "check":
            metrics.checks += 1
        elif action == "all_in":
            metrics.raises += 1  # Count all-in as aggressive action
        
        # Track preflop actions
        if round_name == "preflop" and action in ["fold", "call", "raise"]:
            metrics.preflop_actions += 1
    
    def _track_hand_participation(self, agent_id: str, put_money_in: bool, in_blind: bool):
        """Track hand participation for VPIP calculation"""
        if agent_id not in self.agent_metrics:
            self.agent_metrics[agent_id] = AgentMetrics()
        
        metrics = self.agent_metrics[agent_id]
        
        if put_money_in:
            metrics.hands_participated += 1
            if not in_blind:
                metrics.hands_voluntarily_played += 1
    
    def _track_hand_result(self, agent_id: str, won: bool, position: int, winnings: int, at_showdown: bool):
        """Track hand result for position and showdown metrics"""
        if agent_id not in self.agent_metrics:
            self.agent_metrics[agent_id] = AgentMetrics()
        
        metrics = self.agent_metrics[agent_id]
        
        # Track position
        position_name = self._get_position_name(position)
        if position_name not in metrics.hands_by_position:
            metrics.hands_by_position[position_name] = 0
        metrics.hands_by_position[position_name] += 1
        
        if won:
            if position_name not in metrics.wins_by_position:
                metrics.wins_by_position[position_name] = 0
            metrics.wins_by_position[position_name] += 1
            
            # Track showdown vs non-showdown winnings
            if at_showdown:
                metrics.showdown_winnings += winnings
            else:
                metrics.non_showdown_winnings += winnings
    
    def _get_position_name(self, position: int) -> str:
        """Get position name from position index"""
        if position == 0:
            return "Dealer"
        elif position == 1:
            return "Small Blind"
        elif position == 2:
            return "Big Blind"
        elif position == 3:
            return "Early Position"
        else:
            return f"Position {position}"

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
        """Print final evaluation report with detailed metrics"""
        print("\n" + "="*100)
        print("POKER AGENT EVALUATION REPORT")
        print("="*100)
        
        if not self.evaluation_results:
            print("No agents evaluated.")
            return
        
        # Sort by performance score
        sorted_results = sorted(
            self.evaluation_results.values(),
            key=lambda x: x.performance_score,
            reverse=True
        )
        
        print(f"\n{'Rank':<4} {'Agent Name':<25} {'Win Rate':<10} {'Net Chips':<12} {'Score':<8}")
        print("-" * 100)
        
        for i, result in enumerate(sorted_results, 1):
            print(f"{i:<4} {result.agent_name:<25} {result.win_rate:.2%} {result.net_chips:>+10} {result.performance_score:>6.1f}")
        
        print("\n" + "="*100)
        print("DETAILED STRATEGIC METRICS")
        print("="*100)
        
        for i, result in enumerate(sorted_results, 1):
            print(f"\n{i}. {result.agent_name} ({result.agent_type})")
            print("-" * 80)
            metrics = result.metrics
            
            # 1. Aggression Factor
            af = metrics.calculate_af()
            af_str = f"{af:.2f}" if af != float('inf') else "∞"
            print(f"   🎯 Aggression Factor (AF): {af_str}")
            if af < 0.5:
                print(f"      → Very passive player")
            elif af < 1.0:
                print(f"      → Passive player")
            elif af < 2.0:
                print(f"      → Balanced player")
            elif af < 3.0:
                print(f"      → Aggressive player")
            else:
                print(f"      → Very aggressive player")
            
            # 2. VPIP
            vpip = metrics.calculate_vpip()
            print(f"   📊 VPIP: {vpip:.1f}%")
            if vpip < 15:
                print(f"      → Tight player (selective)")
            elif vpip < 25:
                print(f"      → Moderate player")
            elif vpip < 35:
                print(f"      → Loose player (plays many hands)")
            else:
                print(f"      → Very loose player")
            
            # 3. Preflop Raise
            pfr = metrics.calculate_pfr()
            print(f"   🚀 Preflop Raise (PFR): {pfr:.1f}%")
            if pfr > 0:
                pfr_vpip_ratio = pfr / vpip if vpip > 0 else 0
                print(f"      → PFR/VPIP Ratio: {pfr_vpip_ratio:.2f}")
                if pfr_vpip_ratio > 0.8:
                    print(f"      → Very aggressive preflop player")
                elif pfr_vpip_ratio > 0.5:
                    print(f"      → Aggressive preflop player")
            
            # 4. Positional Win Rates
            positional_wr = metrics.get_positional_win_rate()
            if positional_wr:
                print(f"   📍 Positional Win Rates:")
                for pos_name, wr in positional_wr.items():
                    print(f"      {pos_name}: {wr:.1f}%")
            
            # 5. Showdown vs Non-Showdown
            showdown_ratio = metrics.get_showdown_ratio()
            if showdown_ratio > 0 or metrics.non_showdown_winnings > 0:
                print(f"   💰 Winnings Source:")
                print(f"      Showdown: {metrics.showdown_winnings:+d} chips")
                print(f"      Non-Showdown: {metrics.non_showdown_winnings:+d} chips")
                if showdown_ratio > 0.6:
                    print(f"      → Wins mostly by having best hands")
                elif showdown_ratio > 0.4:
                    print(f"      → Balanced win strategy")
                else:
                    print(f"      → Wins mostly by forcing folds (bluff/aggression)")
            
            # 6. Fold to 3-Bet
            fold_to_3bet = metrics.calculate_fold_to_3bet()
            if metrics.faced_3bet > 0:
                print(f"   ⚡ Fold to 3-Bet: {fold_to_3bet:.1f}% ({metrics.folded_to_3bet}/{metrics.faced_3bet})")
                if fold_to_3bet > 70:
                    print(f"      → Highly exploitable by aggressive 3-bets")
                elif fold_to_3bet < 30:
                    print(f"      → Resilient to 3-bets")
            
            # Summary stats
            print(f"   📈 Action Summary:")
            print(f"      Folds: {metrics.folds}, Calls: {metrics.calls}, Raises: {metrics.raises}, Checks: {metrics.checks}")
        
        print("\n" + "="*100)



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
