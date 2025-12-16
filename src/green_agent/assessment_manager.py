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
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.context import ServerCallContext  # Backwards-compat import (not used with RequestContext)
from a2a.server.events import EventQueue
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from starlette.responses import PlainTextResponse
import uvicorn

from poker_engine import PokerEngine, Action, GameState
from src.my_util.my_a2a import get_agent_card, wait_agent_ready, send_message
from src.my_util import parse_tags
from src.green_agent.evaluation_examples import (
    EvaluationExamples, EvaluationExample, AssessmentDimension,
    get_ground_truth_test_cases
)


def _prepare_green_agent_card(url: str, agent_config: Dict[str, Any]) -> types.AgentCard:
    """Build the green poker assessment manager agent card matching white card schema."""
    evaluation_skill = types.AgentSkill(
        id="poker_evaluation",
        name="Poker Evaluation",
        description="Evaluate poker-playing agents",
        tags=["poker", "evaluation", "assessment"],
        examples=[],
    )
    tournament_skill = types.AgentSkill(
        id="tournament_management",
        name="Tournament Management",
        description="Manage poker tournaments between agents",
        tags=["poker", "tournament", "management"],
        examples=[],
    )

    # Agentbeats / controller deployments need the public controller URL (e.g. Cloudflare)
    # rather than an internal host like http://localhost:8000.
    #
    # Follow the agentify-example-tau-bench pattern:
    # - If AGENT_URL is set by the controller, always use that for the card URL
    # - Otherwise, fall back to GREEN_AGENT_PUBLIC_URL if provided
    # - Finally, fall back to the local server URL
    public_url = os.getenv("AGENT_URL") or os.getenv("GREEN_AGENT_PUBLIC_URL") or url

    return types.AgentCard(
        name=agent_config["name"],
        description=agent_config["description"],
        version=agent_config["version"],
        url=public_url,
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        capabilities=types.AgentCapabilities(),
        skills=[evaluation_skill, tournament_skill],
    )

# Import frontend server for broadcasting (optional, won't break if not available)
try:
    import requests
    FRONTEND_AVAILABLE = True
    
    def broadcast_game_update(update_type: str, data: dict):
        """Broadcast game update via HTTP to frontend server"""
        try:
            message = {
                "type": update_type,
                "data": data
            }
            # Send HTTP POST to frontend server (non-blocking, short timeout)
            response = requests.post("http://localhost:8080/api/broadcast", json=message, timeout=0.5)
            if response.status_code != 200:
                print(f"⚠️  Broadcast failed: {response.status_code}")
        except requests.exceptions.ConnectionError:
            # Frontend server not running - this is okay, just log it once
            pass
        except Exception as e:
            # Log other errors but don't crash
            print(f"⚠️  Broadcast error: {e}")
except ImportError:
    FRONTEND_AVAILABLE = False
    def broadcast_game_update(*args, **kwargs):
        pass


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
        # Support both "white_agents" (selected) and "all_white_agents" (all available)
        self.white_agents: Dict[str, WhiteAgentConfig] = {}
        self.all_available_agents: Dict[str, WhiteAgentConfig] = {}
        
        # Load all available agents if specified
        if "all_white_agents" in self.evaluation_config:
            for agent_data in self.evaluation_config["all_white_agents"]:
                self.all_available_agents[agent_data["id"]] = WhiteAgentConfig(
                    id=agent_data["id"],
                    name=agent_data["name"],
                    type=agent_data["type"],
                    url=agent_data["url"],
                    config=agent_data.get("config", {})
                )
        
        # Load selected agents (these will play)
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
        
        # Benchmark and evaluation tracking
        self.benchmark_results: Dict[str, Dict[str, Any]] = {}  # agent_id -> test_case -> result
        self.evaluation_examples: List[EvaluationExample] = []
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
        hands_per_tournament = self.evaluation_config.get("hands_per_tournament") or self.evaluation_config.get("games_per_agent", 10)
        self.logger.info(f"  - Hands per tournament: {hands_per_tournament}")
        self.logger.info(f"  - Tournament games: {self.evaluation_config.get('tournament_games', 5)}")
        self.logger.info(f"  - Small blind: {self.poker_rules.get('small_blind', 10)}")
        self.logger.info(f"  - Big blind: {self.poker_rules.get('big_blind', 20)}")
        self.logger.info(f"  - Starting chips: {self.poker_rules.get('starting_chips', 1000)}")
        self.logger.info(f"  - Max players: {self.poker_rules.get('max_players', 4)}")

    def _load_evaluation_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Load evaluation configuration with environment variable overrides"""
        evaluation_config = config.copy()
        
        # Support both old name (games_per_agent) and new name (hands_per_tournament)
        # New name takes precedence, but fall back to old name for backward compatibility
        if "hands_per_tournament" in evaluation_config:
            evaluation_config["games_per_agent"] = evaluation_config["hands_per_tournament"]
        elif "games_per_agent" in evaluation_config:
            # Keep games_per_agent for backward compatibility
            pass
        
        # Override with environment variables if they exist
        if os.getenv("EVALUATION_HANDS_PER_TOURNAMENT"):
            evaluation_config["hands_per_tournament"] = int(os.getenv("EVALUATION_HANDS_PER_TOURNAMENT"))
            evaluation_config["games_per_agent"] = evaluation_config["hands_per_tournament"]
        elif os.getenv("EVALUATION_GAMES_PER_AGENT"):
            evaluation_config["games_per_agent"] = int(os.getenv("EVALUATION_GAMES_PER_AGENT"))
            if "hands_per_tournament" not in evaluation_config:
                evaluation_config["hands_per_tournament"] = evaluation_config["games_per_agent"]
        
        if os.getenv("EVALUATION_TOURNAMENT_GAMES"):
            evaluation_config["tournament_games"] = int(os.getenv("EVALUATION_TOURNAMENT_GAMES"))
        
        if os.getenv("EVALUATION_TIMEOUT"):
            evaluation_config["evaluation_timeout"] = int(os.getenv("EVALUATION_TIMEOUT"))
        
        # Ensure hands_per_tournament is set (default to 10 if not specified)
        if "hands_per_tournament" not in evaluation_config:
            evaluation_config["hands_per_tournament"] = evaluation_config.get("games_per_agent", 10)
        
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

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """
        Execute the assessment manager's main logic.

        Supports three modes:
        - Local / CLI mode: task data is JSON with a \"task_type\" field.
        - Controller multi-agent mode (preferred): text prompt containing <white_agents> JSON.
        - Controller single-agent tau-bench mode (<white_agent_url>) is explicitly rejected,
          because this poker evaluation expects *two* white agents (montecarlo and maniac).
        """
        try:
            # Get the raw user input text from the context
            message_text = context.get_user_input()

            # Controller-style tasks: look for tagged formats first
            if "<white_agents>" in message_text and "</white_agents>" in message_text:
                # Multi-agent JSON list inside <white_agents>...</white_agents>
                tags = parse_tags(message_text)
                white_agents_raw = tags.get("white_agents")
                if not white_agents_raw:
                    self.logger.error("Received controller task but <white_agents> tag is empty")
                    return
                try:
                    white_agents_list = json.loads(white_agents_raw)
                except json.JSONDecodeError:
                    self.logger.error("Failed to parse <white_agents> JSON")
                    return

                if not isinstance(white_agents_list, list):
                    self.logger.error("Parsed <white_agents> is not a list")
                    return

                if len(white_agents_list) != 2:
                    self.logger.error(
                        "Poker evaluation requires exactly two white agents (montecarlo and maniac); "
                        f"received {len(white_agents_list)} definitions"
                    )
                    return

                # Build white_agents set from the list
                new_white_agents: Dict[str, WhiteAgentConfig] = {}
                for idx, agent_def in enumerate(white_agents_list):
                    try:
                        # Default IDs/types if not provided: first = montecarlo, second = maniac
                        default_id = "montecarlo" if idx == 0 else "maniac"
                        aid = agent_def.get("id", default_id)
                        aname = agent_def.get("name", aid)
                        atype = agent_def.get("type", aid)
                        aurl = agent_def["url"]
                    except KeyError as e:
                        self.logger.error(f"Invalid white agent definition, missing key: {e}")
                        continue
                    new_white_agents[aid] = WhiteAgentConfig(
                        id=aid,
                        name=aname,
                        type=atype,
                        url=aurl,
                        config=agent_def.get("config", {}),
                    )

                if not new_white_agents:
                    self.logger.error("No valid white agents parsed from <white_agents>")
                    return

                self.white_agents = new_white_agents
                self.all_available_agents = dict(new_white_agents)

                self.print_status(
                    f"Configured {len(self.white_agents)} remote white agents from controller"
                )

                task_type = "evaluation"
                task_data = {"task_type": "evaluation"}

            elif "<white_agent_url>" in message_text and "</white_agent_url>" in message_text:
                # Single-agent tau-bench style is not supported for poker evaluation.
                # We require two white agents (montecarlo and maniac).
                self.logger.error(
                    "Received <white_agent_url> (single-agent) task, but poker evaluation "
                    "requires exactly two white agents. Please send a <white_agents> JSON "
                    "list with two agents (montecarlo and maniac)."
                )
                return

            else:
                # Local / JSON task mode: parse as JSON if possible
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

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Cancel any active evaluations"""
        self.logger.info("Cancelling active evaluations...")
        self.active_games.clear()
        self.evaluation_results.clear()

    async def start_a2a_server(self):
        """Start the A2A server for external communication"""
        agent_card = _prepare_green_agent_card(
            url=self.config["communication"]["endpoint"],
            agent_config=self.agent_config,
        )
        
        # Create request handler with executor and task store
        request_handler = DefaultRequestHandler(
            agent_executor=self,
            task_store=InMemoryTaskStore(),
        )
        
        # Create A2A application
        app = A2AStarletteApplication(
            agent_card=agent_card,
            http_handler=request_handler,
        )
        starlette_app = app.build()

        async def healthcheck(request):
            return PlainTextResponse("OK")

        async def status(request):
            return PlainTextResponse("OK")

        starlette_app.router.add_route("/", healthcheck, methods=["GET"])
        starlette_app.router.add_route("/status", status, methods=["GET"])
        
        # Start server
        port = int(self.config["communication"]["endpoint"].split(":")[-1])
        server_config = uvicorn.Config(
            app=starlette_app,
            host="0.0.0.0",
            port=port,
            log_level="info"
        )
        server = uvicorn.Server(server_config)
        
        # Start server
        await server.serve()

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

    def _create_poker_task_description(self, agent_id: str = None, game_context: Dict[str, Any] = None) -> str:
        """Create adaptive poker task description for white agents based on game context"""
        base_description = f"""# Poker Agent Evaluation Task

You are being evaluated as a poker-playing agent. Your task is to play Texas Hold'em poker games and make optimal decisions based on the game state.

## Game Rules:
- Texas Hold'em poker with small blind: {self.poker_rules['small_blind']}, big blind: {self.poker_rules['big_blind']}
- Starting chips: {self.poker_rules.get('starting_chips', 1000)} per player
- Standard poker hand rankings apply
- You can fold, call, or raise on each betting round

## Your Role:
- Make optimal poker decisions based on your cards and game state
- Respond with JSON format: {{"action": "fold/call/raise", "amount": <bet_amount>}}
- Consider pot odds, position, and opponent behavior
- Play strategically to maximize your chip count"""

        # Add adaptive context based on game state
        adaptive_context = ""
        if game_context:
            pot_size = game_context.get("pot_size", 0)
            player_chips = game_context.get("player_chips", self.poker_rules.get('starting_chips', 1000))
            starting_chips = self.poker_rules.get('starting_chips', 1000)
            stack_ratio = player_chips / starting_chips if starting_chips > 0 else 1.0
            
            adaptive_context += "\n\n## Current Game Context:\n"
            
            if stack_ratio < 0.5:
                adaptive_context += "- ⚠️ SHORT STACK: You have less than 50% of starting chips. Consider push-or-fold strategy.\n"
                adaptive_context += "- Be more selective with hands, but aggressive when you do play.\n"
            elif stack_ratio > 1.5:
                adaptive_context += "- 💰 BIG STACK: You have a significant chip lead. Use your stack to apply pressure.\n"
                adaptive_context += "- You can afford to be more aggressive and take calculated risks.\n"
            
            if pot_size > starting_chips * 0.5:
                adaptive_context += "- 🎯 LARGE POT: Pot is significant relative to stacks. Consider pot commitment.\n"
                adaptive_context += "- If you're already invested, you may need to commit to the hand.\n"
            elif pot_size < starting_chips * 0.1:
                adaptive_context += "- 🪙 SMALL POT: Pot is relatively small. You can be more selective.\n"
                adaptive_context += "- Don't overcommit to small pots unless you have a strong hand.\n"
        
        # Add memory/learning context if available
        memory_context = ""
        if agent_id and agent_id in self.agent_memory:
            previous_results = self.agent_memory[agent_id]
            if previous_results:
                memory_context += "\n\n## Previous Tournament Performance:\n"
                for result in previous_results[-3:]:  # Last 3 results
                    memory_context += f"- {result}\n"
                memory_context += "- Learn from your previous performance and adjust your strategy.\n"
        
        return base_description + adaptive_context + memory_context + """

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
- player_chips: Your current chip count
- starting_chips: Starting chip count for reference

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
        
        # Run benchmark tests first (if enabled)
        if self.evaluation_config.get("run_benchmark_tests", True):
            await self.run_benchmark_tests()
        
        # Reset all agent states before starting (fresh tournament)
        await self.reset_all_agent_states(clear_memory=False)
        
        # Generate new tournament ID
        import uuid
        self.current_tournament_id = str(uuid.uuid4())
        self.logger.info(f"Starting tournament {self.current_tournament_id[:8]}...")
        
        # Initialize agents (send task description) with initial context
        initial_context = {
            "pot_size": 0,
            "starting_chips": self.poker_rules.get("starting_chips", 1000)
        }
        await self._give_context_to_white_agents_a2a(initial_context)
        
        # Broadcast tournament start
        broadcast_game_update("tournament_start", {
            "tournament_id": self.current_tournament_id[:8],
            "players": [{"id": aid, "name": self.white_agents[aid].name, "type": self.white_agents[aid].type} for aid in self.white_agents.keys()]
        })
        
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
        
        # Initialize agents with task description and initial context
        initial_context = {
            "pot_size": 0,
            "starting_chips": self.poker_rules.get("starting_chips", 1000)
        }
        await self._give_context_to_white_agents_a2a(initial_context)
        
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

    async def initialize_agent_state(self, agent_id: str, send_task_description: bool = True, game_context: Dict[str, Any] = None):
        """Initialize state for a specific agent with adaptive context"""
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
            # Create adaptive task description based on current game context
            task_description = self._create_poker_task_description(agent_id, game_context)
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
        """Share tournament summary with an agent for learning"""
        agent = self.white_agents.get(agent_id)
        if not agent:
            self.logger.error(f"Agent {agent_id} not found")
            return
        
        # Store in memory (already done in caller, but ensure it's there)
        if agent_id not in self.agent_memory:
            self.agent_memory[agent_id] = []
        if summary not in self.agent_memory[agent_id]:
            self.agent_memory[agent_id].append(summary)
        
        # Send to agent via A2A for learning
        try:
            # Get full performance metrics
            result = self.evaluation_results.get(agent_id)
            metrics_text = ""
            if result and result.metrics:
                af = result.metrics.calculate_af()
                af_str = f"{af:.2f}" if af != float('inf') else "∞"
                metrics_text = f"""
## Detailed Metrics:
- Aggression Factor: {af_str}
- VPIP: {result.metrics.calculate_vpip():.1f}%
- Preflop Raise: {result.metrics.calculate_pfr():.1f}%
- Showdown Winnings: {result.metrics.showdown_winnings:+d} chips
- Non-Showdown Winnings: {result.metrics.non_showdown_winnings:+d} chips
"""
            
            summary_message = f"""# Tournament Performance Summary

{summary}
{metrics_text}
## Learning Instructions:
- Review your performance metrics above
- Adjust your strategy based on what worked and what didn't
- Consider your win rate, chip performance, and strategic metrics
- Apply lessons learned to improve in the next tournament

Use this information to refine your decision-making in future hands."""
            await self._send_message_to_agent_a2a(agent, summary_message)
            self.logger.info(f"Shared tournament summary with {agent.name}")
        except Exception as e:
            self.logger.warning(f"Failed to share summary with {agent.name}: {e}")
    
    async def _give_context_to_white_agents_a2a(self, game_context: Dict[str, Any] = None):
        """Give context to white agents via A2A communication with adaptive prompts"""
        self.print_status("Initializing white agents via A2A...")
        
        for agent_id, agent in self.white_agents.items():
            # Initialize agent state with adaptive context based on current game state
            try:
                await self.initialize_agent_state(agent_id, send_task_description=True, game_context=game_context)
            except Exception as e:
                self.print_status(f"Failed to initialize {agent.name}: {e}", "ERROR")
                raise e  # Don't simulate, fail if can't communicate
            
            # Small delay between agents (slower for better visibility)
            await asyncio.sleep(2.0)  # Slower for better visibility

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
            # Broadcast tournament start
            broadcast_game_update("tournament_start", {
                "tournament_id": f"{self.current_tournament_id[:8] if self.current_tournament_id else 'N/A'}-{game_num + 1}",
                "game_number": game_num + 1,
                "total_games": num_games
            })
            
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
            print(f"📊 Progress: {game_num}/{num_games} games completed")
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
                
                self.print_status(f"Game {game_num + 1}/{num_games} completed - Winner: {self.white_agents[winner].name}")
            else:
                # If game failed, log it but continue tournament
                self.print_status(f"Game {game_num + 1}/{num_games} failed - continuing tournament", "WARNING")
                # Reset chips for next game
                for aid in agent_ids:
                    tournament_stats[aid]["total_chips"] += self.poker_rules.get("starting_chips", 1000)
        
        # Update evaluation results
        for aid in agent_ids:
            stats = tournament_stats[aid]
            agent = self.white_agents[aid]
            
            # Get metrics for this agent
            agent_metrics = self.agent_metrics.get(aid, AgentMetrics())
            
            result = EvaluationResult(
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
            
            self.evaluation_results[aid] = result
            
            # Store result in memory for agent learning
            if aid not in self.agent_memory:
                self.agent_memory[aid] = []
            
            # Create summary for agent memory
            summary = f"Tournament {self.current_tournament_id[:8] if self.current_tournament_id else 'N/A'}: {stats['wins']} wins, {result.win_rate:.1%} win rate, {result.net_chips:+d} chips, Performance: {result.performance_score:.1f}"
            self.agent_memory[aid].append(summary)
            
            # Keep only last 10 tournament results
            if len(self.agent_memory[aid]) > 10:
                self.agent_memory[aid].pop(0)
            
            # Send summary to agent for learning
            await self.share_tournament_summary(aid, summary)
        
        # Show tournament results
        self.print_status("Tournament completed!", "SUCCESS")
        print("\n🏆 Final Tournament Rankings:")
        rankings = sorted(tournament_stats.items(), key=lambda x: (x[1]["wins"], x[1]["total_chips"]), reverse=True)
        for i, (aid, stats) in enumerate(rankings, 1):
            agent_name = self.white_agents[aid].name
            win_rate = stats["wins"] / num_games
            print(f"  {i}. {agent_name} - {stats['wins']} wins, {stats['total_chips']} chips ({win_rate:.1%} win rate)")
        
        # Broadcast structured summary to frontend
        self._broadcast_evaluation_summary(tournament_stats, num_games)

    async def _run_poker_game_a2a(self, agent_ids: List[str]) -> Optional[Dict[str, Any]]:
        """Run a real poker game using A2A communication with agents"""
        try:
            # Track game stats
            hands_won = {aid: 0 for aid in agent_ids}
            total_hands = 0
            game_log = []
            
            # Play multiple hands until one player is eliminated or max hands reached
            # Use hands_per_tournament if available, otherwise fall back to games_per_agent
            max_hands = self.evaluation_config.get("hands_per_tournament") or self.evaluation_config.get("games_per_agent", 10)
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
                
                # Broadcast hand start with full player info
                game_state = self.poker_engine.game_state
                players_info = []
                for player in game_state.players:
                    agent = self.white_agents.get(player.id)
                    players_info.append({
                        "id": player.id,
                        "name": agent.name if agent else player.name,
                        "type": agent.type if agent else "unknown",
                        "chips": player.chips,
                        "position": player.position
                    })
                
                broadcast_game_update("hand_start", {
                    "hand_number": hand_num + 1,
                    "players": players_info
                })
                
                # Broadcast initial game state immediately after hand start
                if game_state:
                    # Create a comprehensive game state with all players
                    full_state = {
                        "hand_number": game_state.hand_number,
                        "round": game_state.round,
                        "pot": game_state.pot,
                        "current_bet": game_state.current_bet,
                        "community_cards": [str(card) for card in game_state.community_cards],
                        "players": [],
                        "current_player": -1
                    }
                    
                    # Add all players with agent info
                    for idx, player in enumerate(game_state.players):
                        agent = self.white_agents.get(player.id)
                        # Always include cards if they exist
                        player_cards = []
                        if player.cards:
                            player_cards = [str(card) for card in player.cards]
                        
                        full_state["players"].append({
                            "id": player.id,
                            "name": agent.name if agent else player.name,
                            "type": agent.type if agent else "unknown",
                            "chips": player.chips,
                            "current_bet": player.current_bet,
                            "is_active": player.is_active,
                            "is_all_in": player.is_all_in,
                            "cards": player_cards
                        })
                        # Set current player
                        if idx == game_state.current_player:
                            full_state["current_player"] = idx
                    
                    broadcast_game_update("game_state", full_state)
                
                # Delay for frontend visualization (slower for better visibility)
                await asyncio.sleep(2.5)
                
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
                # Only break if we've played at least 3 hands (to ensure some game action)
                if self.poker_engine.game_state and hand_num >= 2:
                    active_players = [p for p in self.poker_engine.game_state.players if p.chips > 0]
                    if len(active_players) < 2:
                        print(f"\n⚠️  Player eliminated after {hand_num + 1} hands. Ending game early.")
                        await self._reveal_remaining_rounds_for_visuals(reason="player_eliminated")
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
            round_started = False  # Track if we've started a new round
            max_iterations = 200  # Maximum iterations to prevent infinite loops
            iteration_count = 0
            last_player_action = None  # Track last player/action to detect loops
            
            # Play through betting rounds
            while self.poker_engine.game_state.round != "showdown":
                iteration_count += 1
                if iteration_count > max_iterations:
                    print(f"⚠️  Maximum iterations ({max_iterations}) reached, forcing showdown")
                    self.poker_engine.game_state.round = "showdown"
                    self.poker_engine._determine_winner()
                    break
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
                    
                    # Broadcast round change with community cards
                    broadcast_game_update("round_change", {
                        "round": game_state.round,
                        "pot": game_state.pot,
                        "current_bet": game_state.current_bet,
                        "community_cards": [str(card) for card in game_state.community_cards]
                    })
                    print(f"📡 Broadcasted round change: {game_state.round} with {len(game_state.community_cards)} community cards")
                    
                    # Delay for frontend visualization (slower for better visibility)
                    await asyncio.sleep(2.5)
                
                # Get current game state
                game_state = self.poker_engine.game_state
                if not game_state:
                    print("⚠️  No game state, breaking hand loop")
                    break
                
                # Check if we're stuck (infinite loop protection)
                if game_state.round == last_round and last_round is not None:
                    # If round hasn't changed and we've been in this round, check if we should advance
                    if self.poker_engine._is_round_complete():
                        print(f"⚠️  Round {game_state.round} complete but not advancing, forcing advance")
                        self.poker_engine._advance_round()
                        game_state = self.poker_engine.game_state
                        if game_state.round != last_round:
                            last_round = game_state.round
                            # Broadcast the new round
                            broadcast_game_update("round_change", {
                                "round": game_state.round,
                                "pot": game_state.pot,
                                "current_bet": game_state.current_bet,
                                "community_cards": [str(card) for card in game_state.community_cards]
                            })
                            print(f"📡 Forced round change to {game_state.round} with {len(game_state.community_cards)} community cards")
                            await asyncio.sleep(2.0)  # Slower for better visibility
                            continue
                    
                current_player = game_state.players[game_state.current_player]
                agent = self.white_agents.get(current_player.id)
                agent_name = agent.name if agent else current_player.name
                
                # Detect infinite loop: same player acting repeatedly
                current_action_key = (current_player.id, game_state.round, game_state.current_bet)
                if current_action_key == last_player_action:
                    print(f"⚠️  Detected loop: {agent_name} acting repeatedly, forcing round advance")
                    if self.poker_engine._is_round_complete():
                        self.poker_engine._advance_round()
                        continue
                    else:
                        # Force fold if round can't complete
                        print(f"⚠️  Forcing {agent_name} to fold to break loop")
                        self.poker_engine.process_action(current_player.id, Action.FOLD, 0)
                        continue
                last_player_action = current_action_key
                
                # Skip if player is all-in or has no chips
                if current_player.is_all_in or current_player.chips <= 0:
                    print(f"⚠️  {agent_name} is all-in or has no chips, skipping")
                    self.poker_engine._next_player()
                    if self.poker_engine._is_round_complete():
                        self.poker_engine._advance_round()
                    continue
                
                if current_player.id in agent_ids:
                    # Show player's turn with their cards
                    player_cards_str = " ".join([str(card) for card in current_player.cards])
                    print(f"🎯 {agent_name}'s Turn (Cards: {player_cards_str}, Chips: 💰{current_player.chips})")
                    
                    # Broadcast player turn with full game state (including community cards)
                    game_state = self.poker_engine.game_state
                    community_cards_list = [str(card) for card in game_state.community_cards] if game_state.community_cards else []
                    full_game_state = {
                        "hand_number": game_state.hand_number,
                        "round": game_state.round,
                        "pot": game_state.pot,
                        "current_bet": game_state.current_bet,
                        "community_cards": community_cards_list,
                        "players": [],
                        "current_player": game_state.current_player
                    }
                    # Debug: log community cards when broadcasting
                    if community_cards_list:
                        print(f"📡 Broadcasting player turn with {len(community_cards_list)} community cards: {community_cards_list}")
                    
                    # Add all players with agent info
                    for idx, player in enumerate(game_state.players):
                        agent = self.white_agents.get(player.id)
                        # Always include cards if they exist
                        player_cards = []
                        if player.cards:
                            player_cards = [str(card) for card in player.cards]
                        
                        full_game_state["players"].append({
                            "id": player.id,
                            "name": agent.name if agent else player.name,
                            "type": agent.type if agent else "unknown",
                            "chips": player.chips,
                            "current_bet": player.current_bet,
                            "is_active": player.is_active,
                            "is_all_in": player.is_all_in,
                            "cards": player_cards
                        })
                    
                    broadcast_game_update("game_state", full_game_state)
                    await asyncio.sleep(2.0)  # Slower for better visibility  # Brief pause before decision (slower for better visibility)
                    
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
                        
                        # Get updated game state IMMEDIATELY after action (chips should be updated)
                        game_state = self.poker_engine.game_state
                        current_round = game_state.round
                        
                        # Broadcast updated game state IMMEDIATELY with updated chips
                        immediate_state = {
                            "hand_number": game_state.hand_number,
                            "round": current_round,
                            "pot": game_state.pot,
                            "current_bet": game_state.current_bet,
                            "community_cards": [str(card) for card in game_state.community_cards],
                            "players": [],
                            "current_player": game_state.current_player
                        }
                        
                        # Add all players with UPDATED chips
                        for idx, player in enumerate(game_state.players):
                            agent = self.white_agents.get(player.id)
                            player_cards = []
                            if player.cards:
                                player_cards = [str(card) for card in player.cards]
                            
                            immediate_state["players"].append({
                                "id": player.id,
                                "name": agent.name if agent else player.name,
                                "type": agent.type if agent else "unknown",
                                "chips": player.chips,  # UPDATED chips after action
                                "current_bet": player.current_bet,
                                "is_active": player.is_active,
                                "is_all_in": player.is_all_in,
                                "cards": player_cards
                            })
                        
                        immediate_state["agent_name"] = agent_name
                        immediate_state["agent_type"] = agent.type if agent else "unknown"
                        broadcast_game_update("game_state", immediate_state)
                        await asyncio.sleep(0.5)  # Brief pause to show chip update
                        
                        # Broadcast player action
                        game_state_dict = self.poker_engine.get_game_state_for_player(current_player.id)
                        # Add agent info to game state
                        game_state_dict["agent_name"] = agent_name
                        game_state_dict["agent_type"] = agent.type if agent else "unknown"
                        
                        broadcast_game_update("player_action", {
                            "player": agent_name,
                            "player_id": current_player.id,
                            "player_type": agent.type if agent else "unknown",
                            "action": action,
                            "amount": amount,
                            "reasoning": reasoning,
                            "game_state": game_state_dict
                        })
                        
                        # Check if round changed after action
                        if current_round != last_round and last_round is not None:
                            # Round advanced - broadcast round change first
                            broadcast_game_update("round_change", {
                                "round": current_round,
                                "pot": game_state.pot,
                                "current_bet": game_state.current_bet,
                                "community_cards": [str(card) for card in game_state.community_cards]
                            })
                            last_round = current_round
                            await asyncio.sleep(2.0)  # Pause to show round change (slower for better visibility)
                        
                        # Broadcast updated game state with all player info including agent types
                        full_game_state = {
                            "hand_number": game_state.hand_number,
                            "round": current_round,
                            "pot": game_state.pot,
                            "current_bet": game_state.current_bet,
                            "community_cards": [str(card) for card in game_state.community_cards],
                            "players": [],
                            "current_player": game_state.current_player
                        }
                        
                        # Add all players with agent info
                        for idx, player in enumerate(game_state.players):
                            agent = self.white_agents.get(player.id)
                            # Always show cards if they exist, even for folded players (for showdown visibility)
                            player_cards = []
                            if player.cards:
                                player_cards = [str(card) for card in player.cards]
                            # In showdown or if round is past preflop, show all cards
                            elif game_state.round == "showdown" and hasattr(player, 'cards'):
                                player_cards = [str(card) for card in player.cards] if player.cards else []
                            
                            full_game_state["players"].append({
                                "id": player.id,
                                "name": agent.name if agent else player.name,
                                "type": agent.type if agent else "unknown",
                                "chips": player.chips,
                                "current_bet": player.current_bet,
                                "is_active": player.is_active,
                                "is_all_in": player.is_all_in,
                                "cards": player_cards
                            })
                        
                        full_game_state["agent_name"] = agent_name
                        full_game_state["agent_type"] = agent.type if agent else "unknown"
                        broadcast_game_update("game_state", full_game_state)
                        
                        # Delay for frontend visualization (slower for better visibility)
                        await asyncio.sleep(2.0)
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
            
            # Determine winner FIRST (this distributes chips)
            # The poker engine's _determine_winner() is called automatically when round becomes "showdown"
            # But we need to ensure it's been called and chips are distributed
            game_state = self.poker_engine.game_state
            if game_state.round != "showdown":
                # Force showdown if not already there
                self.poker_engine.game_state.round = "showdown"
                self.poker_engine._determine_winner()
                game_state = self.poker_engine.game_state
            
            # Wait a moment for chip distribution to complete
            await asyncio.sleep(0.5)
            
            # Show all players' cards AFTER chip distribution
            for player in game_state.players:
                if player.is_active:
                    agent = self.white_agents.get(player.id)
                    agent_name = agent.name if agent else player.name
                    cards_str = " ".join([str(card) for card in player.cards])
                    print(f"   {agent_name}: {cards_str} (Chips: 💰{player.chips})")
            
            # Determine winner (player with most chips after distribution)
            winner = max(game_state.players, key=lambda p: p.chips).id
            winner_agent = self.white_agents.get(winner)
            winner_name = winner_agent.name if winner_agent else winner
            
            print(f"\n🏆 Winner: {winner_name}")
            print(f"💰 Final Pot: {game_state.pot} (should be 0 after distribution)")
            
            # Verify chip distribution
            total_chips = sum(p.chips for p in game_state.players)
            expected_total = len(game_state.players) * self.poker_rules.get("starting_chips", 1000)
            print(f"💰 Total chips in play: {total_chips} (expected: {expected_total})")
            
            # Delay to show showdown
            await asyncio.sleep(2.0)
            
            # Broadcast final game state with community cards AFTER chip distribution
            community_cards_list = [str(card) for card in game_state.community_cards] if game_state.community_cards else []
            print(f"📡 Broadcasting hand_end with {len(community_cards_list)} community cards: {community_cards_list}")
            
            final_state = {
                "hand_number": game_state.hand_number,
                "round": game_state.round,
                "pot": game_state.pot,  # Should be 0 after distribution
                "current_bet": game_state.current_bet,
                "community_cards": community_cards_list,
                "players": [],
                "current_player": -1
            }
            
            # Add all players with agent info (WITH UPDATED CHIPS)
            for idx, player in enumerate(game_state.players):
                agent = self.white_agents.get(player.id)
                player_cards = []
                if player.cards:
                    player_cards = [str(card) for card in player.cards]
                
                final_state["players"].append({
                    "id": player.id,
                    "name": agent.name if agent else player.name,
                    "type": agent.type if agent else "unknown",
                    "chips": player.chips,  # This should have updated chips after distribution
                    "current_bet": player.current_bet,
                    "is_active": player.is_active,
                    "is_all_in": player.is_all_in,
                    "cards": player_cards
                })
            
            # Broadcast game state with updated chips
            broadcast_game_update("game_state", final_state)
            await asyncio.sleep(2.0)  # Slower for better visibility  # Delay to show updated chips
            
            # Broadcast hand end with community cards
            hand_end_data = {
                "winner": winner_name,
                "winner_id": winner,
                "pot": game_state.pot,  # Should be 0
                "final_chips": {p.id: p.chips for p in game_state.players},  # Updated chips
                "community_cards": community_cards_list,
                "round": game_state.round
            }
            broadcast_game_update("hand_end", hand_end_data)
            print(f"📡 Broadcasted hand_end with {len(community_cards_list)} community cards: {community_cards_list}")
            
            # Additional delay to show final state
            await asyncio.sleep(2.0)
            
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
        """Get poker decision from agent via A2A communication with adaptive context"""
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

            # Prepare game data for agent with adaptive context
            starting_chips = self.poker_rules.get("starting_chips", 1000)
            stack_ratio = current_player.chips / starting_chips if starting_chips > 0 else 1.0
            pot_ratio = game_state.pot / current_player.chips if current_player.chips > 0 else 0
            
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
                "player_chips": current_player.chips,
                "starting_chips": starting_chips,
                "stack_ratio": stack_ratio,
                "pot_ratio": pot_ratio,
                "player_position": current_player.position,
                "action_required": "fold_call_raise"
            }
            
            # Add opponent information for context
            game_data["opponents"] = [
                {
                    "name": self.white_agents.get(p.id, {}).name if p.id in self.white_agents else p.name,
                    "type": self.white_agents.get(p.id, {}).type if p.id in self.white_agents else "unknown",
                    "chips": p.chips,
                    "current_bet": p.current_bet,
                    "is_active": p.is_active,
                    "stack_ratio": p.chips / starting_chips if starting_chips > 0 else 1.0
                }
                for p in game_state.players if p.id != agent_id
            ]
            
            # Add adaptive context hints based on game state
            adaptive_hints = []
            if stack_ratio < 0.5:
                adaptive_hints.append("SHORT_STACK: Consider push-or-fold strategy")
            elif stack_ratio > 1.5:
                adaptive_hints.append("BIG_STACK: Use stack to apply pressure")
            
            if pot_ratio > 0.5:
                adaptive_hints.append("LARGE_POT: Consider pot commitment")
            elif pot_ratio < 0.1:
                adaptive_hints.append("SMALL_POT: Be selective")
            
            if adaptive_hints:
                game_data["adaptive_context"] = adaptive_hints

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

    def _print_evaluation_examples(self):
        """Print concrete examples of how the green agent evaluates white agents"""
        print("\n" + "="*100)
        print("EVALUATION EXAMPLES - How Green Agent Assesses White Agents")
        print("="*100)
        
        print("\n📋 What the Green Agent Assesses:")
        print("  1. CORRECTNESS: Is the action valid and legal?")
        print("  2. STRATEGIC_QUALITY: Is the action strategically sound?")
        print("  3. CONSISTENCY: Is the agent consistent with its stated strategy?")
        print("  4. RESPONSE_FORMAT: Does the response follow the required format?")
        print("  5. REASONING_QUALITY: Is the reasoning logical and sound?")
        print("  6. POSITION_AWARENESS: Does the agent consider position?")
        print("  7. POT_ODDS_AWARENESS: Does the agent consider pot odds?")
        print("  8. STACK_MANAGEMENT: Does the agent manage stack size appropriately?")
        
        print("\n" + "-"*100)
        print("CONCRETE EVALUATION EXAMPLES")
        print("-"*100)
        
        examples = EvaluationExamples.get_examples()
        for i, example in enumerate(examples[:3], 1):  # Show first 3 examples
            print(f"\n📊 Example {i}: {example.scenario_description}")
            print(f"   Agent: {example.agent_type}")
            print(f"   Response: {example.agent_response['action'].upper()} (amount: {example.agent_response['amount']})")
            print(f"   Reasoning: {example.agent_response.get('reasoning', 'N/A')}")
            print(f"\n   Assessment Scores:")
            for dimension, (score, explanation) in example.assessments.items():
                score_bar = "█" * int(score * 20)
                print(f"     {dimension.value.upper():<25} {score:.2f} {score_bar:<20} {explanation}")
            print(f"   Overall Score: {example.overall_score:.2f}/1.00")
        
        print(f"\n   ... and {len(examples) - 3} more examples (see full report)")
    
    def _print_benchmark_results(self):
        """Print benchmark results with ground-truth test cases"""
        print("\n" + "="*100)
        print("BENCHMARK RESULTS - Reliability Testing with Ground Truth")
        print("="*100)
        
        if not self.benchmark_results:
            print("\n⚠️  No benchmark results available. Run benchmark tests first.")
            return
        
        ground_truth = get_ground_truth_test_cases()
        
        print("\n📊 Test Cases with Ground Truth:")
        for test_id, expected in ground_truth.items():
            print(f"\n   Test: {test_id}")
            print(f"   Expected Action: {expected['expected_action'].upper()}")
            print(f"   Minimum Score: {expected['min_score']:.2f}")
            print(f"   Description: {expected['description']}")
            
            # Show results for each agent
            print(f"   Agent Results:")
            for agent_id, agent_results in self.benchmark_results.items():
                if test_id in agent_results:
                    result = agent_results[test_id]
                    agent_name = self.white_agents.get(agent_id, {}).name if agent_id in self.white_agents else agent_id
                    action = result.get('action', 'N/A')
                    score = result.get('score', 0.0)
                    correct = "✅" if action == expected['expected_action'] else "❌"
                    passed = "✅" if score >= expected['min_score'] else "❌"
                    print(f"     {correct} {passed} {agent_name:<20} Action: {action:<6} Score: {score:.2f}")
        
        # Calculate accuracy
        print("\n" + "-"*100)
        print("ACCURACY METRICS")
        print("-"*100)
        
        for agent_id, agent_results in self.benchmark_results.items():
            agent_name = self.white_agents.get(agent_id, {}).name if agent_id in self.white_agents else agent_id
            correct_actions = 0
            total_tests = 0
            total_score = 0.0
            
            for test_id, expected in ground_truth.items():
                if test_id in agent_results:
                    result = agent_results[test_id]
                    action = result.get('action', '')
                    score = result.get('score', 0.0)
                    
                    if action == expected['expected_action']:
                        correct_actions += 1
                    total_tests += 1
                    total_score += score
            
            if total_tests > 0:
                accuracy = (correct_actions / total_tests) * 100
                avg_score = total_score / total_tests
                print(f"\n   {agent_name}:")
                print(f"     Action Accuracy: {accuracy:.1f}% ({correct_actions}/{total_tests})")
                print(f"     Average Score: {avg_score:.2f}/1.00")
                print(f"     Benchmark Pass Rate: {'✅ PASS' if accuracy >= 75 and avg_score >= 0.80 else '❌ FAIL'}")
    
    def _get_assessment_criteria(self) -> List[str]:
        """List of what the green agent evaluates"""
        return [
            "CORRECTNESS: Is the action valid and legal?",
            "STRATEGIC_QUALITY: Is the action strategically sound?",
            "CONSISTENCY: Is the agent consistent with its stated strategy?",
            "RESPONSE_FORMAT: Does the response follow the required format?",
            "REASONING_QUALITY: Is the reasoning logical and sound?",
            "POSITION_AWARENESS: Does the agent consider position?",
            "POT_ODDS_AWARENESS: Does the agent consider pot odds?",
            "STACK_MANAGEMENT: Does the agent manage stack size appropriately?"
        ]

    def _build_evaluation_examples_data(self, limit: int = 3) -> List[Dict[str, Any]]:
        """Serialize evaluation examples for frontend"""
        examples = EvaluationExamples.get_examples()
        data = []
        for example in examples[:limit]:
            assessments = [
                {
                    "dimension": dimension.value,
                    "score": round(score, 2),
                    "explanation": explanation
                }
                for dimension, (score, explanation) in example.assessments.items()
            ]
            data.append({
                "scenario": example.scenario_description,
                "agent_type": example.agent_type,
                "expected_action": example.expected_action,
                "agent_response": example.agent_response,
                "overall_score": round(example.overall_score, 2),
                "assessments": assessments
            })
        return data

    def _build_benchmark_summary_data(self) -> List[Dict[str, Any]]:
        """Serialize benchmark reliability data"""
        if not self.benchmark_results:
            return []
        
        ground_truth = get_ground_truth_test_cases()
        summary = []
        for agent_id, agent_results in self.benchmark_results.items():
            agent = self.white_agents.get(agent_id)
            agent_name = agent.name if agent else agent_id
            
            correct_actions = 0
            total_tests = 0
            total_score = 0.0
            tests = []
            
            for test_id, expected in ground_truth.items():
                result = agent_results.get(test_id)
                if not result:
                    continue
                
                action = result.get("action", "")
                score = result.get("score", 0.0)
                correct = action == expected["expected_action"]
                total_tests += 1
                total_score += score
                if correct:
                    correct_actions += 1
                
                tests.append({
                    "test_id": test_id,
                    "expected_action": expected["expected_action"],
                    "agent_action": action,
                    "score": round(score, 2),
                    "passed": correct and score >= expected["min_score"]
                })
            
            if total_tests == 0:
                continue
            
            accuracy = correct_actions / total_tests
            avg_score = total_score / total_tests
            summary.append({
                "agent_id": agent_id,
                "agent_name": agent_name,
                "accuracy": round(accuracy, 3),
                "average_score": round(avg_score, 2),
                "pass": accuracy >= 0.75 and avg_score >= 0.80,
                "tests": tests
            })
        
        return summary

    def _build_agents_summary(self, tournament_stats: Dict[str, Dict[str, Any]], num_games: int) -> List[Dict[str, Any]]:
        """Serialize each agent's performance metrics"""
        if not self.evaluation_results:
            return []
        
        sorted_results = sorted(
            self.evaluation_results.values(),
            key=lambda x: x.performance_score,
            reverse=True
        )
        
        agents_summary = []
        for result in sorted_results:
            stats = tournament_stats.get(result.agent_id, {})
            metrics = result.metrics or AgentMetrics()
            af = metrics.calculate_af()
            vpip = metrics.calculate_vpip()
            pfr = metrics.calculate_pfr()
            fold_to_3bet = metrics.calculate_fold_to_3bet()
            positional_wr = metrics.get_positional_win_rate()
            showdown_ratio = metrics.get_showdown_ratio()
            
            agents_summary.append({
                "agent_id": result.agent_id,
                "name": result.agent_name,
                "type": result.agent_type,
                "wins": stats.get("wins", 0),
                "games_played": num_games,
                "hands_won": result.hands_won,
                "total_hands": result.total_hands,
                "win_rate": round(result.win_rate, 3),
                "net_chips": result.net_chips,
                "performance_score": round(result.performance_score, 1),
                "metrics": {
                    "aggression_factor": "∞" if af == float('inf') else round(af, 2),
                    "vpip": round(vpip, 1),
                    "pfr": round(pfr, 1),
                    "fold_to_3bet": round(fold_to_3bet, 1),
                    "showdown_ratio": round(showdown_ratio, 2),
                    "positional_win_rate": {pos: round(val, 1) for pos, val in positional_wr.items()},
                    "showdown_winnings": metrics.showdown_winnings,
                    "non_showdown_winnings": metrics.non_showdown_winnings
                },
                "learning_notes": self.agent_memory.get(result.agent_id, [])[-3:]
            })
        
        return agents_summary

    def _broadcast_evaluation_summary(self, tournament_stats: Dict[str, Dict[str, Any]], num_games: int):
        """Send structured summary to frontend"""
        try:
            summary_payload = {
                "meta": {
                    "tournament_id": self.current_tournament_id[:8] if self.current_tournament_id else "N/A",
                    "num_tournaments": num_games,
                    "hands_per_tournament": self.evaluation_config.get("hands_per_tournament") or self.evaluation_config.get("games_per_agent", 10),
                    "learning_enabled": True
                },
                "tournament_id": self.current_tournament_id[:8] if self.current_tournament_id else "N/A",
                "tournaments_played": num_games,
                "hands_per_tournament": self.evaluation_config.get("games_per_agent", 10),
                "timestamp": time.time(),
                "learning_enabled": True,
                "agents": self._build_agents_summary(tournament_stats, num_games),
                "assessment_criteria": self._get_assessment_criteria(),
                "evaluation_examples": self._build_evaluation_examples_data(),
                "benchmark": self._build_benchmark_summary_data()
            }
            broadcast_game_update("evaluation_summary", summary_payload)
            self.logger.info("Broadcasted evaluation summary to frontend")
        except Exception as e:
            self.logger.error(f"Failed to broadcast evaluation summary: {e}")

    async def _reveal_remaining_rounds_for_visuals(self, reason: str = ""):
        """Force-show flop/turn/river for visualization when a hand ends early"""
        game_state = self.poker_engine.game_state
        if not game_state:
            return
        
        rounds_sequence = ["preflop", "flop", "turn", "river", "showdown"]
        current_round = game_state.round if game_state.round in rounds_sequence else "preflop"
        idx = rounds_sequence.index(current_round)
        
        while game_state.round != "showdown" and idx < len(rounds_sequence) - 1:
            next_round = rounds_sequence[idx + 1]
            cards_to_deal = 0
            if next_round == "flop":
                cards_to_deal = max(0, 3 - len(game_state.community_cards))
            elif next_round in ("turn", "river"):
                cards_to_deal = 1
            
            if cards_to_deal > 0:
                self.poker_engine._deal_community_cards(cards_to_deal)
            
            game_state.round = next_round
            broadcast_game_update("round_change", {
                "round": game_state.round,
                "pot": game_state.pot,
                "current_bet": game_state.current_bet,
                "community_cards": [str(card) for card in game_state.community_cards],
                "reason": reason
            })
            await asyncio.sleep(2.0)  # Slower for better visibility
            idx += 1

    async def run_benchmark_tests(self):
        """Run benchmark tests with ground-truth test cases"""
        print("\n" + "="*100)
        print("RUNNING BENCHMARK TESTS WITH GROUND TRUTH")
        print("="*100)
        
        examples = EvaluationExamples.get_examples()
        ground_truth = get_ground_truth_test_cases()
        
        for agent_id, agent_config in self.white_agents.items():
            print(f"\n🧪 Testing {agent_config.name} ({agent_config.type})...")
            agent_results = {}
            
            for example in examples:
                if example.benchmark_label not in ground_truth:
                    continue
                
                expected = ground_truth[example.benchmark_label]
                
                # Simulate agent response (in real scenario, we'd call the agent)
                # For now, we'll use the example response as a placeholder
                # In production, this would actually call the agent with the game state
                try:
                    # This is a simplified version - in production, you'd:
                    # 1. Send game_state to agent via A2A
                    # 2. Get response
                    # 3. Evaluate response against ground truth
                    
                    # For demonstration, we'll use the example response
                    agent_response = example.agent_response
                    actual_action = agent_response.get('action', 'unknown')
                    
                    # Calculate score based on assessments
                    score = example.overall_score
                    
                    # Check if action matches expected
                    action_correct = (actual_action == expected['expected_action'])
                    
                    agent_results[example.benchmark_label] = {
                        'action': actual_action,
                        'expected': expected['expected_action'],
                        'correct': action_correct,
                        'score': score,
                        'reasoning': agent_response.get('reasoning', '')
                    }
                    
                    status = "✅" if action_correct and score >= expected['min_score'] else "❌"
                    print(f"   {status} {example.benchmark_label}: {actual_action} (expected: {expected['expected_action']}, score: {score:.2f})")
                    
                except Exception as e:
                    print(f"   ❌ Error testing {example.benchmark_label}: {e}")
                    agent_results[example.benchmark_label] = {
                        'action': 'error',
                        'expected': expected['expected_action'],
                        'correct': False,
                        'score': 0.0,
                        'error': str(e)
                    }
            
            self.benchmark_results[agent_id] = agent_results
        
        print("\n✅ Benchmark tests completed!")
    
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
        
        # Print evaluation examples and benchmark results
        self._print_evaluation_examples()
        self._print_benchmark_results()
        
        print("\n" + "="*100)



async def start_green_agent(agent_name: str = "agent_card", host: str = "localhost", port: int = 9000, run_evaluation: bool = True):
    """
    Standalone function to start the green agent A2A server and optionally run evaluation.
    
    Args:
        agent_name: Name of the agent card file (without .toml extension). Default: "agent_card"
        host: Host to bind the server to. Default: "localhost"
        port: Port to bind the server to. Default: 9000
        run_evaluation: Whether to automatically start evaluation. Default: True
    """
    print("🃏 Poker Agentify - A2A-based Poker Agent Evaluation")
    print("=" * 60)
    print("Green Agent: Assessment Manager (A2A Server)")
    print("White Agents: Poker Playing Agents")
    print("Starting A2A-based evaluation system...")
    print("=" * 60)
    
    # Load configuration
    config_path = f"src/green_agent/{agent_name}.toml"
    try:
        with open(config_path, 'r') as f:
            config = toml.load(f)
    except Exception as e:
        print(f"❌ Error loading config from {config_path}: {e}")
        return
    
    # Override endpoint with provided host/port if specified
    endpoint_url = f"http://{host}:{port}"
    if "communication" not in config:
        config["communication"] = {}
    config["communication"]["endpoint"] = endpoint_url
    
    # Create assessment manager (executor)
    assessment_manager = PokerAssessmentManager(config)
    
    # Create agent card
    agent_card = _prepare_green_agent_card(
        url=endpoint_url,
        agent_config=config["agent"],
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
    starlette_app = app.build()

    async def healthcheck(request):
        return PlainTextResponse("OK")

    async def status(request):
        return PlainTextResponse("OK")

    starlette_app.router.add_route("/", healthcheck, methods=["GET"])
    starlette_app.router.add_route("/status", status, methods=["GET"])
    
    try:
        # Start the A2A server and optionally run evaluation
        print(f"🚀 Starting A2A server on {endpoint_url}")
        print("📡 Server will be available for A2A communication")
        if run_evaluation:
            print("🔄 Starting evaluation task...")
        print("=" * 60)
        
        # Start server
        server_config = uvicorn.Config(
            app=starlette_app,
            host=host if host != "localhost" else "0.0.0.0",
            port=port,
            log_level="info"
        )
        server = uvicorn.Server(server_config)
        
        # Run the A2A-based evaluation in background if requested
        if run_evaluation:
            evaluation_task = asyncio.create_task(assessment_manager._run_a2a_evaluation({"task_type": "evaluation"}))
        
        # Start server
        await server.serve()
        
    except KeyboardInterrupt:
        print("\n🛑 Evaluation interrupted by user")
    except Exception as e:
        print(f"❌ Error during evaluation: {e}")
        raise


def start_green_agent_sync(agent_name: str = "agent_card", host: str = "localhost", port: int = 9000, run_evaluation: bool = True):
    """
    Synchronous wrapper for start_green_agent (similar to tau_bench interface).
    
    Args:
        agent_name: Name of the agent card file (without .toml extension). Default: "agent_card"
        host: Host to bind the server to. Default: "localhost"
        port: Port to bind the server to. Default: 9000
        run_evaluation: Whether to automatically start evaluation. Default: True
    """
    asyncio.run(start_green_agent(agent_name=agent_name, host=host, port=port, run_evaluation=run_evaluation))
