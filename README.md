# Poker Agentify - Terminal-based Poker Agent Evaluation System

A terminal-based poker agent evaluation system inspired by the [agentify-example-tau-bench](https://github.com/agentbeats/agentify-example-tau-bench/tree/904ed9f80e7bcdd42abd3057e731350300b43961) approach. This system uses A2A (Agent-to-Agent) and MCP (Multi-Agent Communication Protocol) standards to evaluate multiple types of poker-playing agents.

## Project Structure

```
poker-agentify/
├── src/
│   ├── green_agent/           # Assessment manager agent
│   │   ├── agent_card.toml    # Green agent configuration
│   │   └── assessment_manager.py  # Main green agent implementation
│   └── white_agent/           # Poker-playing agents
│       ├── agent_card.toml    # White agent configuration
│       └── poker_player.py    # Main white agent implementation
├── launcher.py               # Unified launcher script
├── main.py                   # Main entry point (delegates to launcher)
├── poker_engine.py           # Poker game engine
├── pyproject.toml            # Project dependencies
├── env.example               # Environment variables template
└── README.md                 # This file
```

## Installation

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   # or
   pip install -e .
   ```

2. **Set up environment variables:**
   ```bash
   cp env.example .env
   # Edit .env with your actual values
   ```

## Usage

### Launch Complete Evaluation System

```bash
# Launch the complete evaluation system (green agent + white agents + evaluation)
python main.py
# or directly
python launcher.py
```

### Launch Individual Components

```bash
# Start only the green agent A2A server
python launcher.py --green-only

# Start only a white agent A2A server
python launcher.py --white-only --agent-id random_1 --port 8001
```

### Running White Agents

To run white agents for A2A communication, start them in separate terminals:

```bash
# Terminal 1: Start Random Agent 1
python launcher.py --white-only --agent-id random_1 --port 8001

# Terminal 2: Start Random Agent 2  
python launcher.py --white-only --agent-id random_2 --port 8002

# Terminal 3: Start A2A Poker Agent
python launcher.py --white-only --agent-id a2a_agent --port 8003

# Terminal 4: Start OpenAI Poker Agent (with fallback if no API key)
python launcher.py --white-only --agent-id openai_agent --port 8004

# Terminal 5: Start Custom Strategy Agent
python launcher.py --white-only --agent-id custom_agent --port 8005
```

### OpenAI White Agent

The system includes a bare bones OpenAI-based poker playing agent that:

- **Uses OpenAI GPT-4** for intelligent poker decision making
- **Manages context** across multiple hands and sessions
- **Falls back to random strategy** if no OpenAI API key is provided
- **Learns from game history** and opponent behavior
- **Provides detailed reasoning** for each decision

#### Setting up OpenAI Agent

1. **Get an OpenAI API key** from [OpenAI Platform](https://platform.openai.com/api-keys)

2. **Set the environment variable**:
   ```bash
   export OPENAI_API_KEY="your-api-key-here"
   ```

3. **Run the OpenAI agent**:
   ```bash
   # Using the launcher
   python launcher.py --white-only --agent-id openai_agent --port 8004
   
   # Or using the example script
   python example_openai_agent.py
   ```

#### OpenAI Agent Features

- **Context Management**: Tracks game history, opponent behavior, and session performance
- **Strategic Decision Making**: Uses GPT-4 to analyze game state and make optimal decisions
- **Adaptive Play**: Adjusts strategy based on previous hands and outcomes
- **Detailed Reasoning**: Provides explanations for each poker decision
- **Fallback Strategy**: Uses intelligent random strategy if OpenAI is unavailable

Then run the main system to evaluate all agents via A2A communication.

## A2A Agent Structure

The `PokerAssessmentManager` is a proper A2A agent with the following methods:

- **`__init__(config)`**: Initialize the agent with configuration
- **`execute(context, event_queue)`**: Main execution method for handling A2A requests
- **`cancel(context, event_queue)`**: Cancel any active evaluations
- **`start_a2a_server()`**: Start the A2A server for external communication
- **`_run_a2a_evaluation()`**: Run evaluation using A2A communication with white agents
- **`_run_a2a_tournament()`**: Run tournament using A2A communication with white agents

The system operates in A2A mode:
1. **Green Agent A2A Server**: Starts A2A server to receive evaluation requests
2. **White Agent Communication**: Uses A2A protocol to communicate with white agents
3. **Evaluation Process**: Runs actual poker evaluations through A2A calls
4. **Results Output**: Generates comprehensive evaluation reports

## Configuration

### Green Agent Configuration (`src/green_agent/agent_card.toml`)

The green agent (assessment manager) configuration includes:

- **Agent metadata**: name, description, version, type
- **Capabilities**: evaluation, agent_management, game_coordination, etc.
- **White agents list**: agents to evaluate with their URLs and types
- **Evaluation settings**: games per agent, tournament games, timeouts
- **Poker rules**: blinds, starting chips, max players
- **Metrics tracking**: what to measure and track
- **Output format**: terminal display preferences

### White Agent Configuration (`src/white_agent/agent_card.toml`)

The white agent (poker player) configuration includes:

- **Agent metadata**: name, description, version, type
- **Poker strategy**: strategy type, bluff frequency, aggression factor
- **Game interface**: expected inputs and output format
- **Decision parameters**: fold/call/raise thresholds
- **Evaluation criteria**: performance targets and metrics

## Agent Types

### Supported White Agent Types

1. **Random**: Makes random poker decisions
2. **Conservative**: Folds more often, smaller bets
3. **Aggressive**: Bets more often, larger amounts
4. **Smart**: Considers multiple factors (cards, position, pot odds)
5. **A2A**: Communicates via A2A protocol
6. **OpenAI**: Uses OpenAI API for decision making
7. **Custom**: User-defined strategy

### White Agent Inputs/Outputs

#### Expected Inputs from Green Agent:
- `game_state`: Current game phase and state
- `player_cards`: Player's hole cards
- `community_cards`: Community cards (flop, turn, river)
- `pot_size`: Current pot size
- `current_bet`: Current bet amount
- `player_position`: Player position (button, early, etc.)
- `action_required`: What action is required (fold/call/raise)

#### Output Format for White Agent:
```json
{
  "action": "fold|call|raise",
  "amount": 60,
  "confidence": 0.8,
  "reasoning": "Strong starting hand, raising to build pot"
}
```

## Example Usage

### Basic Evaluation

```bash
# Start the complete system
python main.py launch
```

This will:
1. Launch the green agent (assessment manager)
2. Launch all configured white agents
3. Run individual evaluations for each agent
4. Run a tournament between all agents
5. Display final results and rankings

### Custom Evaluation

You can modify the `src/green_agent/agent_card.toml` file to:
- Add/remove white agents
- Change evaluation parameters
- Modify poker rules
- Adjust metrics tracking

## Metrics & Evaluation

The system tracks comprehensive poker metrics for each agent to evaluate playing style and performance:

### Basic Performance Metrics

- **Win Rate**: Percentage of hands won
- **Net Chips**: Total chip gain/loss from starting stack
- **Performance Score**: Composite score based on win rate and chip performance
- **Total Hands**: Number of hands played
- **Hands Won**: Number of hands won

### Playing Style Metrics

#### Aggression Factor (AF)
- **Formula**: `(raises + bets) / calls`
- **Interpretation**: 
  - AF > 3: Very aggressive
  - AF 2-3: Aggressive
  - AF 1-2: Balanced
  - AF < 1: Passive
- **Purpose**: Measures how often an agent bets/raises vs calls

#### VPIP (Voluntarily Put money In Pot)
- **Formula**: `(hands voluntarily played / hands participated) × 100`
- **Interpretation**:
  - VPIP > 30%: Loose (plays many hands)
  - VPIP 20-30%: Moderate
  - VPIP < 20%: Tight (plays few hands)
- **Purpose**: Measures how often an agent voluntarily enters pots (excluding blind positions)

#### PFR (Preflop Raise)
- **Formula**: `(preflop raises / preflop actions) × 100`
- **Interpretation**: Percentage of preflop actions that are raises
- **Purpose**: Measures preflop aggression and hand selection

#### Fold to 3-Bet
- **Formula**: `(folded to 3bet / faced 3bet) × 100`
- **Interpretation**: How often an agent folds when facing a 3-bet
- **Purpose**: Measures response to aggression and hand strength assessment

### Action Tracking

The system tracks all actions for each agent:
- **Folds**: Number of times agent folded
- **Calls**: Number of times agent called
- **Raises**: Number of times agent raised
- **Bets**: Number of times agent bet (post-flop)
- **Checks**: Number of times agent checked

### Positional Metrics

- **Hands by Position**: Number of hands played from each position (Button, Small Blind, Big Blind, Early, Middle, Late)
- **Wins by Position**: Number of wins from each position
- **Positional Win Rate**: Win rate calculated for each position
- **Purpose**: Evaluates how well agents play from different positions

### Showdown Metrics

- **Showdown Winnings**: Chips won at showdown (when cards are revealed)
- **Non-Showdown Winnings**: Chips won without showdown (opponents folded)
- **Showdown Ratio**: Ratio of showdown winnings to total winnings
- **Purpose**: Distinguishes between winning by having the best hand vs. winning by making opponents fold

### Advanced Tracking

- **Hand Participation**: Tracks which hands an agent voluntarily entered
- **Preflop Actions**: Tracks all preflop decision-making
- **3-Bet Situations**: Tracks how agents respond to 3-bets (re-raises)
- **Response Time**: Average time for agent to make decisions

### Metric Calculation

All metrics are calculated automatically during tournament play and displayed in:
- Terminal output during evaluation
- Final tournament summary
- Evaluation results for each agent
- Frontend visualization (if enabled)

### Example Metrics Output

```
## Detailed Metrics:
- Aggression Factor: 2.5 (Aggressive)
- VPIP: 25.3% (Moderate)
- PFR: 18.7% (Moderate)
- Fold to 3-Bet: 65.0%
- Positional Win Rates:
  - Button: 55.2%
  - Small Blind: 42.1%
  - Big Blind: 38.5%
  - Early Position: 45.3%
  - Middle Position: 48.7%
  - Late Position: 52.1%
- Showdown Ratio: 0.65 (65% of winnings from showdown)
```

## Output Format

The system provides tau-bench style terminal output:

```
🃏 Poker Agentify - Terminal-based Poker Agent Evaluation
============================================================
Green Agent: Assessment Manager (Evaluator)
White Agents: Poker Playing Agents
Starting evaluation system...
============================================================

✅ Launching green agent...
✅ Green agent is ready.
✅ Launching white agents...
✅ White agents are ready.

ℹ️  Starting evaluation...
@@@ Green agent: Sending message to Random Agent 1... -->

# Poker Agent Evaluation Task
...

@@@ Random Agent 1 response:
{
  "action": "raise",
  "amount": 60,
  "confidence": 0.8,
  "reasoning": "Strong starting hand"
}

✅ Evaluation completed for Random Agent 1
   Win Rate: 45.00%
   Net Chips: +150
   Performance Score: 67.5
   
## Detailed Metrics:
- Aggression Factor: 2.3 (Aggressive)
- VPIP: 28.5% (Moderate)
- PFR: 15.2% (Moderate)
- Fold to 3-Bet: 60.0%

🏆 Final Tournament Rankings:
  1. Smart Agent - 3 wins, 2800 chips (60.0% win rate)
  2. Aggressive Agent - 2 wins, 2200 chips (40.0% win rate)
  3. Random Agent 1 - 1 wins, 1800 chips (20.0% win rate)
```

## Development

### Adding New Agent Types

1. **Create agent implementation** in `src/white_agent/`
2. **Add agent configuration** to `src/green_agent/agent_card.toml`
3. **Update strategy handler** in `assessment_manager.py`

### Customizing Evaluation

1. **Modify poker rules** in green agent config
2. **Adjust metrics tracking** in configuration
3. **Change output format** preferences

## Architecture

### Green Agent (Assessment Manager)
- **Role**: Coordinates evaluations, manages white agents
- **Capabilities**: Agent registration, game management, metrics collection
- **Communication**: A2A protocol for agent communication

### White Agents (Poker Players)
- **Role**: Play poker games, make decisions
- **Types**: Random, Conservative, Aggressive, Smart, A2A, OpenAI, Custom
- **Interface**: Standardized input/output format

### Launcher (Evaluation Coordinator)
- **Role**: Orchestrates the complete evaluation process
- **Functions**: Start agents, coordinate evaluation, display results

## License

MIT License - see LICENSE file for details

## References

- [Agentify Example: Tau-Bench](https://github.com/agentbeats/agentify-example-tau-bench/tree/904ed9f80e7bcdd42abd3057e731350300b43961)
- [A2A Protocol Documentation](https://github.com/google/a2a-sdk)
- [MCP Standards](https://github.com/modelcontextprotocol)