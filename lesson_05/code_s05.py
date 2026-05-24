#!/usr/bin/env python3
"""
s05_todo_write_deepseek.py - TodoWrite with DeepSeek API

  +---------+      +---------+      +------------------+
  |  User   | ---> | DeepSeek| ---> | TOOL_HANDLERS    |
  | prompt  |      |   API   |      |  bash            |
  +---------+      +---+-----+      |  read_file       |
                       ^            |  write_file      |
                       | result     |  edit_file       |
                       +------------+  glob            |
                                      todo_write ← NEW
                                   +------------------+
                                        |
                        .tasks/current_todos.json
                                        |
                        if rounds_since_todo >= 3:
                          inject <reminder>

Changes from s04:
  + todo_write tool + run_todo_write() implementation
  + Nag reminder (inject reminder after 3 rounds without todo update)
  + SYSTEM prompt includes "plan before execute" guidance
  + rounds_since_todo counter in agent_loop

Usage:
    uv venv && uv pip install openai python-dotenv
    DEEPSEEK_API_KEY=sk-xxx uv run python code_s05.py
"""

import os
import subprocess
import json
from pathlib import Path

try:
    import readline
    readline.parse_and_bind('set bind-tty-special-chars off')
    readline.parse_and_bind('set input-meta on')
    readline.parse_and_bind('set output-meta on')
    readline.parse_and_bind('set convert-meta off')
except ImportError:
    pass

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv(override=True)

# ── DeepSeek API 配置 ────────────────────────────
client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)

MODEL = os.getenv("MODEL_ID", "deepseek-chat")

WORKDIR = Path(os.getcwd()).resolve()
TASKS_DIR = WORKDIR / ".tasks"
TASKS_DIR.mkdir(exist_ok=True)

# s05 change: SYSTEM prompt adds planning guidance
SYSTEM = (
    f"You are a coding agent at {WORKDIR}. "
    "Before starting any multi-step task, use todo_write to plan your steps. "
    "Update status as you go."
)


# ═══════════════════════════════════════════════════════════
#  FROM s02-s04 (unchanged): Tool Implementations
# ═══════════════════════════════════════════════════════════

def safe_path(path: str) -> Path:
    """验证路径在工作目录内"""
    p = (WORKDIR / path).resolve()
    if not str(p).startswith(str(WORKDIR)):
        raise ValueError(f"Path {path} is outside workspace")
    return p


def run_bash(command: str) -> str:
    """安全执行 shell 命令"""
    try:
        r = subprocess.run(
            command, shell=True, cwd=str(WORKDIR),
            capture_output=True, text=True, timeout=120
        )
        out = (r.stdout + r.stderr).strip()
        return out[:50000] if out else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Command timeout (120s)"
    except Exception as e:
        return f"Error: {e}"


def run_read(path: str, limit: int = None) -> str:
    """读取文件内容"""
    try:
        p = safe_path(path)
        if not p.exists():
            return f"Error: File {path} not found"
        lines = p.read_text(encoding='utf-8').splitlines()
        if limit and limit > 0:
            lines = lines[:limit]
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


def run_write(path: str, content: str) -> str:
    """写入文件"""
    try:
        p = safe_path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding='utf-8')
        return f"Wrote {len(content)} bytes to {path}"
    except Exception as e:
        return f"Error: {e}"


def run_edit(path: str, old_text: str, new_text: str) -> str:
    """编辑文件，替换第一次出现的文本"""
    try:
        p = safe_path(path)
        if not p.exists():
            return f"Error: File {path} not found"
        text = p.read_text(encoding='utf-8')
        if old_text not in text:
            return f"Error: text not found in {path}"
        p.write_text(text.replace(old_text, new_text, 1), encoding='utf-8')
        return f"Edited {path}"
    except Exception as e:
        return f"Error: {e}"


def run_glob(pattern: str) -> str:
    """搜索匹配模式的文件"""
    import glob as g
    try:
        matches = g.glob(pattern, root_dir=str(WORKDIR))
        return "\n".join(matches) if matches else "(no matches)"
    except Exception as e:
        return f"Error: {e}"


# ═══════════════════════════════════════════════════════════
#  NEW in s05: todo_write tool — plan only, no execution
# ═══════════════════════════════════════════════════════════

def run_todo_write(todos: list) -> str:
    """写入并显示任务列表"""
    # 验证必填字段
    for i, t in enumerate(todos):
        if "content" not in t or "status" not in t:
            return f"Error: todos[{i}] missing 'content' or 'status'"
        if t["status"] not in ("pending", "in_progress", "completed"):
            return f"Error: todos[{i}] has invalid status '{t['status']}'"

    # 保存到文件
    tasks_file = TASKS_DIR / "current_todos.json"
    tasks_file.write_text(json.dumps(todos, indent=2, ensure_ascii=False))

    # 打印任务列表
    lines = ["\n\033[33m## Current Tasks\033[0m"]
    for t in todos:
        icon = {
            "pending": " ",
            "in_progress": "\033[36m▸\033[0m",
            "completed": "\033[32m✓\033[0m"
        }[t["status"]]
        lines.append(f"  [{icon}] {t['content']}")
    print("\n".join(lines))

    return f"Updated {len(todos)} tasks"


TOOL_HANDLERS = {
    "bash": run_bash,
    "read_file": run_read,
    "write_file": run_write,
    "edit_file": run_edit,
    "glob": run_glob,
    "todo_write": run_todo_write,  # s05: 新工具
}


# ── Tool definitions ────────────────────────────────────
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "执行 shell 命令。用于运行代码、安装依赖、执行脚本等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "要执行的 shell 命令"}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取文件内容。用于查看代码、配置文件等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径（相对于工作目录）"},
                    "limit": {"type": "integer", "description": "限制读取的行数（可选）"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "写入文件。用于创建新文件或覆盖现有文件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径（相对于工作目录）"},
                    "content": {"type": "string", "description": "要写入的文件内容"}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "编辑文件，替换指定文本（只替换第一次出现）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "old_text": {"type": "string", "description": "要替换的原文本"},
                    "new_text": {"type": "string", "description": "替换后的新文本"}
                },
                "required": ["path", "old_text", "new_text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "glob",
            "description": "搜索匹配模式的文件。如 *.py, **/*.txt, src/**",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "文件匹配模式"}
                },
                "required": ["pattern"]
            }
        }
    },
    # s05: 新工具
    {
        "type": "function",
        "function": {
            "name": "todo_write",
            "description": "创建和管理当前会话的任务列表。用于规划多步骤任务。",
            "parameters": {
                "type": "object",
                "properties": {
                    "todos": {
                        "type": "array",
                        "description": "任务列表",
                        "items": {
                            "type": "object",
                            "properties": {
                                "content": {
                                    "type": "string",
                                    "description": "任务描述"
                                },
                                "status": {
                                    "type": "string",
                                    "enum": ["pending", "in_progress", "completed"],
                                    "description": "任务状态: pending=待办, in_progress=进行中, completed=已完成"
                                }
                            },
                            "required": ["content", "status"]
                        }
                    }
                },
                "required": ["todos"]
            }
        }
    }
]


# ═══════════════════════════════════════════════════════════
#  FROM s04 (unchanged): Hook System
# ═══════════════════════════════════════════════════════════

HOOKS = {
    "UserPromptSubmit": [],
    "PreToolUse": [],
    "PostToolUse": [],
    "Stop": []
}


def register_hook(event: str, callback):
    """注册钩子回调"""
    HOOKS[event].append(callback)


def trigger_hooks(event: str, *args):
    """触发钩子，返回第一个非 None 结果（用于阻断）"""
    for callback in HOOKS[event]:
        result = callback(*args)
        if result is not None:
            return result
    return None


# ═══════════════════════════════════════════════════════════
#  Hook callbacks
# ═══════════════════════════════════════════════════════════

DENY_LIST = ["rm -rf /", "sudo", "shutdown", "reboot", "mkfs", "dd if="]
DESTRUCTIVE = ["rm ", "> /etc/", "chmod 777"]


def permission_hook(tool_name: str, args: dict):
    """PreToolUse: 权限检查"""
    if tool_name == "bash":
        command = args.get("command", "")
        for pattern in DENY_LIST:
            if pattern in command:
                print(f"\n\033[31m⛔ Blocked: '{pattern}'\033[0m")
                return "Permission denied by deny list"
        for kw in DESTRUCTIVE:
            if kw in command:
                print(f"\n\033[33m⚠  Potentially destructive command\033[0m")
                print(f"   Tool: {tool_name}({args})")
                choice = input("   Allow? [y/N] ").strip().lower()
                if choice not in ("y", "yes"):
                    return "Permission denied by user"

    if tool_name in ("write_file", "edit_file"):
        path = args.get("path", "")
        try:
            if not (WORKDIR / path).resolve().is_relative_to(WORKDIR):
                print(f"\n\033[33m⚠  Writing outside workspace\033[0m")
                print(f"   Tool: {tool_name}({args})")
                choice = input("   Allow? [y/N] ").strip().lower()
                if choice not in ("y", "yes"):
                    return "Permission denied by user"
        except Exception:
            pass

    return None


def log_hook(tool_name: str, args: dict):
    """PreToolUse: 记录工具调用"""
    print(f"\033[90m[HOOK] {tool_name}\033[0m")
    return None


def context_inject_hook(query: str):
    """UserPromptSubmit: 记录工作目录"""
    print(f"\033[90m[HOOK] UserPromptSubmit: working in {WORKDIR}\033[0m")
    return None


def summary_hook(messages: list):
    """Stop: 打印工具调用统计"""
    tool_count = sum(1 for m in messages if m.get("role") == "tool")
    print(f"\033[90m[HOOK] Stop: session used {tool_count} tool calls\033[0m")
    return None


# 注册所有钩子
register_hook("UserPromptSubmit", context_inject_hook)
register_hook("PreToolUse", permission_hook)
register_hook("PreToolUse", log_hook)
register_hook("Stop", summary_hook)


# ═══════════════════════════════════════════════════════════
#  DeepSeek API 调用封装
# ═══════════════════════════════════════════════════════════

def call_deepseek(messages: list):
    """调用 DeepSeek API"""
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM},
            *messages
        ],
        tools=TOOLS,
        tool_choice="auto",
        max_tokens=8000,
        temperature=0.0,
    )
    return response.choices[0].message


# ═══════════════════════════════════════════════════════════
#  agent_loop — s04 + nag reminder counter
# ═══════════════════════════════════════════════════════════

rounds_since_todo = 0


def agent_loop(messages: list):
    """Agent 主循环：带 todo 提醒机制"""
    global rounds_since_todo

    while True:
        # s05: nag reminder — 连续 3 轮没更新 todo 就提醒
        if rounds_since_todo >= 3 and messages:
            messages.append({
                "role": "user",
                "content": "<reminder>Update your todos.</reminder>"
            })
            rounds_since_todo = 0

        response_message = call_deepseek(messages)

        # 构建 assistant 消息
        assistant_message = {
            "role": "assistant",
            "content": response_message.content or ""
        }

        if response_message.tool_calls:
            assistant_message["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments
                    }
                }
                for tc in response_message.tool_calls
            ]

        messages.append(assistant_message)

        # 没有工具调用 → 触发 Stop 钩子并退出
        if not response_message.tool_calls:
            force = trigger_hooks("Stop", messages)
            if force:
                messages.append({"role": "user", "content": str(force)})
                continue
            return

        rounds_since_todo += 1

        # 执行每个工具调用
        for tool_call in response_message.tool_calls:
            tool_name = tool_call.function.name

            # 解析参数
            try:
                args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                args = {}

            # 🪝 PreToolUse 钩子
            blocked = trigger_hooks("PreToolUse", tool_name, args)
            if blocked:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_name,
                    "content": str(blocked)
                })
                continue

            # 执行工具
            print(f"\033[33m> {tool_name}\033[0m")
            handler = TOOL_HANDLERS.get(tool_name)
            output = handler(**args) if handler else f"Error: Unknown tool {tool_name}"
            print(str(output)[:200])

            # 🪝 PostToolUse 钩子
            trigger_hooks("PostToolUse", tool_name, args, output)

            # s05: 重置 nag 计数器（当调用 todo_write 时）
            if tool_name == "todo_write":
                rounds_since_todo = 0

            # 追加工具结果
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": tool_name,
                "content": str(output)
            })


# ── 主入口 ──────────────────────────────────────
if __name__ == "__main__":
    print("\033[36m" + "="*60 + "\033[0m")
    print("\033[36m🚀 DeepSeek Agent Loop (TodoWrite + Hooks)\033[0m")
    print("\033[36m" + "="*60 + "\033[0m")
    print(f"📁 工作目录: {WORKDIR}")
    print(f"🤖 使用模型: {MODEL}")
    print(f"🛠️  可用工具: {', '.join(TOOL_HANDLERS.keys())}")
    print(f"🪝  已注册钩子: UserPromptSubmit, PreToolUse×2, Stop")
    print(f"📋 Todo 提醒: 连续 3 轮未更新自动提醒")
    print("\n使用方法：")
    print("  - 输入任务描述，回车发送")
    print("  - 输入 'q' 或 'exit' 退出")
    print("  - 输入 'clear' 清空对话历史")
    print()

    history = []

    while True:
        try:
            query = input("\033[36m💡 任务 >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            print("\n👋 再见！")
            break

        query = query.strip()

        if query.lower() in ("q", "exit"):
            print("👋 再见！")
            break

        if query.lower() == "clear":
            history = []
            rounds_since_todo = 0
            print("🗑️  对话历史已清空")
            continue

        if not query:
            continue

        # 🪝 UserPromptSubmit 钩子
        trigger_hooks("UserPromptSubmit", query)

        history.append({"role": "user", "content": query})
        agent_loop(history)

        # 打印模型的最终文本响应
        if history:
            last_message = history[-1]
            if last_message["role"] == "assistant" and last_message["content"]:
                print(f"\n\033[32m{'='*60}\033[0m")
                print(f"\033[32m{last_message['content']}\033[0m")
                print(f"\033[32m{'='*60}\033[0m")

        print()