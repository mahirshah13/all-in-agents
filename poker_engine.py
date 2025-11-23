"""
Poker Game Engine - Handles game logic, hand evaluation, and game state management
"""
import random
from enum import Enum
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass
from collections import Counter


class Suit(Enum):
    HEARTS = "hearts"
    DIAMONDS = "diamonds"
    CLUBS = "clubs"
    SPADES = "spades"


class Rank(Enum):
    TWO = 2
    THREE = 3
    FOUR = 4
    FIVE = 5
    SIX = 6
    SEVEN = 7
    EIGHT = 8
    NINE = 9
    TEN = 10
    JACK = 11
    QUEEN = 12
    KING = 13
    ACE = 14


class HandRank(Enum):
    HIGH_CARD = 1
    PAIR = 2
    TWO_PAIR = 3
    THREE_OF_A_KIND = 4
    STRAIGHT = 5
    FLUSH = 6
    FULL_HOUSE = 7
    FOUR_OF_A_KIND = 8
    STRAIGHT_FLUSH = 9
    ROYAL_FLUSH = 10


class Action(Enum):
    FOLD = "fold"
    CALL = "call"
    RAISE = "raise"
    CHECK = "check"
    ALL_IN = "all_in"


@dataclass
class Card:
    rank: Rank
    suit: Suit
    
    def __str__(self):
        rank_str = {11: 'J', 12: 'Q', 13: 'K', 14: 'A'}.get(self.rank.value, str(self.rank.value))
        suit_symbol = {'hearts': '♥', 'diamonds': '♦', 'clubs': '♣', 'spades': '♠'}
        return f"{rank_str}{suit_symbol[self.suit.value]}"


@dataclass
class Player:
    id: str
    name: str
    chips: int
    cards: List[Card]
    current_bet: int = 0
    total_bet: int = 0
    is_active: bool = True
    is_all_in: bool = False
    position: int = 0
    has_acted_this_round: bool = False  # Track if player has acted in current betting round
    
    def __str__(self):
        return f"{self.name} (Chips: {self.chips}, Bet: {self.current_bet})"


@dataclass
class GameState:
    players: List[Player]
    community_cards: List[Card]
    pot: int
    current_bet: int
    dealer_position: int
    current_player: int
    round: str  # "preflop", "flop", "turn", "river", "showdown"
    deck: List[Card]
    small_blind: int
    big_blind: int
    hand_number: int
    last_raise_amount: int = 0  # Track the last raise delta for minimum raise calculation
    minimum_raise: int = 0  # Minimum raise amount (previous raise delta)


class PokerEngine:
    def __init__(self, small_blind: int = 10, big_blind: int = 20):
        self.small_blind = small_blind
        self.big_blind = big_blind
        self.game_state: Optional[GameState] = None
        self.dealer_position: int = 0  # Track dealer position across hands
        self.hand_number: int = 0  # Track hand number across games
        
    def create_deck(self) -> List[Card]:
        """Create a standard 52-card deck"""
        deck = []
        for suit in Suit:
            for rank in Rank:
                deck.append(Card(rank, suit))
        return deck
    
    def shuffle_deck(self, deck: List[Card]) -> List[Card]:
        """Shuffle the deck"""
        return random.sample(deck, len(deck))
    
    def deal_cards(self, deck: List[Card], num_cards: int) -> Tuple[List[Card], List[Card]]:
        """Deal cards from deck"""
        dealt = deck[:num_cards]
        remaining = deck[num_cards:]
        return dealt, remaining
    
    def start_new_hand(self, player_ids: List[str], player_names: List[str], 
                      starting_chips: int = 1000, preserve_chips: bool = False) -> GameState:
        """Start a new poker hand with rotating blinds"""
        # Increment hand number
        self.hand_number += 1
        
        # Create players (preserve chips if continuing a game, otherwise start fresh)
        players = []
        player_chips = {}
        if preserve_chips and self.game_state is not None:
            # Preserve chip counts from previous hand
            for player in self.game_state.players:
                player_chips[player.id] = player.chips
        
        for i, (pid, name) in enumerate(zip(player_ids, player_names)):
            chips = player_chips.get(pid, starting_chips) if preserve_chips else starting_chips
            players.append(Player(
                id=pid,
                name=name,
                chips=chips,
                cards=[],
                position=i
            ))
        
        # Rotate dealer position clockwise after each hand
        # For first hand (hand_number == 1), dealer starts at 0
        # After that, rotate clockwise
        if self.hand_number > 1 and len(players) > 0:
            self.dealer_position = (self.dealer_position + 1) % len(players)
        elif self.hand_number == 1:
            # First hand: dealer starts at position 0
            self.dealer_position = 0
        
        # Create and shuffle deck
        deck = self.shuffle_deck(self.create_deck())
        
        # Set up game state
        self.game_state = GameState(
            players=players,
            community_cards=[],
            pot=0,
            current_bet=0,
            dealer_position=self.dealer_position,
            current_player=0,  # Will be set correctly in _post_blinds
            round="preflop",
            deck=deck,
            small_blind=self.small_blind,
            big_blind=self.big_blind,
            hand_number=self.hand_number,
            last_raise_amount=0,
            minimum_raise=self.big_blind - self.small_blind  # Initial minimum raise is BB - SB
        )
        
        # Deal hole cards first
        self._deal_hole_cards()
        
        # Post blinds (this will set current_player correctly)
        self._post_blinds()
        
        return self.game_state
    
    def _post_blinds(self):
        """Post small and big blinds"""
        sb_pos = (self.game_state.dealer_position + 1) % len(self.game_state.players)
        bb_pos = (self.game_state.dealer_position + 2) % len(self.game_state.players)
        
        # Small blind
        sb_amount = min(self.small_blind, self.game_state.players[sb_pos].chips)
        self.game_state.players[sb_pos].chips -= sb_amount
        self.game_state.players[sb_pos].current_bet = sb_amount
        self.game_state.players[sb_pos].total_bet = sb_amount
        self.game_state.pot += sb_amount
        if self.game_state.players[sb_pos].chips == 0:
            self.game_state.players[sb_pos].is_all_in = True
        
        # Big blind
        bb_amount = min(self.big_blind, self.game_state.players[bb_pos].chips)
        self.game_state.players[bb_pos].chips -= bb_amount
        self.game_state.players[bb_pos].current_bet = bb_amount
        self.game_state.players[bb_pos].total_bet = bb_amount
        self.game_state.pot += bb_amount
        if self.game_state.players[bb_pos].chips == 0:
            self.game_state.players[bb_pos].is_all_in = True
        
        self.game_state.current_bet = bb_amount
        self.game_state.last_raise_amount = bb_amount - sb_amount  # BB - SB is the initial raise
        self.game_state.minimum_raise = self.game_state.last_raise_amount
        
        # Preflop action starts with player left of BB (UTG)
        # If only 2 players, this wraps around to SB
        utg_pos = (bb_pos + 1) % len(self.game_state.players)
        # Skip players with no chips
        active_indices = [i for i, p in enumerate(self.game_state.players) if p.is_active and p.chips > 0]
        if utg_pos in active_indices:
            self.game_state.current_player = utg_pos
        elif active_indices:
            self.game_state.current_player = active_indices[0]
    
    def _deal_hole_cards(self):
        """Deal 2 cards to each player"""
        for _ in range(2):
            for player in self.game_state.players:
                if player.is_active and player.chips > 0:
                    card, self.game_state.deck = self.deal_cards(self.game_state.deck, 1)
                    player.cards.extend(card)
    
    def get_hand_rank(self, cards: List[Card]) -> Tuple[HandRank, List[int]]:
        """Evaluate hand rank and return (rank, tiebreaker_values)"""
        if len(cards) < 5:
            return HandRank.HIGH_CARD, [max(card.rank.value for card in cards)]
        
        # Get all possible 5-card combinations
        from itertools import combinations
        best_rank = HandRank.HIGH_CARD
        best_tiebreaker = []
        
        for combo in combinations(cards, 5):
            rank, tiebreaker = self._evaluate_hand(list(combo))
            if rank.value > best_rank.value or (rank.value == best_rank.value and tiebreaker > best_tiebreaker):
                best_rank = rank
                best_tiebreaker = tiebreaker
        
        return best_rank, best_tiebreaker
    
    def _evaluate_hand(self, cards: List[Card]) -> Tuple[HandRank, List[int]]:
        """Evaluate a 5-card hand"""
        ranks = [card.rank.value for card in cards]
        suits = [card.suit for card in cards]
        
        rank_counts = Counter(ranks)
        suit_counts = Counter(suits)
        
        # Sort ranks by frequency then by value
        sorted_ranks = sorted(rank_counts.items(), key=lambda x: (x[1], x[0]), reverse=True)
        values = [rank for rank, count in sorted_ranks]
        counts = [count for rank, count in sorted_ranks]
        
        is_flush = len(suit_counts) == 1
        is_straight = self._is_straight(ranks)
        
        if is_straight and is_flush:
            if min(ranks) == 10:  # 10, J, Q, K, A
                return HandRank.ROYAL_FLUSH, []
            else:
                return HandRank.STRAIGHT_FLUSH, [max(ranks)]
        elif counts == [4, 1]:
            return HandRank.FOUR_OF_A_KIND, values
        elif counts == [3, 2]:
            return HandRank.FULL_HOUSE, values
        elif is_flush:
            return HandRank.FLUSH, sorted(ranks, reverse=True)
        elif is_straight:
            return HandRank.STRAIGHT, [max(ranks)]
        elif counts == [3, 1, 1]:
            return HandRank.THREE_OF_A_KIND, values
        elif counts == [2, 2, 1]:
            return HandRank.TWO_PAIR, values
        elif counts == [2, 1, 1, 1]:
            return HandRank.PAIR, values
        else:
            return HandRank.HIGH_CARD, sorted(ranks, reverse=True)
    
    def _is_straight(self, ranks: List[int]) -> bool:
        """Check if ranks form a straight"""
        sorted_ranks = sorted(set(ranks))
        if len(sorted_ranks) != 5:
            return False
        
        # Check for regular straight
        for i in range(4):
            if sorted_ranks[i+1] - sorted_ranks[i] != 1:
                break
        else:
            return True
        
        # Check for A-2-3-4-5 straight
        if sorted_ranks == [2, 3, 4, 5, 14]:
            return True
        
        return False
    
    def process_action(self, player_id: str, action: Action, amount: int = 0) -> Dict[str, Any]:
        """Process a player's action with proper poker rules enforcement"""
        if not self.game_state:
            return {"error": "No active game"}
        
        player = next((p for p in self.game_state.players if p.id == player_id), None)
        if not player:
            return {"error": "Player not found"}
        
        # Validate it's player's turn
        player_index = self.game_state.players.index(player)
        if player_index != self.game_state.current_player:
            return {"error": "Not your turn"}
        
        if not player.is_active:
            return {"error": "Player has already folded"}
        
        if player.is_all_in:
            return {"error": "Player is all-in, cannot act"}
        
        if player.chips <= 0:
            return {"error": "Player has no chips"}
        
        result = {"success": True, "action": action.value, "amount": amount}
        
        # Calculate amount needed to call
        amount_to_call = self.game_state.current_bet - player.current_bet
        
        if action == Action.FOLD:
            player.is_active = False
            player.has_acted_this_round = True
            result["message"] = f"{player.name} folded"
        elif action == Action.CALL:
            # If player can't afford full call, they go all-in automatically
            if player.chips < amount_to_call:
                # Auto all-in
                call_amount = player.chips
                player.chips = 0
                player.current_bet += call_amount
                player.total_bet += call_amount
                player.is_all_in = True
                self.game_state.pot += call_amount
                result["message"] = f"{player.name} called all-in with {call_amount}"
            else:
                call_amount = amount_to_call
                player.chips -= call_amount
                player.current_bet += call_amount
                player.total_bet += call_amount
                self.game_state.pot += call_amount
                result["message"] = f"{player.name} called {call_amount}"
            player.has_acted_this_round = True
        elif action == Action.RAISE:
            # Validate raise amount
            if amount <= player.current_bet:
                return {"error": f"Raise amount {amount} must be greater than current bet {player.current_bet}"}
            
            # Cap raise amount to what player can actually afford
            max_affordable = player.current_bet + player.chips
            if amount > max_affordable:
                # Player is trying to raise more than they have - cap it to all-in
                amount = max_affordable
            
            # Calculate minimum raise: current_bet + minimum_raise
            minimum_raise_to = self.game_state.current_bet + self.game_state.minimum_raise
            if amount < minimum_raise_to and amount < max_affordable:
                # If player can't afford minimum raise, they must go all-in or call
                if player.chips > 0:
                    # They can go all-in
                    amount = max_affordable
                else:
                    return {"error": f"Raise to {amount} is below minimum raise of {minimum_raise_to} and player has no chips"}
            
            # Calculate how much player needs to put in
            raise_amount = amount - player.current_bet
            
            # If player can't afford full raise, they go all-in
            if player.chips < raise_amount:
                # Auto all-in
                all_in_amount = player.chips
                old_current_bet = self.game_state.current_bet
                player.chips = 0
                player.current_bet += all_in_amount
                player.total_bet += all_in_amount
                player.is_all_in = True
                self.game_state.pot += all_in_amount
                if player.current_bet > old_current_bet:
                    self.game_state.current_bet = player.current_bet
                    # Update minimum raise: the raise delta is the new minimum
                    raise_delta = player.current_bet - old_current_bet
                    self.game_state.last_raise_amount = raise_delta
                    self.game_state.minimum_raise = raise_delta
                    
                    # When a player raises (even all-in), all other players who can act need to respond
                    # Reset their has_acted_this_round flag so they can act again
                    for other_player in self.game_state.players:
                        if (other_player.id != player_id and 
                            other_player.is_active and 
                            not other_player.is_all_in and 
                            other_player.chips > 0 and
                            other_player.current_bet < self.game_state.current_bet):
                            other_player.has_acted_this_round = False
                
                result["message"] = f"{player.name} raised all-in to {player.current_bet}"
            else:
                old_current_bet = self.game_state.current_bet
                player.chips -= raise_amount
                player.current_bet = amount
                player.total_bet += raise_amount
                self.game_state.pot += raise_amount
                # Update minimum raise: the raise delta is the new minimum
                raise_delta = amount - old_current_bet
                self.game_state.current_bet = amount
                self.game_state.last_raise_amount = raise_delta
                self.game_state.minimum_raise = raise_delta
                result["message"] = f"{player.name} raised to {amount}"
                
                # When a player raises, all other players who can act need to respond to the new bet
                # Reset their has_acted_this_round flag so they can act again
                for other_player in self.game_state.players:
                    if (other_player.id != player_id and 
                        other_player.is_active and 
                        not other_player.is_all_in and 
                        other_player.chips > 0 and
                        other_player.current_bet < self.game_state.current_bet):
                        other_player.has_acted_this_round = False
            
            player.has_acted_this_round = True
        elif action == Action.CHECK:
            # Can only check if no bet to call
            if player.current_bet < self.game_state.current_bet:
                return {"error": "Cannot check when there's a bet to call. Use 'call' or 'fold'"}
            result["message"] = f"{player.name} checked"
            player.has_acted_this_round = True
        elif action == Action.ALL_IN:
            all_in_amount = player.chips
            old_current_bet = self.game_state.current_bet
            player.chips = 0
            player.current_bet += all_in_amount
            player.total_bet += all_in_amount
            player.is_all_in = True
            self.game_state.pot += all_in_amount
            if player.current_bet > old_current_bet:
                self.game_state.current_bet = player.current_bet
                # Update minimum raise if this is a raise (not just a call)
                raise_delta = player.current_bet - old_current_bet
                self.game_state.last_raise_amount = raise_delta
                self.game_state.minimum_raise = raise_delta
                
                # When a player raises (even all-in), all other players who can act need to respond
                # Reset their has_acted_this_round flag so they can act again
                for other_player in self.game_state.players:
                    if (other_player.id != player_id and 
                        other_player.is_active and 
                        not other_player.is_all_in and 
                        other_player.chips > 0 and
                        other_player.current_bet < self.game_state.current_bet):
                        other_player.has_acted_this_round = False
            
            player.has_acted_this_round = True
            result["message"] = f"{player.name} went all-in with {all_in_amount}"
        else:
            return {"error": f"Unknown action: {action}"}
        
        # Move to next player
        self._next_player()
        
        # Check if round is complete
        if self._is_round_complete():
            self._advance_round()
        
        return result
    
    def _next_player(self):
        """Move to next active player who can act (clockwise order)"""
        # Get players who can still act (active, not all-in, have chips, haven't matched bet)
        eligible_players = [
            i for i, p in enumerate(self.game_state.players) 
            if p.is_active and not p.is_all_in and p.chips > 0 and p.current_bet < self.game_state.current_bet
        ]
        
        if not eligible_players:
            # No one can act - round should complete
            return
        
        # Find next player in clockwise order
        # Clockwise means going forward in the array (0 -> 1 -> 2 -> 3 -> 4 -> 0)
        num_players = len(self.game_state.players)
        
        # Start searching from current player + 1 (clockwise)
        start_pos = (self.game_state.current_player + 1) % num_players
        
        # Search clockwise for next eligible player
        for offset in range(num_players):
            pos = (start_pos + offset) % num_players
            if pos in eligible_players:
                self.game_state.current_player = pos
                return
        
        # Fallback: if current player is eligible but we can't find next, stay on current
        # This shouldn't happen, but prevents errors
        if self.game_state.current_player in eligible_players:
            return
        
        # If current player is not eligible, find first eligible player in clockwise order
        if eligible_players:
            # Find first eligible player after current position (clockwise)
            for offset in range(1, num_players + 1):
                pos = (self.game_state.current_player + offset) % num_players
                if pos in eligible_players:
                    self.game_state.current_player = pos
                    return
            # If still not found, use first in list (shouldn't happen)
            self.game_state.current_player = eligible_players[0]
    
    def _is_round_complete(self) -> bool:
        """Check if current betting round is complete according to poker rules"""
        # Get all active players (not folded)
        active_players = [p for p in self.game_state.players if p.is_active]
        
        if len(active_players) <= 1:
            return True
        
        # Get players who can still act (not all-in, have chips)
        players_who_can_act = [p for p in active_players if not p.is_all_in and p.chips > 0]
        
        # If no one can act, round is complete
        if not players_who_can_act:
            return True
        
        # If there's no bet (current_bet == 0), all players who can act must have checked
        if self.game_state.current_bet == 0:
            for player in players_who_can_act:
                if not player.has_acted_this_round:
                    return False
            return True
        
        # If there's a bet, check two conditions:
        # 1. All players who can act must have matched the bet OR acted (folded/checked/called)
        # 2. All players who can act must have had a chance to act since the last raise
        
        for player in players_who_can_act:
            # If player hasn't acted this round, round is not complete
            if not player.has_acted_this_round:
                return False
            
            # If player hasn't matched the bet and can still act, round is not complete
            if player.current_bet < self.game_state.current_bet:
                return False
        
        # All players who can act have matched the bet and have acted
        # Round is complete
        return True
    
    def _advance_round(self):
        """Advance to next betting round"""
        # Check if only one player is active - if so, they win immediately
        active_players = [p for p in self.game_state.players if p.is_active]
        if len(active_players) <= 1:
            self._deal_remaining_board_for_visuals()
            self.game_state.round = "showdown"
            self._determine_winner()
            return
        
        # IMPORTANT: Reset current_bet (per-round tracking) but KEEP the pot accumulated
        # The pot accumulates across all betting rounds and should NOT be reset until hand ends
        pot_before_round_reset = self.game_state.pot  # Track pot before reset for verification
        
        for player in self.game_state.players:
            # Reset current_bet for next round (this is just per-round tracking)
            # The chips that were bet are already in the pot and stay there
            player.current_bet = 0
            player.has_acted_this_round = False
            # NOTE: player.chips and self.game_state.pot should NOT be reset here
            # Chips already bet are in the pot and stay there
        
        # Reset current_bet tracking for next round (this is just the betting level, not the pot)
        self.game_state.current_bet = 0
        self.game_state.last_raise_amount = 0
        self.game_state.minimum_raise = self.big_blind - self.small_blind  # Reset to BB-SB
        
        # Verify pot is still intact (should not have changed)
        if self.game_state.pot != pot_before_round_reset:
            print(f"⚠️ POT ERROR: Pot changed from {pot_before_round_reset} to {self.game_state.pot} during round reset!")
            self.game_state.pot = pot_before_round_reset  # Restore pot
        else:
            print(f"✅ Pot maintained: {self.game_state.pot} (unchanged during round reset)")
        
        # Advance to next round and deal community cards
        if self.game_state.round == "preflop":
            self.game_state.round = "flop"
            self._deal_community_cards(3)
            # Post-flop action starts with first active player left of dealer button
            self._set_postflop_action_start()
        elif self.game_state.round == "flop":
            self.game_state.round = "turn"
            self._deal_community_cards(1)
            self._set_postflop_action_start()
        elif self.game_state.round == "turn":
            self.game_state.round = "river"
            self._deal_community_cards(1)
            self._set_postflop_action_start()
        elif self.game_state.round == "river":
            # After river betting round completes, go to showdown
            self.game_state.round = "showdown"
            self._determine_winner()
    
    def _set_postflop_action_start(self):
        """Set current player to first active player left of dealer button (post-flop)"""
        # Find first active player left of dealer (dealer + 1, wrapping around)
        active_indices = [
            i for i, p in enumerate(self.game_state.players) 
            if p.is_active and (not p.is_all_in or p.chips > 0)
        ]
        if not active_indices:
            return
        
        # Start with dealer + 1, wrapping around
        start_pos = (self.game_state.dealer_position + 1) % len(self.game_state.players)
        
        # Find first active player at or after start_pos
        for offset in range(len(self.game_state.players)):
            pos = (start_pos + offset) % len(self.game_state.players)
            if pos in active_indices:
                self.game_state.current_player = pos
                return
        
        # Fallback: use first active player
        self.game_state.current_player = active_indices[0]
    
    def _deal_community_cards(self, num_cards: int):
        """Deal community cards"""
        cards, self.game_state.deck = self.deal_cards(self.game_state.deck, num_cards)
        self.game_state.community_cards.extend(cards)

    def _deal_remaining_board_for_visuals(self):
        """Deal remaining community cards purely for visualization when a hand ends early"""
        if not self.game_state:
            return
        remaining = 5 - len(self.game_state.community_cards)
        if remaining > 0:
            cards, self.game_state.deck = self.deal_cards(self.game_state.deck, remaining)
            self.game_state.community_cards.extend(cards)
    
    def _determine_winner(self):
        """Determine the winner of the hand with side pot support"""
        active_players = [p for p in self.game_state.players if p.is_active]
        
        # Store pot amount before distribution for verification
        pot_before = self.game_state.pot
        total_chips_before = sum(p.chips for p in self.game_state.players)
        
        if len(active_players) == 1:
            # Only one player left - they win everything
            winner = active_players[0]
            winner.chips += self.game_state.pot
            self.game_state.pot = 0  # Reset pot after distribution
        else:
            # Check if we need side pots (players went all-in with different amounts)
            all_in_amounts = sorted(set(p.total_bet for p in active_players if p.total_bet > 0), reverse=True)
            
            if len(all_in_amounts) > 1:
                # Need side pots
                self._distribute_side_pots(active_players, all_in_amounts)
            else:
                # Simple pot distribution
                self._distribute_simple_pot(active_players)
            
            # Reset pot after distribution
            self.game_state.pot = 0
        
        # VERIFICATION: Ensure all chips were correctly distributed
        total_chips_after = sum(p.chips for p in self.game_state.players)
        expected_total = total_chips_before + pot_before
        
        if total_chips_after != expected_total:
            # This should never happen, but log it if it does
            print(f"⚠️ CHIP DISTRIBUTION ERROR: Expected {expected_total} chips, got {total_chips_after}")
            print(f"   Pot before: {pot_before}, Total before: {total_chips_before}, Total after: {total_chips_after}")
            # Fix the discrepancy by adjusting the winner's chips
            difference = expected_total - total_chips_after
            if active_players:
                active_players[0].chips += difference
                print(f"   Fixed: Added {difference} chips to {active_players[0].name}")
        else:
            print(f"✅ Chip distribution verified: {total_chips_before} + {pot_before} = {total_chips_after}")
    
    def _distribute_side_pots(self, active_players: List[Player], all_in_amounts: List[int]):
        """Distribute pots with side pot logic for all-in players with different stack sizes"""
        # Sort all-in amounts in descending order
        all_in_amounts = sorted(set(all_in_amounts), reverse=True)
        
        # Create side pots level by level
        previous_level = 0
        total_distributed = 0
        
        for level in all_in_amounts:
            # Calculate pot at this level
            pot_at_level = 0
            eligible_players = []
            
            for player in active_players:
                if player.total_bet >= level:
                    # This player is eligible for this pot level
                    eligible_players.append(player)
                    # Calculate their contribution to this level
                    # Each player contributes the difference between this level and previous level
                    # (up to their total bet)
                    contribution = min(level - previous_level, player.total_bet - previous_level)
                    pot_at_level += contribution
            
            if pot_at_level > 0 and eligible_players:
                # Determine winner(s) among eligible players
                winners = self._evaluate_hands_for_pot(eligible_players)
                
                # Distribute this side pot
                pot_per_winner = pot_at_level // len(winners)
                remainder = pot_at_level % len(winners)
                
                for winner in winners:
                    winner.chips += pot_per_winner
                if remainder > 0 and winners:
                    winners[0].chips += remainder
                
                total_distributed += pot_at_level
                print(f"   Side pot level {level}: {pot_at_level} chips distributed to {len(winners)} winner(s)")
            
            previous_level = level
        
        # Distribute any remaining pot (shouldn't happen, but safety check)
        remaining = self.game_state.pot - total_distributed
        if remaining > 0:
            print(f"   ⚠️ Distributing remaining pot: {remaining} chips")
            # Distribute to all active players (shouldn't happen in normal play)
            winners = self._evaluate_hands_for_pot(active_players)
            pot_per_winner = remaining // len(winners)
            remainder = remaining % len(winners)
            for winner in winners:
                winner.chips += pot_per_winner
            if remainder > 0 and winners:
                winners[0].chips += remainder
            total_distributed += remaining
        
        # Verify all pot was distributed
        if total_distributed != self.game_state.pot:
            print(f"   ⚠️ Pot distribution mismatch: distributed {total_distributed}, pot was {self.game_state.pot}")
    
    def _distribute_simple_pot(self, active_players: List[Player]):
        """Distribute pot when no side pots are needed"""
        winners = self._evaluate_hands_for_pot(active_players)
        
        pot_per_winner = self.game_state.pot // len(winners)
        remainder = self.game_state.pot % len(winners)
        
        for winner in winners:
            winner.chips += pot_per_winner
        if remainder > 0 and winners:
            winners[0].chips += remainder
        
        print(f"   Simple pot: {self.game_state.pot} chips distributed to {len(winners)} winner(s)")
    
    def _evaluate_hands_for_pot(self, players: List[Player]) -> List[Player]:
        """Evaluate hands and return list of winners (may be multiple for ties)"""
        if not players:
            return []
        
        if len(players) == 1:
            return players
        
        best_rank = HandRank.HIGH_CARD
        best_tiebreaker = []
        winners = []
        
        for player in players:
            all_cards = player.cards + self.game_state.community_cards
            rank, tiebreaker = self.get_hand_rank(all_cards)
            
            if rank.value > best_rank.value:
                best_rank = rank
                best_tiebreaker = tiebreaker
                winners = [player]
            elif rank.value == best_rank.value:
                # Compare tiebreakers
                if tiebreaker > best_tiebreaker:
                    best_tiebreaker = tiebreaker
                    winners = [player]
                elif tiebreaker == best_tiebreaker:
                    winners.append(player)
        
        return winners if winners else players  # Fallback to all players if evaluation fails
    
    def get_game_state_for_player(self, player_id: str) -> Dict[str, Any]:
        """Get game state visible to a specific player"""
        if not self.game_state:
            return {"error": "No active game"}
        
        player = next((p for p in self.game_state.players if p.id == player_id), None)
        if not player:
            return {"error": "Player not found"}
        
        return {
            "hand_number": self.game_state.hand_number,
            "round": self.game_state.round,
            "pot": self.game_state.pot,
            "current_bet": self.game_state.current_bet,
            "community_cards": [str(card) for card in self.game_state.community_cards],
            "your_cards": [str(card) for card in player.cards],
            "your_chips": player.chips,
            "your_current_bet": player.current_bet,
            "your_total_bet": player.total_bet,
            "is_your_turn": self.game_state.current_player == self.game_state.players.index(player),
            "players": [
                {
                    "name": p.name,
                    "chips": p.chips,
                    "current_bet": p.current_bet,
                    "is_active": p.is_active,
                    "is_all_in": p.is_all_in
                }
                for p in self.game_state.players
            ]
        }
