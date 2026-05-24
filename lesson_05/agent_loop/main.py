import sys
from pathlib import Path

# 确保 lesson_05/ 在 sys.path 中，支持从任意目录直接运行
_parent = Path(__file__).resolve().parent.parent
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from agent_loop.config import WORKDIR, MODEL
from agent_loop.tools import TOOL_HANDLERS
from agent_loop.hooks import trigger_hooks
from agent_loop.agent import agent_loop, reset_todo_counter


def main():
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
            reset_todo_counter()
            print("🗑️  对话历史已清空")
            continue

        if not query:
            continue

        trigger_hooks("UserPromptSubmit", query)

        history.append({"role": "user", "content": query})
        agent_loop(history)

        if history:
            last_message = history[-1]
            if last_message["role"] == "assistant" and last_message["content"]:
                print(f"\n\033[32m{'='*60}\033[0m")
                print(f"\033[32m{last_message['content']}\033[0m")
                print(f"\033[32m{'='*60}\033[0m")

        print()


if __name__ == "__main__":
    main()
