#!/usr/bin/env python3
"""
s02: Tool Use — 在 s01 基础上新增 4 个工具 + 分发映射。

运行: python code_s02.py
需要: pip install anthropic python-dotenv + .env 中配置 ANTHROPIC_API_KEY

本文件 = s01 的全部代码 + 以下新增:
  + run_read / run_write / run_edit / run_glob 四个工具实现
  + TOOL_HANDLERS 分发映射（替代 s01 中硬编码的 run_bash 调用）
  + safe_path 路径安全校验

循环本身（agent_loop）与 s01 完全一致。
"""

import os
import subprocess
import json
from pathlib import Path

try:
    import readline
    # macOS 的 libedit 在处理中文输入时有退格问题，这四行修复它
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
    dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/", "mkfs", "dd if="]
    if any(d in command for d in dangerous):
        return "Error: Dangerous command blocked"
    
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
            
            # 解析参数（JSON 字符串 → dict）
            try:
                args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                args = {}
            
            # 🎯 字典分发 + **args 解包，无需 if-elif
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
    print("\033[36m🚀 DeepSeek Agent Loop\033[0m")
    print("\033[36m" + "="*60 + "\033[0m")
    print(f"📁 工作目录: {WORKDIR}")
    print(f"🤖 使用模型: {MODEL}")
    print(f"🛠️  可用工具: {', '.join(TOOL_HANDLERS.keys())}")
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