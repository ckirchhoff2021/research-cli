import json
import mimetypes
import re
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import streamlit as st

from agent import create_research_agent
from stream import build_agent_config, normalize_message_content, merge_stream_response, truncate_text

from dotenv import load_dotenv

load_dotenv()

SESSIONS_DIR = Path(__file__).parent / "sessions"
OUTPUTS_DIR = Path(__file__).parent / "outputs"
SESSIONS_DIR.mkdir(exist_ok=True)
OUTPUTS_DIR.mkdir(exist_ok=True)

MAX_ARGS_DISPLAY_LENGTH = 3000
MAX_RESULT_DISPLAY_LENGTH = 3000
MAX_THINKING_DISPLAY_LENGTH = 3000
MAX_FILE_DISPLAY_LENGTH = 36
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
VIDEO_EXTENSIONS = {".mp4", ".webm", ".avi", ".mov", ".mkv", ".flv", ".wmv"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma", ".aiff"}


def get_session_files():
    files = sorted(SESSIONS_DIR.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    return files


def load_session(session_id: str) -> dict:
    session_file = SESSIONS_DIR / f"{session_id}.json"
    if session_file.exists():
        with open(session_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"session_id": session_id, "messages": [], "created_at": datetime.now().isoformat()}


def save_session(session: dict):
    if "title" not in session or not session["title"]:
        session["title"] = generate_session_title(session.get("messages", []))
    session["updated_at"] = datetime.now().isoformat()
    session_file = SESSIONS_DIR / f"{session['session_id']}.json"
    with open(session_file, "w", encoding="utf-8") as f:
        json.dump(session, f, ensure_ascii=False, indent=2)


def delete_session(session_id: str):
    session_file = SESSIONS_DIR / f"{session_id}.json"
    if session_file.exists():
        session_file.unlink()


def format_session_timestamp(timestamp: str) -> str:
    if not timestamp:
        return "Unknown"
    try:
        dt = datetime.fromisoformat(timestamp)
    except ValueError:
        return timestamp[:16]

    now = datetime.now()
    if dt.date() == now.date():
        return f"Today · {dt.strftime('%H:%M')}"
    if (now.date() - dt.date()).days == 1:
        return f"Yesterday · {dt.strftime('%H:%M')}"
    return dt.strftime("%Y-%m-%d")


def get_session_preview(messages: list) -> str:
    for msg in messages:
        if msg.get("role") == "user":
            content = normalize_message_content(msg.get("content", "")).replace("\n", " ").strip()
            if content:
                return truncate_text(content, 72)
    return "No messages yet"


def get_session_records():
    records = []
    for session_file in get_session_files():
        session_id = session_file.stem
        try:
            with open(session_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}

        messages = data.get("messages", [])
        title = data.get("title") or session_id
        created_at = data.get("created_at", "")
        records.append(
            {
                "session_id": session_id,
                "title": truncate_text(title, 42),
                "full_title": title,
                "preview": get_session_preview(messages),
                "message_count": len(messages),
                "created_at": created_at,
                "display_time": format_session_timestamp(created_at),
            }
        )
    return records


def generate_session_title(messages: list) -> str:
    if not messages:
        return "New Chat"

    first_user_msg = None
    for msg in messages:
        if msg.get("role") == "user":
            first_user_msg = msg.get("content", "")
            break

    if not first_user_msg:
        return "New Chat"

    if len(first_user_msg) <= 30:
        return first_user_msg

    return first_user_msg[:30] + "..."


def render_process_steps(steps: list, is_complete: bool = True):
    if not steps:
        return

    label = "✅ Trace" if is_complete else "📝 Trace"
    state = "complete" if is_complete else "running"
    with st.status(label, state=state, expanded=not is_complete):
        turn_index = 0
        last_step_index = len(steps) - 1
        for step_index, step in enumerate(steps):
            is_latest_step = not is_complete and step_index == last_step_index
            if step["type"] == "thinking":
                turn_index += 1
                with st.expander(
                    f"💭 Thinking (**:blue[>>> Turn {turn_index}]**)",
                    expanded=is_latest_step,
                ):
                    content = step["content"]
                    if len(content) > MAX_THINKING_DISPLAY_LENGTH:
                        content = content[:MAX_THINKING_DISPLAY_LENGTH] + "..."
                    st.markdown(content)
            elif step["type"] == "tool_call":
                with st.expander(f"🔨 Tool Call (`{step['name']}`)", expanded=is_latest_step):
                    args_str = str(step.get("args", {}))
                    if len(args_str) > MAX_ARGS_DISPLAY_LENGTH:
                        args_str = args_str[:MAX_ARGS_DISPLAY_LENGTH] + "..."
                    result_str = str(step.get("result", ""))
                    if len(result_str) > MAX_RESULT_DISPLAY_LENGTH:
                        result_str = result_str[:MAX_RESULT_DISPLAY_LENGTH] + "..."

                    st.markdown(f"**Tool:** `{step['name']}`")
                    st.markdown(f"**Args:** `{args_str}`")
                    st.markdown(f"**Result:**\n```\n{result_str}\n```")


def display_process_steps(placeholder, steps: list, is_complete: bool = True):
    if not steps:
        return

    with placeholder.container():
        render_process_steps(steps, is_complete=is_complete)


def resolve_local_path(raw_path: str) -> Path | None:
    if not raw_path:
        return None

    normalized = raw_path.strip()
    if normalized.startswith("sandbox:"):
        normalized = normalized[len("sandbox:") :]
    elif normalized.startswith("file://"):
        normalized = normalized[len("file://") :]

    candidate = Path(normalized)
    if candidate.exists():
        return candidate
    return None


def parse_markdown_link(line: str) -> tuple[str, str] | None:
    match = re.fullmatch(r"\[([^\]]+)\]\(([^)]+)\)", line.strip())
    if not match:
        return None
    return match.group(1), match.group(2)


def get_media_suffix(value: str) -> str:
    normalized = value.strip()
    if normalized.startswith("sandbox:"):
        normalized = normalized[len("sandbox:") :]
    elif normalized.startswith("file://"):
        normalized = normalized[len("file://") :]

    parsed = urlparse(normalized)
    path = parsed.path if parsed.scheme else normalized
    return Path(path).suffix.lower()


def render_remote_media(url: str, display_name: str = "") -> bool:
    suffix = get_media_suffix(url)
    if suffix in IMAGE_EXTENSIONS:
        st.image(url, caption=display_name or None, use_container_width=True)
        return True
    if suffix in VIDEO_EXTENSIONS:
        st.video(url)
        return True
    if suffix in AUDIO_EXTENSIONS:
        st.audio(url)
        return True
    return False


def render_file(file_path: str, display_name: str = ""):
    if not file_path:
        st.warning("No file path provided")
        return

    file_path_obj = resolve_local_path(file_path)
    if file_path_obj is None:
        candidate = Path(file_path)
        if not candidate.is_absolute():
            candidate = OUTPUTS_DIR / candidate.name
        file_path_obj = candidate if candidate.exists() else None

    if file_path_obj is None:
        st.error(f"File not found: {file_path}")
        return

    if not display_name:
        display_name = file_path_obj.name

    if len(display_name) > MAX_FILE_DISPLAY_LENGTH:
        display_name_truncated = display_name[: MAX_FILE_DISPLAY_LENGTH - 3] + "..."
    else:
        display_name_truncated = display_name

    file_extension = file_path_obj.suffix.lower()
    file_icon = {
        ".pdf": "📕",
        ".png": "🖼️",
        ".jpg": "🖼️",
        ".jpeg": "🖼️",
        ".gif": "🖼️",
        ".webp": "🖼️",
        ".bmp": "🖼️",
        ".doc": "📝",
        ".docx": "📝",
        ".xls": "📊",
        ".xlsx": "📊",
        ".csv": "📊",
        ".ppt": "📙",
        ".pptx": "📙",
        ".zip": "🗜️",
        ".rar": "🗜️",
        ".md": "📄",
        ".txt": "📄",
        ".py": "📄",
        ".json": "📄",
        ".mp4": "🎬",
        ".webm": "🎬",
        ".avi": "🎬",
        ".mov": "🎬",
        ".mp3": "🎵",
        ".wav": "🎵",
        ".flac": "🎵",
        ".aac": "🎵",
    }.get(file_extension, "📎")

    is_image = file_extension in IMAGE_EXTENSIONS
    is_video = file_extension in VIDEO_EXTENSIONS
    is_audio = file_extension in AUDIO_EXTENSIONS

    try:
        with open(file_path_obj, "rb") as f:
            file_data = f.read()

        mime_type, _ = mimetypes.guess_type(str(file_path_obj))
        mime_type = mime_type or "application/octet-stream"

        if is_image:
            st.image(file_data, caption=display_name, use_container_width=True)
        elif is_video:
            st.video(file_data, format=mime_type)
        elif is_audio:
            st.audio(file_data, format=mime_type)

        st.markdown("""
        <style>
        div[data-testid="stDownloadButton"] {
            width: min(360px, 100%) !important;
        }
        div[data-testid="stDownloadButton"] > button {
            display: flex !important;
            align-items: center !important;
            justify-content: space-between !important;
            width: min(360px, 100%) !important;
            min-height: 40px !important;
            padding: 7px 12px !important;
            border-radius: 6px !important;
            border: 1px solid #cbd5e1 !important;
            background: #f8fafc !important;
            transition: background-color 0.2s ease, border-color 0.2s ease, color 0.2s ease !important;
            color: #111827 !important;
            font-weight: 500 !important;
            box-shadow: none !important;
            opacity: 1 !important;
        }
        div[data-testid="stDownloadButton"] > button:hover {
            background: #ffffff !important;
            border-color: #94a3b8 !important;
            color: #020617 !important;
        }
        div[data-testid="stDownloadButton"] > button p {
            color: inherit !important;
            opacity: 1 !important;
        }
        </style>
        """, unsafe_allow_html=True)

        st.download_button(
            label=f"{file_icon} {display_name_truncated}",
            data=file_data,
            file_name=display_name,
            mime=mime_type,
            key=f"download_{file_path}_{id(file_data)}",
        )
    except Exception as e:
        st.error(f"Error reading file: {str(e)}")


def render_markdown_content(content: str):
    if not content:
        return

    content = content.strip()

    if content.startswith("{") and content.endswith("}"):
        try:
            config = json.loads(content)
            if config.get("type") == "file":
                render_file(config.get("file_path", ""), config.get("display_name", ""))
                return
            elif config.get("type") == "table":
                headers = config.get("headers", [])
                rows = config.get("rows", [])
                title = config.get("title", "")
                if title:
                    st.subheader(title)
                if headers and rows:
                    df = pd.DataFrame(rows, columns=headers)
                    st.dataframe(df, hide_index=True)
                else:
                    st.warning("No data to display")
                return
        except (json.JSONDecodeError, TypeError):
            pass

    lines = content.split("\n")
    i = 0
    text_lines = []

    while i < len(lines):
        line = lines[i]
        stripped_line = line.strip()

        image_match = re.fullmatch(r"!\[([^\]]*)\]\(([^)]+)\)", stripped_line)
        if image_match:
            alt = image_match.group(1)
            src = image_match.group(2)
            resolved_path = resolve_local_path(src)
            if resolved_path is not None:
                render_file(str(resolved_path), alt or resolved_path.name)
            elif render_remote_media(src, alt):
                pass
            else:
                text_lines.append(line)
            i += 1
            continue

        markdown_link = parse_markdown_link(stripped_line)
        if markdown_link:
            link_text, link_url = markdown_link
            resolved_path = resolve_local_path(link_url)
            if resolved_path is not None:
                suffix = resolved_path.suffix.lower()
                if suffix in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS | AUDIO_EXTENSIONS:
                    render_file(str(resolved_path), link_text or resolved_path.name)
                    i += 1
                    continue
            elif render_remote_media(link_url, link_text):
                i += 1
                continue

        local_path_match = re.search(r"`(/[^`]+)`", stripped_line)
        if local_path_match:
            raw_path = local_path_match.group(1)
            resolved_path = resolve_local_path(raw_path)
            if resolved_path is not None:
                suffix = resolved_path.suffix.lower()
                if suffix in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS | AUDIO_EXTENSIONS:
                    render_file(str(resolved_path), resolved_path.name)
                    i += 1
                    continue

        if "|" in line and i + 1 < len(lines) and all(c in lines[i + 1] for c in "|-"):
            header_line = line
            table_lines = [header_line]
            i += 2
            while i < len(lines) and "|" in lines[i]:
                table_lines.append(lines[i])
                i += 1

            headers = [h.strip() for h in table_lines[0].split("|") if h.strip()]
            rows = []
            for row_line in table_lines[2:]:
                cells = [c.strip() for c in row_line.split("|") if c.strip()]
                if len(cells) == len(headers):
                    rows.append(cells)

            if headers and rows:
                df = pd.DataFrame(rows, columns=headers)
                st.dataframe(df, hide_index=True, use_container_width=True)
            else:
                text_lines.extend(table_lines)
            continue

        text_lines.append(line)
        i += 1

    if text_lines:
        st.markdown("\n".join(text_lines))


def display_message(msg: dict):
    role = msg.get("role", "unknown")
    content = msg.get("content", "")
    process_steps = msg.get("process_steps", [])

    if role == "user":
        with st.chat_message("user"):
            st.markdown(content)
    elif role == "assistant":
        with st.chat_message("assistant"):
            if content:
                render_markdown_content(content)

            if process_steps:
                st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
                render_process_steps(process_steps, is_complete=True)


def main():
    st.set_page_config(
        page_title="Research CLI",
        page_icon="🔬",
        layout="wide",
    )

    st.markdown("""
    <style>
    .block-container {
        max-width: 940px !important;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
    }

    [data-testid="stBottomBlockContainer"] {
        max-width: 940px !important;
        margin: 0 auto !important;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
    }

    [data-testid="stChatInput"] {
        max-width: 940px !important;
        margin: 0 auto !important;
    }

    .stChatMessage h1 { font-size: 1.5rem !important; }
    .stChatMessage h2 { font-size: 1.3rem !important; }
    .stChatMessage h3 { font-size: 1.1rem !important; }
    .stChatMessage h4 { font-size: 1.0rem !important; }
    .stChatMessage p { font-size: 0.95rem !important; }
    .stChatMessage li { font-size: 0.95rem !important; }
    .stChatMessage table { font-size: 0.9rem !important; }
    .stChatMessage code { font-size: 0.85rem !important; }

    .stChatMessage .stDataFrame {
        width: fit-content !important;
        max-width: 100%;
    }

    [data-testid="stSidebar"] [data-testid="stTextInputRootElement"] input {
        border-radius: 14px !important;
    }

    [data-testid="stSidebar"] [data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 18px !important;
        border-color: rgba(120, 134, 161, 0.22) !important;
        background: color-mix(in srgb, var(--secondary-background-color) 92%, transparent) !important;
    }

    [data-testid="stSidebar"] button[kind="secondary"],
    [data-testid="stSidebar"] button[kind="tertiary"] {
        border-radius: 12px !important;
    }

    [data-testid="stSidebar"] button[kind="secondary"] {
        border-color: rgba(120, 134, 161, 0.24) !important;
    }

    .session-list [data-testid="stVerticalBlockBorderWrapper"],
    .session-list [data-testid="stVerticalBlockBorderWrapper"] > div {
        padding: 0.08rem 0.12rem 0.14rem !important;
        margin-bottom: 0.42rem !important;
        border-radius: 16px !important;
        background: #d9e8ff !important;
        border-color: #4f8fe6 !important;
        box-shadow: 0 8px 22px rgba(59, 130, 246, 0.26), inset 0 0 0 1px rgba(255, 255, 255, 0.38) !important;
        transition: background-color 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease !important;
        overflow: hidden !important;
    }

    .session-list [data-testid="stVerticalBlockBorderWrapper"]:hover,
    .session-list [data-testid="stVerticalBlockBorderWrapper"]:hover > div {
        background: #c6dcff !important;
        border-color: #377ee0 !important;
        box-shadow: 0 12px 26px rgba(59, 130, 246, 0.32), inset 0 0 0 1px rgba(255, 255, 255, 0.42) !important;
    }

    .session-list [data-testid="stVerticalBlockBorderWrapper"]:has(.session-card-badge.current),
    .session-list [data-testid="stVerticalBlockBorderWrapper"]:has(.session-card-badge.current) > div {
        background: #d5f3df !important;
        border-color: rgba(34, 197, 94, 0.56) !important;
        box-shadow: 0 12px 26px rgba(34, 197, 94, 0.26), inset 0 0 0 1px rgba(255, 255, 255, 0.34) !important;
    }

    .session-list button[kind="tertiary"] {
        min-height: 1.95rem !important;
        padding: 0.24rem 0.5rem !important;
        font-size: 0.82rem !important;
        background: transparent !important;
        border: 1px solid rgba(120, 134, 161, 0.18) !important;
    }

    .sidebar-kicker {
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: var(--text-color);
        opacity: 0.68;
        margin-bottom: 0.15rem;
    }

    .sidebar-title {
        font-size: 1.25rem;
        font-weight: 700;
        letter-spacing: -0.02em;
        margin-bottom: 0.35rem;
    }

    .sidebar-subtitle {
        font-size: 0.9rem;
        color: var(--text-color);
        opacity: 0.72;
        margin-bottom: 0.2rem;
        line-height: 1.45;
    }

    .session-card-meta {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 0.75rem;
        margin-bottom: 0.28rem;
    }

    .session-card-badge {
        display: inline-flex;
        align-items: center;
        gap: 0.35rem;
        padding: 0.3rem 0.74rem;
        border-radius: 999px;
        font-size: 0.98rem;
        font-weight: 600;
        background: color-mix(in srgb, var(--primary-color) 12%, transparent);
        color: var(--primary-color);
    }

    .session-card-badge.current {
        background: color-mix(in srgb, #22c55e 18%, transparent);
        color: #15803d;
    }

    .session-card-time {
        font-size: 1rem;
        color: var(--text-color);
        opacity: 0.84;
    }

    .session-card-title {
        font-size: 0.97rem;
        font-weight: 400;
        line-height: 1.3;
        margin: 0.06rem 0 0.04rem;
    }

    .session-card-title.current {
        color: #15803d;
        font-weight: 700;
    }

    .session-card-footer {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        font-size: 0.84rem;
        color: var(--text-color);
        opacity: 0.78;
        margin-top: 0.18rem;
    }

    .session-section-label {
        font-size: 0.78rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: var(--text-color);
        opacity: 0.56;
        margin: 0.3rem 0 0.6rem;
    }
    </style>
    """, unsafe_allow_html=True)

    if "session_id" not in st.session_state:
        session_files = get_session_files()
        if session_files:
            latest_session = session_files[0].stem
            st.session_state.session_id = latest_session
        else:
            st.session_state.session_id = str(uuid.uuid4())[:8]

    if "messages" not in st.session_state:
        session = load_session(st.session_state.session_id)
        st.session_state.messages = session.get("messages", [])
        st.session_state.session_title = session.get("title", "")

    if "pending_delete_session_id" not in st.session_state:
        st.session_state.pending_delete_session_id = None

    with st.sidebar:
        session_records = get_session_records()
        st.markdown(
            f"""
            <div class="sidebar-kicker">Workspace</div>
            <div class="sidebar-title">📁 Sessions</div>
            <div class="sidebar-subtitle">{len(session_records)} saved conversations</div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("➕ New Session", use_container_width=True, key="new_session_btn", type="primary"):
            st.session_state.session_id = str(uuid.uuid4())[:8]
            st.session_state.messages = []
            st.session_state.session_title = ""
            st.session_state.pending_delete_session_id = None
            st.rerun()

        search_query = st.text_input(
            "Search sessions",
            key="session_search",
            placeholder="Search title or first question...",
            label_visibility="collapsed",
        ).strip().lower()

        if search_query:
            filtered_records = [
                record
                for record in session_records
                if search_query in record["full_title"].lower()
                or search_query in record["preview"].lower()
                or search_query in record["display_time"].lower()
            ]
        else:
            filtered_records = session_records

        st.markdown('<div class="session-section-label">Recent Sessions</div>', unsafe_allow_html=True)

        if not filtered_records:
            st.info("No sessions match your search.")

        st.markdown('<div class="session-list">', unsafe_allow_html=True)
        for record in filtered_records[:20]:
            session_id = record["session_id"]
            is_current = session_id == st.session_state.session_id
            with st.container(border=True):
                badge_text = "Current" if is_current else "Saved"
                badge_class = "session-card-badge current" if is_current else "session-card-badge"
                st.markdown(
                    f"""
                    <div class="session-card-meta">
                        <span class="{badge_class}">{badge_text}</span>
                        <span class="session-card-time">{record["display_time"]}</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                button_label = record["title"]
                title_class = "session-card-title current" if is_current else "session-card-title"
                st.markdown(f'<div class="{title_class}">{button_label}</div>', unsafe_allow_html=True)

                footer_cols = st.columns([2.8, 1.15, 1.15])
                with footer_cols[0]:
                    if is_current:
                        footer_html = (
                            f'<div class="session-card-footer">'
                            f'<span>● Active now · {record["message_count"]} messages</span>'
                            f'</div>'
                        )
                    else:
                        footer_html = (
                            f'<div class="session-card-footer">'
                            f'<span>{record["message_count"]} messages</span>'
                            f'</div>'
                        )
                    st.markdown(footer_html, unsafe_allow_html=True)
                with footer_cols[1]:
                    if not is_current and st.button(
                        "Open",
                        key=f"load_{session_id}",
                        use_container_width=True,
                        type="tertiary",
                    ):
                        st.session_state.session_id = session_id
                        session = load_session(session_id)
                        st.session_state.messages = session.get("messages", [])
                        st.session_state.session_title = session.get("title", "")
                        st.session_state.pending_delete_session_id = None
                        st.rerun()
                with footer_cols[2]:
                    if st.button(
                        "Delete",
                        key=f"prepare_delete_{session_id}",
                        use_container_width=True,
                        type="tertiary",
                    ):
                        st.session_state.pending_delete_session_id = session_id
                        st.rerun()

                if st.session_state.pending_delete_session_id == session_id:
                    st.warning("Delete this session? This action cannot be undone.")
                    confirm_cols = st.columns(2)
                    with confirm_cols[0]:
                        if st.button("Cancel", key=f"cancel_delete_{session_id}", use_container_width=True):
                            st.session_state.pending_delete_session_id = None
                            st.rerun()
                    with confirm_cols[1]:
                        if st.button(
                            "Confirm Delete",
                            key=f"confirm_delete_{session_id}",
                            use_container_width=True,
                            type="secondary",
                        ):
                            delete_session(session_id)
                            st.session_state.pending_delete_session_id = None
                            if is_current:
                                st.session_state.session_id = str(uuid.uuid4())[:8]
                                st.session_state.messages = []
                                st.session_state.session_title = ""
                            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

        st.divider()
        st.markdown("""
        ### 💡 Tips
        - Ask any question that interests you
        - Examples:
          - "Generate an image of a cat."
          - "Tell a story about space."
        """)
        st.markdown("""
        ### ⚡ Features
        - **Shell Execute**: Run Python/bash commands
        - **Memory**: Agent remembers context
        - **Skills**: Specialized workflows
        """)

    st.title("🔬 Research CLI")

    st.markdown("""
    <style>
    .session-info-bar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 12px 16px;
        background: color-mix(in srgb, var(--primary-color) 6%, transparent);
        border-radius: 12px;
        border: 1px solid rgba(120, 134, 161, 0.16);
        margin-bottom: 16px;
        gap: 16px;
    }
    .session-info-item {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 0.88rem;
    }
    .session-info-label {
        color: var(--text-color);
        opacity: 0.56;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        font-size: 0.76rem;
    }
    .session-info-value {
        color: var(--text-color);
        font-weight: 500;
        font-family: 'SF Mono', 'Menlo', monospace;
    }
    .session-info-value.project {
        font-weight: 600;
        font-family: inherit;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown(f"""
    <div class="session-info-bar">
        <div class="session-info-item">
            <span class="session-info-label">Project</span>
            <span class="session-info-value project">research-cli</span>
        </div>
        <div class="session-info-item">
            <span class="session-info-label">Session</span>
            <span class="session-info-value">{st.session_state.session_id}</span>
        </div>
        <div class="session-info-item">
            <span class="session-info-label">Messages</span>
            <span class="session-info-value">{len(st.session_state.messages)}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    for msg in st.session_state.messages:
        display_message(msg)

    if prompt := st.chat_input("Ask a question ..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            agent = create_research_agent()

            messages_for_agent = []
            for m in st.session_state.messages:
                if m["role"] == "user":
                    messages_for_agent.append({"role": "user", "content": m["content"]})
                elif m["role"] == "assistant":
                    messages_for_agent.append({"role": "assistant", "content": m.get("content", "")})

            response_placeholder = st.empty()
            trace_placeholder = st.empty()
            full_response = ""
            process_steps = []
            pending_tool_calls = []

            try:
                with st.spinner("🤔 Agent is thinking..."):
                    for event in agent.stream(
                        {"messages": messages_for_agent},
                        config=build_agent_config(st.session_state.session_id),
                        stream_mode="updates",
                    ):
                        has_new_output = False
                        for node_name, node_output in event.items():
                            if isinstance(node_output, dict) and "messages" in node_output:
                                messages = node_output["messages"]
                                if isinstance(messages, list):
                                    for msg in messages:
                                        msg_type = type(msg).__name__
                                        if msg_type == "AIMessage":
                                            content_text = normalize_message_content(msg.content)
                                            if content_text:
                                                display_text = content_text[:MAX_THINKING_DISPLAY_LENGTH] + "..." if len(content_text) > MAX_THINKING_DISPLAY_LENGTH else content_text
                                                if process_steps and process_steps[-1]["type"] == "thinking":
                                                    process_steps[-1]["content"] = display_text
                                                else:
                                                    process_steps.append({
                                                        "type": "thinking",
                                                        "content": display_text,
                                                    })
                                                merged_response = merge_stream_response(full_response, content_text)
                                                if merged_response != full_response:
                                                    full_response = merged_response
                                                    response_placeholder.markdown(full_response)
                                                    has_new_output = True

                                            if hasattr(msg, "tool_calls") and msg.tool_calls:
                                                for tc in msg.tool_calls:
                                                    tool_name = tc.get("name", "unknown")
                                                    tool_call = {
                                                        "name": tool_name,
                                                        "args": tc.get("args", {}),
                                                        "id": tc.get("id", ""),
                                                    }
                                                    pending_tool_calls.append(tool_call)
                                                    process_steps.append({
                                                        "type": "tool_call",
                                                        "name": tool_name,
                                                        "args": tc.get("args", {}),
                                                        "result": None,
                                                        "in_progress": True,
                                                        "tool_id": tc.get("id", ""),
                                                    })
                                                    has_new_output = True

                                        elif msg_type == "ToolMessage":
                                            result_text = normalize_message_content(msg.content)
                                            tool_call_id = getattr(msg, "tool_call_id", "")

                                            matched = False
                                            for i, step in enumerate(process_steps):
                                                if step.get("in_progress") and (not step.get("tool_id") or step["tool_id"] == tool_call_id):
                                                    display_result = result_text[:MAX_RESULT_DISPLAY_LENGTH] + "..." if len(result_text) > MAX_RESULT_DISPLAY_LENGTH else result_text
                                                    process_steps[i]["result"] = display_result
                                                    process_steps[i]["in_progress"] = False
                                                    has_new_output = True
                                                    matched = True
                                                    break

                                            if not matched and pending_tool_calls:
                                                for i, step in enumerate(process_steps):
                                                    if step.get("in_progress"):
                                                        display_result = result_text[:MAX_RESULT_DISPLAY_LENGTH] + "..." if len(result_text) > MAX_RESULT_DISPLAY_LENGTH else result_text
                                                        process_steps[i]["result"] = display_result
                                                        process_steps[i]["in_progress"] = False
                                                        has_new_output = True
                                                        break

                        if has_new_output and process_steps:
                            display_process_steps(trace_placeholder, process_steps, is_complete=False)

                if not full_response:
                    full_response = "Done."

                response_placeholder.markdown(full_response)
                if process_steps:
                    display_process_steps(trace_placeholder, process_steps, is_complete=True)

            except Exception as e:
                full_response = f"❌ Error: {str(e)}"
                response_placeholder.markdown(full_response)

        st.session_state.messages.append({
            "role": "assistant",
            "content": full_response,
            "process_steps": process_steps,
        })

        session = {
            "session_id": st.session_state.session_id,
            "messages": st.session_state.messages,
            "created_at": datetime.now().isoformat(),
        }
        if "session_title" in st.session_state:
            session["title"] = st.session_state.session_title
        save_session(session)


if __name__ == "__main__":
    main()
