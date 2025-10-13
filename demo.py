#!/usr/bin/env python3
"""
Demo script showing how to use the Poker Evaluation Agent system
"""
import asyncio
import logging
import time
from evaluation_agent import EvaluationAgent, AgentConfig, GameConfig


async def demo_evaluation_agent():
    """Demonstrate the evaluation agent functionality"""
    print("🃏 Poker Evaluation Agent Demo")
    print("=" * 50)
    
    # Create evaluation agent with custom config
    game_config = GameConfig(
        small_blind=5,
        big_blind=10,
        starting_chips=500,
        max_hands=1,
        hand_timeout=60
    )
    
    evaluation_agent = EvaluationAgent(game_config)
    
    # Register some mock agents (these would normally be running on different ports)
    print("Registering mock agents...")
    evaluation_agent.register_agent(AgentConfig(
        id="random_agent",
        name="Random Agent",
        url="http://localhost:8001"
    ))
    
    evaluation_agent.register_agent(AgentConfig(
        id="conservative_agent", 
        name="Conservative Agent",
        url="http://localhost:8002"
    ))
    
    evaluation_agent.register_agent(AgentConfig(
        id="aggressive_agent",
        name="Aggressive Agent", 
        url="http://localhost:8003"
    ))
    
    print(f"Registered {len(evaluation_agent.agents)} agents")
    
    # Show agent metrics
    print("\nAgent Metrics:")
    metrics = evaluation_agent.get_agent_metrics()
    for agent_id, metric in metrics.items():
        print(f"  {metric['agent_name']}: {metric['games_played']} games played")
    
    # Simulate a game (without actual agent communication)
    print("\nSimulating a poker game...")
    
    # Create a mock game state
    from poker_engine import PokerEngine
    engine = PokerEngine(small_blind=5, big_blind=10)
    
    player_ids = ["random_agent", "conservative_agent", "aggressive_agent"]
    player_names = ["Random Agent", "Conservative Agent", "Aggressive Agent"]
    
    game_state = engine.start_new_hand(player_ids, player_names, 500)
    
    print(f"Game started with {len(game_state.players)} players")
    print(f"Small blind: {game_state.small_blind}, Big blind: {game_state.big_blind}")
    print(f"Starting chips: 500 per player")
    print(f"Initial pot: {game_state.pot}")
    
    # Show initial game state
    print("\nInitial Game State:")
    for i, player in enumerate(game_state.players):
        print(f"  Player {i+1} ({player.name}): {player.chips} chips, {len(player.cards)} cards")
    
    # Simulate some actions
    print("\nSimulating actions...")
    
    from poker_engine import Action
    
    # Player 1 folds
    result = engine.process_action("random_agent", Action.FOLD)
    print(f"Random Agent: {result['message']}")
    
    # Player 2 calls
    result = engine.process_action("conservative_agent", Action.CALL)
    print(f"Conservative Agent: {result['message']}")
    
    # Player 3 raises
    result = engine.process_action("aggressive_agent", Action.RAISE, 50)
    print(f"Aggressive Agent: {result['message']}")
    
    print(f"\nCurrent pot: {game_state.pot}")
    print(f"Current bet: {game_state.current_bet}")
    
    # Show final standings
    print("\nFinal Standings:")
    for i, player in enumerate(game_state.players):
        chip_change = player.chips - 500
        print(f"  {i+1}. {player.name}: {player.chips} chips ({chip_change:+d})")
    
    print("\n✅ Demo completed successfully!")
    print("\nTo run the full system with web interface:")
    print("1. Start example agents: python example_agents.py")
    print("2. Start evaluation agent: python main.py")
    print("3. Open web dashboard: http://localhost:8000")


def main():
    """Main function"""
    # Suppress logs for cleaner demo output
    logging.basicConfig(level=logging.WARNING)
    
    asyncio.run(demo_evaluation_agent())


if __name__ == "__main__":
    main()
