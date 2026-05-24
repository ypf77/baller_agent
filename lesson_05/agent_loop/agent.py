import json

from agent_loop.api import call_deepseek
from agent_loop.tools import TOOL_HANDLERS
from agent_loop.hooks import trigger_hooks

rounds_since_todo = 0


def reset_todo_counter():
    global rounds_since_todo
    rounds_since_todo = 0


def agent_loop(messages: list):
    global rounds_since_todo

    while True:
        if rounds_since_todo >= 3 and messages:
            messages.append({
                "role": "user",
                "content": "<reminder>Update your todos.</reminder>"
            })
            rounds_since_todo = 0

        response_message = call_deepseek(messages)

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

        if not response_message.tool_calls:
            force = trigger_hooks("Stop", messages)
            if force:
                messages.append({"role": "user", "content": str(force)})
                continue
            return

        rounds_since_todo += 1

        for tool_call in response_message.tool_calls:
            tool_name = tool_call.function.name

            try:
                args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                args = {}

            blocked = trigger_hooks("PreToolUse", tool_name, args)
            if blocked:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_name,
                    "content": str(blocked)
                })
                continue

            print(f"\033[33m> {tool_name}\033[0m")
            handler = TOOL_HANDLERS.get(tool_name)
            output = handler(**args) if handler else f"Error: Unknown tool {tool_name}"
            print(str(output)[:200])

            trigger_hooks("PostToolUse", tool_name, args, output)

            if tool_name == "todo_write":
                rounds_since_todo = 0

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": tool_name,
                "content": str(output)
            })
