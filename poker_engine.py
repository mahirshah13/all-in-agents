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
        
        # Rotate dealer position (only rotate if we have existing game state)
        # For first hand, dealer starts at 0, then rotates after each hand
        if self.game_state is not None and len(players) > 0:
            self.dealer_position = (self.dealer_position + 1) % len(players)
        
        # Create and shuffle deck
        deck = self.shuffle_deck(self.create_deck())
        
        # Set up game state
        self.game_state = GameState(
            players=players,
            community_cards=[],
            pot=0,
            current_bet=0,
            dealer_position=self.dealer_position,
            current_player=1,  # Will be set correctly in _post_blinds
            round="preflop",
            deck=deck,
            small_blind=self.small_blind,
            big_blind=self.big_blind,
            hand_number=self.hand_number
        )
        
        # Post blinds (this will set current_player correctly)
        self._post_blinds()
        
        # Deal hole cards
        self._deal_hole_cards()
        
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
        
        # Big blind
        bb_amount = min(self.big_blind, self.game_state.players[bb_pos].chips)
        self.game_state.players[bb_pos].chips -= bb_amount
        self.game_state.players[bb_pos].current_bet = bb_amount
        self.game_state.players[bb_pos].total_bet = bb_amount
        self.game_state.pot += bb_amount
        
        self.game_state.current_bet = bb_amount
        self.game_state.current_player = bb_pos
    
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
        """Process a player's action"""
        if not self.game_state:
            return {"error": "No active game"}
        
        player = next((p for p in self.game_state.players if p.id == player_id), None)
        if not player:
            return {"error": "Player not found"}
        
        if not player.is_active:
            return {"error": "Player is not active"}
        
        if player.chips <= 0 and action != Action.FOLD:
            return {"error": "Player has no chips"}
        
        result = {"success": True, "action": action.value, "amount": amount}
        
        if action == Action.FOLD:
            player.is_active = False
            result["message"] = f"{player.name} folded"
        elif action == Action.CALL:
            call_amount = min(self.game_state.current_bet - player.current_bet, player.chips)
            player.chips -= call_amount
            player.current_bet += call_amount
            player.total_bet += call_amount
            self.game_state.pot += call_amount
            result["message"] = f"{player.name} called {call_amount}"
        elif action == Action.RAISE:
            if amount <= self.game_state.current_bet:
                return {"error": "Raise amount must be greater than current bet"}
            raise_amount = min(amount - player.current_bet, player.chips)
            player.chips -= raise_amount
            player.current_bet += raise_amount
            player.total_bet += raise_amount
            self.game_state.pot += raise_amount
            self.game_state.current_bet = player.current_bet
            result["message"] = f"{player.name} raised to {player.current_bet}"
        elif action == Action.CHECK:
            if player.current_bet < self.game_state.current_bet:
                return {"error": "Cannot check when there's a bet to call"}
            result["message"] = f"{player.name} checked"
        elif action == Action.ALL_IN:
            all_in_amount = player.chips
            player.chips = 0
            player.current_bet += all_in_amount
            player.total_bet += all_in_amount
            player.is_all_in = True
            self.game_state.pot += all_in_amount
            if player.current_bet > self.game_state.current_bet:
                self.game_state.current_bet = player.current_bet
            result["message"] = f"{player.name} went all-in with {all_in_amount}"
        
        # Move to next player
        self._next_player()
        
        # Check if round is complete
        if self._is_round_complete():
            self._advance_round()
        
        return result
    
    def _next_player(self):
        """Move to next active player"""
        active_players = [i for i, p in enumerate(self.game_state.players) if p.is_active and p.chips > 0]
        if not active_players:
            return
        
        # If current player is not active, find the next active player
        if self.game_state.current_player not in active_players:
            self.game_state.current_player = active_players[0]
            return
        
        current_idx = active_players.index(self.game_state.current_player)
        self.game_state.current_player = active_players[(current_idx + 1) % len(active_players)]
    
    def _is_round_complete(self) -> bool:
        """Check if current betting round is complete"""
        active_players = [p for p in self.game_state.players if p.is_active and p.chips > 0]
        if len(active_players) <= 1:
            return True
        
        # Check if all active players have either folded, gone all-in, or matched the current bet
        for player in active_players:
            if player.current_bet < self.game_state.current_bet and player.chips > 0:
                return False
        
        return True
    
    def _advance_round(self):
        """Advance to next betting round"""
        # Check if only one player is active - if so, they win immediately
        active_players = [p for p in self.game_state.players if p.is_active and p.chips > 0]
        if len(active_players) <= 1:
            self.game_state.round = "showdown"
            self._determine_winner()
            return
        
        # Reset current bets
        for player in self.game_state.players:
            player.current_bet = 0
        
        self.game_state.current_bet = 0
        
        if self.game_state.round == "preflop":
            self.game_state.round = "flop"
            self._deal_community_cards(3)
        elif self.game_state.round == "flop":
            self.game_state.round = "turn"
            self._deal_community_cards(1)
        elif self.game_state.round == "turn":
            self.game_state.round = "river"
            self._deal_community_cards(1)
        elif self.game_state.round == "river":
            self.game_state.round = "showdown"
            self._determine_winner()
    
    def _deal_community_cards(self, num_cards: int):
        """Deal community cards"""
        cards, self.game_state.deck = self.deal_cards(self.game_state.deck, num_cards)
        self.game_state.community_cards.extend(cards)
    
    def _determine_winner(self):
        """Determine the winner of the hand"""
        active_players = [p for p in self.game_state.players if p.is_active]
        
        if len(active_players) == 1:
            # Only one player left
            winner = active_players[0]
            winner.chips += self.game_state.pot
            return
        
        # Evaluate all hands
        best_hand = None
        best_rank = HandRank.HIGH_CARD
        best_tiebreaker = []
        winners = []
        
        for player in active_players:
            all_cards = player.cards + self.game_state.community_cards
            rank, tiebreaker = self.get_hand_rank(all_cards)
            
            if rank.value > best_rank.value or (rank.value == best_rank.value and tiebreaker > best_tiebreaker):
                best_hand = player
                best_rank = rank
                best_tiebreaker = tiebreaker
                winners = [player]
            elif rank.value == best_rank.value and tiebreaker == best_tiebreaker:
                winners.append(player)
        
        # Distribute pot
        pot_per_winner = self.game_state.pot // len(winners)
        for winner in winners:
            winner.chips += pot_per_winner
        
        # Handle remainder
        remainder = self.game_state.pot % len(winners)
        if remainder > 0:
            winners[0].chips += remainder
    
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
