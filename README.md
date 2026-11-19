# Boba（波波茶铺）

> 用一间奶茶店，讲清楚并实现一个 Agent Harness。

这里没有一上来就抽象到失真的“智能体平台”。只有一个可运行的最小内核：

**店员（Agent）** 拿着 **配方卡（system prompt）**，在 **门店运营体系（Harness）** 里调用 **设备（Tools）**，被 **店长守则（Guardrails）** 约束，每单留下 **小票（Trace）**。

奶茶店既是比喻，也是第一个真实可跑的应用场景。框架不认识“奶茶”，奶茶店只是它的第一个租户。

![status](https://img.shields.io/badge/MVP-runnable-brightgreen) ![python](https://img.shields.io/badge/python-3.11%2B-blue) ![deps](https://img.shields.io/badge/runtime%20deps-0-success)

---

## 60 秒上手

无需 API key，无需安装第三方依赖：

```bash
git clone https://github.com/ShangGuan2613/boba.git
cd boba

python3 -m boba demo
python3 -m unittest discover -s tests -v
```

真实输出：

```text
🍵 波波茶铺 · Boba Harness MVP
👤 顾客：你好，我要两杯珍珠奶茶：一杯少冰半糖，一杯正常冰全糖。

🧑‍🍳 小波：好嘞，我先看下今天的菜单，再帮你确认原料够不够～
   🔧 menu_list({})
      ↳ 波波茶铺 · 4 款饮品
   🔧 inventory_check({"item_id": "boba_milk_tea", "qty": 2})
      ↳ 珍珠奶茶 ×2 · 原料充足
   🔧 order_create({"customer": "阿珍"})
      ↳ 开单 B1001 · 阿珍
   🔧 order_add_item({"item_id": "boba_milk_tea", "qty": 1, "ice": "less", "sugar": "half"})
      ↳ 珍珠奶茶 ×1 · 订单共 ¥12
   🔧 order_add_item({"item_id": "boba_milk_tea", "qty": 1, "ice": "normal", "sugar": "full"})
      ↳ 珍珠奶茶 ×1 · 订单共 ¥24
   🔧 order_submit({})
      ↳ B1001 已提交 · ¥24 · 约 6 分钟
🧑‍🍳 小波：搞定啦，阿珍！订单 B1001：珍珠奶茶 ×1（中杯 / 少冰 / 半糖）、珍珠奶茶 ×1（中杯 / 正常冰 / 全糖），共 ¥24，预计 6 分钟后叫号取茶。🍵

✅ 完成 · 7 轮模型 · 6 次工具调用
🧾 小票流水：traces/20261119T101232-run_895e15bbbb.jsonl
```

每单都会落一张 JSONL 小票，可以随时回看：

```bash
python3 -m boba trace traces/<那张小票>.jsonl
```

```text
  1 🏁 run.started      点单员小波 · scripted · 7 件工具
  2 👤 session.message  你好，我要两杯珍珠奶茶：一杯少冰半糖，一杯正常冰全糖。
  4 🧑‍🍳 model.response   第 1 轮 · tool_use · 好嘞，我先看下今天的菜单，再帮你确认原料够不够～
  5 🔧 tool.call        menu_list({})
  6 ✅ tool.result      menu_list · 0.02ms · {"shop": "波波茶铺", ...
 ...
 29 🧾 run.finished     ok · 7 轮 · 6 次工具 · 0.82ms
```

想看菜单：`python3 -m boba menu`。

## 接入真实模型

`demo` 用的是确定性的 `ScriptedModel`（测试替身），所以离线也能复现。要接待真实顾客，接 Claude：

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[anthropic]'
export ANTHROPIC_API_KEY=...

python -m boba chat
```

默认使用 `claude-opus-5-5`，开启 adaptive thinking，`effort=medium`，并默认启用服务端 refusal fallback。可以调：

```bash
python -m boba chat --model claude-opus-5-5 --effort high
```

`chat` 里输入 `/menu` 看菜单，`/quit` 打烊。所有对话共享一个 `Session`，每轮 run 各留一张小票。

> 适配器遵循 Anthropic Messages API 的工具调用形状；离线测试用注入的 fake client 验证了请求/响应映射，但真实 API 调用需要你自己的 key 和网络。

## 一张图看懂

```text
顾客（用户）
   │ 一条消息
   ▼
┌──────────────────── Harness（门店运营体系）────────────────────┐
│                                                                │
│  Session 历史 ──► Model.generate ──► 有 tool_use？             │
│       ▲                                  │ 否 → 返回最终回复   │
│       │                                  │ 是                   │
│       │                                  ▼                      │
│       └──── tool_result ◄── Tool 执行 ◄── Guardrail 放行？      │
│                                      │                          │
│                                      └── 拒绝 → 错误结果给模型   │
│                                                                │
│  每一步都写入 Trace（小票流水，JSONL）                          │
└────────────────────────────────────────────────────────────────┘
```

循环的骨架其实就是：

```python
while under_budget():
    turn = model.generate(system=prompt, messages=history, tools=tools)
    if not turn.tool_calls:
        return turn.text
    for call in turn.tool_calls:
        check_guardrails(call) or execute_tool(call)
        history.append_paired_tool_result(call)
```

## 奶茶店 ↔ 代码

| 奶茶店 | 代码 | 作用 |
| --- | --- | --- |
| 顾客 | 调用方 / `user_text` | 提出需求 |
| 点单员小波 | `Agent`（`boba/barista.py`） | 配方卡 + 技能 |
| 配方卡 | `system_prompt` | 行为规范 |
| 门店运营体系 | `Harness`（`boba/harness.py`） | 循环、上下文、预算、派发 |
| 设备/工位 | `Tool`（`boba/shop/tools.py`） | 查看菜单、查库存、开单、加单、提交 |
| 茶底/原料 | `Model`（`boba/models.py`） | 产出下一步动作 |
| 库存 | `Shop.inventory` | 可被校验、扣减的真实状态 |
| 店长守则 | `Guardrail`（`boba/shop/guardrails.py`） | 工具执行前的否决权 |
| 小票流水 | `Trace`（`boba/trace.py`） | 可回放、可评测的事件日志 |
| 一次接待 | `Session` | 多轮共享的会话历史 |
| 试饮会 | Evals（路线图） | 用真实小票做回归与对比 |

## MVP 里到底有什么

| 能力 | 位置 | 说明 |
| --- | --- | --- |
| Agent 循环 | `boba/harness.py` | 模型 → 工具 → 模型，直到无工具调用或预算耗尽 |
| 模型无关 | `boba/core.py` `Model` 协议 | 离线脚本模型 + 可选 Claude 适配器 |
| 工具注册 | `Tool(name, description, input_schema, handler)` | JSON Schema 直接可交给模型 |
| 工具错误 | `ToolError` | 预期失败变成 `is_error` 的 tool_result，模型能自行纠正 |
| 护栏 | `Guardrail.check()` | 返回拒绝理由即拦截；护栏自身异常也按拒绝处理 |
| 预算 | `HarnessConfig` | `max_turns` / `max_tool_calls` / `max_seconds` |
| 小票 | `Trace` + `render_events()` | 每个事件带 `seq/ts/run_id/type/data` |
| 会话 | `Session` | 跨多次 `run()` 保留上下文，CLI 已用上 |
| 领域示例 | `boba/shop/` | 菜单、选项、库存、订单、7 件工具 |
| 测试 | `tests/` | 41 个 unittest，零依赖 |

一个刻意的实现细节：**只要模型发起了 `tool_use`，Harness 一定会回一条配对的 `tool_result`**——哪怕预算已经耗尽，也会回一条 `is_error`。否则会话历史会永久损坏，下一轮模型调用直接报错。

## 小票事件长什么样

```json
{"seq": 5, "ts": "2026-11-19T10:12:32.402Z", "run_id": "run_895e15bbbb",
 "type": "tool.call", "data": {"id": "call_1", "tool": "menu_list", "arguments": {}}}
```

| 事件 | 关键字段 |
| --- | --- |
| `run.started` | `agent`, `model`, `session_id`, `tools`, `limits` |
| `session.message` | `role`, `text` |
| `model.request` / `model.response` | `turn`, `stop_reason`, `text`, `tool_calls` |
| `tool.call` / `tool.result` | `id`, `tool`, `arguments`, `ok`, `duration_ms`, `result`/`error` |
| `guardrail.denied` | `tool`, `arguments`, `reason` |
| `harness.stopped` | `reason`, `limit` |
| `run.finished` | `status`, `turns`, `tool_calls`, `duration_ms` |

`status` 取值：`ok` / `max_turns` / `max_tool_calls` / `timeout` / `refusal` / `model_error` / `harness_error`。

## 设计取舍

1. **先有门店，再有平台。** 所有抽象都被一家真实奶茶店逼出来：没有“记忆模块”，只有库存；没有“可观测性平台”，只有小票。
2. **模型只是原料。** `Model` 是一个三方法的协议；换成别的模型不该动 Harness 一行。
3. **护栏是否决权，不是提示词。** 店长守则写在代码里，模型绕不过去；护栏异常时默认拒绝（fail closed）。
4. **小票是一等公民。** Trace 不是调试日志的附属品，而是后续评测、回放、复盘的数据底座。
5. **离线优先。** 确定性脚本模型让 demo 和 CI 不依赖网络/密钥；真实模型是可选增强，不是运行前提。

## MVP 的边界

- 库存和订单在内存里，进程重启即清零；还没有持久化。
- 工具串行执行；并行工具、handoff、多 Agent 尚未实现。
- demo 的“智能”来自脚本，不是真实推理——它证明的是 Harness/工具/护栏/trace 的链路。
- `chat` 适配器未经真实 API 端到端验证（见上文）。
- 没有 Web UI、鉴权、多租户隔离或生产级限流。

这些不是遗漏，是下一站。见 [ROADMAP.md](ROADMAP.md)。

## 继续读

- [架构决策：Harness 就是一家门店](docs/0001-harness-is-a-shop.md)
- [术语表](docs/glossary.md)
- [路线图](ROADMAP.md)

## License

[MIT](LICENSE)
