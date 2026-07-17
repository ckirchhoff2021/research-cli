from deepagents import create_deep_agent
from deepagents.backends import LocalShellBackend
from langchain_openai import ChatOpenAI

from dotenv import load_dotenv
import os
from tools.custom_tools import get_custom_tools

load_dotenv()


def create_research_agent():
    model = ChatOpenAI(
        api_key=os.getenv("BRAIN_API_KEY"),
        base_url=os.getenv("BRAIN_API_URL"),
        model=os.getenv("BRAIN_MODEL_NAME"),
        temperature=0.7,
        timeout=300000,
        streaming=True,
    )
    custom_tools = get_custom_tools()
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    agent = create_deep_agent(
        model=model,
        memory=["./memory/AGENTS.md"],
        skills=["./skills/"],
        tools=custom_tools,
        subagents=[],
        backend=LocalShellBackend(
            root_dir=base_dir,
            virtual_mode=False,
            inherit_env=True,
        )
    )
    return agent