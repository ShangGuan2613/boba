# 术语表

项目内中英文、代码符号与奶茶店喻体的对照。

| 中文 | English | 代码 | 奶茶店里的意思 |
| --- | --- | --- | --- |
| 智能体 / 店员 | Agent | `boba.core.Agent` | 点单员小波：配方卡 + 技能 |
| 门店运营体系 | Harness | `boba.harness.Harness` | 接待、派活、记账、收口 |
| 一次运行 | run | `Harness.run()` / `RunResult` | 接待一位顾客的一轮完整服务 |
| 一次接待 | session | `boba.harness.Session` | 同一顾客的多轮对话 |
| 配方卡 | system prompt | `Agent.system_prompt` | 店员的行为手册 |
| 设备 / 工位 | Tool | `boba.core.Tool` | 菜单机、收银台、封口机 |
| 茶底 / 原料 | Model | `boba.core.Model` | 决定这杯茶的上限 |
| 模型回合 | turn | `boba.core.ModelTurn` | 店员的一次思考/动作 |
| 工具调用 | tool call | `boba.core.ToolCall` | 按一下设备按钮 |
| 工具结果 | tool result | `tool_result` content block | 设备返回的小票/报错 |
| 店长守则 | guardrail | `boba.core.Guardrail` | 执行前的否决权 |
| 预算 | budget | `HarnessConfig` | 最多接待几轮、几次操作、多久 |
| 小票流水 | trace | `boba.trace.Trace` | 每单的完整事件记录 |
| 事件 | event | `TraceEvent` | 小票上的一行 |
| 试饮会 | eval | 路线图 | 用真实小票回归、对比 |
| 交接班 | memory / persistence | 路线图 | 下一班还能接上 |
| 连锁店 | multi-tenant deployment | 路线图 | 同一套运营体系开多家店 |
| 新品研发 | experiment | 路线图 | 换配方、A/B、看数据 |

## 状态词

| 状态 | 含义 |
| --- | --- |
| `ok` | 模型正常结束，没有待执行的工具调用 |
| `max_turns` | 达到模型回合上限 |
| `max_tool_calls` | 达到工具调用上限 |
| `timeout` | 达到墙钟时间上限 |
| `refusal` | 模型安全拒答 |
| `model_error` | 模型调用抛错 |
| `harness_error` | Harness 自身兜底捕获的异常 |

## 订单状态

| 状态 | 含义 |
| --- | --- |
| `draft` | 草稿单，可继续加饮品 |
| `submitted` | 已提交，库存已扣减，返回小票 |
