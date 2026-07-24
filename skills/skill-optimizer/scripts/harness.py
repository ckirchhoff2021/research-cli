from deepagents import create_deep_agent
from deepagents.backends import LocalShellBackend
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from dotenv import load_dotenv
import os
import argparse
import json

from datetime import datetime

load_dotenv()


def build_agent_config(thread_id: str | None = None) -> dict:
    """Build LangGraph-compatible config so runs can be grouped by thread."""
    resolved_thread_id = thread_id or f"cli-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    return {"configurable": {"thread_id": resolved_thread_id}}


def format_message_content(content, max_length):
    """Truncate content to max_length if needed."""
    if not content:
        return content
    if len(content) > max_length:
        return content[:max_length] + "..."
    return content


def load_tasks(task_arg):
    """Load tasks from a plain string or a JSON file."""
    if not task_arg:
        return []

    task_path = os.path.abspath(task_arg)
    if not os.path.isfile(task_path):
        return [task_arg]

    with open(task_path, "r", encoding="utf-8") as file:
        payload = json.load(file)

    tasks = []
    for item in payload:
        value = item.get('query', '')
        if len(value.strip()) > 0:
            tasks.append(value.strip())
  
    if not tasks:
        raise ValueError("Task file must be a JSON array of strings/objects or an object containing a tasks list.")
    return tasks


def parse_messages(messages):
    """Parse messages to a list of dictionaries."""
    traces = []
    for idx, msg in enumerate(messages):
        msg_type = type(msg).__name__
        
        if msg_type == "HumanMessage":
            traces.append({
                "type": "query",
                "content": msg.content
            })
        
        elif msg_type == "AIMessage":
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tool_call in msg.tool_calls:
                    tool_name = tool_call.get("name", "unknown")
                    tool_args = tool_call.get("args", {})
                    traces.append({
                        "type": "tool_call",
                        "name": tool_name,
                        "args": tool_args,
                        "content": None
                    })
            elif msg.content:
                traces.append({
                    "type": "output" if idx == len(messages) - 1 else "thinking",
                    "content": msg.content
                })
        elif msg_type == "ToolMessage":
            if traces and traces[-1]["type"] == "tool_call":
                traces[-1]["result"] = format_message_content(msg.content, 500)
        else:
            print(f"Warning: Unknown message_type: {msg_type}")
            continue
        
    return traces


def create_research_agent(args):
    model = ChatOpenAI(
        api_key=os.getenv("BRAIN_API_KEY"),
        base_url=os.getenv("BRAIN_API_URL"),
        model=os.getenv("BRAIN_MODEL_NAME"),
        temperature=0.7,
        timeout=300000,
        streaming=True,
    )
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    memory = os.path.join(base_dir, "assets/optimizer.md")
    agent = create_deep_agent(
        model=model,
        memory=[memory],
        skills=[args.skill],
        tools=[],
        subagents=[],
        backend=LocalShellBackend(
            root_dir=base_dir,
            virtual_mode=False,
            inherit_env=True,
        )
    )
    return agent


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Skill Optimizer Harness")
    parser.add_argument("--skill", type=str, required=True, help="target skill path")
    parser.add_argument("--task", type=str, required=True, help="prompt to execute the task")
    parser.add_argument("--trace_file", type=str, default=None, help="path to save traces to")    
    
    args = parser.parse_args()
    tasks = load_tasks(args.task)

    agent = create_research_agent(args)
    all_results = []
    for i, task in enumerate(tasks):
        print(f"Processing task {i+1}/{len(tasks)}: {task}")
        
        result = agent.invoke(
            {
                "messages": [
                    HumanMessage(
                        content=task
                    )
                ]
            },
            config=build_agent_config(None)
        )
        traces = parse_messages(result["messages"])
        all_results.append({
            "task": task,
            "traces": traces
        })
        
    trace_file = args.trace_file
    if args.trace_file is None:
        trace_file = f"trace_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
  
    print(f"Saving traces to {trace_file}")
    with open(trace_file, "w", encoding="utf-8") as file:
        json.dump(all_results, file, indent=2, ensure_ascii=False)
