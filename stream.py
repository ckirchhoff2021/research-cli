import sys
import os
import json
import time
from datetime import datetime

from dotenv import load_dotenv

from langchain_core.messages import HumanMessage
from agent import create_research_agent

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.tree import Tree
from rich.markdown import Markdown


def build_agent_config(thread_id: str | None = None) -> dict:
    resolved_thread_id = thread_id or f"cli-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    return {"configurable": {"thread_id": resolved_thread_id}}


MAX_ARGS_DISPLAY_LENGTH = 500
MAX_RESULT_PREVIEW_LINES = 5
MAX_RESULT_PREVIEW_CHARS = 600
MAX_THINKING_DISPLAY_LENGTH = 1000

HIDE_PREFIXES = (
    "SkillsMiddleware", "PatchToolCalls", "MemoryMiddleware",
    "TodoList", "SubAgent", "FileSystem", "Summarization"
)


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


def truncate_text(text: str, max_len: int) -> str:
    text = normalize_message_content(text)
    if len(text) > max_len:
        return text[:max_len] + "..."
    return text


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
        if isinstance(v, str) and ("/" in v or "\\" in v) and len(v) > 40:
            formatted[k] = shorten_path(v)
        elif isinstance(v, str) and len(v) > 100:
            formatted[k] = v[:100] + "..."
        else:
            formatted[k] = v
    try:
        return json.dumps(formatted, ensure_ascii=False, indent=2)
    except Exception:
        return str(formatted)


def classify_tool_call(tool_name: str, tool_args: dict) -> tuple[str, str]:
    file_path = str(tool_args.get("file_path", ""))
    if tool_name in ("read_file", "read"):
        if "SKILL.md" in file_path:
            skill_name = os.path.basename(os.path.dirname(file_path))
            return "skill", skill_name
        if "AGENTS.md" in file_path or "/memory/" in file_path:
            return "memory", "memory"
    if tool_name in ("ls", "glob", "grep"):
        return "filesystem", ""
    if tool_name in ("execute", "run_command", "shell"):
        return "execute", ""
    return "normal", ""


def format_tool_result(result_text: str, tool_type: str = "normal") -> tuple[str, bool]:
    lines = result_text.splitlines()
    total_lines = len(lines)
    total_chars = len(result_text)

    if tool_type == "skill":
        return f"[dim blue]📖 已加载技能配置 ({total_lines} 行)[/dim blue]", False
    if tool_type == "memory":
        return f"[dim blue]📝 已加载记忆 ({total_lines} 行)[/dim blue]", False

    is_truncated = False
    preview_lines = lines[:MAX_RESULT_PREVIEW_LINES]
    preview = "\n".join(preview_lines)

    if len(preview) > MAX_RESULT_PREVIEW_CHARS:
        preview = preview[:MAX_RESULT_PREVIEW_CHARS]
        is_truncated = True

    if total_lines > MAX_RESULT_PREVIEW_LINES or total_chars > MAX_RESULT_PREVIEW_CHARS:
        is_truncated = True

    if is_truncated:
        preview += f"\n\n... [共 {total_lines} 行, {total_chars} 字符]"

    return preview, is_truncated


def should_hide_node(node_name: str) -> bool:
    return any(node_name.startswith(prefix) for prefix in HIDE_PREFIXES)


def save_trace_json(process_steps: list, final_response: str, elapsed: float, task_prompt: str, output_dir: str = "traces") -> str:
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"trace_{timestamp}.json"
    filepath = os.path.join(output_dir, filename)

    trace_data = {
        "timestamp": datetime.now().isoformat(),
        "task": task_prompt,
        "elapsed_seconds": round(elapsed, 2),
        "final_response": final_response,
        "total_steps": len(process_steps),
        "steps": process_steps,
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(trace_data, f, ensure_ascii=False, indent=2)

    return filepath


def build_process_tree(process_steps: list, final_response: str = "", elapsed: float = 0) -> Tree:
    tree = Tree("[bold blue]🤖 Agent 执行过程[/bold blue]")

    for idx, step in enumerate(process_steps, 1):
        if step["type"] == "thinking":
            node = tree.add(f"[dim]Step {idx}:[/dim] [italic yellow]💭 思考中...[/italic yellow]")
            content = truncate_text(step["content"], MAX_THINKING_DISPLAY_LENGTH)
            node.add(f"[dim white]{content}[/dim white]")
        elif step["type"] == "tool_call":
            tool_type = step.get("tool_type", "normal")
            is_special = tool_type != "normal"
            is_error = step.get("is_error", False)

            if is_error:
                name_style = "[bold red]"
                icon = "❌"
            elif tool_type == "execute":
                name_style = "[bold magenta]"
                icon = "⚡"
            elif is_special:
                name_style = "[dim cyan]"
                icon = "🔧"
            else:
                name_style = "[bold cyan]"
                icon = "🔧"

            label = f" ([dim]{step.get('label', '')}[/])" if step.get("label") and tool_type == "skill" else ""
            node = tree.add(f"[dim]Step {idx}:[/dim] {name_style}{icon} 调用工具: {step['name']}{label}[/]")
            args_str = format_args(step.get("args", {}))
            args_display = truncate_text(args_str, MAX_ARGS_DISPLAY_LENGTH)
            node.add(f"[dim]📥 参数:[/dim]\n[dim white]{args_display}[/dim white]")

            if step.get("result"):
                result_node = node.add("[green]📤 结果:[/green]")
                preview, is_truncated = format_tool_result(
                    step["result"], tool_type
                )
                style = "[dim red]" if is_error else ("[dim yellow]" if is_truncated else "[dim white]")
                result_node.add(f"{style}{preview}[/]")
            elif step.get("in_progress"):
                node.add("[dim yellow]⏳ 执行中...[/dim yellow]")

    if final_response:
        final_node = tree.add("[bold green]✅ 最终回复[/bold green]")
        try:
            final_node.add(Markdown(final_response))
        except Exception:
            final_node.add(f"[white]{final_response}[/white]")

    if elapsed > 0:
        tree.add(f"[dim]⏱️  耗时: {elapsed:.1f}s[/dim]")

    return tree


def rich_console_stream_call(task_prompt: str, thread_id: str | None = None):
    load_dotenv()
    console = Console()
    console.print(
        Panel(f"[bold cyan]📝 Task:[/bold cyan] {task_prompt}", border_style="cyan")
    )
    console.print()

    start_time = time.time()
    try:
        with console.status("[dim]🔄 正在初始化 Research Agent...[/dim]"):
            agent = create_research_agent()

        console.print("[dim]✅ Agent 初始化完成，开始处理任务...\n[/dim]")

        process_steps = []
        pending_tool_calls = {}
        tool_counter = 0
        seen_skill_loads = set()
        full_response = ""

        with Live(console=console, refresh_per_second=4) as live:
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
                        if should_hide_node(node_name):
                            continue

                        if not isinstance(node_output, dict):
                            continue

                        messages = node_output.get("messages", [])
                        if not isinstance(messages, list):
                            continue

                        for msg in messages:
                            msg_type = type(msg).__name__

                            if msg_type == "AIMessage":
                                if hasattr(msg, "tool_calls") and msg.tool_calls:
                                    for tc in msg.tool_calls:
                                        tool_name = tc.get("name", "unknown")
                                        tool_args = tc.get("args", {})
                                        tool_id = tc.get("id", f"tool_{tool_counter}")
                                        tool_counter += 1
                                        tool_type, label = classify_tool_call(tool_name, tool_args)

                                        skip = False
                                        if tool_type == "skill":
                                            cache_key = f"skill:{label}"
                                            if cache_key in seen_skill_loads:
                                                skip = True
                                            else:
                                                seen_skill_loads.add(cache_key)

                                        if not skip:
                                            step_idx = len(process_steps)
                                            process_steps.append({
                                                "type": "tool_call",
                                                "name": tool_name,
                                                "args": tool_args,
                                                "result": None,
                                                "tool_type": tool_type,
                                                "label": label,
                                                "tool_id": tool_id,
                                                "in_progress": True,
                                            })
                                            has_new_output = True
                                            pending_tool_calls[tool_id] = step_idx

                                        pending_tool_calls[f"_pending_{tool_id}"] = skip

                                content_text = normalize_message_content(msg.content)
                                if content_text:
                                    display_text = truncate_text(content_text, MAX_THINKING_DISPLAY_LENGTH)

                                    is_update = False
                                    has_tool_calls = hasattr(msg, "tool_calls") and msg.tool_calls

                                    if process_steps and process_steps[-1]["type"] == "thinking" and not has_tool_calls:
                                        process_steps[-1]["content"] = display_text
                                        is_update = True
                                    elif not has_tool_calls:
                                        process_steps.append({
                                            "type": "thinking",
                                            "content": display_text,
                                        })
                                        is_update = True

                                    if content_text and not has_tool_calls:
                                        full_response = content_text

                                    if is_update:
                                        has_new_output = True

                            elif msg_type == "ToolMessage":
                                result_text = normalize_message_content(msg.content)
                                tool_id = getattr(msg, "tool_call_id", None)

                                if tool_id and tool_id in pending_tool_calls:
                                    step_idx = pending_tool_calls.pop(tool_id)
                                    pending_tool_calls.pop(f"_pending_{tool_id}", None)
                                    if step_idx < len(process_steps):
                                        step = process_steps[step_idx]
                                        step["result"] = result_text
                                        step["in_progress"] = False
                                        step["is_error"] = (
                                            "Error:" in result_text
                                            or "Traceback" in result_text
                                            or result_text.startswith("Error")
                                        )
                                        has_new_output = True
                                elif pending_tool_calls:
                                    for tid in list(pending_tool_calls.keys()):
                                        if tid.startswith("_pending_"):
                                            continue
                                        step_idx = pending_tool_calls[tid]
                                        if step_idx < len(process_steps) and process_steps[step_idx]["result"] is None:
                                            is_skip = pending_tool_calls.get(f"_pending_{tid}", False)
                                            pending_tool_calls.pop(tid, None)
                                            pending_tool_calls.pop(f"_pending_{tid}", None)
                                            if not is_skip:
                                                process_steps[step_idx]["result"] = result_text
                                                process_steps[step_idx]["in_progress"] = False
                                                has_new_output = True
                                            break

                    if has_new_output:
                        elapsed = time.time() - start_time
                        live.update(build_process_tree(process_steps, full_response, elapsed))

                elapsed = time.time() - start_time
                live.update(build_process_tree(process_steps, full_response, elapsed))

            except KeyboardInterrupt:
                console.print("\n[yellow]⚠️  用户中断任务[/yellow]")
                return

        elapsed = time.time() - start_time
        console.print()
        console.print(Panel(
            f"[bold green]✨ 任务完成![/bold green]\n[dim]总耗时: {elapsed:.1f}s[/dim]",
            border_style="green"
        ))

        trace_path = save_trace_json(process_steps, full_response, elapsed, task_prompt)
        console.print(f"[dim]📁 执行轨迹已保存: {trace_path}[/dim]")

    except Exception as e:
        console.print()
        console.print(Panel(
            f"[bold red]❌ 执行出错[/bold red]\n{type(e).__name__}: {str(e)}",
            border_style="red"
        ))
        import traceback
        console.print("[dim]")
        traceback.print_exc(file=console.file)
        console.print("[/dim]")
        sys.exit(1)
