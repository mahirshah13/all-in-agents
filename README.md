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

## Commands Summary

### Running White Agents
```bash
# Run individual white agent (replace AGENT_ID, PORT, and TYPE)
python launcher.py --white-only --agent-id <AGENT_ID> --port <PORT> --agent-type <TYPE>

# Examples:
python launcher.py --white-only --agent-id tagbot --port 8001 --agent-type tagbot
python launcher.py --white-only --agent-id smart_agent --port 8004 --agent-type smart
```

### Running Green Agent to Evaluate
```bash
# Complete system (starts all agents + green agent + evaluation)
python launcher.py

# Green agent only (requires white agents to be running separately)
python launcher.py --green-only
```

### Testing Green Agent Evaluation Results
```bash
# Benchmark tests run automatically with complete system
python launcher.py

# Test cases are defined in src/green_agent/evaluation_examples.py
# Results displayed in terminal output after benchmark tests complete
```

### Reproducing Benchmark Results
```bash
# Run with same configuration to reproduce results
python launcher.py
# Results are deterministic (assuming deterministic white agents)
```

## Usage

### Running White Agents to Complete the Task

White agents are poker-playing agents that participate in evaluations. To run individual white agents for A2A communication, start them in separate terminals:

```bash
# Terminal 1: Start TAGBot (Tight-Aggressive)
python launcher.py --white-only --agent-id tagbot --port 8001 --agent-type tagbot

# Terminal 2: Start Monte Carlo Agent
python launcher.py --white-only --agent-id montecarlo --port 8002 --agent-type montecarlo

# Terminal 3: Start Maniac Agent (Ultra-Aggressive)
python launcher.py --white-only --agent-id maniac --port 8003 --agent-type maniac

# Terminal 4: Start Smart Agent
python launcher.py --white-only --agent-id smart_agent --port 8004 --agent-type smart

# Terminal 5: Start Equity Calculator Agent
python launcher.py --white-only --agent-id equity --port 8005 --agent-type equity

# Terminal 6: Start Adaptive Heuristic Agent
python launcher.py --white-only --agent-id adaptive --port 8006 --agent-type adaptive
```

**Available agent types:**
- `tagbot` - Tight-Aggressive Bot
- `montecarlo` - Monte Carlo simulation-based
- `maniac` - Ultra-aggressive strategy
- `smart` - Pot odds and position aware
- `equity` - Equity calculator based
- `adaptive` - Adaptive heuristic strategy

Each white agent will start an A2A server on the specified port and wait for evaluation requests from the green agent.

### Running Green Agent to Evaluate White Agents

The green agent (assessment manager) coordinates evaluations and evaluates white agents. To run the green agent:

#### Option 1: Complete System (Recommended)
This automatically starts all white agents and the green agent:

```bash
# Launch the complete evaluation system (green agent + all white agents + evaluation)
python main.py
# or directly
python launcher.py
```

This will:
1. Start all 6 white agents automatically
2. Start the green agent A2A server
3. Run benchmark tests with ground-truth test cases
4. Run individual evaluations for each agent
5. Run tournaments between agents
6. Display comprehensive results and metrics

#### Option 2: Green Agent Only
If white agents are already running, start only the green agent:

```bash
# Start only the green agent A2A server
python launcher.py --green-only
```

The green agent will:
- Start an A2A server on `http://localhost:8000`
- Connect to white agents configured in `src/green_agent/agent_card.toml`
- Run evaluations and tournaments
- Generate detailed evaluation reports

### Testing Green Agent's Evaluation Results on Test Cases

The green agent includes 8 ground-truth test cases to verify evaluation reliability. These test cases are automatically run when the green agent starts (if `run_benchmark_tests = true` in the config).

#### Running Benchmark Tests

Benchmark tests run automatically when you start the complete system:

```bash
python launcher.py
```

The benchmark tests evaluate each white agent on 8 test cases:
1. **preflop_strong_hand** - Pocket aces should raise preflop
2. **preflop_weak_hand** - 7-2 offsuit should fold preflop
3. **flop_strong_hand** - Top pair should bet/raise on flop
4. **flop_draw_pot_odds** - Flush draw with good pot odds should call
5. **river_weak_hand** - Weak hand on river should fold to large bet
6. **short_stack_all_in** - Short stack with strong hand should push all-in
7. **position_awareness** - Strong hand in good position should raise
8. **pot_odds_calculation** - Draw with favorable pot odds should call

#### Viewing Test Case Results

Test case results are displayed in the terminal output after benchmark tests complete. You'll see:

```
📊 Test Cases with Ground Truth:
   ✅ preflop_strong_hand: raise (expected: raise, score: 0.91)
   ✅ preflop_weak_hand: fold (expected: fold, score: 0.97)
   ...
```

#### Test Case Configuration

To enable/disable benchmark tests, edit `src/green_agent/agent_card.toml`:

```toml
[evaluation]
run_benchmark_tests = true  # Set to false to skip benchmark tests
```

#### Test Case Details

Test cases are defined in `src/green_agent/evaluation_examples.py` with:
- Game state (cards, position, pot size, etc.)
- Expected action (ground truth)
- Minimum score threshold
- Assessment dimensions (correctness, strategic quality, etc.)

For detailed information about the evaluation system and test cases, see `EVALUATION_SYSTEM.md`.

### Reproducing Benchmark Results

The benchmark results are deterministic and can be reproduced by running the same evaluation configuration. To reproduce results:

1. **Ensure consistent configuration:**
   ```bash
   # Check that src/green_agent/agent_card.toml has:
   [evaluation]
   hands_per_tournament = 10
   tournament_games = 3
   run_benchmark_tests = true
   ```

2. **Run the complete evaluation:**
   ```bash
   python launcher.py
   ```

3. **Results will include:**
   - Benchmark test results (8 test cases per agent)
   - Individual agent evaluations
   - Tournament rankings
   - Detailed metrics (AF, VPIP, PFR, positional win rates, etc.)

The system uses a deterministic poker engine, so running the same configuration multiple times will produce consistent results (assuming white agents behave deterministically).

### AgentBeats Compatibility

This benchmark/green agent is designed to be runnable on AgentBeats. The system follows A2A (Agent-to-Agent) protocol standards and is compatible with AgentBeats infrastructure.

#### AgentBeats Requirements

- **A2A Protocol**: All agents communicate via A2A protocol
- **Agent Cards**: Both green and white agents have `agent_card.toml` files
- **Standard Endpoints**: Agents expose standard A2A endpoints
- **Discovery**: Agents support `/.well-known/agent.json` discovery endpoint

#### Running on AgentBeats

1. **Green Agent Configuration:**
   - Agent card: `src/green_agent/agent_card.toml`
   - Endpoint: `http://localhost:8000` (configurable)
   - Discovery: `http://localhost:8000/.well-known/agent.json`

2. **White Agent Configuration:**
   - Agent cards: `src/white_agent/agent_card.toml`
   - Endpoints: Configurable ports (8001-8006)
   - Discovery: Each agent exposes `/.well-known/agent.json`

3. **Deployment:**
   - Green agent can be deployed as a standalone A2A server
   - White agents can be deployed individually or as a group
   - All agents are A2A-compliant and can be registered with AgentBeats

#### AgentBeats Integration

The system is compatible with AgentBeats because:
- ✅ Uses standard A2A protocol for agent communication
- ✅ Implements `AgentExecutor` interface from `a2a.server.agent_execution`
- ✅ Exposes A2A endpoints via `A2AStarletteApplication`
- ✅ Supports agent discovery via `/.well-known/agent.json`
- ✅ Uses standard A2A message format for agent-to-agent communication
- ✅ Green agent can be invoked via A2A `execute` method
- ✅ White agents respond to A2A requests with proper JSON format

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

## Quick Start Examples

### Example 1: Complete Evaluation (All-in-One)

Run the complete system with all agents:

```bash
python launcher.py
```

This automatically:
1. Starts all 6 white agents (TAGBot, Monte Carlo, Maniac, Smart, Equity, Adaptive)
2. Starts the green agent (assessment manager)
3. Runs benchmark tests with 8 ground-truth test cases
4. Runs individual evaluations for each agent
5. Runs tournaments between all agents
6. Displays comprehensive results, metrics, and rankings

### Example 2: Manual Agent Setup

Start agents manually for more control:

```bash
# Terminal 1: Start white agent
python launcher.py --white-only --agent-id tagbot --port 8001 --agent-type tagbot

# Terminal 2: Start another white agent
python launcher.py --white-only --agent-id smart_agent --port 8004 --agent-type smart

# Terminal 3: Start green agent (will evaluate the running white agents)
python launcher.py --green-only
```

### Example 3: Testing Specific Agent

To test a specific agent type:

```bash
# Start only one white agent
python launcher.py --white-only --agent-id test_agent --port 8001 --agent-type smart

# In another terminal, start green agent
python launcher.py --green-only
```

### Customizing Evaluation

You can modify the `src/green_agent/agent_card.toml` file to:
- Add/remove white agents
- Change evaluation parameters (hands per tournament, number of tournaments)
- Modify poker rules (blinds, starting chips, max players)
- Adjust metrics tracking
- Enable/disable benchmark tests

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