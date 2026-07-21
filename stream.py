import sys
import os
import json
import time
import copy
from datetime import datetime

from dotenv import load_dotenv

from langchain_core.messages import HumanMessage
from agent import create_research_agent

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.tree import Tree
from rich.markdown import Markdown
from rich.text import Text


MAX_ARGS_DISPLAY_LENGTH = 3000
MAX_RESULT_DISPLAY_LENGTH = 3000
MAX_THINKING_DISPLAY_LENGTH = 3000
MAX_FINAL_RESPONSE_DISPLAY_LENGTH = 5000


def build_agent_config(thread_id: str | None = None) -> dict:
    resolved_thread_id = thread_id or f"cli-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    return {"configurable": {"thread_id": resolved_thread_id}}


def normalize_message_content(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if text:
                    parts.append(str(text))
            elif item is not None:
                parts.append(str(item))
        return "\n".join(part for part in parts if part).strip()
    if isinstance(content, dict):
        return str(content.get("text") or content.get("content") or content)
    if content is None:
        return ""
    return str(content)


def truncate_text(value: str, max_length: int) -> str:
    value = normalize_message_content(value)
    if len(value) <= max_length:
        return value
    return value[: max_length - 3] + "..."


def merge_stream_response(existing: str, incoming: str) -> str:
    if not incoming:
        return existing
    if not existing:
        return incoming
    if incoming == existing:
        return existing
    if incoming.startswith(existing):
        return incoming
    if existing.startswith(incoming):
        return existing

    max_overlap = min(len(existing), len(incoming))
    for overlap in range(max_overlap, 0, -1):
        if existing.endswith(incoming[:overlap]):
            return existing + incoming[overlap:]

    separator = "" if existing.endswith(("\n", " ")) or incoming.startswith(("\n", " ")) else "\n"
    return existing + separator + incoming


def shorten_path(path_str: str) -> str:
    try:
        cwd = os.getcwd()
        if path_str.startswith(cwd):
            return "./" + os.path.relpath(path_str, cwd)
        home = os.path.expanduser("~")
        if path_str.startswith(home):
            return "~" + path_str[len(home):]
    except (ValueError, OSError):
        pass
    return path_str


def format_args(args: dict) -> str:
    formatted = {}
    for k, v in args.items():
        if isinstance(v, str) and ("/" in v or "\\" in v) and len(v) > 60:
            formatted[k] = shorten_path(v)
        else:
            formatted[k] = v
    try:
        raw = json.dumps(formatted, ensure_ascii=False, indent=2)
    except Exception:
        raw = str(formatted)
    if len(raw) > MAX_ARGS_DISPLAY_LENGTH:
        raw = raw[:MAX_ARGS_DISPLAY_LENGTH] + "..."
    return raw


def detect_tool_icon(name: str, args: dict) -> tuple[str, str]:
    if name in ("execute", "run_command", "shell", "bash"):
        return "⚡", "magenta"
    if name in ("read_file", "read"):
        return "📖", "cyan"
    if name in ("write_file", "write", "edit_file", "edit"):
        return "✏️", "green"
    if name in ("ls", "glob", "grep", "find"):
        return "🔍", "dim cyan"
    if name in ("mkdir", "rm", "cp", "mv"):
        return "📁", "yellow"
    if name == "write_todos":
        return "📋", "dim"
    return "🔧", "cyan"


def is_skill_read(name: str, args: dict) -> bool:
    if name != "read_file":
        return False
    file_path = args.get("file_path", "")
    return "/skills/" in file_path and ("SKILL.md" in file_path or "AGENTS.md" in file_path)


def format_tool_result(name: str, args: dict, result: str) -> str:
    if is_skill_read(name, args):
        line_count = result.count("\n") + 1
        return f"📖 已加载技能配置 ({line_count} 行)"
    return result


def detect_error(result_text: str) -> bool:
    if not result_text:
        return False
    error_markers = ["Traceback", "Error:", "Exception:", "Exit code: 1", "Command failed", "No such file", "Permission denied"]
    return any(marker in result_text for marker in error_markers)


class TraceWriter:
    def __init__(self, task_prompt: str, output_dir: str = "traces", flush_interval: float = 1.0):
        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.filepath = os.path.join(output_dir, f"trace_{timestamp}.json")
        self.start_time = time.time()
        self.flush_interval = flush_interval
        self._last_flush = 0.0
        self._dirty = False
        self.data = {
            "timestamp": datetime.now().isoformat(),
            "task": task_prompt,
            "status": "running",
            "elapsed_seconds": 0,
            "final_response": "",
            "total_steps": 0,
            "steps": [],
            "tool_calls": [],
            "tool_results": [],
        }
        self._write(force=True)

    def update(self, process_steps: list, full_response: str, tool_calls: list, tool_results: list):
        self.data["steps"] = copy.deepcopy(process_steps)
        self.data["final_response"] = full_response
        self.data["tool_calls"] = copy.deepcopy(tool_calls)
        self.data["tool_results"] = copy.deepcopy(tool_results)
        self.data["total_steps"] = len(process_steps)
        self.data["elapsed_seconds"] = round(time.time() - self.start_time, 2)
        self._dirty = True
        self._write()

    def finish(self, full_response: str, status: str = "completed"):
        self.data["status"] = status
        self.data["final_response"] = full_response
        self.data["elapsed_seconds"] = round(time.time() - self.start_time, 2)
        self._dirty = True
        self._write(force=True)

    def _write(self, force: bool = False):
        now = time.time()
        if not force and (not self._dirty or now - self._last_flush < self.flush_interval):
            return
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            self._last_flush = now
            self._dirty = False
        except Exception:
            pass


def build_tree(process_steps: list, final_response: str = "", elapsed: float = 0, running: bool = False) -> Tree:
    tree_label = "[bold blue]🤖 Agent 执行过程[/bold blue]"
    if running:
        tree_label = "[bold blue]🤖 Agent 执行过程[/bold blue] [dim](streaming...)[/dim]"
    tree = Tree(tree_label)

    turn_index = 0
    for step in process_steps:
        if step["type"] == "thinking":
            turn_index += 1
            content = truncate_text(step["content"], MAX_THINKING_DISPLAY_LENGTH)
            label = f"💭 Turn {turn_index} 思考"
            node = tree.add(f"[italic yellow]{label}[/italic yellow]")
            node.add(Text(content, style="dim white"))
        elif step["type"] == "tool_call":
            icon, color = detect_tool_icon(step["name"], step.get("args", {}))
            is_error = step.get("is_error", False)
            if is_error:
                name_style = "[bold red]"
                status_icon = "❌"
            elif step.get("in_progress"):
                name_style = f"[bold {color}]"
                status_icon = "⏳"
            else:
                name_style = f"[bold {color}]"
                status_icon = icon

            node = tree.add(f"{name_style}{status_icon} {step['name']}[/]")
            args_str = format_args(step.get("args", {}))
            node.add(Text(f"📥 参数:\n{args_str}", style="dim white"))

            if step.get("result") is not None:
                result = step["result"]
                display_result = format_tool_result(step["name"], step.get("args", {}), result)
                if display_result == result:
                    display_result = truncate_text(result, MAX_RESULT_DISPLAY_LENGTH)
                result_style = "dim red" if is_error else "dim white"
                result_node = node.add("[green]📤 结果:[/green]")
                result_node.add(Text(display_result, style=result_style))

    if final_response:
        final_node = tree.add("[bold green]✅ 最终回复[/bold green]")
        display_final = truncate_text(final_response, MAX_FINAL_RESPONSE_DISPLAY_LENGTH)
        try:
            final_node.add(Markdown(display_final))
        except Exception:
            final_node.add(Text(display_final, style="white"))

    if elapsed > 0:
        tree.add(f"[dim]⏱️  耗时: {elapsed:.1f}s[/dim]")

    return tree


def rich_console_stream_call(task_prompt: str, thread_id: str | None = None):
    load_dotenv()

    import sys
    sys.stdout.reconfigure(line_buffering=True)

    console = Console(force_terminal=True, force_interactive=True)

    def do_flush():
        if hasattr(console, 'file') and console.file:
            console.file.flush()

    start_time = time.time()
    trace_writer = None
    process_steps = []
    tool_calls = []
    tool_results = []
    full_response = ""
    try:
        console.print(Panel(f"[bold cyan]📝 Task:[/bold cyan] {task_prompt}", border_style="cyan"))
        do_flush()

        init_tree = Tree("[bold blue]🤖 Agent 执行过程[/bold blue]")
        init_tree.add("[dim]🔄 正在初始化 Research Agent...[/dim]")

        with Live(init_tree, console=console, refresh_per_second=10, transient=False) as live:
            agent = create_research_agent()

            trace_writer = TraceWriter(task_prompt)

            process_steps.clear()
            pending_tool_calls = {}
            tool_calls.clear()
            tool_results.clear()
            full_response = ""

            waiting_tree = Tree("[bold blue]🤖 Agent 执行过程[/bold blue]")
            waiting_tree.add("[dim]⏳ 等待 Agent 响应...[/dim]")
            live.update(waiting_tree)

            try:
                for event in agent.stream(
                    {
                        "messages": [
                            HumanMessage(content=task_prompt)
                        ]
                    },
                    config=build_agent_config(thread_id),
                    stream_mode="updates",
                ):
                    has_new_output = False

                    for node_name, node_output in event.items():
                        if not isinstance(node_output, dict):
                            continue

                        messages = node_output.get("messages", [])
                        if not isinstance(messages, list):
                            continue

                        for msg in messages:
                            msg_type = type(msg).__name__

                            if msg_type == "AIMessage":
                                content_text = normalize_message_content(msg.content)
                                if content_text:
                                    display_text = truncate_text(content_text, MAX_THINKING_DISPLAY_LENGTH)

                                    if process_steps and process_steps[-1]["type"] == "thinking":
                                        process_steps[-1]["content"] = display_text
                                    else:
                                        process_steps.append({
                                            "type": "thinking",
                                            "content": display_text,
                                        })

                                    merged = merge_stream_response(full_response, content_text)
                                    if merged != full_response:
                                        full_response = merged
                                        has_new_output = True

                                if hasattr(msg, "tool_calls") and msg.tool_calls:
                                    for tc in msg.tool_calls:
                                        tool_name = tc.get("name", "unknown")
                                        tool_args = tc.get("args", {})
                                        tool_id = tc.get("id", "")
                                        tool_call = {"name": tool_name, "args": tool_args, "id": tool_id}
                                        tool_calls.append(tool_call)
                                        pending_tool_calls[tool_id] = {"name": tool_name, "step_idx": len(process_steps)}
                                        process_steps.append({
                                            "type": "tool_call",
                                            "name": tool_name,
                                            "args": tool_args,
                                            "result": None,
                                            "in_progress": True,
                                            "is_error": False,
                                            "tool_id": tool_id,
                                        })
                                        has_new_output = True

                            elif msg_type == "ToolMessage":
                                result_text = normalize_message_content(msg.content)
                                tool_results.append(result_text)
                                tool_call_id = getattr(msg, "tool_call_id", "")
                                matched = False
                                if tool_call_id and tool_call_id in pending_tool_calls:
                                    info = pending_tool_calls.pop(tool_call_id)
                                    step_idx = info["step_idx"]
                                    display_result = truncate_text(result_text, MAX_RESULT_DISPLAY_LENGTH)
                                    if 0 <= step_idx < len(process_steps):
                                        process_steps[step_idx]["result"] = display_result
                                        process_steps[step_idx]["in_progress"] = False
                                        process_steps[step_idx]["is_error"] = detect_error(result_text)
                                        matched = True
                                if not matched and pending_tool_calls:
                                    first_id = next(iter(pending_tool_calls))
                                    info = pending_tool_calls.pop(first_id)
                                    step_idx = info["step_idx"]
                                    display_result = truncate_text(result_text, MAX_RESULT_DISPLAY_LENGTH)
                                    if 0 <= step_idx < len(process_steps):
                                        process_steps[step_idx]["result"] = display_result
                                        process_steps[step_idx]["in_progress"] = False
                                        process_steps[step_idx]["is_error"] = detect_error(result_text)
                                has_new_output = True

                    if has_new_output and process_steps:
                        elapsed = time.time() - start_time
                        tree = build_tree(process_steps, full_response, elapsed, running=True)
                        live.update(tree)
                        do_flush()
                        trace_writer.update(process_steps, full_response, tool_calls, tool_results)

                elapsed = time.time() - start_time
                if not full_response and tool_results:
                    full_response = tool_results[-1] if tool_results else "Done."
                tree = build_tree(process_steps, full_response, elapsed, running=False)
                live.update(tree)

            except KeyboardInterrupt:
                elapsed = time.time() - start_time
                if trace_writer:
                    trace_writer.finish(full_response, status="interrupted")
                console.print()
                console.print(Panel(
                    f"[bold yellow]⚠️  用户中断任务[/bold yellow]\n[dim]已耗时: {elapsed:.1f}s[/dim]",
                    border_style="yellow"
                ))
                return

        elapsed = time.time() - start_time
        console.print()
        console.print(Panel(
            f"[bold green]✨ 任务完成![/bold green]\n[dim]总耗时: {elapsed:.1f}s[/dim]",
            border_style="green"
        ))

        if trace_writer:
            trace_writer.finish(full_response, status="completed")
            console.print(f"[dim]📁 执行轨迹已保存: {trace_writer.filepath}[/dim]")

    except Exception as e:
        if trace_writer:
            trace_writer.finish(full_response, status="error")
        console.print()
        console.print(Panel(
            f"[bold red]❌ 执行出错[/bold red]\n{type(e).__name__}: {str(e)}",
            border_style="red"
        ))
        import traceback
        console.print("[dim]")
        traceback.print_exc(file=console.file)
        console.print("[/dim]")
        if trace_writer:
            console.print(f"[dim]📁 执行轨迹已保存: {trace_writer.filepath}[/dim]")
        sys.exit(1)
