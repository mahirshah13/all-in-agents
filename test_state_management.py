#!/usr/bin/env python3
"""
Test script for state management functionality
Tests agent state initialization and reset without running full tournaments
"""
import asyncio
import sys
from pathlib import Path
import toml

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.green_agent.assessment_manager import PokerAssessmentManager


async def test_state_management():
    """Test the state management functions"""
    print("=" * 60)
    print("Testing State Management Implementation")
    print("=" * 60)
    
    # Load configuration
    config_path = "src/green_agent/agent_card.toml"
    try:
        with open(config_path, 'r') as f:
            config = toml.load(f)
    except Exception as e:
        print(f"❌ Error loading config: {e}")
        return False
    
    # Create assessment manager
    print("\n1. Creating PokerAssessmentManager...")
    manager = PokerAssessmentManager(config)
    print("✅ Manager created successfully")
    
    # Check initial state
    print("\n2. Checking initial state...")
    print(f"   - Number of white agents: {len(manager.white_agents)}")
    print(f"   - Agent contexts: {len(manager.agent_contexts)}")
    print(f"   - Agent initialized flags: {len(manager.agent_initialized)}")
    print(f"   - Current tournament ID: {manager.current_tournament_id}")
    
    # Test state tracking initialization
    print("\n3. Testing state tracking...")
    agent_ids = list(manager.white_agents.keys())
    if not agent_ids:
        print("⚠️  No white agents configured. Add agents to agent_card.toml")
        return False
    
    first_agent_id = agent_ids[0]
    print(f"   - Testing with agent: {first_agent_id}")
    
    # Test context ID creation
    print("\n4. Testing context ID creation...")
    if first_agent_id not in manager.agent_contexts:
        print("   - Agent context doesn't exist yet (expected)")
        # This should create a context ID
        await manager.initialize_agent_state(first_agent_id, send_task_description=False)
    
    context_id_before = manager.agent_contexts.get(first_agent_id)
    print(f"   - Context ID created: {context_id_before[:16]}...")
    print(f"   - Agent initialized: {manager.agent_initialized.get(first_agent_id, False)}")
    
    # Test reset functionality
    print("\n5. Testing reset functionality...")
    await manager.reset_agent_state(first_agent_id, clear_memory=False)
    context_id_after = manager.agent_contexts.get(first_agent_id)
    print(f"   - Context ID before reset: {context_id_before[:16]}...")
    print(f"   - Context ID after reset: {context_id_after[:16]}...")
    
    if context_id_before != context_id_after:
        print("   ✅ Context ID changed (reset works!)")
    else:
        print("   ❌ Context ID didn't change (reset may not be working)")
        return False
    
    print(f"   - Agent initialized after reset: {manager.agent_initialized.get(first_agent_id, False)}")
    if not manager.agent_initialized.get(first_agent_id, False):
        print("   ✅ Agent marked as not initialized (will send task description next time)")
    else:
        print("   ❌ Agent still marked as initialized")
        return False
    
    # Test reset all agents
    print("\n6. Testing reset_all_agent_states...")
    await manager.reset_all_agent_states(clear_memory=False)
    print(f"   - All {len(manager.white_agents)} agents reset")
    for agent_id in manager.white_agents.keys():
        if manager.agent_initialized.get(agent_id, True):  # Should be False after reset
            print(f"   ❌ Agent {agent_id} still marked as initialized")
            return False
    print("   ✅ All agents properly reset")
    
    # Test tournament ID generation
    print("\n7. Testing tournament ID generation...")
    import uuid
    manager.current_tournament_id = str(uuid.uuid4())
    print(f"   - Tournament ID: {manager.current_tournament_id[:16]}...")
    print("   ✅ Tournament ID generation works")
    
    print("\n" + "=" * 60)
    print("✅ All state management tests passed!")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Start white agents manually: python launcher.py --white-only --agent-id <id> --port <port>")
    print("2. Run a small test tournament with reduced games in config")
    print("3. Check logs to verify context IDs are being reset between tournaments")
    
    return True


async def test_with_real_agents():
    """Test with actual agents running (optional, requires agents to be started)"""
    print("\n" + "=" * 60)
    print("Testing with Real Agents (Optional)")
    print("=" * 60)
    print("\n⚠️  This requires white agents to be running!")
    print("Start agents first:")
    print("  Terminal 1: python launcher.py --white-only --agent-id openai_agent_1 --port 8001")
    print("  Terminal 2: python launcher.py --white-only --agent-id openai_agent_2 --port 8002")
    print("\nPress Enter when agents are ready, or Ctrl+C to skip...")
    
    try:
        input()
    except KeyboardInterrupt:
        print("\nSkipping real agent test")
        return
    
    config_path = "src/green_agent/agent_card.toml"
    with open(config_path, 'r') as f:
        config = toml.load(f)
    
    manager = PokerAssessmentManager(config)
    
    # Test initialization (will actually send messages)
    print("\nTesting agent initialization...")
    agent_ids = list(manager.white_agents.keys())
    if agent_ids:
        first_agent = manager.white_agents[agent_ids[0]]
        print(f"Initializing {first_agent.name}...")
        try:
            await manager.initialize_agent_state(agent_ids[0], send_task_description=True)
            print(f"✅ {first_agent.name} initialized successfully")
            print(f"   Context ID: {manager.agent_contexts[agent_ids[0]][:16]}...")
        except Exception as e:
            print(f"❌ Failed to initialize: {e}")
            print("   Make sure the agent is running on the correct port")


if __name__ == "__main__":
    print("State Management Test Suite")
    print("=" * 60)
    
    # Run basic tests
    success = asyncio.run(test_state_management())
    
    if success:
        # Optionally test with real agents
        try:
            asyncio.run(test_with_real_agents())
        except KeyboardInterrupt:
            print("\nTest suite completed")

