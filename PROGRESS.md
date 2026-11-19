# 学习进程

> 这是 GitHub 上可见的学习日志。完整经验与 STAR 记录同步在 [Notion](https://app.notion.com/p/41d3b41c3823814b99eae1e4cd40425b?pvs=204)。

## 课程进度

| 课次 | 主题 | 状态 | 产物 |
| --- | --- | --- | --- |
| 01 | 一杯奶茶的 Agent 闭环 | 已 review，比喻已修正 | `lessons/0001-agent-loop.html` |
| 02 | 工具协议：参数、错误、未知工具 | 待开始 | — |

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
