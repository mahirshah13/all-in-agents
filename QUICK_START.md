# Quick Start Guide

## 🚀 Get Started in 3 Steps

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run the Demo
```bash
python demo.py
```

### 3. Start the Full System
```bash
# Terminal 1: Start example agents
python example_agents.py

# Terminal 2: Start evaluation agent
python main.py

# Open browser: http://localhost:8000
```

## 🎯 What You Get

- **Complete Poker Engine**: Texas Hold'em with hand evaluation, betting rounds, and game state management
- **A2A Protocol**: Agent-to-Agent communication supporting HTTP and WebSocket
- **Web Dashboard**: Real-time monitoring and control interface
- **Example Agents**: 4 different playing styles (Random, Conservative, Aggressive, Smart)
- **Comprehensive Metrics**: Win rate, chip performance, playing style analysis, response times

## 📊 Key Features

### Poker Game Engine
- Full Texas Hold'em implementation
- Hand ranking and evaluation
- Betting rounds (preflop, flop, turn, river)
- Blinds and pot management
- Player actions (fold, call, raise, check, all-in)

### A2A Communication Protocol
- HTTP and WebSocket support
- Message types: game_start, action_request, action_response, game_end
- Health checks and error handling
- Timeout management

### Evaluation Metrics
- **Performance**: Win rate, net chips, games played
- **Style**: VPIP, PFR, aggression factor, fold/call/raise percentages
- **Technical**: Response times, errors, timeouts

### Web Dashboard
- Agent registration and management
- Game and tournament control
- Real-time game monitoring
- Live metrics display
- WebSocket updates

## 🧪 Testing

Run the test suite to verify everything works:
```bash
python test_system.py
```

## 📁 Project Structure

```
Green Agent/
├── main.py                 # Main application
├── evaluation_agent.py     # Core evaluation logic
├── poker_engine.py         # Poker game engine
├── a2a_protocol.py         # A2A communication
├── web_interface.py        # Web dashboard
├── example_agents.py       # Example agents
├── config.py              # Configuration
├── demo.py                # Demo script
├── test_system.py         # Test suite
├── start_demo.py          # Startup script
└── README.md              # Full documentation
```

## 🔧 Configuration

Edit `config.py` to customize:
- Server ports and settings
- Game parameters (blinds, chips, timeouts)
- Agent settings
- Evaluation metrics

## 🤝 Creating Custom Agents

Implement the A2A protocol in your agent:

```python
from fastapi import FastAPI

app = FastAPI()

@app.post("/")
async def handle_message(request: dict):
    if request["message_type"] == "action_request":
        game_state = request["data"]["game_state"]
        # Your poker logic here
        action = your_strategy(game_state)
        return {"action": "raise", "amount": 100}
```

## 📈 Monitoring

Access the web dashboard at http://localhost:8000 to:
- Monitor active games in real-time
- View agent performance metrics
- Start new games and tournaments
- Manage agent registrations

## 🆘 Troubleshooting

- **Port conflicts**: Change ports in `config.py`
- **Agent timeouts**: Increase timeout values
- **WebSocket issues**: Check firewall settings
- **Dependencies**: Ensure all packages are installed

## 📚 Full Documentation

See `README.md` for complete documentation including:
- Detailed API reference
- A2A protocol specification
- Advanced configuration options
- Contributing guidelines
