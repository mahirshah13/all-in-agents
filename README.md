# Poker Evaluation Agent

A comprehensive system for evaluating poker-playing agents using the A2A (Agent-to-Agent) protocol. This system includes a poker game engine, A2A communication protocol, evaluation metrics, and a web-based dashboard for monitoring games and results.

## Features

- **Poker Game Engine**: Complete Texas Hold'em implementation with hand evaluation, betting rounds, and game state management
- **A2A Protocol**: Agent-to-Agent communication protocol supporting both HTTP and WebSocket connections
- **Evaluation Metrics**: Comprehensive metrics tracking including win rate, chip performance, playing style analysis, and response times
- **Web Dashboard**: Real-time monitoring interface for games, agent management, and results visualization
- **Example Agents**: Multiple example agents with different playing styles (Random, Conservative, Aggressive, Smart)

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Web Dashboard │    │ Evaluation Agent│    │  Poker Agents   │
│                 │    │                 │    │                 │
│  - Agent Mgmt   │◄──►│  - Game Engine  │◄──►│  - Random       │
│  - Game Control │    │  - A2A Protocol │    │  - Conservative │
│  - Metrics      │    │  - Metrics      │    │  - Aggressive   │
│  - Live Log     │    │  - Web Server   │    │  - Smart        │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd "Green Agent"
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Quick Start

### 1. Start Example Agents

First, start the example participating agents:

```bash
python example_agents.py
```

This will start 4 example agents on ports 8001-8004:
- Random Agent (http://localhost:8001)
- Conservative Agent (http://localhost:8002) 
- Aggressive Agent (http://localhost:8003)
- Smart Agent (http://localhost:8004)

### 2. Start Evaluation Agent

In a separate terminal, start the main evaluation agent:

```bash
python main.py
```

This will start:
- Web dashboard at http://localhost:8000
- A2A server at ws://localhost:8765

### 3. Access Web Dashboard

Open your browser and go to http://localhost:8000 to access the web dashboard where you can:
- Register and manage agents
- Start individual games or tournaments
- Monitor real-time game progress
- View detailed metrics and statistics

## Usage

### Web Dashboard

The web dashboard provides a user-friendly interface for:

1. **Agent Management**: Register new agents by providing their ID, name, and URL
2. **Game Control**: Start individual games or tournaments with selected agents
3. **Real-time Monitoring**: Watch games progress in real-time with live updates
4. **Metrics Viewing**: Analyze agent performance with detailed statistics

### Programmatic Usage

You can also use the evaluation agent programmatically:

```python
from evaluation_agent import EvaluationAgent, AgentConfig, GameConfig

# Create evaluation agent
evaluation_agent = EvaluationAgent()

# Register agents
evaluation_agent.register_agent(AgentConfig(
    id="my_agent",
    name="My Poker Agent",
    url="http://localhost:8005"
))

# Run a single game
result = await evaluation_agent.run_single_game([
    "http://localhost:8001",
    "http://localhost:8002"
])

# Run a tournament
tournament_result = await evaluation_agent.run_tournament([
    "http://localhost:8001",
    "http://localhost:8002",
    "http://localhost:8003"
], num_games=10)
```

## A2A Protocol

The A2A protocol enables communication between the evaluation agent and participating poker agents. Agents must implement the following message types:

### Message Types

- `game_start`: Notifies agent that a game is starting
- `action_request`: Requests an action from the agent
- `action_response`: Agent's response with chosen action
- `game_end`: Notifies agent that a game has ended
- `ping`: Health check message
- `pong`: Health check response

### Message Format

```json
{
    "message_type": "action_request",
    "game_id": "game_123",
    "player_id": "agent_1",
    "data": {
        "game_state": {
            "round": "preflop",
            "pot": 100,
            "current_bet": 20,
            "your_cards": ["A♠", "K♥"],
            "community_cards": [],
            "your_chips": 980,
            "is_your_turn": true
        }
    },
    "timestamp": 1234567890.123,
    "message_id": "msg_456"
}
```

### Action Response Format

```json
{
    "action": "raise",
    "amount": 60
}
```

Valid actions:
- `fold`: Fold the hand
- `call`: Call the current bet
- `raise`: Raise to specified amount
- `check`: Check (if no bet to call)
- `all_in`: Go all-in

## Metrics

The system tracks comprehensive metrics for each agent:

### Performance Metrics
- **Win Rate**: Percentage of hands won
- **Net Chips**: Total chip gain/loss
- **Games Played**: Number of games participated in

### Playing Style Metrics
- **VPIP**: Voluntarily Put money In Pot percentage
- **PFR**: Pre-Flop Raise percentage
- **Aggression Factor**: Ratio of raises to calls
- **Fold Percentage**: How often the agent folds
- **Call Percentage**: How often the agent calls
- **Raise Percentage**: How often the agent raises
- **All-in Percentage**: How often the agent goes all-in

### Technical Metrics
- **Average Response Time**: Mean time to respond to action requests
- **Errors**: Number of communication errors
- **Timeouts**: Number of timeout errors

## Creating Custom Agents

To create your own poker agent, implement the A2A protocol:

```python
from fastapi import FastAPI
import json

app = FastAPI()

@app.post("/")
async def handle_message(request: dict):
    message_type = request.get("message_type")
    data = request.get("data", {})
    
    if message_type == "action_request":
        game_state = data.get("game_state", {})
        
        # Your poker logic here
        action = your_poker_strategy(game_state)
        
        return {
            "message_type": "action_response",
            "data": action,
            "timestamp": request.get("timestamp"),
            "message_id": request.get("message_id")
        }
    
    # Handle other message types...
    return {"success": True}
```

## Configuration

The system can be configured through the `config.py` file:

- **Server Config**: Host, ports, logging level
- **Game Config**: Blinds, starting chips, timeouts
- **Agent Config**: Timeouts, retry settings
- **Evaluation Config**: Metrics update intervals, concurrent games

## API Endpoints

### Web API
- `GET /api/agents` - List registered agents
- `POST /api/agents` - Register new agent
- `DELETE /api/agents/{agent_id}` - Unregister agent
- `GET /api/metrics` - Get agent metrics
- `POST /api/games/start` - Start a game
- `POST /api/tournaments/start` - Start a tournament
- `GET /api/games/active` - Get active games

### WebSocket
- `ws://localhost:8000/ws` - Real-time updates

## Development

### Project Structure
```
Green Agent/
├── main.py                 # Main application entry point
├── evaluation_agent.py     # Core evaluation agent
├── poker_engine.py         # Poker game engine
├── a2a_protocol.py         # A2A communication protocol
├── web_interface.py        # Web dashboard
├── example_agents.py       # Example participating agents
├── config.py              # Configuration settings
├── requirements.txt        # Python dependencies
└── README.md              # This file
```

### Running Tests

```bash
# Run example agents for testing
python example_agents.py

# Run evaluation agent
python main.py

# Access web dashboard
open http://localhost:8000
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For questions, issues, or contributions, please open an issue on the GitHub repository.
