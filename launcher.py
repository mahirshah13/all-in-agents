#!/usr/bin/env python3
"""
Poker Agentify Launcher
Single launcher script for starting green and white agents
"""
import asyncio
import logging
import sys
import argparse
from pathlib import Path
import os
import dotenv

# Load environment variables
dotenv.load_dotenv()

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.green_agent.assessment_manager import PokerAssessmentManager, start_green_agent
from src.white_agent.poker_player import GeneralWhiteAgentExecutor, start_white_agent


async def start_green_agent_only():
    """Start only the green agent (assessment manager)"""
    print("🟢 Starting Green Agent (Assessment Manager)...")
    print("=" * 50)
    
    # Load configuration
    config_path = "src/green_agent/agent_card.toml"
    try:
        import toml
        with open(config_path, 'r') as f:
            config = toml.load(f)
    except Exception as e:
        print(f"❌ Error loading config from {config_path}: {e}")
        return
    
    # Create assessment manager
    assessment_manager = PokerAssessmentManager(config)
    
    try:
        # Start the A2A server
        print(f"🚀 Starting A2A server on {config['communication']['endpoint']}")
        print("📡 Server will be available for A2A communication")
        print("🛑 Press Ctrl+C to stop the server")
        print("=" * 50)
        
        await assessment_manager.start_a2a_server()
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
    except Exception as e:
        print(f"❌ Error starting server: {e}")
        raise


def start_white_agent_only(agent_id: str, port: int):
    """Start only a specific white agent"""
    print(f"⚪ Starting White Agent: {agent_id} on port {port}")
    print("=" * 50)
    
    try:
        # Start the A2A server using the existing function
        print(f"🚀 Starting A2A server on http://localhost:{port}")
        print("📡 Server will be available for A2A communication")
        print("🛑 Press Ctrl+C to stop the server")
        print("=" * 50)
        
        start_white_agent(agent_name=agent_id, host="localhost", port=port)
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
    except Exception as e:
        print(f"❌ Error starting server: {e}")
        raise




async def start_full_system():
    """Start the complete evaluation system (green agent A2A server + evaluation)"""
    import subprocess
    import time
    
    # Load configuration to get white agents
    config_path = "src/green_agent/agent_card.toml"
    try:
        import toml
        with open(config_path, 'r') as f:
            config = toml.load(f)
    except Exception as e:
        print(f"❌ Error loading config from {config_path}: {e}")
        return
    
    # Start white agents in background
    white_agent_processes = []
    try:
        print("🚀 Starting white agents...")
        for agent_data in config["evaluation"]["white_agents"]:
            agent_id = agent_data["id"]
            port = int(agent_data["url"].split(":")[-1])
            
            print(f"⚪ Starting {agent_data['name']} on port {port}")
            
            # Start white agent in background process
            process = subprocess.Popen([
                "python", "launcher.py", 
                "--white-only", 
                "--agent-id", agent_id, 
                "--port", str(port)
            ])
            white_agent_processes.append(process)
            
            # Wait a bit between starting agents
            time.sleep(2)
        
        print("✅ All white agents started")
        print("🔄 Starting green agent and evaluation...")
        
        # Start green agent (this will run the evaluation)
        await start_green_agent()
        
    except KeyboardInterrupt:
        print("\n🛑 System stopped by user")
    except Exception as e:
        print(f"❌ Error during system startup: {e}")
        raise
    finally:
        # Clean up white agent processes
        print("🧹 Cleaning up white agent processes...")
        for process in white_agent_processes:
            try:
                process.terminate()
                process.wait(timeout=5)
            except:
                process.kill()


def main():
    """Main entry point with command line arguments"""
    parser = argparse.ArgumentParser(
        description="Poker Agentify - Poker Agent Evaluation System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python launcher.py                    # Start complete evaluation system
  python launcher.py --green-only      # Start only green agent A2A server
  python launcher.py --white-only --agent-id random_1 --port 8001  # Start white agent
        """
    )
    
    parser.add_argument(
        "--green-only", 
        action="store_true", 
        help="Start only the green agent A2A server"
    )
    parser.add_argument(
        "--white-only", 
        action="store_true", 
        help="Start only a white agent A2A server"
    )
    parser.add_argument(
        "--agent-id", 
        type=str, 
        help="Agent ID for white agent (required with --white-only)"
    )
    parser.add_argument(
        "--port", 
        type=int, 
        default=8001, 
        help="Port for white agent (default: 8001)"
    )
    
    args = parser.parse_args()
    
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    try:
        if args.green_only:
            asyncio.run(start_green_agent_only())
        elif args.white_only:
            if not args.agent_id:
                print("❌ Agent ID required for white agent launch")
                print("Usage: python launcher.py --white-only --agent-id <agent_id> [--port <port>]")
                sys.exit(1)
            start_white_agent_only(args.agent_id, args.port)
        else:
            # Default: start full system
            asyncio.run(start_full_system())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
