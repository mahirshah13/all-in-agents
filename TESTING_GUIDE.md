# State Management Testing Guide

This guide helps you test the new state management features without breaking your system.

## Quick Test (No Agents Required)

Test the state management logic without running any agents:

```bash
python test_state_management.py
```

This will:
- ✅ Verify state tracking variables exist
- ✅ Test context ID creation
- ✅ Test reset functionality
- ✅ Verify tournament ID generation
- ✅ Check that agents are properly marked as initialized/uninitialized

**Expected output:** All tests should pass with ✅ marks.

## Step-by-Step Testing

### Step 1: Verify Code Compiles
```bash
python -c "from src.green_agent.assessment_manager import PokerAssessmentManager; print('✅ Import successful')"
```

### Step 2: Check Configuration
```bash
python -c "import toml; config = toml.load('src/green_agent/agent_card.toml'); print(f'✅ Config loaded: {len(config[\"evaluation\"][\"white_agents\"])} agents')"
```

### Step 3: Run Basic State Management Test
```bash
python test_state_management.py
```

### Step 4: Test with Real Agents (Optional)

**Terminal 1 - Start Agent 1:**
```bash
python launcher.py --white-only --agent-id openai_agent_1 --port 8001
```

**Terminal 2 - Start Agent 2:**
```bash
python launcher.py --white-only --agent-id openai_agent_2 --port 8002
```

**Terminal 3 - Run Test:**
```bash
python test_state_management.py
# When prompted, press Enter to test with real agents
```

### Step 5: Small Tournament Test

First, create a test config with minimal games:

1. Backup your current config:
```bash
cp src/green_agent/agent_card.toml src/green_agent/agent_card.toml.backup
```

2. Edit config to reduce games (for faster testing):
```toml
[evaluation]
games_per_agent = 2      # Reduced from 10
tournament_games = 1     # Just 1 tournament game
```

3. Start agents (Terminals 1 & 2 from Step 4)

4. Run a small tournament:
```bash
python launcher.py
```

5. Watch the logs for:
   - "Resetting all agent states for new tournament..." 
   - "Starting tournament [ID]..."
   - Context ID changes in logs

### Step 6: Test Multiple Tournaments

To test that state resets between tournaments:

1. Modify the code to run 2 tournaments (or manually run `launcher.py` twice)
2. Check logs to see:
   - Different tournament IDs
   - Different context IDs for agents
   - Task description sent only once per tournament

## What to Look For

### ✅ Success Indicators:

1. **Context IDs change between tournaments**
   - Look for log messages like: `"Reset state for agent... (old context: abc12345..., new: def67890...)"`

2. **Agents are marked as not initialized after reset**
   - After reset, `agent_initialized[agent_id]` should be `False`

3. **Task description sent once per tournament**
   - You should see "Initializing white agents via A2A..." once at tournament start
   - Not repeatedly during the tournament

4. **No errors about missing context IDs**
   - All agents should have valid context IDs

### ❌ Warning Signs:

1. **Same context ID across tournaments**
   - This means reset isn't working

2. **Task description sent multiple times**
   - Agents shouldn't receive the same instructions repeatedly

3. **Agents remember conversations from previous tournaments**
   - After reset, agents should start fresh

## Verification Commands

Check state management is working:

```python
# In Python REPL
import asyncio
import toml
from src.green_agent.assessment_manager import PokerAssessmentManager

config = toml.load('src/green_agent/agent_card.toml')
manager = PokerAssessmentManager(config)

# Check initial state
print("Initial context IDs:", manager.agent_contexts)
print("Initialized flags:", manager.agent_initialized)

# Test reset
agent_id = list(manager.white_agents.keys())[0]
old_context = manager.agent_contexts.get(agent_id)

await manager.reset_agent_state(agent_id)
new_context = manager.agent_contexts.get(agent_id)

print(f"Reset worked: {old_context != new_context}")  # Should be True
```

## Troubleshooting

### Problem: Import errors
**Solution:** Make sure you're in the project root directory and all dependencies are installed.

### Problem: Agents not found
**Solution:** Check `src/green_agent/agent_card.toml` has white agents configured.

### Problem: Context IDs not changing
**Solution:** Check that `reset_agent_state()` is being called. Look for reset messages in logs.

### Problem: White agent errors
**Solution:** Make sure white agents are running on the correct ports before testing.

## Safe Rollback

If something breaks, you can revert:

1. **Revert code changes:**
```bash
git checkout src/green_agent/assessment_manager.py
```

2. **The new methods are additive** - old code should still work without them
3. **White agents don't need changes** - they already support multiple context IDs

## Next Steps After Testing

Once tests pass:
1. ✅ Run a full tournament to verify everything works
2. ✅ Check that conversation history is properly maintained within tournaments
3. ✅ Verify agents start fresh between tournaments
4. ✅ Monitor performance - state management should be lightweight

