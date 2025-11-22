# Green Agent Evaluation System

## Overview

The green agent (Poker Assessment Manager) evaluates white agents across multiple dimensions to assess their poker-playing capabilities. This document explains what the green agent assesses, how it evaluates outputs, and how reliability is demonstrated through ground-truth test cases.

## What the Green Agent Assesses

The green agent evaluates white agents across **8 key dimensions**:

### 1. **CORRECTNESS**
- **What**: Is the action valid and legal?
- **How**: Checks if the action (fold/call/raise) is allowed by poker rules
- **Example**: A raise must be at least 2x the current bet

### 2. **STRATEGIC_QUALITY**
- **What**: Is the action strategically sound?
- **How**: Evaluates if the decision makes sense given the game state (hand strength, position, pot size)
- **Example**: Raising with pocket aces preflop is strategically sound

### 3. **CONSISTENCY**
- **What**: Is the agent consistent with its stated strategy?
- **How**: Compares actions to the agent's declared strategy type (TAGBot should be tight-aggressive, Maniac should be aggressive, etc.)
- **Example**: A TAGBot that folds 7-2 offsuit is consistent; a TAGBot that raises with 7-2 is inconsistent

### 4. **RESPONSE_FORMAT**
- **What**: Does the response follow the required format?
- **How**: Validates JSON structure, required fields (action, amount, reasoning)
- **Example**: Response must be valid JSON with "action", "amount", and optionally "reasoning"

### 5. **REASONING_QUALITY**
- **What**: Is the reasoning logical and sound?
- **How**: Analyzes the reasoning provided by the agent for logical consistency and poker knowledge
- **Example**: Reasoning that mentions pot odds, equity, or position shows good understanding

### 6. **POSITION_AWARENESS**
- **What**: Does the agent consider position?
- **How**: Checks if the agent's decision and reasoning account for position (early/middle/late/button)
- **Example**: Raising with KQ on the button shows position awareness

### 7. **POT_ODDS_AWARENESS**
- **What**: Does the agent consider pot odds?
- **How**: Evaluates if the agent calculates or considers pot odds when making decisions
- **Example**: Calling a flush draw when pot odds are favorable shows pot odds awareness

### 8. **STACK_MANAGEMENT**
- **What**: Does the agent manage stack size appropriately?
- **How**: Assesses if bet sizes are appropriate relative to stack size and game situation
- **Example**: Short stack (5% of starting chips) with strong hand should push all-in

## Concrete Evaluation Examples

The system includes **8 concrete examples** showing how different agents are evaluated:

1. **Preflop with Strong Hand** (Pocket Aces)
   - Expected: Raise
   - Tests: Strategic quality, consistency, reasoning

2. **Preflop with Weak Hand** (7-2 offsuit)
   - Expected: Fold
   - Tests: Strategic quality, consistency, position awareness

3. **Flop with Strong Hand** (Top pair)
   - Expected: Bet/Raise
   - Tests: Strategic quality, equity awareness

4. **Flop with Draw** (Flush draw)
   - Expected: Call (if pot odds favorable)
   - Tests: Pot odds awareness, strategic quality

5. **River with Weak Hand**
   - Expected: Fold
   - Tests: Strategic quality, reasoning quality

6. **Short Stack All-In Decision**
   - Expected: All-in (with strong hand)
   - Tests: Stack management, strategic quality

7. **Position Awareness**
   - Expected: Raise (in good position)
   - Tests: Position awareness, strategic quality

8. **Pot Odds Calculation**
   - Expected: Call (if pot odds favorable)
   - Tests: Pot odds awareness, reasoning quality

Each example includes:
- Game state (cards, pot, position, etc.)
- Agent response (action, amount, reasoning)
- Assessment scores for all 8 dimensions
- Overall score (0-1 scale)

## Ground-Truth Test Cases

The system includes **8 ground-truth test cases** with known correct answers:

| Test Case | Expected Action | Minimum Score | Description |
|-----------|----------------|---------------|-------------|
| `preflop_strong_hand` | raise | 0.85 | Pocket aces should raise preflop |
| `preflop_weak_hand` | fold | 0.90 | 7-2 offsuit should fold preflop |
| `flop_strong_hand` | raise | 0.80 | Top pair should bet/raise on flop |
| `flop_draw_pot_odds` | call | 0.85 | Flush draw with good pot odds should call |
| `river_weak_hand` | fold | 0.80 | Weak hand on river should fold to large bet |
| `short_stack_all_in` | all_in | 0.85 | Short stack with strong hand should push all-in |
| `position_awareness` | raise | 0.85 | Strong hand in good position should raise |
| `pot_odds_calculation` | call | 0.85 | Draw with favorable pot odds should call |

## Benchmark Results

The green agent runs benchmark tests before the main tournament to assess reliability. Results include:

### Accuracy Metrics
- **Action Accuracy**: Percentage of test cases where the agent chose the correct action
- **Average Score**: Average assessment score across all test cases
- **Benchmark Pass Rate**: PASS if accuracy ≥ 75% and average score ≥ 0.80

### Quantitative Results

For each agent, the benchmark reports:
1. **Per-Test Results**: Shows action chosen, expected action, correctness, and score
2. **Overall Accuracy**: Percentage of correct actions
3. **Average Score**: Mean assessment score
4. **Pass/Fail Status**: Whether the agent meets benchmark thresholds

## How to View Results

When you run the evaluation system, the green agent will:

1. **Run Benchmark Tests** (if enabled)
   - Tests each agent on ground-truth test cases
   - Shows per-test results and accuracy metrics

2. **Run Tournament**
   - Plays actual poker games between agents
   - Tracks detailed metrics (VPIP, PFR, aggression factor, etc.)

3. **Print Final Report**
   - Shows tournament rankings and performance scores
   - Displays detailed strategic metrics for each agent
   - **Shows evaluation examples** with concrete assessments
   - **Shows benchmark results** with accuracy metrics

## Example Output

```
====================================================================================================
EVALUATION EXAMPLES - How Green Agent Assesses White Agents
====================================================================================================

📋 What the Green Agent Assesses:
  1. CORRECTNESS: Is the action valid and legal?
  2. STRATEGIC_QUALITY: Is the action strategically sound?
  3. CONSISTENCY: Is the agent consistent with its stated strategy?
  4. RESPONSE_FORMAT: Does the response follow the required format?
  5. REASONING_QUALITY: Is the reasoning logical and sound?
  6. POSITION_AWARENESS: Does the agent consider position?
  7. POT_ODDS_AWARENESS: Does the agent consider pot odds?
  8. STACK_MANAGEMENT: Does the agent manage stack size appropriately?

----------------------------------------------------------------------------------------------------
CONCRETE EVALUATION EXAMPLES
----------------------------------------------------------------------------------------------------

📊 Example 1: Preflop with pocket aces (A♠ A♥) on button, facing big blind
   Agent: TAGBot
   Response: RAISE (amount: 80)
   Reasoning: Pocket aces is the strongest starting hand. Raising to build pot and isolate opponents.

   Assessment Scores:
     CORRECTNESS               1.00 ████████████████████ Action is valid and legal
     STRATEGIC_QUALITY         0.95 ████████████████████ Raising with aces is optimal. Amount is reasonable (4x BB).
     CONSISTENCY               1.00 ████████████████████ Consistent with tight-aggressive strategy
     RESPONSE_FORMAT           1.00 ████████████████████ Valid JSON with required fields
     REASONING_QUALITY         0.90 ████████████████████ Reasoning is sound - recognizes hand strength
     POSITION_AWARENESS        0.80 ████████████████████ Position mentioned but not deeply analyzed
     POT_ODDS_AWARENESS        0.70 ████████████████████ Pot odds not explicitly calculated
     STACK_MANAGEMENT           0.90 ████████████████████ Bet size appropriate for stack (8% of stack)
   Overall Score: 0.91/1.00

...

====================================================================================================
BENCHMARK RESULTS - Reliability Testing with Ground Truth
====================================================================================================

📊 Test Cases with Ground Truth:

   Test: preflop_strong_hand
   Expected Action: RAISE
   Minimum Score: 0.85
   Description: Pocket aces should raise preflop
   Agent Results:
     ✅ ✅ TAGBot              Action: raise  Score: 0.91
     ✅ ✅ Monte Carlo         Action: raise  Score: 0.88
     ❌ ❌ Maniac              Action: fold   Score: 0.45

...

----------------------------------------------------------------------------------------------------
ACCURACY METRICS
----------------------------------------------------------------------------------------------------

   TAGBot:
     Action Accuracy: 87.5% (7/8)
     Average Score: 0.89/1.00
     Benchmark Pass Rate: ✅ PASS

   Monte Carlo:
     Action Accuracy: 75.0% (6/8)
     Average Score: 0.82/1.00
     Benchmark Pass Rate: ✅ PASS

   Maniac:
     Action Accuracy: 50.0% (4/8)
     Average Score: 0.65/1.00
     Benchmark Pass Rate: ❌ FAIL
```

## Configuration

To enable/disable benchmark tests, edit `src/green_agent/agent_card.toml`:

```toml
[evaluation]
run_benchmark_tests = true  # Set to false to skip benchmark tests
```

## Files

- `src/green_agent/evaluation_examples.py`: Contains all evaluation examples and ground-truth test cases
- `src/green_agent/assessment_manager.py`: Main green agent that runs evaluations and displays results

