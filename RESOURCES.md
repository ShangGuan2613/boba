# Agent & Harness Resources

## Knowledge

- [Anthropic · Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents)
  最该先读的一手文章：workflow 与 agent 的区别、何时才该上 agent、工具/ACI 设计。用于：第 1–3 课的概念校准。
- [Anthropic · Writing Effective Tools for Agents](https://www.anthropic.com/engineering/writing-tools-for-agents)
  工具不是普通 API endpoint；命名、描述、返回结构会直接影响 agent 表现。用于：工具协议与工具设计课。
- [HumanLayer · 12-Factor Agents](https://github.com/humanlayer/12-factor-agents)
  把 agent 当软件工程：own prompts/context/control flow、tools as structured outputs、unify state、stateless reducer。用于：Harness 工程化。
- [OpenAI · Harness Engineering](https://openai.com/index/harness-engineering/)
  “Humans steer, agents execute.” 通过环境、AGENTS.md、结构性约束和反馈回路提升 agent 可靠性。用于：为什么 harness 值得工程化。
- [Mitchell Hashimoto · My AI Adoption Journey](https://mitchellh.com/writing/my-ai-adoption-journey)
  harness engineering 的原始定义之一：每次 agent 犯错，就工程化一个让它永不再犯的解法。用于：护栏与失败复盘。
- [LangChain · The Anatomy of an Agent Harness](https://blog.langchain.com/the-anatomy-of-a-agent-harness/)
  “Agent = Model + Harness”；把 harness 拆成文件系统、执行、沙箱、记忆、上下文、长时任务六类。用于：Harness 组件地图。
- [arXiv · Optimize the Harness, Not the Model](https://arxiv.org/abs/2611.03434)
  最小 harness、自下而上的构建与评测；先证明新增组件的必要性。用于：评测与迭代课。
- [Wikipedia · Agent harness](https://zh.wikipedia.org/wiki/Agent_harness)
  快速建立术语全景；只作索引，不作为一手依据。

## Wisdom (Communities)

- 尚未确认学习者愿意加入的社区。暂不推荐低信噪比群组。
- 候选：HumanLayer / LangChain 的 GitHub Discussions；等学习者确认后再加入。

## Gaps

- 中文一手资料少；课程优先读英文原文，再用中文讲解。
- STD-1000 的正式定义缺失，见 `docs/STD-1000-PENDING.md`。
- 需要补一篇“如何评测 Agent Harness”的高质量一手材料。
