#!/usr/bin/env python3
"""
s01_agent_loop_deepseek.py - The Agent Loop (DeepSeek Version)

使用 DeepSeek API 的 AI 编程助手核心循环模式：

    while stop_reason == "tool_use":
        response = LLM(messages, tools)
        execute tools
        append results

    +----------+      +---------+      +---------+
    |   User   | ---> | DeepSeek| ---> |  Tool   |
    |  prompt  |      |   API   |      | execute |
    +----------+      +-----+---+      +----+----+
                            ^               |
                            |   tool_result |
                            +---------------+
                            (loop continues)

Usage:
    pip install openai python-dotenv
    DEEPSEEK_API_KEY=... python s01_agent_loop_deepseek.py
"""

import os
import subprocess
import json

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

# 可用的 DeepSeek 模型
# deepseek-chat: 通用对话模型
# deepseek-reasoner: 推理模型（支持深度思考）
MODEL = os.getenv("MODEL_ID", "deepseek-chat")

SYSTEM = f"You are a coding agent at {os.getcwd()}. Use bash to solve tasks. Act, don't explain."

# ── Tool definition: just bash ────────────────────────────
TOOLS = [{
    "type": "function",
    "function": {
        "name": "bash",
        "description": "在终端中执行 shell 命令。用于运行代码、操作文件、安装依赖等。",
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
}]


# ── Tool execution ────────────────────────────────────────
def run_bash(command: str) -> str:
    """
    安全执行 shell 命令，带有危险命令过滤和超时保护
    """
    dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/", "mkfs", "dd if="]
    if any(d in command for d in dangerous):
        return "Error: Dangerous command blocked"
    
    try:
        r = subprocess.run(
            command, 
            shell=True, 
            cwd=os.getcwd(),
            capture_output=True, 
            text=True, 
            timeout=120
        )
        out = (r.stdout + r.stderr).strip()
        return out[:50000] if out else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Command timeout (120s)"
    except (FileNotFoundError, OSError) as e:
        return f"Error: {e}"


# ── DeepSeek API 调用封装 ──────────────────────
def call_deepseek(messages: list):
    """
    调用 DeepSeek API，支持工具调用
    """
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM},
            *messages
        ],
        tools=TOOLS,
        tool_choice="auto",  # 让模型自动决定是否使用工具
        max_tokens=8000,
        temperature=0.0,  # 降低随机性，获得更确定性的输出
    )
    return response.choices[0].message


# ── The core pattern: 工具调用循环 ───────────────
def agent_loop(messages: list):
    """
    Agent 主循环：不断调用 DeepSeek API，执行工具，直到模型决定停止
    """
    while True:
        # 调用 DeepSeek
        response_message = call_deepseek(messages)
        
        # 构建 assistant 消息
        assistant_message = {
            "role": "assistant",
            "content": response_message.content
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
        
        # 将助手消息添加到历史
        messages.append(assistant_message)
        
        # 如果没有工具调用，结束循环
        if not response_message.tool_calls:
            return
        
        # 执行每个工具调用
        for tool_call in response_message.tool_calls:
            if tool_call.function.name == "bash":
                # 解析参数
                try:
                    args = json.loads(tool_call.function.arguments)
                    command = args.get("command", "")
                except json.JSONDecodeError:
                    command = tool_call.function.arguments
                
                # 执行命令
                print(f"\033[33m$ {command}\033[0m")
                output = run_bash(command)
                print(output[:200])  # 显示前200个字符
                
                # 将工具执行结果添加到消息历史
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": "bash",
                    "content": output
                })
        
        # 循环继续，模型会看到工具执行结果并决定下一步


# ── 主入口 ──────────────────────────────────────
if __name__ == "__main__":
    print("\033[36m" + "="*60 + "\033[0m")
    print("\033[36m🚀 DeepSeek Agent Loop\033[0m")
    print("\033[36m" + "="*60 + "\033[0m")
    print(f"📁 工作目录: {os.getcwd()}")
    print(f"🤖 使用模型: {MODEL}")
    print("\n使用方法：")
    print("  - 输入任务描述，回车发送")
    print("  - 输入 'q' 或 'exit' 退出")
    print("  - 输入 'clear' 清空对话历史")
    print()

    history = []
    
    while True:
        try:
            # 获取用户输入
            query = input("\033[36m💡 任务 >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            print("\n👋 再见！")
            break
        
        query = query.strip()
        
        # 退出命令
        if query.lower() in ("q", "exit"):
            print("👋 再见！")
            break
        
        # 清空历史
        if query.lower() == "clear":
            history = []
            print("🗑️  对话历史已清空")
            continue
        
        # 跳过空输入
        if not query:
            continue
        
        # 添加用户消息到历史
        history.append({"role": "user", "content": query})
        
        # 运行 agent 循环
        agent_loop(history)
        
        # 打印模型的最终文本响应
        if history:
            last_message = history[-1]
            if last_message["role"] == "assistant" and last_message["content"]:
                print(f"\n\033[32m{'='*60}\033[0m")
                print(f"\033[32m{last_message['content']}\033[0m")
                print(f"\033[32m{'='*60}\033[0m")
        
        print()  # 空行分隔不同任务