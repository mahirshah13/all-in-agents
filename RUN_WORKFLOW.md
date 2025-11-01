# Running the Full Workflow - State Management Test

This guide shows you how to run the complete workflow to verify state management is working.

## Quick Start (Full Workflow)

The launcher will automatically start all agents and run a tournament. Just run:

```bash
python main.py
```

OR

```bash
python launcher.py
```

## What to Watch For

When you run the workflow, you should see these state management indicators:

### 1. At Tournament Start:

```
🔄 State Management: Generating new context IDs for all agents...
   ✅ OpenAI Poker Agent 1: New context ID created (a1b2c3d4...)
   ✅ OpenAI Poker Agent 2: New context ID created (e5f6g7h8...)
✅ All 2 agents reset with new context IDs
🏆 Tournament ID: 9i0j1k2l3m4n5o6p...
```

### 2. During Agent Initialization:

```
Initializing white agents via A2A...
   ✅ OpenAI Poker Agent 1: Initialized with context ID a1b2c3d4e5f6g7h8...
   ✅ OpenAI Poker Agent 2: Initialized with context ID e5f6g7h8i9j0k1l2...
```

### 3. Verify Context IDs Don't Change During Tournament:

The context IDs shown during initialization should remain the same throughout the tournament. You should NOT see new context IDs being created during gameplay.

### 4. If You Run Multiple Tournaments:

Each tournament should show:
- **Different tournament IDs**
- **Different context IDs for each agent** (reset happened)
- Task description sent once per tournament (not repeatedly)

## Detailed Step-by-Step

### Option 1: Automatic (Recommended for Testing)

The launcher automatically starts everything:

```bash
python main.py
```

This will:
1. Start all white agents in background processes
2. Start the green agent
3. Reset agent states
4. Initialize agents (send task description)
5. Run tournament
6. Show results

### Option 2: Manual (For Debugging)

If you want more control or to see individual agent logs:

**Terminal 1 - Start Agent 1:**
```bash
python launcher.py --white-only --agent-id openai_agent_1 --port 8001
```

**Terminal 2 - Start Agent 2:**
```bash
python launcher.py --white-only --agent-id openai_agent_2 --port 8002
```

**Terminal 3 - Start Green Agent (runs tournament):**
```bash
python launcher.py --green-only
# OR run full system:
python launcher.py
```

## Faster Testing (Reduce Game Counts)

To test faster, temporarily reduce games in `src/green_agent/agent_card.toml`:

```toml
[evaluation]
games_per_agent = 2      # Reduced from 10 (fewer hands per game)
tournament_games = 1     # Reduced from 5 (just 1 tournament game)
```

This makes a full test run much faster (~2-5 minutes instead of 10-20 minutes).

## Success Criteria

✅ **State Management Works If:**

1. **Context IDs are created at tournament start**
   - See: `✅ OpenAI Poker Agent 1: New context ID created (xxxxx...)`

2. **Context IDs don't change during the tournament**
   - Same IDs should appear throughout gameplay

3. **Task description sent only once per tournament**
   - Should see initialization message once at start
   - Not repeatedly during the tournament

4. **If running multiple tournaments, context IDs change**
   - Each new tournament gets fresh context IDs
   - Old conversation history doesn't carry over

5. **No errors about missing context or state**
   - Tournament runs smoothly
   - Agents respond correctly

## Troubleshooting

### Problem: Context IDs not showing
**Solution:** Make sure logging level is set correctly. The print statements should always show.

### Problem: Agents not initializing
**Solution:** 
- Check that white agents are running: `curl http://localhost:8001/.well-known/agent.json`
- Verify ports match config: Check `src/green_agent/agent_card.toml`

### Problem: State not resetting
**Solution:** 
- Check logs for "Resetting all agent states..." message
- Verify `reset_all_agent_states()` is being called in tournament start

### Problem: Task description sent multiple times
**Solution:** 
- Check `agent_initialized` flag is working
- Look for "Initialized agent..." messages - should only appear once per tournament

## Verifying Conversation Memory

To verify agents remember within a tournament but forget between tournaments:

1. **Run Tournament 1:**
   - Note the context IDs shown
   - Agents should build conversation history during the tournament

2. **Run Tournament 2:**
   - Should see NEW context IDs (different from Tournament 1)
   - Agents start fresh (don't remember Tournament 1)

3. **Within a single tournament:**
   - Agents should remember earlier decisions in the same tournament
   - Conversation history grows during the tournament

## Next Steps

After verifying state management works:

1. ✅ Increase game counts back to normal
2. ✅ Run full tournaments
3. ✅ Monitor performance
4. ✅ Consider enabling memory preservation if needed (optional)

