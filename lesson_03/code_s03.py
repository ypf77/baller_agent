#!/usr/bin/env python3
"""
s03_permission.py - Permission System

Three gates inserted before tool execution:

    Gate 1: Hard deny list (rm -rf /, sudo, ...)
    Gate 2: Rule matching (write outside workspace? destructive cmd?)
    Gate 3: User approval (pause and wait for confirmation)

    +-------+    +--------+    +--------+    +--------+    +------+
    | Tool  | -> | Gate 1 | -> | Gate 2 | -> | Gate 3 | -> | Exec |
    | call  |    | deny?  |    | match? |    | allow? |    |      |
    +-------+    +--------+    +--------+    +--------+    +------+
         |            |             |             |
         v            v             v             v
      (normal)     (blocked)    (ask user)   (user says no?)

Only one line added to the agent loop:

    if not check_permission(block):
        continue

Builds on s02 (multi-tool). Usage:

    python code_s03.py
    Needs: pip install anthropic python-dotenv + ANTHROPIC_API_KEY in .env
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

SYSTEM = f"You are a coding agent at {WORKDIR}. Use tools to solve tasks. Act, don't explain."

# ── 安全路径验证 ────────────────────────────────────────
def safe_path(path: str) -> Path:
    """验证路径在工作目录内"""
    p = (WORKDIR / path).resolve()
    if not str(p).startswith(str(WORKDIR)):
        raise ValueError(f"Path {path} is outside workspace")
    return p


# ── Tool implementations ────────────────────────────────
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


# ── 工具处理器映射 ──────────────────────────────────
TOOL_HANDLERS = {
    "bash": run_bash,
    "read_file": run_read,
    "write_file": run_write,
    "edit_file": run_edit,
    "glob": run_glob,
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
                    "command": {
                        "type": "string",
                        "description": "要执行的 shell 命令"
                    }
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
                    "path": {
                        "type": "string",
                        "description": "文件路径（相对于工作目录）"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "限制读取的行数（可选）"
                    }
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
                    "path": {
                        "type": "string",
                        "description": "文件路径（相对于工作目录）"
                    },
                    "content": {
                        "type": "string",
                        "description": "要写入的文件内容"
                    }
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
                    "path": {
                        "type": "string",
                        "description": "文件路径"
                    },
                    "old_text": {
                        "type": "string",
                        "description": "要替换的原文本"
                    },
                    "new_text": {
                        "type": "string",
                        "description": "替换后的新文本"
                    }
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
                    "pattern": {
                        "type": "string",
                        "description": "文件匹配模式"
                    }
                },
                "required": ["pattern"]
            }
        }
    }
]


# ═══════════════════════════════════════════════════════════
#  Three-Gate Permission Pipeline
# ═══════════════════════════════════════════════════════════

# Gate 1: Hard deny list — 直接拒绝
DENY_LIST = ["rm -rf /", "sudo", "shutdown", "reboot", "mkfs", "dd if=", "> /dev/sda"]

def check_deny_list(tool_name: str, args: dict) -> str | None:
    """检查是否命中硬拒绝列表"""
    if tool_name == "bash":
        command = args.get("command", "")
        for pattern in DENY_LIST:
            if pattern in command:
                return f"'{pattern}' is on the deny list"
    return None


# Gate 2: Rule matching — 上下文检查
PERMISSION_RULES = [
    {
        "tools": ["write_file", "edit_file"],
        "check": lambda args: not (WORKDIR / args.get("path", "")).resolve().is_relative_to(WORKDIR),
        "message": "Writing outside workspace"
    },
    {
        "tools": ["bash"],
        "check": lambda args: any(kw in args.get("command", "") for kw in ["rm ", "> /etc/", "chmod 777"]),
        "message": "Potentially destructive command"
    },
]

def check_rules(tool_name: str, args: dict) -> str | None:
    """检查是否命中规则"""
    for rule in PERMISSION_RULES:
        if tool_name in rule["tools"]:
            try:
                if rule["check"](args):
                    return rule["message"]
            except Exception:
                pass  # 规则检查异常时跳过
    return None


# Gate 3: User approval — 人工确认
def ask_user(tool_name: str, args: dict, reason: str) -> str:
    """询问用户是否允许执行"""
    print(f"\n\033[33m⚠  {reason}\033[0m")
    print(f"   Tool: {tool_name}")
    for k, v in args.items():
        print(f"   {k}: {str(v)[:100]}")
    choice = input("   Allow? [y/N] ").strip().lower()
    return "allow" if choice in ("y", "yes") else "deny"


# Pipeline: 三级权限检查
def check_permission(tool_name: str, args: dict) -> bool:
    """
    三级权限检查流水线：
    1. Deny list → 直接拒绝
    2. Rules → 触发则进入人工审批
    3. User approval → 用户确认
    """
    # Gate 1: Deny list
    reason = check_deny_list(tool_name, args)
    if reason:
        print(f"\n\033[31m⛔ DENIED: {reason}\033[0m")
        return False
    
    # Gate 2: Rules → Gate 3: User approval
    reason = check_rules(tool_name, args)
    if reason:
        decision = ask_user(tool_name, args, reason)
        if decision == "deny":
            print(f"\033[31m⛔ User denied\033[0m")
            return False
        print(f"\033[32m✅ User approved\033[0m")
    
    return True


# ── DeepSeek API 调用封装 ──────────────────────
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


# ── The core pattern: 工具调用循环 ───────────────
def agent_loop(messages: list):
    """
    Agent 主循环：不断调用 DeepSeek API，执行工具，直到模型决定停止
    """
    while True:
        response_message = call_deepseek(messages)
        
        # 构建 assistant 消息
        assistant_message = {
            "role": "assistant",
            "content": response_message.content or ""
        }
        
        # 如果有工具调用，添加到消息中
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
        
        # 如果没有工具调用，结束循环
        if not response_message.tool_calls:
            return
        
        # 执行每个工具调用
        for tool_call in response_message.tool_calls:
            tool_name = tool_call.function.name
            
            # 解析参数
            try:
                args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                args = {}
            
            # 🛡️ 权限检查（三级流水线）
            if not check_permission(tool_name, args):
                output = "Permission denied by security pipeline"
                print(f"\033[31m⛔ {output}\033[0m")
            else:
                # 🎯 字典分发 + **args 解包
                print(f"\033[33m> {tool_name}\033[0m")
                handler = TOOL_HANDLERS.get(tool_name)
                output = handler(**args) if handler else f"Error: Unknown tool {tool_name}"
                print(str(output)[:200])
            
            # 将工具执行结果添加到消息历史
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": tool_name,
                "content": str(output)
            })


# ── 主入口 ──────────────────────────────────────
if __name__ == "__main__":
    print("\033[36m" + "="*60 + "\033[0m")
    print("\033[36m🚀 DeepSeek Agent Loop (with Permission Pipeline)\033[0m")
    print("\033[36m" + "="*60 + "\033[0m")
    print(f"📁 工作目录: {WORKDIR}")
    print(f"🤖 使用模型: {MODEL}")
    print(f"🛠️  可用工具: {', '.join(TOOL_HANDLERS.keys())}")
    print(f"🛡️  安全: 三级权限校验已启用")
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
            print("🗑️  对话历史已清空")
            continue
        
        if not query:
            continue
        
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