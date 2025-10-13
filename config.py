"""
Configuration settings for the Poker Evaluation Agent
"""
from dataclasses import dataclass
from typing import List, Dict, Any


@dataclass
class ServerConfig:
    """Server configuration"""
    host: str = "0.0.0.0"
    web_port: int = 8000
    a2a_port: int = 8765
    log_level: str = "INFO"


@dataclass
class GameConfig:
    """Game configuration"""
    small_blind: int = 10
    big_blind: int = 20
    starting_chips: int = 1000
    max_hands: int = 100
    hand_timeout: int = 300  # 5 minutes per hand
    max_actions_per_hand: int = 50


@dataclass
class AgentConfig:
    """Default agent configuration"""
    timeout: int = 30
    max_retries: int = 3
    retry_delay: int = 1


@dataclass
class EvaluationConfig:
    """Evaluation configuration"""
    metrics_update_interval: int = 5  # seconds
    max_concurrent_games: int = 10
    tournament_break_delay: int = 1  # seconds between games


# Default configurations
DEFAULT_SERVER_CONFIG = ServerConfig()
DEFAULT_GAME_CONFIG = GameConfig()
DEFAULT_AGENT_CONFIG = AgentConfig()
DEFAULT_EVALUATION_CONFIG = EvaluationConfig()

# Example agent configurations
EXAMPLE_AGENTS = [
    {
        "id": "random",
        "name": "Random Agent",
        "url": "http://localhost:8001",
        "timeout": 30
    },
    {
        "id": "conservative",
        "name": "Conservative Agent", 
        "url": "http://localhost:8002",
        "timeout": 30
    },
    {
        "id": "aggressive",
        "name": "Aggressive Agent",
        "url": "http://localhost:8003",
        "timeout": 30
    },
    {
        "id": "smart",
        "name": "Smart Agent",
        "url": "http://localhost:8004",
        "timeout": 30
    }
]
