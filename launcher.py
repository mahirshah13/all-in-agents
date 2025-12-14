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

from src.green_agent.assessment_manager import PokerAssessmentManager, start_green_agent, start_green_agent_sync
from src.white_agent.poker_player import GeneralWhiteAgentExecutor, start_white_agent


class PokerAgentifySettings:
    """Settings class similar to TaubenchSettings - reads from environment variables"""
    def __init__(self):
        self.role: str = os.getenv("ROLE", "unspecified")
        self.host: str = os.getenv("HOST", "127.0.0.1")
        self.agent_port: int = int(os.getenv("AGENT_PORT", "9000"))
        self.agent_name: str = os.getenv("AGENT_NAME", "agent_card")


async def start_green_agent_only(agent_name: str = None, host: str = None, port: int = None, run_evaluation: bool = False):
    """
    Start only the green agent (assessment manager) without running evaluation.
    
    Args:
        agent_name: Name of the agent card file (without .toml extension)
        host: Host to bind the server to
        port: Port to bind the server to
        run_evaluation: Whether to run evaluation (default: False for server-only mode)
    """
    print("🟢 Starting Green Agent (Assessment Manager)...")
    print("=" * 50)
    
    # Use provided values or load from config
    if agent_name is None or host is None or port is None:
        # Load configuration to get defaults
        config_path = "src/green_agent/agent_card.toml"
        try:
            import toml
            with open(config_path, 'r') as f:
                config = toml.load(f)
        except Exception as e:
            print(f"❌ Error loading config from {config_path}: {e}")
            return
        
        if agent_name is None:
            agent_name = "agent_card"
        if host is None:
            # Extract host from endpoint or use default
            endpoint = config.get("communication", {}).get("endpoint", "http://localhost:9000")
            host = endpoint.split("://")[1].split(":")[0] if "://" in endpoint else "localhost"
        if port is None:
            # Extract port from endpoint or use default
            endpoint = config.get("communication", {}).get("endpoint", "http://localhost:9000")
            port = int(endpoint.split(":")[-1]) if ":" in endpoint else 9000
    
    try:
        # Start the A2A server using the new parameterized function
        print(f"🚀 Starting A2A server on http://{host}:{port}")
        print("📡 Server will be available for A2A communication")
        print("🛑 Press Ctrl+C to stop the server")
        print("=" * 50)
        
        await start_green_agent(agent_name=agent_name, host=host, port=port, run_evaluation=run_evaluation)
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
    except Exception as e:
        print(f"❌ Error starting server: {e}")
        raise


def start_white_agent_only(agent_id: str, port: int, agent_type: str = "openai"):
    """Start only a specific white agent"""
    print(f"⚪ Starting White Agent: {agent_id} (type: {agent_type}) on port {port}")
    print("=" * 50)
    
    try:
        # Start the A2A server using the existing function
        print(f"🚀 Starting A2A server on http://localhost:{port}")
        print("📡 Server will be available for A2A communication")
        print("🛑 Press Ctrl+C to stop the server")
        print("=" * 50)
        
        start_white_agent(agent_name=agent_id, host="localhost", port=port, agent_type=agent_type)
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
    except Exception as e:
        print(f"❌ Error starting server: {e}")
        raise




async def start_full_system(agent_name: str = None, host: str = None, port: int = None):
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
    
    # Start frontend server in background (optional)
    frontend_process = None
    try:
        print("🌐 Starting frontend server...")
        frontend_process = subprocess.Popen([
            sys.executable, "frontend_server.py"
        ])
        print("✅ Frontend server started on http://localhost:8080")
        time.sleep(1)  # Give frontend server time to start
    except Exception as e:
        print(f"⚠️  Could not start frontend server: {e}")
        print("   You can start it manually: python frontend_server.py")
    
    # Start ALL available white agents (6 total) so they're ready for selection
    white_agent_processes = []
    try:
        print("🚀 Starting all available white agents...")
        
        # All 6 available agents
        all_agents = [
            {"id": "tagbot", "name": "TAGBot", "type": "tagbot", "port": 8001},
            {"id": "montecarlo", "name": "Monte Carlo", "type": "montecarlo", "port": 8002},
            {"id": "maniac", "name": "Maniac", "type": "maniac", "port": 8003},
            {"id": "smart_agent", "name": "Smart Agent", "type": "smart", "port": 8004},
            {"id": "equity", "name": "Equity Calculator", "type": "equity", "port": 8005},
            {"id": "adaptive", "name": "Adaptive Heuristic", "type": "adaptive", "port": 8006}
        ]
        
        for agent_data in all_agents:
            agent_id = agent_data["id"]
            agent_type = agent_data["type"]
            port = agent_data["port"]
            
            print(f"⚪ Starting {agent_data['name']} (type: {agent_type}) on port {port}")
            
            # Start white agent in background process
            process = subprocess.Popen([
                sys.executable, "launcher.py", 
                "--white-only", 
                "--agent-id", agent_id, 
                "--port", str(port),
                "--agent-type", agent_type
            ])
            white_agent_processes.append(process)
            
            # Wait a bit between starting agents
            time.sleep(2)
        
        print("✅ All white agents started")
        print("🔄 Starting green agent and evaluation...")
        
        # Start green agent (this will run the evaluation)
        # Use green_port to avoid conflict with white agent port variable
        green_port = port if port is not None else 9000
        await start_green_agent(
            agent_name=agent_name or "agent_card",
            host=host or "localhost",
            port=green_port,
            run_evaluation=True
        )
        
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
        
        # Clean up frontend server
        if frontend_process:
            try:
                print("🧹 Cleaning up frontend server...")
                frontend_process.terminate()
                frontend_process.wait(timeout=5)
            except:
                frontend_process.kill()


def run_from_env():
    """
    Run agent based on environment variables (similar to tau_bench's 'run' command).
    Reads ROLE, HOST, AGENT_PORT, and AGENT_NAME from environment.
    """
    settings = PokerAgentifySettings()
    if settings.role == "green":
        start_green_agent_sync(
            agent_name=settings.agent_name,
            host=settings.host,
            port=settings.agent_port,
            run_evaluation=False  # Server-only mode when run from env
        )
    elif settings.role == "white":
        # For white agent, we'd need agent_id from env or config
        agent_id = os.getenv("AGENT_ID", "general_white_agent")
        agent_type = os.getenv("AGENT_TYPE", "openai")
        start_white_agent_only(agent_id, settings.agent_port, agent_type)
    else:
        raise ValueError(f"Unknown role: {settings.role}. Set ROLE environment variable to 'green' or 'white'")


def main():
    """Main entry point with command line arguments"""
    parser = argparse.ArgumentParser(
        description="Poker Agentify - Poker Agent Evaluation System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python launcher.py                    # Start complete evaluation system
  python launcher.py --green-only      # Start only green agent A2A server
  python launcher.py --green-only --host 0.0.0.0 --port 9001  # Start green agent with custom host/port
  python launcher.py --white-only --agent-id random_1 --port 8001  # Start white agent
  python launcher.py run                # Run based on environment variables (ROLE, HOST, AGENT_PORT)
        """
    )
    
    parser.add_argument(
        "command",
        nargs="?",
        choices=["run"],
        help="Command to run. 'run' reads from environment variables (ROLE, HOST, AGENT_PORT)"
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
        "--agent-name",
        type=str,
        help="Agent card name for green agent (without .toml extension, default: 'agent_card')"
    )
    parser.add_argument(
        "--host",
        type=str,
        help="Host to bind the server to (default: from config or 'localhost')"
    )
    parser.add_argument(
        "--port", 
        type=int, 
        help="Port for the agent (default: from config or 9000 for green, 8001 for white)"
    )
    parser.add_argument(
        "--agent-type", 
        type=str, 
        default="openai", 
        help="Agent type: random, conservative, aggressive, smart, openai (default: openai)"
    )
    parser.add_argument(
        "--no-evaluation",
        action="store_true",
        help="Don't run evaluation automatically (server-only mode for green agent)"
    )
    
    args = parser.parse_args()
    
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    try:
        # Handle 'run' command (similar to tau_bench)
        if args.command == "run":
            run_from_env()
        elif args.green_only:
            asyncio.run(start_green_agent_only(
                agent_name=args.agent_name,
                host=args.host,
                port=args.port,
                run_evaluation=not args.no_evaluation
            ))
        elif args.white_only:
            if not args.agent_id:
                print("❌ Agent ID required for white agent launch")
                print("Usage: python launcher.py --white-only --agent-id <agent_id> [--port <port>] [--agent-type <type>]")
                sys.exit(1)
            start_white_agent_only(
                args.agent_id,
                args.port or 8001,
                args.agent_type
            )
        else:
            # Default: start full system
            asyncio.run(start_full_system(
                agent_name=args.agent_name,
                host=args.host,
                port=args.port
            ))
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
