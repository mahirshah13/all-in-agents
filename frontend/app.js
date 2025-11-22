// WebSocket connection and game state management
class PokerVisualization {
    constructor() {
        this.ws = null;
        this.gameState = null;
        this.players = [];
        this.handNumber = 0;
        this.currentRound = 'preflop';
        this.init();
    }

    init() {
        this.connectWebSocket();
        this.setupEventListeners();
    }

    connectWebSocket() {
        const wsUrl = `ws://${window.location.hostname}:8080/ws`;
        console.log('Connecting to WebSocket:', wsUrl);
        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            console.log('✅ Connected to WebSocket server');
            this.updateConnectionStatus(true);
            this.addLogEntry('Connected to game server. Waiting for game to start...', 'info');
            this.ws.send(JSON.stringify({type: 'get_state'}));
        };

        this.ws.onmessage = (event) => {
            try {
                const message = JSON.parse(event.data);
                this.handleMessage(message);
            } catch (error) {
                console.error('Error parsing WebSocket message:', error, event.data);
            }
        };

        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
            this.updateConnectionStatus(false);
        };

        this.ws.onclose = () => {
            console.log('Disconnected from server');
            this.updateConnectionStatus(false);
            setTimeout(() => this.connectWebSocket(), 3000);
        };
    }

    updateConnectionStatus(connected) {
        const statusEl = document.getElementById('connection-status');
        if (statusEl) {
            if (connected) {
                statusEl.textContent = 'Connected';
                statusEl.className = 'status-indicator connected';
            } else {
                statusEl.textContent = 'Disconnected';
                statusEl.className = 'status-indicator disconnected';
            }
        }
    }

    handleMessage(message) {
        console.log('Received message:', message);
        try {
            switch (message.type) {
                case 'game_state':
                    this.updateGameState(message.data);
                    // Explicitly update community cards
                    if (message.data.community_cards) {
                        this.updateCommunityCards(message.data.community_cards);
                    }
                    break;
                case 'hand_start':
                    this.handleHandStart(message.data);
                    break;
                case 'round_change':
                    this.handleRoundChange(message.data);
                    // Explicitly update community cards
                    if (message.data.community_cards) {
                        this.updateCommunityCards(message.data.community_cards);
                    }
                    break;
                case 'player_action':
                    this.handlePlayerAction(message.data);
                    // Update community cards from game_state if provided
                    if (message.data.game_state && message.data.game_state.community_cards) {
                        this.updateCommunityCards(message.data.game_state.community_cards);
                    }
                    break;
                case 'hand_end':
                    this.handleHandEnd(message.data);
                    // Explicitly update community cards
                    if (message.data.community_cards) {
                        this.updateCommunityCards(message.data.community_cards);
                    }
                    break;
                case 'history':
                    this.loadHistory(message.data);
                    break;
                case 'info':
                    this.addLogEntry(message.data.message || 'Info', 'info');
                    break;
            }
        } catch (error) {
            console.error('Error handling message:', error, message);
        }
    }

    updateGameState(state) {
        this.gameState = state;
        console.log('Updating game state:', state);
        
        // Update game info in sidebar
        if (state.hand_number !== undefined) {
            const el = document.getElementById('hand-number');
            if (el) el.textContent = state.hand_number;
            this.handNumber = state.hand_number;
        }
        if (state.round) {
            const el = document.getElementById('round');
            if (el) el.textContent = state.round.toUpperCase();
            this.currentRound = state.round;
            this.updateRoundDisplay(state.round);
        }
        if (state.pot !== undefined) {
            const el = document.getElementById('pot');
            if (el) el.textContent = `💰${state.pot}`;
            const potDisplay = document.getElementById('pot-display');
            if (potDisplay) potDisplay.textContent = `💰${state.pot}`;
        }
        if (state.current_bet !== undefined) {
            const el = document.getElementById('current-bet');
            if (el) el.textContent = `💰${state.current_bet}`;
        }

        // Update community cards
        this.updateCommunityCards(state.community_cards || []);

        // Update players around table
        if (state.players && Array.isArray(state.players) && state.players.length > 0) {
            const currentPlayerIndex = state.current_player !== undefined ? state.current_player : -1;
            this.updatePlayersOnTable(state.players, currentPlayerIndex);
        }
    }

    updateRoundDisplay(round) {
        const roundEl = document.getElementById('round-display');
        if (roundEl) {
            roundEl.textContent = round.charAt(0).toUpperCase() + round.slice(1);
        }
    }

    updateCommunityCards(cards) {
        const container = document.getElementById('community-cards');
        if (!container) {
            console.error('❌ Community cards container not found!');
            return;
        }

        // Clear existing cards
        container.innerHTML = '';
        
        if (!cards || !Array.isArray(cards)) {
            console.warn('⚠️ Invalid cards data:', cards);
            cards = [];
        }
        
        console.log('🃏 Updating community cards:', cards, 'length:', cards.length, 'type:', typeof cards);
        
        // Create 5 card slots
        for (let i = 0; i < 5; i++) {
            const slot = document.createElement('div');
            slot.className = 'card-slot';
            
            if (i < cards.length && cards[i]) {
                const cardStr = String(cards[i]).trim();
                if (cardStr && cardStr !== 'undefined' && cardStr !== 'null') {
                    try {
                        console.log(`Creating card ${i + 1}: "${cardStr}"`);
                        const card = this.createCardElement(cardStr);
                        slot.appendChild(card);
                        console.log(`✅ Card ${i + 1} created successfully`);
                    } catch (e) {
                        console.error(`❌ Error creating community card ${i + 1}:`, e, 'Card string:', cardStr);
                        // Add placeholder if card creation fails
                        const placeholder = document.createElement('div');
                        placeholder.className = 'card';
                        placeholder.textContent = '🂠';
                        placeholder.style.opacity = '0.3';
                        slot.appendChild(placeholder);
                    }
                } else {
                    console.warn(`⚠️ Empty or invalid card at index ${i}:`, cards[i]);
                }
            }
            
            container.appendChild(slot);
        }
        
        // Log community cards update
        if (cards.length > 0) {
            console.log(`✅ Community cards updated: ${cards.join(', ')}`);
            // Force a visual update
            container.style.display = 'none';
            setTimeout(() => {
                container.style.display = 'flex';
            }, 10);
        } else {
            console.log('⚠️ No community cards to display (this is normal for preflop)');
        }
    }

    createCardElement(cardStr) {
        const card = document.createElement('div');
        card.className = 'card';
        
        // Convert to string and trim
        if (!cardStr) {
            console.warn('Invalid card string (null/undefined):', cardStr);
            card.textContent = '🂠';
            card.classList.add('black');
            return card;
        }
        
        cardStr = String(cardStr).trim();
        
        if (!cardStr || cardStr === 'undefined' || cardStr === 'null') {
            console.warn('Invalid card string (empty):', cardStr);
            card.textContent = '🂠';
            card.classList.add('black');
            return card;
        }
        
        // Determine if red or black
        const isRed = cardStr.includes('♥') || cardStr.includes('♦') || cardStr.includes('h') || cardStr.includes('d');
        card.classList.add(isRed ? 'red' : 'black');
        
        let display = cardStr;
        
        // Handle different card formats
        // Format 1: "A♥", "K♠" (already has suit symbols)
        if (cardStr.includes('♥') || cardStr.includes('♦') || cardStr.includes('♠') || cardStr.includes('♣')) {
            // Already in correct format, just use it
            display = cardStr;
        }
        // Format 2: "As", "Kh", "10d", "2c" (letter format)
        else if (cardStr.length >= 2 && !cardStr.includes('Rank.') && !cardStr.includes('Suit.')) {
            const rank = cardStr[0];
            const suit = cardStr[1];
            const suitMap = { 's': '♠', 'h': '♥', 'd': '♦', 'c': '♣', 'S': '♠', 'H': '♥', 'D': '♦', 'C': '♣' };
            const rankMap = { 'A': 'A', 'K': 'K', 'Q': 'Q', 'J': 'J', 'T': '10', 'a': 'A', 'k': 'K', 'q': 'Q', 'j': 'J', 't': '10' };
            const finalRank = rankMap[rank] || rank;
            const finalSuit = suitMap[suit] || suit;
            display = finalRank + finalSuit;
            // Update color based on suit
            if (suit === 'h' || suit === 'd' || suit === 'H' || suit === 'D') {
                card.classList.remove('black');
                card.classList.add('red');
            }
        }
        // Format 3: Card object string like "Rank.ACE Suit.HEARTS"
        else if (cardStr.includes('Rank.') || cardStr.includes('Suit.')) {
            const rankMatch = cardStr.match(/Rank\.(\w+)/);
            const suitMatch = cardStr.match(/Suit\.(\w+)/);
            if (rankMatch && suitMatch) {
                const rank = rankMatch[1];
                const suit = suitMatch[1];
                const suitMap = { 'HEARTS': '♥', 'DIAMONDS': '♦', 'SPADES': '♠', 'CLUBS': '♣' };
                const rankMap = { 'ACE': 'A', 'KING': 'K', 'QUEEN': 'Q', 'JACK': 'J', 'TEN': '10', 'NINE': '9', 'EIGHT': '8', 'SEVEN': '7', 'SIX': '6', 'FIVE': '5', 'FOUR': '4', 'THREE': '3', 'TWO': '2' };
                const finalRank = rankMap[rank] || rank[0];
                display = finalRank + (suitMap[suit] || suit[0]);
                if (suit === 'HEARTS' || suit === 'DIAMONDS') {
                    card.classList.remove('black');
                    card.classList.add('red');
                }
            }
        }
        
        card.textContent = display;
        console.log(`Created card element: "${display}" from "${cardStr}"`);
        return card;
    }

    updatePlayersOnTable(players, currentPlayerIndex) {
        const container = document.getElementById('players-container');
        if (!container) return;

        console.log('Updating players on table:', players, 'current:', currentPlayerIndex);
        
        container.innerHTML = '';
        this.players = players;

        const typeLabels = {
            'tagbot': 'TAGBot',
            'montecarlo': 'Monte Carlo',
            'maniac': 'Maniac',
            'smart': 'Smart',
            'conservative': 'Conservative',
            'aggressive': 'Aggressive',
            'openai': 'OpenAI',
            'unknown': 'Unknown'
        };

        players.forEach((player, index) => {
            const seat = document.createElement('div');
            seat.className = 'player-seat';
            seat.classList.add(`position-${index}`);
            
            if (index === currentPlayerIndex && currentPlayerIndex >= 0) {
                seat.classList.add('active');
            }
            if (player.is_active === false) {
                seat.classList.add('folded');
            }

            const agentName = player.name || `Player ${index + 1}`;
            const agentType = (player.type || 'unknown').toLowerCase();
            const typeLabel = typeLabels[agentType] || agentType;

            seat.innerHTML = `
                <div class="player-header-seat">
                    <span class="player-name-seat">${agentName}</span>
                    <span class="player-type-seat">${typeLabel}</span>
                </div>
                <div class="player-chips-seat">💰${player.chips || 0}</div>
                <div class="player-bet-seat">Bet: 💰${player.current_bet || 0}</div>
                <div class="player-cards-seat">
                    ${player.cards && Array.isArray(player.cards) && player.cards.length > 0 ? 
                        player.cards.map(card => {
                            try {
                                return this.createCardElement(card).outerHTML;
                            } catch (e) {
                                console.error('Error creating card element:', e, card);
                                return '<div class="card" style="opacity: 0.3;">🂠</div>';
                            }
                        }).filter(html => html).join('') : 
                        '<div class="card" style="opacity: 0.3;">🂠</div><div class="card" style="opacity: 0.3;">🂠</div>'
                    }
                </div>
            `;

            container.appendChild(seat);
        });
    }

    handleHandStart(data) {
        console.log('Hand start data:', data);
        this.handNumber = data.hand_number || 0;
        const playersList = data.players ? data.players.map(p => `${p.name} (${p.type || 'unknown'})`).join(', ') : '';
        this.addLogEntry(`Hand ${this.handNumber} started with players: ${playersList}`, 'info');
        
        const handNumberEl = document.getElementById('hand-number');
        if (handNumberEl) handNumberEl.textContent = this.handNumber;
        
        if (data.players && Array.isArray(data.players) && data.players.length > 0) {
            const players = data.players.map(p => ({
                name: p.name || 'Unknown',
                type: p.type || 'unknown',
                chips: p.chips !== undefined ? p.chips : 1000,
                position: p.position !== undefined ? p.position : 0,
                is_active: true,
                current_bet: 0,
                cards: []
            }));
            this.updatePlayersOnTable(players, -1);
        }
    }

    handleRoundChange(data) {
        const roundName = data.round ? data.round.toUpperCase() : 'UNKNOWN';
        const cardCount = data.community_cards ? data.community_cards.length : 0;
        this.addLogEntry(`Round changed to ${roundName}${cardCount > 0 ? ` (${cardCount} community cards)` : ''}`, 'info');
        if (data.round) {
            this.currentRound = data.round;
            this.updateRoundDisplay(data.round);
        }
        if (data.community_cards) {
            this.updateCommunityCards(data.community_cards);
        }
        // Also update pot and current bet
        if (data.pot !== undefined) {
            const potEl = document.getElementById('pot');
            if (potEl) potEl.textContent = `💰${data.pot}`;
            const potDisplay = document.getElementById('pot-display');
            if (potDisplay) potDisplay.textContent = `💰${data.pot}`;
        }
        if (data.current_bet !== undefined) {
            const betEl = document.getElementById('current-bet');
            if (betEl) betEl.textContent = `💰${data.current_bet}`;
        }
    }

    handlePlayerAction(data) {
        const action = data.action || 'action';
        const amount = data.amount || 0;
        const reasoning = data.reasoning || '';
        const player = data.player || 'Unknown';
        const round = data.game_state?.round || this.currentRound || 'preflop';
        
        // Format action message
        let actionMsg = `${player}: ${action.toUpperCase()}`;
        if (action === 'raise' && amount > 0) {
            actionMsg += ` to 💰${amount}`;
        } else if (action === 'call' && amount > 0) {
            actionMsg += ` 💰${amount}`;
        } else if (action === 'all_in' && amount > 0) {
            actionMsg += ` 💰${amount}`;
        }
        if (reasoning) {
            actionMsg += ` - ${reasoning}`;
        }
        
        this.addLogEntry(actionMsg, 'action');
        
        // Update game state if provided
        if (data.game_state) {
            this.updateGameState(data.game_state);
        }
    }

    handleHandEnd(data) {
        this.addLogEntry(`Hand ended. Winner: ${data.winner || 'Unknown'}`, 'info');
        
        // Update community cards if provided
        if (data.community_cards && Array.isArray(data.community_cards)) {
            this.updateCommunityCards(data.community_cards);
        }
        
        // Update game state if provided
        if (data.round) {
            this.currentRound = data.round;
            this.updateRoundDisplay(data.round);
            const roundEl = document.getElementById('round');
            if (roundEl) roundEl.textContent = data.round.toUpperCase();
        }
        
        if (data.pot !== undefined) {
            const potEl = document.getElementById('pot');
            if (potEl) potEl.textContent = `💰${data.pot}`;
            const potDisplay = document.getElementById('pot-display');
            if (potDisplay) potDisplay.textContent = `💰${data.pot}`;
        }
    }

    addLogEntry(message, type = 'info') {
        const logContainer = document.getElementById('action-log');
        if (!logContainer) return;
        
        const entry = document.createElement('div');
        entry.className = `log-entry ${type}`;
        
        const timestamp = new Date().toLocaleTimeString();
        entry.innerHTML = `<span class="log-timestamp">${timestamp}</span>${message}`;
        
        logContainer.insertBefore(entry, logContainer.firstChild);
        
        while (logContainer.children.length > 100) {
            logContainer.removeChild(logContainer.lastChild);
        }
    }

    loadHistory(history) {
        history.forEach(msg => this.handleMessage(msg));
    }

    setupEventListeners() {
        // Load and display selected agents
        this.loadSelectedAgents();
    }
    
    loadSelectedAgents() {
        // Fetch selected agents from backend
        fetch('/api/selected-agents')
            .then(response => response.json())
            .then(data => {
                if (data.agents && data.agents.length > 0) {
                    this.displaySelectedAgents(data.agents);
                } else {
                    // No agents selected, redirect to selection page
                    window.location.href = '/select';
                }
            })
            .catch(() => {
                // If endpoint doesn't exist, show default agents
                const defaultAgents = [
                    {id: "tagbot", name: "TAGBot", description: "Tight-Aggressive"},
                    {id: "montecarlo", name: "Monte Carlo", description: "Simulation-Based"},
                    {id: "maniac", name: "Maniac", description: "Ultra-Aggressive"},
                    {id: "smart_agent", name: "Smart Agent", description: "Pot Odds & Position"}
                ];
                this.displaySelectedAgents(defaultAgents);
            });
    }
    
    displaySelectedAgents(agents) {
        const botList = document.getElementById('bot-list');
        if (!botList) return;
        
        botList.innerHTML = '';
        agents.forEach(agent => {
            const item = document.createElement('div');
            item.className = 'bot-item';
            item.innerHTML = `
                <div class="bot-name">${agent.name}</div>
                <div class="bot-type">${agent.description || agent.type || ''}</div>
            `;
            botList.appendChild(item);
        });
    }
}

// Initialize when page loads
document.addEventListener('DOMContentLoaded', () => {
    new PokerVisualization();
});
