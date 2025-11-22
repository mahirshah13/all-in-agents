"""Different poker playing strategies for white agents"""
import json
import random
from typing import Dict, Any, Optional


class PokerStrategy:
    """Base class for poker strategies"""
    
    def make_decision(self, game_data: Dict[str, Any]) -> Dict[str, Any]:
        """Make a poker decision based on game state"""
        raise NotImplementedError


class TAGBotStrategy(PokerStrategy):
    """Tight-Aggressive Rule-Based Agent - plays conservatively pre-flop, aggressively post-flop when strong"""
    
    def _evaluate_hand_strength(self, player_cards: list, community_cards: list) -> float:
        """Evaluate hand strength with position-adjusted preflop ranges"""
        if not player_cards:
            return 0.0
        
        all_cards = player_cards + community_cards
        
        # Extract ranks
        ranks = []
        for card_str in all_cards:
            rank_char = card_str[0]
            if rank_char == 'A':
                ranks.append(14)
            elif rank_char == 'K':
                ranks.append(13)
            elif rank_char == 'Q':
                ranks.append(12)
            elif rank_char == 'J':
                ranks.append(11)
            else:
                ranks.append(int(rank_char))
        
        from collections import Counter
        rank_counts = Counter(ranks)
        counts = sorted(rank_counts.values(), reverse=True)
        
        strength = 0.0
        if counts[0] >= 2:  # Pair
            strength = 0.5
        if counts[0] >= 3:  # Three of a kind
            strength = 0.75
        if counts[0] >= 4:  # Four of a kind
            strength = 0.95
        if len(counts) >= 2 and counts[0] >= 2 and counts[1] >= 2:  # Two pair
            strength = 0.65
        if counts[0] >= 3 and counts[1] >= 2:  # Full house
            strength = 0.9
        
        max_rank = max(ranks)
        strength += (max_rank / 14.0) * 0.15
        
        return min(strength, 1.0)
    
    def make_decision(self, game_data: Dict[str, Any]) -> Dict[str, Any]:
        player_cards = game_data.get("player_cards", [])
        community_cards = game_data.get("community_cards", [])
        current_bet = game_data.get("current_bet", 0)
        player_chips = game_data.get("player_chips", 1000)
        pot_size = game_data.get("pot_size", 0)
        round_name = game_data.get("game_state", {}).get("round", "preflop")
        player_position = game_data.get("player_position", 0)
        
        hand_strength = self._evaluate_hand_strength(player_cards, community_cards)
        is_preflop = round_name == "preflop"
        
        # Preflop: Tight ranges (position-adjusted)
        if is_preflop:
            # Position adjustment: later position = wider range
            position_bonus = (4 - player_position) * 0.1  # Later position = more aggressive
            adjusted_strength = hand_strength + position_bonus
            
            # Tight preflop: only play strong hands
            if adjusted_strength < 0.5:
                return {
                    "action": "fold",
                    "amount": 0,
                    "confidence": 0.8,
                    "reasoning": "Tight preflop: folding weak hand"
                }
            elif adjusted_strength < 0.7:
                if current_bet > pot_size * 0.25:
                    return {
                        "action": "fold",
                        "amount": 0,
                        "confidence": 0.7,
                        "reasoning": "Moderate hand, bet too high preflop"
                    }
                else:
                    return {
                        "action": "call",
                        "amount": min(current_bet, player_chips),
                        "confidence": 0.6,
                        "reasoning": "Tight preflop: calling with moderate hand"
                    }
            else:  # Strong preflop hand
                raise_amount = int(current_bet * 2) if current_bet > 0 else 80
                return {
                    "action": "raise",
                    "amount": min(raise_amount, player_chips),
                    "confidence": 0.85,
                    "reasoning": "Tight preflop: raising with strong hand"
                }
        else:
            # Post-flop: Aggressive when strong (C-bet with equity threshold)
            if hand_strength < 0.4:
                # Weak post-flop - fold unless pot odds are good
                pot_odds = current_bet / (pot_size + current_bet) if (pot_size + current_bet) > 0 else 0
                if pot_odds < 0.2:
                    return {
                        "action": "call",
                        "amount": min(current_bet, player_chips),
                        "confidence": 0.5,
                        "reasoning": "Post-flop: calling with pot odds"
                    }
                else:
                    return {
                        "action": "fold",
                        "amount": 0,
                        "confidence": 0.7,
                        "reasoning": "Post-flop: folding weak hand"
                    }
            elif hand_strength < 0.7:
                # Moderate strength - C-bet or value bet
                raise_amount = int(current_bet * 1.8) if current_bet > 0 else 100
                return {
                    "action": "raise",
                    "amount": min(raise_amount, player_chips),
                    "confidence": 0.75,
                    "reasoning": "Post-flop: C-betting with equity"
                }
            else:  # Very strong post-flop
                raise_amount = int(current_bet * 2.5) if current_bet > 0 else 150
                return {
                    "action": "raise",
                    "amount": min(raise_amount, player_chips),
                    "confidence": 0.9,
                    "reasoning": "Post-flop: aggressive value bet with strong hand"
                }


class MonteCarloStrategy(PokerStrategy):
    """Monte Carlo Simulation Agent - simulates random outcomes to evaluate EV"""
    
    def _simulate_equity(self, player_cards: list, community_cards: list, num_simulations: int = 1000) -> float:
        """Monte Carlo simulation to estimate hand equity"""
        if not player_cards:
            return 0.0
        
        # Simplified equity calculation
        # In full implementation, would simulate random opponent hands and runouts
        all_cards = player_cards + community_cards
        
        ranks = []
        for card_str in all_cards:
            rank_char = card_str[0]
            if rank_char == 'A':
                ranks.append(14)
            elif rank_char == 'K':
                ranks.append(13)
            elif rank_char == 'Q':
                ranks.append(12)
            elif rank_char == 'J':
                ranks.append(11)
            else:
                ranks.append(int(rank_char))
        
        from collections import Counter
        rank_counts = Counter(ranks)
        counts = sorted(rank_counts.values(), reverse=True)
        
        # Estimate equity based on current hand strength
        equity = 0.0
        if counts[0] >= 2:  # Pair
            equity = 0.55  # Slight favorite
        if counts[0] >= 3:  # Three of a kind
            equity = 0.75
        if counts[0] >= 4:  # Four of a kind
            equity = 0.95
        if len(counts) >= 2 and counts[0] >= 2 and counts[1] >= 2:  # Two pair
            equity = 0.65
        if counts[0] >= 3 and counts[1] >= 2:  # Full house
            equity = 0.9
        
        # Add some randomness to simulate MC variance
        equity += random.uniform(-0.1, 0.1)
        return max(0.0, min(1.0, equity))
    
    def _calculate_ev(self, equity: float, pot_size: int, bet_amount: int) -> float:
        """Calculate expected value"""
        # EV = (equity * pot_size) - (1 - equity) * bet_amount
        win_pot = pot_size + bet_amount
        ev = (equity * win_pot) - ((1 - equity) * bet_amount)
        return ev
    
    def make_decision(self, game_data: Dict[str, Any]) -> Dict[str, Any]:
        player_cards = game_data.get("player_cards", [])
        community_cards = game_data.get("community_cards", [])
        current_bet = game_data.get("current_bet", 0)
        player_chips = game_data.get("player_chips", 1000)
        pot_size = game_data.get("pot_size", 0)
        
        # Monte Carlo simulation
        equity = self._simulate_equity(player_cards, community_cards, num_simulations=1000)
        
        # Evaluate EV for each action
        fold_ev = 0.0  # EV of folding is 0
        
        call_ev = self._calculate_ev(equity, pot_size, current_bet)
        
        # For raise, estimate opponent fold probability (simplified)
        opponent_fold_prob = 0.3  # Assume 30% fold to raise
        raise_amount = int(current_bet * 2) if current_bet > 0 else 100
        raise_ev = (opponent_fold_prob * pot_size) + ((1 - opponent_fold_prob) * self._calculate_ev(equity, pot_size + raise_amount, raise_amount))
        
        # Decision = argmax(EV)
        if raise_ev > call_ev and raise_ev > fold_ev and raise_amount <= player_chips:
            return {
                "action": "raise",
                "amount": min(raise_amount, player_chips),
                "confidence": min(0.9, 0.5 + abs(raise_ev) / 100),
                "reasoning": f"Monte Carlo: Raise EV={raise_ev:.1f}, Equity={equity:.2%}"
            }
        elif call_ev > fold_ev:
            return {
                "action": "call",
                "amount": min(current_bet, player_chips),
                "confidence": min(0.8, 0.5 + abs(call_ev) / 100),
                "reasoning": f"Monte Carlo: Call EV={call_ev:.1f}, Equity={equity:.2%}"
            }
        else:
            return {
                "action": "fold",
                "amount": 0,
                "confidence": 0.7,
                "reasoning": f"Monte Carlo: Fold (negative EV), Equity={equity:.2%}"
            }


class ManiacStrategy(PokerStrategy):
    """Ultra-aggressive LAG player - raises frequently, high bluff frequency"""
    
    def _evaluate_hand_strength(self, player_cards: list) -> float:
        """Simple hand strength (maniac doesn't care much)"""
        if not player_cards:
            return 0.3  # Maniac is optimistic
        
        ranks = []
        for card_str in player_cards:
            rank_char = card_str[0]
            if rank_char == 'A':
                ranks.append(14)
            elif rank_char == 'K':
                ranks.append(13)
            elif rank_char == 'Q':
                ranks.append(12)
            elif rank_char == 'J':
                ranks.append(11)
            else:
                ranks.append(int(rank_char))
        
        max_rank = max(ranks)
        is_pair = len(set(ranks)) == 1
        
        strength = (max_rank / 14.0) * 0.3
        if is_pair:
            strength += 0.2
        if max_rank >= 10:
            strength += 0.1
        
        return min(strength + 0.2, 1.0)  # Maniac bias: always thinks hand is better
    
    def make_decision(self, game_data: Dict[str, Any]) -> Dict[str, Any]:
        player_cards = game_data.get("player_cards", [])
        current_bet = game_data.get("current_bet", 0)
        player_chips = game_data.get("player_chips", 1000)
        pot_size = game_data.get("pot_size", 0)
        
        hand_strength = self._evaluate_hand_strength(player_cards)
        
        # Maniac: 70% chance to raise regardless of hand
        if random.random() < 0.7:
            # Ultra-aggressive raise
            raise_amount = int(current_bet * random.uniform(2.5, 4.0)) if current_bet > 0 else random.randint(100, 200)
            return {
                "action": "raise",
                "amount": min(raise_amount, player_chips),
                "confidence": 0.6,  # Maniac is confident but not smart
                "reasoning": "Maniac: Aggressive raise to put pressure"
            }
        elif random.random() < 0.8:  # 80% of remaining cases = call
            return {
                "action": "call",
                "amount": min(current_bet, player_chips),
                "confidence": 0.5,
                "reasoning": "Maniac: Calling to see more cards"
            }
        else:  # Rare fold
            return {
                "action": "fold",
                "amount": 0,
                "confidence": 0.3,
                "reasoning": "Maniac: Rare fold (very weak hand)"
            }


class ConservativeStrategy(PokerStrategy):
    """Conservative strategy - folds often, small bets"""
    
    def _evaluate_hand_strength(self, player_cards: list) -> float:
        """Simple hand strength evaluation"""
        if not player_cards:
            return 0.0
        
        # Extract ranks
        ranks = []
        for card_str in player_cards:
            rank_char = card_str[0]
            if rank_char == 'A':
                ranks.append(14)
            elif rank_char == 'K':
                ranks.append(13)
            elif rank_char == 'Q':
                ranks.append(12)
            elif rank_char == 'J':
                ranks.append(11)
            else:
                ranks.append(int(rank_char))
        
        max_rank = max(ranks)
        is_pair = len(set(ranks)) == 1
        
        # Simple strength calculation
        strength = (max_rank / 14.0) * 0.5
        if is_pair:
            strength += 0.3
        if max_rank >= 10:  # Face cards
            strength += 0.2
        
        return min(strength, 1.0)
    
    def make_decision(self, game_data: Dict[str, Any]) -> Dict[str, Any]:
        player_cards = game_data.get("player_cards", [])
        current_bet = game_data.get("current_bet", 0)
        player_chips = game_data.get("player_chips", 1000)
        pot_size = game_data.get("pot_size", 0)
        
        hand_strength = self._evaluate_hand_strength(player_cards)
        
        # Conservative: only play strong hands
        if hand_strength < 0.4:
            return {
                "action": "fold",
                "amount": 0,
                "confidence": 0.8,
                "reasoning": "Weak hand, folding conservatively"
            }
        elif hand_strength < 0.6:
            if current_bet > pot_size * 0.3:  # Too expensive
                return {
                    "action": "fold",
                    "amount": 0,
                    "confidence": 0.7,
                    "reasoning": "Moderate hand, but bet too high"
                }
            else:
                return {
                    "action": "call",
                    "amount": min(current_bet, player_chips),
                    "confidence": 0.6,
                    "reasoning": "Moderate hand, calling"
                }
        else:  # Strong hand
            raise_amount = int(current_bet * 1.5) if current_bet > 0 else 50
            return {
                "action": "raise",
                "amount": min(raise_amount, player_chips),
                "confidence": 0.8,
                "reasoning": "Strong hand, raising conservatively"
            }


class AggressiveStrategy(PokerStrategy):
    """Aggressive strategy - raises often, larger bets"""
    
    def _evaluate_hand_strength(self, player_cards: list) -> float:
        """Simple hand strength evaluation"""
        if not player_cards:
            return 0.0
        
        ranks = []
        for card_str in player_cards:
            rank_char = card_str[0]
            if rank_char == 'A':
                ranks.append(14)
            elif rank_char == 'K':
                ranks.append(13)
            elif rank_char == 'Q':
                ranks.append(12)
            elif rank_char == 'J':
                ranks.append(11)
            else:
                ranks.append(int(rank_char))
        
        max_rank = max(ranks)
        is_pair = len(set(ranks)) == 1
        
        strength = (max_rank / 14.0) * 0.5
        if is_pair:
            strength += 0.3
        if max_rank >= 10:
            strength += 0.2
        
        return min(strength, 1.0)
    
    def make_decision(self, game_data: Dict[str, Any]) -> Dict[str, Any]:
        player_cards = game_data.get("player_cards", [])
        current_bet = game_data.get("current_bet", 0)
        player_chips = game_data.get("player_chips", 1000)
        pot_size = game_data.get("pot_size", 0)
        
        hand_strength = self._evaluate_hand_strength(player_cards)
        
        # Aggressive: bet/raise often, even with moderate hands
        if hand_strength < 0.2:
            # Very weak - might still call if bet is small
            if current_bet < pot_size * 0.2:
                return {
                    "action": "call",
                    "amount": min(current_bet, player_chips),
                    "confidence": 0.4,
                    "reasoning": "Weak hand but small bet, calling aggressively"
                }
            else:
                return {
                    "action": "fold",
                    "amount": 0,
                    "confidence": 0.5,
                    "reasoning": "Very weak hand, folding"
                }
        elif hand_strength < 0.5:
            # Moderate - raise to put pressure
            raise_amount = int(current_bet * 2.5) if current_bet > 0 else 100
            return {
                "action": "raise",
                "amount": min(raise_amount, player_chips),
                "confidence": 0.6,
                "reasoning": "Moderate hand, raising aggressively"
            }
        else:  # Strong hand
            raise_amount = int(current_bet * 3) if current_bet > 0 else 150
            return {
                "action": "raise",
                "amount": min(raise_amount, player_chips),
                "confidence": 0.9,
                "reasoning": "Strong hand, raising aggressively"
            }


class SmartStrategy(PokerStrategy):
    """Smart strategy - considers pot odds, position, and hand strength"""
    
    def _evaluate_hand_strength(self, player_cards: list, community_cards: list) -> float:
        """Evaluate hand strength considering community cards"""
        if not player_cards:
            return 0.0
        
        all_cards = player_cards + community_cards
        
        # Extract ranks
        ranks = []
        for card_str in all_cards:
            rank_char = card_str[0]
            if rank_char == 'A':
                ranks.append(14)
            elif rank_char == 'K':
                ranks.append(13)
            elif rank_char == 'Q':
                ranks.append(12)
            elif rank_char == 'J':
                ranks.append(11)
            else:
                ranks.append(int(rank_char))
        
        # Count pairs, trips, etc.
        from collections import Counter
        rank_counts = Counter(ranks)
        counts = sorted(rank_counts.values(), reverse=True)
        
        # Simple strength calculation
        strength = 0.0
        if counts[0] >= 2:  # At least a pair
            strength = 0.4
        if counts[0] >= 3:  # Three of a kind
            strength = 0.7
        if counts[0] >= 4:  # Four of a kind
            strength = 0.95
        if len(counts) >= 2 and counts[0] >= 2 and counts[1] >= 2:  # Two pair
            strength = 0.6
        if counts[0] >= 3 and counts[1] >= 2:  # Full house
            strength = 0.9
        
        # High card bonus
        max_rank = max(ranks)
        strength += (max_rank / 14.0) * 0.2
        
        return min(strength, 1.0)
    
    def _calculate_pot_odds(self, bet_amount: int, pot_size: int) -> float:
        """Calculate pot odds"""
        if pot_size == 0:
            return 0.0
        return bet_amount / (pot_size + bet_amount)
    
    def make_decision(self, game_data: Dict[str, Any]) -> Dict[str, Any]:
        player_cards = game_data.get("player_cards", [])
        community_cards = game_data.get("community_cards", [])
        current_bet = game_data.get("current_bet", 0)
        player_chips = game_data.get("player_chips", 1000)
        pot_size = game_data.get("pot_size", 0)
        player_position = game_data.get("player_position", 0)
        
        hand_strength = self._evaluate_hand_strength(player_cards, community_cards)
        pot_odds = self._calculate_pot_odds(current_bet, pot_size) if current_bet > 0 else 0.0
        
        # Position advantage (later position = better)
        position_factor = 1.0 - (player_position * 0.1)
        position_factor = max(0.5, position_factor)
        
        # Adjusted strength considering position
        adjusted_strength = hand_strength * position_factor
        
        # Decision logic
        if adjusted_strength < 0.3:
            # Weak hand - fold unless pot odds are very good
            if pot_odds < 0.15 and current_bet < pot_size * 0.2:
                return {
                    "action": "call",
                    "amount": min(current_bet, player_chips),
                    "confidence": 0.5,
                    "reasoning": "Weak hand but good pot odds"
                }
            else:
                return {
                    "action": "fold",
                    "amount": 0,
                    "confidence": 0.7,
                    "reasoning": "Weak hand, poor pot odds"
                }
        elif adjusted_strength < 0.6:
            # Moderate hand - call or small raise
            if pot_odds < 0.3:
                raise_amount = int(current_bet * 1.5) if current_bet > 0 else 60
                return {
                    "action": "raise",
                    "amount": min(raise_amount, player_chips),
                    "confidence": 0.65,
                    "reasoning": "Moderate hand, good position/pot odds"
                }
            else:
                return {
                    "action": "call",
                    "amount": min(current_bet, player_chips),
                    "confidence": 0.6,
                    "reasoning": "Moderate hand, calling"
                }
        else:  # Strong hand
            raise_amount = int(current_bet * 2) if current_bet > 0 else 100
            return {
                "action": "raise",
                "amount": min(raise_amount, player_chips),
                "confidence": 0.85,
                "reasoning": "Strong hand, raising for value"
            }


class EquityCalculatorStrategy(PokerStrategy):
    """Equity Calculator Agent - calculates hand equity vs estimated opponent range"""
    
    def _calculate_preflop_equity(self, player_cards: list) -> float:
        """Calculate preflop equity using lookup table approximation"""
        if not player_cards or len(player_cards) < 2:
            return 0.0
        
        ranks = []
        for card_str in player_cards:
            rank_char = card_str[0]
            if rank_char == 'A':
                ranks.append(14)
            elif rank_char == 'K':
                ranks.append(13)
            elif rank_char == 'Q':
                ranks.append(12)
            elif rank_char == 'J':
                ranks.append(11)
            else:
                ranks.append(int(rank_char))
        
        # Simplified preflop equity
        is_pair = len(set(ranks)) == 1
        max_rank = max(ranks)
        min_rank = min(ranks)
        
        if is_pair:
            # Pocket pairs: stronger pairs = higher equity
            equity = 0.5 + (max_rank / 14.0) * 0.3
        elif max_rank >= 12:  # Ace or King high
            equity = 0.45 + (max_rank / 14.0) * 0.2
        elif max_rank >= 10:  # Face cards
            equity = 0.35 + (max_rank / 14.0) * 0.15
        else:
            equity = 0.25 + (max_rank / 14.0) * 0.1
        
        return min(equity, 0.95)
    
    def _calculate_postflop_equity(self, player_cards: list, community_cards: list) -> float:
        """Calculate postflop equity"""
        all_cards = player_cards + community_cards
        if len(all_cards) < 5:
            return self._calculate_preflop_equity(player_cards)
        
        from collections import Counter
        ranks = []
        for card_str in all_cards:
            rank_char = card_str[0]
            if rank_char == 'A':
                ranks.append(14)
            elif rank_char == 'K':
                ranks.append(13)
            elif rank_char == 'Q':
                ranks.append(12)
            elif rank_char == 'J':
                ranks.append(11)
            else:
                ranks.append(int(rank_char))
        
        rank_counts = Counter(ranks)
        counts = sorted(rank_counts.values(), reverse=True)
        
        equity = 0.0
        if counts[0] >= 4:
            equity = 0.95
        elif counts[0] >= 3 and counts[1] >= 2:
            equity = 0.90
        elif counts[0] >= 3:
            equity = 0.75
        elif counts[0] >= 2 and counts[1] >= 2:
            equity = 0.65
        elif counts[0] >= 2:
            equity = 0.50
        else:
            equity = 0.30
        
        return equity
    
    def make_decision(self, game_data: Dict[str, Any]) -> Dict[str, Any]:
        player_cards = game_data.get("player_cards", [])
        community_cards = game_data.get("community_cards", [])
        current_bet = game_data.get("current_bet", 0)
        player_chips = game_data.get("player_chips", 1000)
        pot_size = game_data.get("pot_size", 0)
        round_name = game_data.get("game_state", {}).get("round", "preflop")
        
        # Calculate equity
        if round_name == "preflop":
            equity = self._calculate_preflop_equity(player_cards)
        else:
            equity = self._calculate_postflop_equity(player_cards, community_cards)
        
        # Calculate pot odds
        pot_odds = current_bet / (pot_size + current_bet) if (pot_size + current_bet) > 0 else 0
        
        # Decision based on equity vs pot odds
        if equity < pot_odds * 0.8:  # Not enough equity
            return {
                "action": "fold",
                "amount": 0,
                "confidence": 0.8,
                "reasoning": f"Equity ({equity:.1%}) < Pot Odds ({pot_odds:.1%}), folding"
            }
        elif equity > pot_odds * 1.2:  # Good equity, raise for value
            raise_amount = int(current_bet * 2) if current_bet > 0 else 100
            return {
                "action": "raise",
                "amount": min(raise_amount, player_chips),
                "confidence": 0.85,
                "reasoning": f"Strong equity ({equity:.1%}), raising for value"
            }
        else:  # Call
            return {
                "action": "call",
                "amount": min(current_bet, player_chips),
                "confidence": 0.7,
                "reasoning": f"Equity ({equity:.1%}) justifies call"
            }


class AdaptiveHeuristicStrategy(PokerStrategy):
    """Adaptive Heuristic Agent - adjusts strategy based on opponent patterns and stack size"""
    
    def __init__(self):
        self.opponent_aggression = 0.5  # Track opponent aggression
        self.opponent_fold_rate = 0.5   # Track opponent fold rate
        self.adjustment_factor = 1.0    # Strategy adjustment
    
    def _evaluate_hand_strength(self, player_cards: list, community_cards: list) -> float:
        """Evaluate hand strength"""
        all_cards = player_cards + community_cards
        if not player_cards:
            return 0.0
        
        from collections import Counter
        ranks = []
        for card_str in all_cards:
            rank_char = card_str[0]
            if rank_char == 'A':
                ranks.append(14)
            elif rank_char == 'K':
                ranks.append(13)
            elif rank_char == 'Q':
                ranks.append(12)
            elif rank_char == 'J':
                ranks.append(11)
            else:
                ranks.append(int(rank_char))
        
        rank_counts = Counter(ranks)
        counts = sorted(rank_counts.values(), reverse=True)
        
        strength = 0.0
        if counts[0] >= 2:
            strength = 0.4
        if counts[0] >= 3:
            strength = 0.7
        if counts[0] >= 4:
            strength = 0.95
        if len(counts) >= 2 and counts[0] >= 2 and counts[1] >= 2:
            strength = 0.6
        if counts[0] >= 3 and counts[1] >= 2:
            strength = 0.9
        
        return min(strength, 1.0)
    
    def make_decision(self, game_data: Dict[str, Any]) -> Dict[str, Any]:
        player_cards = game_data.get("player_cards", [])
        community_cards = game_data.get("community_cards", [])
        current_bet = game_data.get("current_bet", 0)
        player_chips = game_data.get("player_chips", 1000)
        pot_size = game_data.get("pot_size", 0)
        starting_chips = game_data.get("starting_chips", 1000)
        
        # Adjust strategy based on stack size
        stack_ratio = player_chips / starting_chips if starting_chips > 0 else 1.0
        
        # If short-stacked, become more aggressive
        if stack_ratio < 0.5:
            self.adjustment_factor = 1.5  # More aggressive
        elif stack_ratio > 1.5:
            self.adjustment_factor = 0.8  # More conservative with big stack
        else:
            self.adjustment_factor = 1.0
        
        hand_strength = self._evaluate_hand_strength(player_cards, community_cards)
        
        # Adjust based on pot size relative to stack
        pot_ratio = pot_size / player_chips if player_chips > 0 else 0
        
        # Decision logic with adaptations
        if hand_strength < 0.3:
            # Weak hand
            if pot_ratio > 0.3 and stack_ratio < 0.7:  # Big pot, short stack
                return {
                    "action": "fold",
                    "amount": 0,
                    "confidence": 0.7,
                    "reasoning": "Weak hand, preserving short stack"
                }
            else:
                return {
                    "action": "fold",
                    "amount": 0,
                    "confidence": 0.8,
                    "reasoning": "Weak hand, folding"
                }
        elif hand_strength < 0.6:
            # Moderate hand
            if stack_ratio < 0.5:  # Short stack - push or fold
                if hand_strength > 0.45:
                    return {
                        "action": "raise",
                        "amount": min(player_chips, current_bet * 3),
                        "confidence": 0.6,
                        "reasoning": "Short stack, pushing with moderate hand"
                    }
                else:
                    return {
                        "action": "fold",
                        "amount": 0,
                        "confidence": 0.6,
                        "reasoning": "Short stack, folding moderate hand"
                    }
            else:
                return {
                    "action": "call",
                    "amount": min(current_bet, player_chips),
                    "confidence": 0.65,
                    "reasoning": "Moderate hand, calling"
                }
        else:  # Strong hand
            raise_amount = int(current_bet * (2 * self.adjustment_factor)) if current_bet > 0 else int(100 * self.adjustment_factor)
            return {
                "action": "raise",
                "amount": min(raise_amount, player_chips),
                "confidence": 0.9,
                "reasoning": f"Strong hand, raising (stack ratio: {stack_ratio:.2f})"
            }


# Strategy factory
STRATEGY_MAP = {
    "tagbot": TAGBotStrategy,
    "montecarlo": MonteCarloStrategy,
    "maniac": ManiacStrategy,
    "conservative": ConservativeStrategy,
    "aggressive": AggressiveStrategy,
    "smart": SmartStrategy,
    "equity": EquityCalculatorStrategy,
    "adaptive": AdaptiveHeuristicStrategy,
    "openai": None  # OpenAI uses LLM, handled separately
}

def get_strategy(agent_type: str) -> Optional[PokerStrategy]:
    """Get strategy instance by type"""
    strategy_class = STRATEGY_MAP.get(agent_type.lower())
    if strategy_class:
        return strategy_class()
    return None

