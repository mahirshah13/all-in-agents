#!/usr/bin/env python3
"""
Test script for the Poker Evaluation Agent system
Tests basic functionality without requiring external agents
"""
import asyncio
import logging
import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from poker_engine import PokerEngine, Action, Card, Suit, Rank
from evaluation_agent import EvaluationAgent, AgentConfig, GameConfig


def test_poker_engine():
    """Test the poker engine functionality"""
    print("Testing Poker Engine...")
    
    engine = PokerEngine(small_blind=10, big_blind=20)
    
    # Test deck creation
    deck = engine.create_deck()
    assert len(deck) == 52, f"Expected 52 cards, got {len(deck)}"
    
    # Test hand evaluation
    test_cards = [
        Card(Rank.ACE, Suit.SPADES),
        Card(Rank.KING, Suit.SPADES),
        Card(Rank.QUEEN, Suit.SPADES),
        Card(Rank.JACK, Suit.SPADES),
        Card(Rank.TEN, Suit.SPADES)
    ]
    
    hand_rank, tiebreaker = engine.get_hand_rank(test_cards)
    assert hand_rank.value == 10, f"Expected royal flush (10), got {hand_rank.value}"
    
    # Test game start
    game_state = engine.start_new_hand(
        ["player1", "player2"], 
        ["Player 1", "Player 2"], 
        1000
    )
    
    assert len(game_state.players) == 2, f"Expected 2 players, got {len(game_state.players)}"
    assert game_state.pot > 0, "Expected pot to have blinds"
    assert len(game_state.players[0].cards) == 2, "Expected 2 hole cards per player"
    
    print("✓ Poker Engine tests passed")


def test_hand_evaluation():
    """Test hand evaluation with various hands"""
    print("Testing Hand Evaluation...")
    
    engine = PokerEngine()
    
    # Test cases: (cards, expected_rank, description)
    test_cases = [
        # Royal flush
        ([Card(Rank.ACE, Suit.SPADES), Card(Rank.KING, Suit.SPADES), 
          Card(Rank.QUEEN, Suit.SPADES), Card(Rank.JACK, Suit.SPADES), 
          Card(Rank.TEN, Suit.SPADES)], 10, "Royal Flush"),
        
        # Straight flush
        ([Card(Rank.NINE, Suit.HEARTS), Card(Rank.EIGHT, Suit.HEARTS),
          Card(Rank.SEVEN, Suit.HEARTS), Card(Rank.SIX, Suit.HEARTS),
          Card(Rank.FIVE, Suit.HEARTS)], 9, "Straight Flush"),
        
        # Four of a kind
        ([Card(Rank.ACE, Suit.SPADES), Card(Rank.ACE, Suit.HEARTS),
          Card(Rank.ACE, Suit.DIAMONDS), Card(Rank.ACE, Suit.CLUBS),
          Card(Rank.KING, Suit.SPADES)], 8, "Four of a Kind"),
        
        # Full house
        ([Card(Rank.ACE, Suit.SPADES), Card(Rank.ACE, Suit.HEARTS),
          Card(Rank.ACE, Suit.DIAMONDS), Card(Rank.KING, Suit.SPADES),
          Card(Rank.KING, Suit.HEARTS)], 7, "Full House"),
        
        # Flush
        ([Card(Rank.ACE, Suit.SPADES), Card(Rank.KING, Suit.SPADES),
          Card(Rank.QUEEN, Suit.SPADES), Card(Rank.JACK, Suit.SPADES),
          Card(Rank.NINE, Suit.SPADES)], 6, "Flush"),
        
        # Straight
        ([Card(Rank.TEN, Suit.SPADES), Card(Rank.NINE, Suit.HEARTS),
          Card(Rank.EIGHT, Suit.DIAMONDS), Card(Rank.SEVEN, Suit.CLUBS),
          Card(Rank.SIX, Suit.SPADES)], 5, "Straight"),
        
        # Three of a kind
        ([Card(Rank.ACE, Suit.SPADES), Card(Rank.ACE, Suit.HEARTS),
          Card(Rank.ACE, Suit.DIAMONDS), Card(Rank.KING, Suit.SPADES),
          Card(Rank.QUEEN, Suit.HEARTS)], 4, "Three of a Kind"),
        
        # Two pair
        ([Card(Rank.ACE, Suit.SPADES), Card(Rank.ACE, Suit.HEARTS),
          Card(Rank.KING, Suit.SPADES), Card(Rank.KING, Suit.HEARTS),
          Card(Rank.QUEEN, Suit.DIAMONDS)], 3, "Two Pair"),
        
        # Pair
        ([Card(Rank.ACE, Suit.SPADES), Card(Rank.ACE, Suit.HEARTS),
          Card(Rank.KING, Suit.SPADES), Card(Rank.QUEEN, Suit.HEARTS),
          Card(Rank.JACK, Suit.DIAMONDS)], 2, "Pair"),
        
        # High card
        ([Card(Rank.ACE, Suit.SPADES), Card(Rank.KING, Suit.HEARTS),
          Card(Rank.QUEEN, Suit.DIAMONDS), Card(Rank.JACK, Suit.CLUBS),
          Card(Rank.NINE, Suit.SPADES)], 1, "High Card")
    ]
    
    for cards, expected_rank, description in test_cases:
        hand_rank, tiebreaker = engine.get_hand_rank(cards)
        assert hand_rank.value == expected_rank, f"{description}: Expected rank {expected_rank}, got {hand_rank.value}"
    
    print("✓ Hand Evaluation tests passed")


def test_action_processing():
    """Test action processing in poker engine"""
    print("Testing Action Processing...")
    
    engine = PokerEngine(small_blind=10, big_blind=20)
    game_state = engine.start_new_hand(
        ["player1", "player2"], 
        ["Player 1", "Player 2"], 
        1000
    )
    
    # Test fold action
    result = engine.process_action("player1", Action.FOLD)
    assert result["success"], f"Fold action failed: {result}"
    assert not game_state.players[0].is_active, "Player should be inactive after fold"
    
    # Test call action
    game_state = engine.start_new_hand(["player1", "player2"], ["Player 1", "Player 2"], 1000)
    result = engine.process_action("player1", Action.CALL)
    assert result["success"], f"Call action failed: {result}"
    
    # Test raise action
    result = engine.process_action("player2", Action.RAISE, 100)
    assert result["success"], f"Raise action failed: {result}"
    assert game_state.current_bet == 100, f"Expected current bet 100, got {game_state.current_bet}"
    
    print("✓ Action Processing tests passed")


async def test_evaluation_agent():
    """Test the evaluation agent functionality"""
    print("Testing Evaluation Agent...")
    
    # Create evaluation agent
    game_config = GameConfig(starting_chips=1000, max_hands=1)
    evaluation_agent = EvaluationAgent(game_config)
    
    # Register test agents (mock URLs)
    evaluation_agent.register_agent(AgentConfig(
        id="test_agent_1",
        name="Test Agent 1",
        url="http://localhost:9999"  # Mock URL
    ))
    
    evaluation_agent.register_agent(AgentConfig(
        id="test_agent_2", 
        name="Test Agent 2",
        url="http://localhost:9998"  # Mock URL
    ))
    
    # Test metrics
    metrics = evaluation_agent.get_agent_metrics()
    assert len(metrics) == 2, f"Expected 2 agents, got {len(metrics)}"
    
    # Test agent unregistration
    evaluation_agent.unregister_agent("test_agent_1")
    metrics = evaluation_agent.get_agent_metrics()
    assert len(metrics) == 1, f"Expected 1 agent after unregistration, got {len(metrics)}"
    
    print("✓ Evaluation Agent tests passed")


def test_a2a_protocol():
    """Test A2A protocol message creation"""
    print("Testing A2A Protocol...")
    
    from a2a_protocol import A2AProtocol, MessageType
    
    protocol = A2AProtocol()
    
    # Test message creation
    message = protocol.create_message(
        MessageType.ACTION_REQUEST,
        "game_123",
        "player_1",
        {"test": "data"}
    )
    
    assert message.message_type == MessageType.ACTION_REQUEST
    assert message.game_id == "game_123"
    assert message.player_id == "player_1"
    assert message.data == {"test": "data"}
    
    print("✓ A2A Protocol tests passed")


async def run_all_tests():
    """Run all tests"""
    print("🧪 Running Poker Evaluation Agent Tests")
    print("=" * 50)
    
    try:
        test_poker_engine()
        test_hand_evaluation()
        test_action_processing()
        test_a2a_protocol()
        await test_evaluation_agent()
        
        print("\n🎉 All tests passed!")
        print("The Poker Evaluation Agent system is working correctly.")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def main():
    """Main function"""
    logging.basicConfig(level=logging.WARNING)  # Suppress logs during testing
    
    asyncio.run(run_all_tests())


if __name__ == "__main__":
    main()
