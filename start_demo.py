#!/usr/bin/env python3
"""
Demo startup script for the Poker Evaluation Agent system
Starts all example agents and the evaluation agent
"""
import asyncio
import subprocess
import sys
import time
import logging
from pathlib import Path


def setup_logging():
    """Set up logging for the demo"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


async def start_agents():
    """Start all example agents"""
    logger = logging.getLogger("Demo")
    
    # Start example agents
    logger.info("Starting example agents...")
    agent_process = subprocess.Popen([
        sys.executable, "example_agents.py"
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    # Wait a moment for agents to start
    await asyncio.sleep(3)
    
    # Start evaluation agent
    logger.info("Starting evaluation agent...")
    eval_process = subprocess.Popen([
        sys.executable, "main.py"
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    logger.info("All services started!")
    logger.info("Web dashboard: http://localhost:8000")
    logger.info("Example agents running on ports 8001-8004")
    logger.info("Press Ctrl+C to stop all services")
    
    try:
        # Wait for processes
        await asyncio.gather(
            asyncio.create_task(wait_for_process(agent_process, "Agents")),
            asyncio.create_task(wait_for_process(eval_process, "Evaluation"))
        )
    except KeyboardInterrupt:
        logger.info("Shutting down services...")
        agent_process.terminate()
        eval_process.terminate()
        logger.info("All services stopped")


async def wait_for_process(process, name):
    """Wait for a process to complete"""
    while process.poll() is None:
        await asyncio.sleep(1)
    
    if process.returncode != 0:
        stdout, stderr = process.communicate()
        logger = logging.getLogger("Demo")
        logger.error(f"{name} process failed:")
        logger.error(f"STDOUT: {stdout.decode()}")
        logger.error(f"STDERR: {stderr.decode()}")


def main():
    """Main function"""
    setup_logging()
    
    # Check if we're in the right directory
    if not Path("main.py").exists():
        print("Error: Please run this script from the project root directory")
        sys.exit(1)
    
    print("🃏 Poker Evaluation Agent Demo")
    print("=" * 40)
    print("This will start:")
    print("- 4 example poker agents (ports 8001-8004)")
    print("- Evaluation agent with web dashboard (port 8000)")
    print("- A2A communication server (port 8765)")
    print()
    
    try:
        asyncio.run(start_agents())
    except KeyboardInterrupt:
        print("\nDemo stopped by user")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
