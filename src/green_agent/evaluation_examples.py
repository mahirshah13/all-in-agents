#!/usr/bin/env python3
"""
Evaluation Examples Module
Shows concrete examples of how the green agent evaluates outputs from different white agents
"""
from typing import Dict, List, Any, Tuple
from dataclasses import dataclass
from enum import Enum
import json


class AssessmentDimension(Enum):
    """What the green agent is assessing"""
    CORRECTNESS = "correctness"  # Is the action valid and legal?
    STRATEGIC_QUALITY = "strategic_quality"  # Is the action strategically sound?
    CONSISTENCY = "consistency"  # Is the agent consistent with its stated strategy?
    RESPONSE_FORMAT = "response_format"  # Does the response follow the required format?
    REASONING_QUALITY = "reasoning_quality"  # Is the reasoning logical and sound?
    POSITION_AWARENESS = "position_awareness"  # Does the agent consider position?
    POT_ODDS_AWARENESS = "pot_odds_awareness"  # Does the agent consider pot odds?
    STACK_MANAGEMENT = "stack_management"  # Does the agent manage stack size appropriately?


@dataclass
class EvaluationExample:
    """A concrete example of evaluating a white agent's output"""
    scenario_description: str
    game_state: Dict[str, Any]
    agent_response: Dict[str, Any]
    agent_type: str
    expected_action: str  # Ground truth or expected action
    assessments: Dict[AssessmentDimension, Tuple[float, str]]  # Score (0-1) and explanation
    overall_score: float
    benchmark_label: str  # For test cases with ground truth


class EvaluationExamples:
    """Collection of concrete evaluation examples"""
    
    @staticmethod
    def get_examples() -> List[EvaluationExample]:
        """Get all evaluation examples"""
        return [
            EvaluationExamples.example_1_preflop_strong_hand(),
            EvaluationExamples.example_2_preflop_weak_hand(),
            EvaluationExamples.example_3_flop_strong_hand(),
            EvaluationExamples.example_4_flop_draw(),
            EvaluationExamples.example_5_river_decision(),
            EvaluationExamples.example_6_all_in_decision(),
            EvaluationExamples.example_7_position_awareness(),
            EvaluationExamples.example_8_pot_odds_calculation(),
        ]
    
    @staticmethod
    def example_1_preflop_strong_hand() -> EvaluationExample:
        """Example: Preflop with pocket aces - should raise"""
        game_state = {
            "round": "preflop",
            "pot": 30,  # Blinds: 10 + 20
            "current_bet": 20,
            "player_chips": 1000,
            "player_position": "button",
            "player_cards": ["A♠", "A♥"],
            "community_cards": [],
            "opponents": [
                {"name": "Player1", "chips": 1000, "current_bet": 20, "is_active": True}
            ]
        }
        
        # TAGBot response (correct)
        tagbot_response = {
            "action": "raise",
            "amount": 80,
            "reasoning": "Pocket aces is the strongest starting hand. Raising to build pot and isolate opponents."
        }
        
        # Maniac response (also correct, but different style)
        maniac_response = {
            "action": "raise",
            "amount": 150,
            "reasoning": "Aces! Going big to maximize value."
        }
        
        # Conservative agent response (suboptimal)
        conservative_response = {
            "action": "call",
            "amount": 20,
            "reasoning": "Good hand, but want to see the flop first."
        }
        
        # Use TAGBot as example
        return EvaluationExample(
            scenario_description="Preflop with pocket aces (A♠ A♥) on button, facing big blind",
            game_state=game_state,
            agent_response=tagbot_response,
            agent_type="TAGBot",
            expected_action="raise",
            assessments={
                AssessmentDimension.CORRECTNESS: (1.0, "Action is valid and legal"),
                AssessmentDimension.STRATEGIC_QUALITY: (0.95, "Raising with aces is optimal. Amount is reasonable (4x BB)."),
                AssessmentDimension.CONSISTENCY: (1.0, "Consistent with tight-aggressive strategy"),
                AssessmentDimension.RESPONSE_FORMAT: (1.0, "Valid JSON with required fields"),
                AssessmentDimension.REASONING_QUALITY: (0.9, "Reasoning is sound - recognizes hand strength"),
                AssessmentDimension.POSITION_AWARENESS: (0.8, "Position mentioned but not deeply analyzed"),
                AssessmentDimension.POT_ODDS_AWARENESS: (0.7, "Pot odds not explicitly calculated"),
                AssessmentDimension.STACK_MANAGEMENT: (0.9, "Bet size appropriate for stack (8% of stack)")
            },
            overall_score=0.91,
            benchmark_label="preflop_strong_hand"
        )
    
    @staticmethod
    def example_2_preflop_weak_hand() -> EvaluationExample:
        """Example: Preflop with 7-2 offsuit - should fold"""
        game_state = {
            "round": "preflop",
            "pot": 30,
            "current_bet": 20,
            "player_chips": 1000,
            "player_position": "early",
            "player_cards": ["7♣", "2♦"],
            "community_cards": [],
            "opponents": [
                {"name": "Player1", "chips": 1000, "current_bet": 20, "is_active": True}
            ]
        }
        
        # Smart agent response (correct)
        smart_response = {
            "action": "fold",
            "amount": 0,
            "reasoning": "7-2 offsuit is the worst starting hand. Folding from early position."
        }
        
        # Maniac response (incorrect)
        maniac_response = {
            "action": "raise",
            "amount": 100,
            "reasoning": "Any two cards can win! Let's go!"
        }
        
        return EvaluationExample(
            scenario_description="Preflop with 7-2 offsuit (worst hand) in early position",
            game_state=game_state,
            agent_response=smart_response,
            agent_type="Smart Agent",
            expected_action="fold",
            assessments={
                AssessmentDimension.CORRECTNESS: (1.0, "Action is valid"),
                AssessmentDimension.STRATEGIC_QUALITY: (1.0, "Folding 7-2 offsuit is correct, especially from early position"),
                AssessmentDimension.CONSISTENCY: (1.0, "Consistent with smart strategy"),
                AssessmentDimension.RESPONSE_FORMAT: (1.0, "Valid format"),
                AssessmentDimension.REASONING_QUALITY: (0.95, "Excellent reasoning - recognizes worst hand"),
                AssessmentDimension.POSITION_AWARENESS: (1.0, "Position explicitly considered"),
                AssessmentDimension.POT_ODDS_AWARENESS: (0.8, "Implicitly considered (folding bad hand)"),
                AssessmentDimension.STACK_MANAGEMENT: (1.0, "Preserving chips by folding")
            },
            overall_score=0.97,
            benchmark_label="preflop_weak_hand"
        )
    
    @staticmethod
    def example_3_flop_strong_hand() -> EvaluationExample:
        """Example: Flop with top pair - should bet/raise"""
        game_state = {
            "round": "flop",
            "pot": 100,
            "current_bet": 0,
            "player_chips": 950,
            "player_position": "button",
            "player_cards": ["A♠", "K♥"],
            "community_cards": ["A♦", "7♣", "2♠"],
            "opponents": [
                {"name": "Player1", "chips": 950, "current_bet": 0, "is_active": True}
            ]
        }
        
        # Equity Calculator response
        equity_response = {
            "action": "raise",
            "amount": 60,
            "reasoning": "Top pair with top kicker. Estimated equity ~85%. Betting for value."
        }
        
        return EvaluationExample(
            scenario_description="Flop with top pair (A♠ K♥ on A♦ 7♣ 2♠ board)",
            game_state=game_state,
            agent_response=equity_response,
            agent_type="Equity Calculator",
            expected_action="raise",
            assessments={
                AssessmentDimension.CORRECTNESS: (1.0, "Valid action"),
                AssessmentDimension.STRATEGIC_QUALITY: (0.9, "Betting for value is correct. Amount is reasonable."),
                AssessmentDimension.CONSISTENCY: (1.0, "Consistent with equity-based strategy"),
                AssessmentDimension.RESPONSE_FORMAT: (1.0, "Valid format"),
                AssessmentDimension.REASONING_QUALITY: (0.95, "Excellent - calculated equity and explained reasoning"),
                AssessmentDimension.POSITION_AWARENESS: (0.8, "Position not explicitly mentioned"),
                AssessmentDimension.POT_ODDS_AWARENESS: (0.9, "Equity calculation shows pot odds awareness"),
                AssessmentDimension.STACK_MANAGEMENT: (0.85, "Bet size appropriate (~6% of stack)")
            },
            overall_score=0.93,
            benchmark_label="flop_strong_hand"
        )
    
    @staticmethod
    def example_4_flop_draw() -> EvaluationExample:
        """Example: Flop with flush draw - should call/raise"""
        game_state = {
            "round": "flop",
            "pot": 150,
            "current_bet": 50,
            "player_chips": 900,
            "player_position": "middle",
            "player_cards": ["9♠", "8♠"],
            "community_cards": ["K♠", "7♠", "2♥"],
            "opponents": [
                {"name": "Player1", "chips": 900, "current_bet": 50, "is_active": True}
            ]
        }
        
        # Smart agent response
        smart_response = {
            "action": "call",
            "amount": 50,
            "reasoning": "Flush draw with 9 outs. Pot odds: 150:50 = 3:1. Need ~25% equity, have ~36%. Call is profitable."
        }
        
        return EvaluationExample(
            scenario_description="Flop with flush draw (9♠ 8♠ on K♠ 7♠ 2♥), facing 50 bet into 150 pot",
            game_state=game_state,
            agent_response=smart_response,
            agent_type="Smart Agent",
            expected_action="call",
            assessments={
                AssessmentDimension.CORRECTNESS: (1.0, "Valid action"),
                AssessmentDimension.STRATEGIC_QUALITY: (0.95, "Calling with flush draw is correct given pot odds"),
                AssessmentDimension.CONSISTENCY: (1.0, "Consistent with pot odds strategy"),
                AssessmentDimension.RESPONSE_FORMAT: (1.0, "Valid format"),
                AssessmentDimension.REASONING_QUALITY: (1.0, "Excellent - calculated pot odds and equity correctly"),
                AssessmentDimension.POSITION_AWARENESS: (0.7, "Position not explicitly considered"),
                AssessmentDimension.POT_ODDS_AWARENESS: (1.0, "Perfect - explicitly calculated pot odds (3:1) and equity (~36%)"),
                AssessmentDimension.STACK_MANAGEMENT: (0.9, "Call size is reasonable")
            },
            overall_score=0.94,
            benchmark_label="flop_draw_pot_odds"
        )
    
    @staticmethod
    def example_5_river_decision() -> EvaluationExample:
        """Example: River with weak hand - should fold"""
        game_state = {
            "round": "river",
            "pot": 500,
            "current_bet": 200,
            "player_chips": 800,
            "player_position": "early",
            "player_cards": ["J♣", "9♦"],
            "community_cards": ["K♠", "Q♥", "10♠", "8♣", "7♦"],
            "opponents": [
                {"name": "Player1", "chips": 800, "current_bet": 200, "is_active": True}
            ]
        }
        
        # TAGBot response
        tagbot_response = {
            "action": "fold",
            "amount": 0,
            "reasoning": "Only high card on scary board. Opponent betting large on river likely has strong hand. Folding."
        }
        
        return EvaluationExample(
            scenario_description="River with only high card (J♣ 9♦) on K♠ Q♥ 10♠ 8♣ 7♦ board, facing 200 bet into 500 pot",
            game_state=game_state,
            agent_response=tagbot_response,
            agent_type="TAGBot",
            expected_action="fold",
            assessments={
                AssessmentDimension.CORRECTNESS: (1.0, "Valid action"),
                AssessmentDimension.STRATEGIC_QUALITY: (0.9, "Folding weak hand on river is correct"),
                AssessmentDimension.CONSISTENCY: (1.0, "Consistent with tight strategy"),
                AssessmentDimension.RESPONSE_FORMAT: (1.0, "Valid format"),
                AssessmentDimension.REASONING_QUALITY: (0.85, "Good reasoning - recognizes board texture and opponent behavior"),
                AssessmentDimension.POSITION_AWARENESS: (0.6, "Position not explicitly mentioned"),
                AssessmentDimension.POT_ODDS_AWARENESS: (0.7, "Implicitly considered (folding when pot odds don't justify call)"),
                AssessmentDimension.STACK_MANAGEMENT: (0.9, "Preserving chips")
            },
            overall_score=0.87,
            benchmark_label="river_weak_hand"
        )
    
    @staticmethod
    def example_6_all_in_decision() -> EvaluationExample:
        """Example: Short stack all-in decision"""
        game_state = {
            "round": "preflop",
            "pot": 30,
            "current_bet": 20,
            "player_chips": 50,  # Very short stack
            "player_position": "button",
            "player_cards": ["A♠", "K♥"],
            "community_cards": [],
            "opponents": [
                {"name": "Player1", "chips": 1000, "current_bet": 20, "is_active": True}
            ]
        }
        
        # Adaptive Heuristic response
        adaptive_response = {
            "action": "all_in",
            "amount": 50,
            "reasoning": "Short stack (50 chips, 5% of starting stack). Strong hand (AK). Push-or-fold situation. All-in is correct."
        }
        
        return EvaluationExample(
            scenario_description="Preflop with A♠ K♥, short stack (50 chips), facing 20 bet",
            game_state=game_state,
            agent_response=adaptive_response,
            agent_type="Adaptive Heuristic",
            expected_action="all_in",
            assessments={
                AssessmentDimension.CORRECTNESS: (1.0, "Valid action"),
                AssessmentDimension.STRATEGIC_QUALITY: (0.95, "All-in with AK short stack is correct push-or-fold strategy"),
                AssessmentDimension.CONSISTENCY: (1.0, "Consistent with adaptive stack-aware strategy"),
                AssessmentDimension.RESPONSE_FORMAT: (1.0, "Valid format"),
                AssessmentDimension.REASONING_QUALITY: (0.95, "Excellent - recognizes short stack situation and applies correct strategy"),
                AssessmentDimension.POSITION_AWARENESS: (0.8, "Position mentioned"),
                AssessmentDimension.POT_ODDS_AWARENESS: (0.7, "Implicitly considered"),
                AssessmentDimension.STACK_MANAGEMENT: (1.0, "Perfect - recognizes short stack and applies push-or-fold")
            },
            overall_score=0.93,
            benchmark_label="short_stack_all_in"
        )
    
    @staticmethod
    def example_7_position_awareness() -> EvaluationExample:
        """Example: Testing position awareness"""
        game_state = {
            "round": "preflop",
            "pot": 30,
            "current_bet": 0,
            "player_chips": 1000,
            "player_position": "button",  # Best position
            "player_cards": ["K♠", "Q♥"],
            "community_cards": [],
            "opponents": [
                {"name": "Player1", "chips": 1000, "current_bet": 0, "is_active": True}
            ]
        }
        
        # Position-aware response
        position_response = {
            "action": "raise",
            "amount": 60,
            "reasoning": "Strong hand (KQ) in excellent position (button). Can raise to steal blinds or build pot."
        }
        
        return EvaluationExample(
            scenario_description="Preflop with K♠ Q♥ on button (best position)",
            game_state=game_state,
            agent_response=position_response,
            agent_type="Smart Agent",
            expected_action="raise",
            assessments={
                AssessmentDimension.CORRECTNESS: (1.0, "Valid action"),
                AssessmentDimension.STRATEGIC_QUALITY: (0.9, "Raising KQ on button is good"),
                AssessmentDimension.CONSISTENCY: (1.0, "Consistent"),
                AssessmentDimension.RESPONSE_FORMAT: (1.0, "Valid format"),
                AssessmentDimension.REASONING_QUALITY: (0.9, "Good reasoning"),
                AssessmentDimension.POSITION_AWARENESS: (1.0, "Perfect - explicitly mentions position and uses it in decision"),
                AssessmentDimension.POT_ODDS_AWARENESS: (0.7, "Not explicitly calculated"),
                AssessmentDimension.STACK_MANAGEMENT: (0.85, "Reasonable bet size")
            },
            overall_score=0.92,
            benchmark_label="position_awareness"
        )
    
    @staticmethod
    def example_8_pot_odds_calculation() -> EvaluationExample:
        """Example: Testing pot odds calculation"""
        game_state = {
            "round": "turn",
            "pot": 300,
            "current_bet": 100,
            "player_chips": 800,
            "player_position": "middle",
            "player_cards": ["6♠", "5♠"],
            "community_cards": ["A♠", "K♠", "7♠", "2♥"],  # Flush draw
            "opponents": [
                {"name": "Player1", "chips": 800, "current_bet": 100, "is_active": True}
            ]
        }
        
        # Pot odds aware response
        pot_odds_response = {
            "action": "call",
            "amount": 100,
            "reasoning": "Flush draw with 9 outs. Pot: 300, Bet: 100, Total pot if call: 500. Pot odds: 500:100 = 5:1. Need 16.7% equity. Have ~20% (9/46). Call is profitable."
        }
        
        return EvaluationExample(
            scenario_description="Turn with flush draw (6♠ 5♠ on A♠ K♠ 7♠ 2♥), facing 100 bet into 300 pot",
            game_state=game_state,
            agent_response=pot_odds_response,
            agent_type="Equity Calculator",
            expected_action="call",
            assessments={
                AssessmentDimension.CORRECTNESS: (1.0, "Valid action"),
                AssessmentDimension.STRATEGIC_QUALITY: (0.95, "Calling with flush draw is correct"),
                AssessmentDimension.CONSISTENCY: (1.0, "Consistent with equity-based strategy"),
                AssessmentDimension.RESPONSE_FORMAT: (1.0, "Valid format"),
                AssessmentDimension.REASONING_QUALITY: (1.0, "Perfect - detailed pot odds calculation"),
                AssessmentDimension.POSITION_AWARENESS: (0.6, "Position not mentioned"),
                AssessmentDimension.POT_ODDS_AWARENESS: (1.0, "Perfect - explicitly calculated pot odds (5:1), equity (~20%), and break-even point (16.7%)"),
                AssessmentDimension.STACK_MANAGEMENT: (0.9, "Call size is reasonable")
            },
            overall_score=0.93,
            benchmark_label="pot_odds_calculation"
        )


def get_ground_truth_test_cases() -> Dict[str, Dict[str, Any]]:
    """
    Ground truth test cases for reliability testing
    Returns: Dict mapping test case ID to expected result
    """
    return {
        "preflop_strong_hand": {
            "expected_action": "raise",
            "min_score": 0.85,
            "description": "Pocket aces should raise preflop"
        },
        "preflop_weak_hand": {
            "expected_action": "fold",
            "min_score": 0.90,
            "description": "7-2 offsuit should fold preflop"
        },
        "flop_strong_hand": {
            "expected_action": "raise",
            "min_score": 0.80,
            "description": "Top pair should bet/raise on flop"
        },
        "flop_draw_pot_odds": {
            "expected_action": "call",
            "min_score": 0.85,
            "description": "Flush draw with good pot odds should call"
        },
        "river_weak_hand": {
            "expected_action": "fold",
            "min_score": 0.80,
            "description": "Weak hand on river should fold to large bet"
        },
        "short_stack_all_in": {
            "expected_action": "all_in",
            "min_score": 0.85,
            "description": "Short stack with strong hand should push all-in"
        },
        "position_awareness": {
            "expected_action": "raise",
            "min_score": 0.85,
            "description": "Strong hand in good position should raise"
        },
        "pot_odds_calculation": {
            "expected_action": "call",
            "min_score": 0.85,
            "description": "Draw with favorable pot odds should call"
        }
    }

