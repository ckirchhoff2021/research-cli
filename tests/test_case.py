from langchain_core.messages import HumanMessage
from agent import create_research_agent
from datetime import datetime


def build_agent_config(thread_id: str | None = None) -> dict:
    """Build LangGraph-compatible config so runs can be grouped by thread."""
    resolved_thread_id = thread_id or f"cli-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    return {"configurable": {"thread_id": resolved_thread_id}}



if __name__ == '__main__':
    agent = create_research_agent()
    for event in agent.stream(
        {
            "messages": [
                HumanMessage(content="讲个笑话")
            ]
        },
        config=build_agent_config(),
        stream_mode="updates",
    ):
        print(type(event))
        print(event)