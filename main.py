"""
Main application entry point for the Poker Evaluation Agent
"""
import asyncio
import logging
import uvicorn
from evaluation_agent import EvaluationAgent, AgentConfig, GameConfig
from web_interface import WebInterface
from a2a_protocol import A2AServer


async def main():
    """Main application entry point"""
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)
    
    # Create game configuration
    game_config = GameConfig(
        small_blind=10,
        big_blind=20,
        starting_chips=1000,
        max_hands=100,
        hand_timeout=300
    )
    
    # Create evaluation agent
    evaluation_agent = EvaluationAgent(game_config)
    
    # Create web interface
    web_interface = WebInterface(evaluation_agent)
    
    # Start the evaluation agent server
    await evaluation_agent.start_evaluation_server()
    
    # Start the web interface
    logger.info("Starting Poker Evaluation Agent...")
    logger.info("Web interface available at: http://localhost:8000")
    logger.info("A2A server running on: ws://localhost:8765")
    
    # Run the web server
    config = uvicorn.Config(
        app=web_interface.app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
    server = uvicorn.Server(config)
    
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
