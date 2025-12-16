"""White agent implementation - the target agent being tested."""

import json
import os
import uvicorn
import dotenv
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentSkill, AgentCard, AgentCapabilities
from a2a.utils import new_agent_text_message
from litellm import completion

from .strategies import get_strategy, PokerStrategy


dotenv.load_dotenv()


def prepare_white_agent_card(url):
    skill = AgentSkill(
        id="task_fulfillment",
        name="Task Fulfillment",
        description="Handles user requests and completes tasks",
        tags=["general"],
        examples=[],
    )
    # When running under Agentbeats / a controller, the public URL is injected via
    # the AGENT_URL environment variable. Prefer that over any local URL derived
    # from host/port so the card always advertises the correct externally
    # reachable address (mirrors agentify-example-tau-bench).
    public_url = os.getenv("AGENT_URL") or url

    card = AgentCard(
        name="file_agent",
        description="Test agent from file",
        url=public_url,
        version="1.0.0",
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        capabilities=AgentCapabilities(),
        skills=[skill],
    )
    return card


class GeneralWhiteAgentExecutor(AgentExecutor):
    """
    White agent executor that maintains conversation state per context_id.
    
    State Management:
    - Each context_id maintains its own conversation history in ctx_id_to_messages
    - When green agent creates a new context_id (e.g., for a new tournament),
      this automatically starts a fresh conversation thread
    - Old context_ids remain in memory but won't be accessed after reset
    """
    def __init__(self, agent_type: str = "openai"):
        self.agent_type = agent_type
        self.strategy: PokerStrategy = get_strategy(agent_type)
        self.ctx_id_to_messages = {}  # Maps context_id -> list of messages (conversation history)
        self.ctx_id_to_game_state = {}  # Maps context_id -> current game state

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        # parse the task
        user_input = context.get_user_input()
        if context.context_id not in self.ctx_id_to_messages:
            self.ctx_id_to_messages[context.context_id] = []
        messages = self.ctx_id_to_messages[context.context_id]
        
        # Check if this is a poker game state (JSON format)
        try:
            game_data = json.loads(user_input)
            if "game_state" in game_data and "player_cards" in game_data:
                # This is a poker game state, handle it specially
                response = await self._handle_poker_decision(game_data, context.context_id)
            else:
                # Regular conversation
                response = await self._handle_regular_conversation(user_input, context.context_id)
        except json.JSONDecodeError:
            # Regular conversation
            response = await self._handle_regular_conversation(user_input, context.context_id)
        
        await event_queue.enqueue_event(
            new_agent_text_message(
                response, context_id=context.context_id
            )
        )

    async def _handle_poker_decision(self, game_data: dict, context_id: str) -> str:
        """Handle poker game decision with proper context"""
        # Store current game state
        self.ctx_id_to_game_state[context_id] = game_data
        
        # If we have a strategy (non-OpenAI agent), use it
        if self.strategy:
            # Extract player chips from game state if available
            game_state = game_data.get("game_state", {})
            players = game_data.get("players", [])
            player_id = None  # We'll need to identify the player somehow
            
            # Try to find player chips from the game state structure
            player_chips = 1000  # Default
            if "your_chips" in game_data:
                player_chips = game_data["your_chips"]
            
            # Add player_chips to game_data for strategy
            game_data["player_chips"] = player_chips
            
            decision = self.strategy.make_decision(game_data)
            return json.dumps(decision)
        
        # Otherwise use OpenAI LLM
        messages = self.ctx_id_to_messages[context_id]
        
        # Add system message if this is the first poker message
        if not any(msg.get("role") == "system" for msg in messages):
            messages.insert(0, {
                "role": "system",
                "content": """You are a poker-playing AI agent. You must respond ONLY with valid JSON in this exact format:
{
  "action": "fold|call|raise",
  "amount": <number>,
  "confidence": <0.0-1.0>,
  "reasoning": "<brief explanation>"
}

CRITICAL: Respond with ONLY the JSON object. Do NOT wrap it in markdown code blocks, do NOT include any other text, explanations, or formatting. Just the raw JSON."""
            })
        
        # Add current game state
        messages.append({
            "role": "user", 
            "content": f"Poker game state: {json.dumps(game_data, indent=2)}"
        })
        
        response = completion(
            messages=messages,
            model="openai/gpt-4o",
            custom_llm_provider="openai",
            temperature=0.1,  # Lower temperature for more consistent JSON
        )
        
        next_message = response.choices[0].message.model_dump()
        content = next_message["content"]
        
        # Clean up the response to ensure it's pure JSON
        content = self._clean_json_response(content)
        
        messages.append({
            "role": "assistant",
            "content": content,
        })
        
        return content

    def _clean_json_response(self, content: str) -> str:
        """Clean up the response to ensure it's pure JSON"""
        import re
        
        # Remove markdown code blocks if present
        content = re.sub(r'```(?:json)?\s*', '', content)
        content = re.sub(r'```\s*$', '', content)
        
        # Remove any leading/trailing whitespace
        content = content.strip()
        
        # Try to find JSON object in the response
        json_match = re.search(r'\{[^{}]*"action"[^{}]*\}', content, re.DOTALL)
        if json_match:
            return json_match.group(0).strip()
        
        return content

    async def _handle_regular_conversation(self, user_input: str, context_id: str) -> str:
        """Handle regular conversation"""
        messages = self.ctx_id_to_messages[context_id]
        messages.append({
            "role": "user",
            "content": user_input,
        })
        
        response = completion(
            messages=messages,
            model="openai/gpt-4o",
            custom_llm_provider="openai",
            temperature=0.0,
        )
        
        next_message = response.choices[0].message.model_dump()
        messages.append({
            "role": "assistant",
            "content": next_message["content"],
        })
        
        return next_message["content"]

    async def cancel(self, context, event_queue) -> None:
        raise NotImplementedError


def start_white_agent(agent_name="general_white_agent", host="localhost", port=9002, agent_type="openai"):
    """Start a white agent with specified type"""
    print(f"Starting white agent: {agent_name} (type: {agent_type}) on {host}:{port}")
    url = f"http://{host}:{port}"
    card = prepare_white_agent_card(url)

    # Get agent type from environment or parameter
    agent_type = os.getenv("AGENT_TYPE", agent_type)
    
    request_handler = DefaultRequestHandler(
        agent_executor=GeneralWhiteAgentExecutor(agent_type=agent_type),
        task_store=InMemoryTaskStore(),
    )

    app = A2AStarletteApplication(
        agent_card=card,
        http_handler=request_handler,
    )

    uvicorn.run(app.build(), host=host, port=port)