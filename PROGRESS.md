# 学习进程

> 这是 GitHub 上可见的学习日志。完整经验与 STAR 记录同步在 [Notion](https://app.notion.com/p/41d3b41c3823814b99eae1e4cd40425b?pvs=204)。

## 课程进度

| 课次 | 主题 | 状态 | 产物 |
| --- | --- | --- | --- |
| 01 | 一杯奶茶的 Agent 闭环 | 已 review，比喻已修正 | `lessons/0001-agent-loop.html` |
| 02 | 工具协议：参数、错误、未知工具 | 已产出，待 review | `lessons/0002-tool-protocol.html` |

## 2026-11-19 · 第 1 课 review

### 学习者的回答

1. **“模型说调用 `get_menu`，谁真正执行？”**
   → Harness 执行。✅ 正确。

2. **“工具结果不回填 `messages`，下一轮会怎样？”**
   → 下一轮模型重新再来一轮。✅ 方向正确，补充：模型没有拿到新信息，通常会重复同一个 `tool_use`，或者开始编；真实 API 还可能因为缺少配对的 `tool_result` 直接报协议错误。

3. **“店员 = Model，店长 = Harness，这个比喻哪里会误导？”**
   → 学习者指出：模型是思考、不执行的；店员本身才是店铺的执行方。✅ 这是对课程的修正，已写进第 1 课和 `learning-records/0001-model-is-not-the-barista.md`。

### 修正后的比喻

- **店员（整个人）** = Agent = Model + Harness
- **店员的判断 / 话术** = Model
- **店员的手脚 + 设备 + 店规** = Harness

### 决策

- 第 1 课的表格与讲解已按上述修正更新。
- 下一课优先讲工具协议：参数缺失、未知工具、工具报错如何回填。这正是第 2 题暴露的边界。

### 证据

- 课程：`lessons/0001-agent-loop.html`
- 速查：`reference/harness-map.html`
- 学习记录：`learning-records/0001-model-is-not-the-barista.md`
- 提交：见本次 commit

## 2026-11-19 · 第 2 课产出

### 本课要解决的问题

工具调用失败时，异常会逃出循环，顾客收不到任何回复。第 2 课把三条失败路径——缺参数、未知工具、工具异常——统一回填成 `tool_result`。

### 产物

- 课程：`lessons/0002-tool-protocol.html`
- 速查：`reference/tool-protocol.html`
- 可运行代码：`boba/tool_protocol.py`
- 测试：`tests/test_tool_protocol.py`（5 个，全部通过）

### 核心不变量

**1 个 `tool_use` → 1 个 `tool_result`；成功是结果，失败也是结果。**

### 留给学习者的 review 问题

1. `unknown_tool` 为什么不应该自动重试？
2. 如果 `is_error` 忘了设 true，但 `content.ok` 是 false，会发生什么？
3. `except Exception` 在这里算不算吞异常？边界在哪？

### 下一课

预算与超时：如果模型收到错误后永远重试，谁喊停？

## 2026-11-19 · 第 2 课可读性修订

### 反馈

学习者指出：第 2 课从第 4 节起脱离奶茶店比喻，变成抽象概念，看不懂。

### 修订

- 第 4 节改为“后厨窗口：一张单子的旅程”：前台写单 → 窗口查单 → 师傅做单 → 小票回前台。
- 第 5 节改为“四种小票，四句人话”：错误码对应前台对顾客说的话。
- 第 6 节改为“窗口不守规矩，店里会怎样”：每条协议对应一个差评。
- 第 7 节练习改用店里语言；第 8 节改为“没修的设备”。
- 新增 `.flow` 流程图组件。

### 教学规则

每个技术段落先讲“店里发生什么”，再映射到代码；讲不成店里故事的段落，说明设计还没讲清。
