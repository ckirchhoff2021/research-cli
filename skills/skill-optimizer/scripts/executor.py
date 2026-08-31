from deepagents import create_deep_agent
from deepagents.backends import LocalShellBackend
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

import os
import argparse
import json
import uuid

from datetime import datetime
from common import ensure_brain_api_config


def build_agent_config(thread_id: str | None = None) -> dict:
    """Build LangGraph-compatible config so runs can be grouped by thread."""
    resolved_thread_id = thread_id or (
        f"cli-{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{uuid.uuid4().hex[:8]}"
    )
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
        task_text = task_arg.strip()
        return [{"task": task_text, "expected": ""}] if task_text else []

    with open(task_path, "r", encoding="utf-8") as file:
        payload = json.load(file)

    if isinstance(payload, dict):
        if "query" in payload:
            payload = [payload]
        elif "tasks" in payload:
            payload = payload["tasks"]
        else:
            raise ValueError("Task object must contain either a query field or a tasks list.")

    if not isinstance(payload, list):
        raise ValueError("Task file must contain a JSON array or object.")

    tasks = []
    for item in payload:
        if isinstance(item, str):
            value = item.strip()
            if value:
                tasks.append({"task": value, "expected": ""})
            continue

        if isinstance(item, dict):
            value = item.get("query", "").strip()
            if value:
                expected = item.get("expected", "").strip()
                tasks.append({"task": value, "expected": expected})
  
    if not tasks:
        raise ValueError(
            "Task file must contain a JSON array, a query object, or an object containing a tasks list."
        )
    return tasks


def parse_messages(messages):
    """Parse messages to a list of dictionaries."""
    traces = []
    tool_calls_by_id = {}
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
                    tool_call_id = tool_call.get("id")
                    trace = {
                        "type": "tool_call",
                        "name": tool_name,
                        "args": tool_args,
                        "content": None
                    }
                    if tool_call_id:
                        trace["id"] = tool_call_id
                        tool_calls_by_id[tool_call_id] = trace
                    traces.append(trace)
            elif msg.content:
                traces.append({
                    "type": "output" if idx == len(messages) - 1 else "thinking",
                    "content": msg.content
                })
        elif msg_type == "ToolMessage":
            tool_call_id = getattr(msg, "tool_call_id", None)
            tool_call_trace = tool_calls_by_id.get(tool_call_id)
            if tool_call_trace is None:
                tool_call_trace = next(
                    (
                        trace for trace in traces
                        if trace["type"] == "tool_call" and "result" not in trace
                    ),
                    None,
                )
            if tool_call_trace is not None:
                tool_call_trace["result"] = format_message_content(msg.content, 500)
        else:
            print(f"Warning: Unknown message_type: {msg_type}")
            continue
        
    return traces


def create_research_agent(args):
    brain_api = ensure_brain_api_config()
    model = ChatOpenAI(
        api_key=brain_api["BRAIN_API_KEY"],
        base_url=brain_api["BRAIN_API_URL"],
        model=brain_api["BRAIN_MODEL_NAME"],
        temperature=0.7,
        timeout=300000,
        streaming=True,
    )
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    skill_root = os.path.dirname(base_dir)
    backend_root = os.path.abspath(args.root_dir)
    memory = os.path.join(skill_root, "assets", "optimizer.md")
    agent = create_deep_agent(
        model=model,
        memory=[memory],
        skills=[args.skill],
        tools=[],
        subagents=[],
        backend=LocalShellBackend(
            root_dir=backend_root,
            virtual_mode=False,
            inherit_env=True,
        )
    )
    return agent


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Skill Optimizer Harness")
    parser.add_argument("--skill", type=str, required=True, help="Directory containing the target Skill package")
    parser.add_argument("--task", type=str, required=True, help="prompt to execute the task")
    parser.add_argument("--trace_file", type=str, default=None, help="path to save traces to")
    parser.add_argument(
        "--root_dir",
        type=str,
        default=None,
        help="Working directory for LocalShellBackend; defaults to --skill when omitted",
    )
    
    args = parser.parse_args()
    args.skill = os.path.abspath(args.skill)
    if not os.path.isdir(args.skill):
        raise NotADirectoryError(f"skill must be an existing directory, got: {args.skill}")
    if args.root_dir is None:
        args.root_dir = args.skill
    if not os.path.isdir(args.root_dir):
        raise NotADirectoryError(f"root_dir must be an existing directory, got: {args.root_dir}")
    tasks = load_tasks(args.task)

    agent = create_research_agent(args)
    all_results = []
    for i, task in enumerate(tasks):
        print(f"Processing task {i+1}/{len(tasks)}: {task}")
        thread_id = f"task_{i+1}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{uuid.uuid4().hex[:8]}"
        
        try:
            result = agent.invoke(
                {
                    "messages": [
                        HumanMessage(
                            content=task["task"]
                        )
                    ]
                },
                config=build_agent_config(thread_id)
            )
            traces = parse_messages(result["messages"])
            all_results.append({
                "task": task["task"],
                "expected": task["expected"],
                "thread_id": thread_id,
                "traces": traces
            })
        except Exception as e:
            error = f"{type(e).__name__}: {e!r}"
            print(f"Error processing task {task['task']!r}: {error}")
            all_results.append({
                "task": task["task"],
                "expected": task["expected"],
                "thread_id": thread_id,
                "error": error,
                "traces": [
                    {
                        "type": "query",
                        "content": task["task"],
                    },
                    {
                        "type": "error",
                        "content": error,
                    },
                ],
            })
        
    trace_file = args.trace_file
    if args.trace_file is None:
        trace_file = f"trace_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    trace_dir = os.path.dirname(os.path.abspath(trace_file))
    if trace_dir:
        os.makedirs(trace_dir, exist_ok=True)

    print(f"Saving traces to {trace_file}")
    with open(trace_file, "w", encoding="utf-8") as file:
        json.dump(all_results, file, indent=2, ensure_ascii=False)
