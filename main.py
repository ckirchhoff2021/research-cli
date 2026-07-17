import argparse
from langchain_core.messages import HumanMessage
from agent import create_research_agent
import json

from rich.console import Console, Group
from rich.panel import Panel
from rich.tree import Tree
from rich.text import Text
from rich.style import Style

from datetime import datetime


def build_agent_config(thread_id: str | None = None) -> dict:
    """Build LangGraph-compatible config so runs can be grouped by thread."""
    resolved_thread_id = thread_id or f"cli-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    return {"configurable": {"thread_id": resolved_thread_id}}


def format_message_content(content, max_length=500):
    if content is None:
        return ""
    text = str(content)
    if len(text) > max_length:
        return text[:max_length] + "..."
    return text


def display_agent_process(result, console):
    process_list = []
    messages = result.get("messages", [])
    
    for _, msg in enumerate(messages[:-1]):
        msg_type = type(msg).__name__
        
        if msg_type == "HumanMessage":
            continue
        
        elif msg_type == "AIMessage":
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tool_call in msg.tool_calls:
                    tool_name = tool_call.get("name", "unknown")
                    tool_args = tool_call.get("args", {})
                    process_list.append({
                        "type": "tool_call",
                        "name": tool_name,
                        "args": tool_args,
                        "content": None
                    })
            elif msg.content:
                process_list.append({
                    "type": "thinking",
                    "content": msg.content
                })
        elif msg_type == "ToolMessage":
            if process_list and process_list[-1]["type"] == "tool_call":
                process_list[-1]["result"] = format_message_content(msg.content, 500)
    
    if process_list:
        tree = Tree("[bold blue]Agent Process[/bold blue]")
        
        for idx, step in enumerate(process_list, 1):
            if step["type"] == "thinking":
                node = tree.add(f"[dim]Step {idx}:[/dim] [italic yellow]Thinking...[/italic yellow]")
                content = format_message_content(step["content"], 500)
                node.add(f"[dim]{content}[/dim]")
            elif step["type"] == "tool_call":
                node = tree.add(f"[dim]Step {idx}:[/dim] [bold cyan]Tool Call: {step['name']}[/bold cyan]")
                args_str = str(step.get("args", {}))
                if len(args_str) > 500:
                    args_str = args_str[:500] + "..."
                node.add(f"[dim]Args: {args_str}[/dim]")
                if step.get("result"):
                    result_node = node.add("[green]Result:[/green]")
                    result_node.add(f"[dim]{step['result']}[/dim]")
        
        console.print(tree)
        console.print()


def rich_console_call(args):
    console = Console()
    console.print(
        Panel(f"[bold cyan]Task:[/bold cyan] {args.task_prompt}", border_style="cyan")
    )
    console.print()
    console.print("[dim]Creating Research Agent...[/dim]") 
    
    agent = create_research_agent()
    console.print("[dim]Processing query...[/dim]\n")
     
    result = agent.invoke(
        {
            "messages": [
                HumanMessage(
                    content= args.task_prompt  
                )
            ]
        },
        config=build_agent_config(args.thread_id)
    )
    
    display_agent_process(result, console)

    final_message = result["messages"][-1]
    answer = (
        final_message.content
        if hasattr(final_message, "content")
        else str(final_message)
    )
    console.print(
        Panel(f"[bold green]Answer:[/bold green]\n\n{answer}", border_style="green")
    )


def normal_call(args):
    agent = create_research_agent()
    result = agent.invoke(
        {
            "messages": [
                HumanMessage(
                    content= args.task_prompt  
                )
            ]
        },
        config=build_agent_config(args.thread_id)
    )
    print(result)
    final_message = result["messages"][-1]
    answer = (
        final_message.content
        if hasattr(final_message, "content")
        else str(final_message)
    )
    print(answer)
    

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="research-cli")
    parser.add_argument("--task_prompt", type=str, required=True, help="prompt to execute the task")
    parser.add_argument(
        "--console", "-c",
        action="store_true",
        help="Show rich console output",
    )
    parser.add_argument(
        "--thread-id",
        type=str,
        default=None,
        help="Optional thread id for LangSmith/LangGraph tracing",
    )
    args = parser.parse_args()
    
    if args.console:
        rich_console_call(args)
    else:
        normal_call(args)