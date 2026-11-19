"""Lesson 01 · 最小 Agent 闭环（奶茶店版）

问题
----
顾客问：“你们今天有什么？”
模型如果凭记忆回答，就会编价格、编售罄。奶茶店不能这样。

设计
----
把“说话”和“做事”分开：
1. 模型只输出一个意图：我想调用 get_menu；
2. 门店代码执行真实函数；
3. 把真实结果放回对话；
4. 模型再基于真实结果回答。

这就是 Agent 循环的最小形状。Harness 后面要做的预算、护栏、
trace，都是围绕这个循环长出来的。
"""

import json

# 柜台后面的真实菜单。价格不是模型“记住”的，是这里给的。
MENU = [
    {"id": "boba_milk_tea", "name": "珍珠奶茶", "price": 12},
    {"id": "cheese_berry", "name": "芝士莓莓", "price": 18},
    {"id": "four_seasons", "name": "四季春", "price": 10},
]


def get_menu():
    """设备：把今日菜单取出来。"""
    return {"items": MENU}


# 工具表：模型说名字，我们查表执行。
TOOLS = {"get_menu": get_menu}


def fake_model(messages):
    """离线模型：第一次看到问题就调工具，看到结果后再回答。

    真实模型会自己决定调不调、调几次；这里用确定性脚本模拟那个决策，
    这样每一步都能复现。
    """
    last_result = _last_tool_result(messages)

    if last_result is None:
        return {
            "type": "tool_use",
            "id": "call_1",
            "name": "get_menu",
            "args": {},
        }

    menu = json.loads(last_result["content"])
    items = "、".join(
        f"{item['name']} {item['price']} 元" for item in menu["items"]
    )
    return {"type": "text", "text": f"今天有：{items}。想喝哪杯？"}


def _last_tool_result(messages):
    """从对话历史里找最近一次工具结果。"""
    for message in reversed(messages):
        for block in message["content"]:
            if block.get("type") == "tool_result":
                return block
    return None


def run(user_text):
    """最小 Harness：一个循环，把模型的意图变成动作，再把结果送回去。"""
    messages = [
        {"role": "user", "content": [{"type": "text", "text": user_text}]}
    ]
    print(f"👤 顾客：{user_text}")

    while True:
        turn = fake_model(messages)
        messages.append({"role": "assistant", "content": [turn]})

        if turn["type"] == "text":
            print(f"🧑‍🍳 小波：{turn['text']}")
            return turn["text"]

        print(f"🧑‍🍳 小波：我想调用 {turn['name']}({turn['args']})")
        tool = TOOLS[turn["name"]]
        result = tool(**turn["args"])
        print(f"🔧 {turn['name']} → {result}")

        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": turn["id"],
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                ],
            }
        )


if __name__ == "__main__":
    run("你们今天有什么？")
