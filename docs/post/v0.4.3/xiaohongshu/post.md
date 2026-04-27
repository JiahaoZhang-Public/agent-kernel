# 小红书 Post — Agent OS Kernel v0.4.3

**平台**: 小红书
**语言**: 中文
**配图**: figure.png (1080x1440 竖版)

---

## 标题

开源了一个 LLM Agent 安全内核，1600 行代码解决 AI 工具调用安全问题

## 正文

给 AI Agent 接上工具之后，你有没有想过：什么在阻止它读错文件、调错 API、执行危险命令？

答案是——没有。模型可能幻觉、被 prompt 注入、或者单纯犯错，而它和真实世界之间没有任何防护层。

所以我们造了这个缺失的层：Agent OS Kernel。

核心机制很简单：
每个工具调用都必须经过一个 Gate——策略检查 -> 执行 -> 审计日志。没有例外，没有绕过路径，在架构层面强制执行。

三个不变量，结构性保证：
1. 所有访问必经 Gate — kernel.submit() 是唯一执行路径
2. 默认拒绝 — 策略没允许的一律阻止
3. 无静默操作 — 每个决策都不可篡改地记录

关键数据：
- 核心代码仅 ~1600 行，一下午就能审计完
- 测试覆盖率 96%+
- 吞吐量 77,000+ ops/s
- 通过 LiteLLM 支持 100+ LLM 供应商
- 30 个可运行示例
- MIT 开源协议

安装一行搞定：
pip install py-agent-kernel

GitHub: github.com/JiahaoZhang-Public/agent-kernel

如果你在用 LLM Agent 做自动化，安全问题值得认真对待。欢迎 Star、提 Issue、提 PR。

#开源 #AI安全 #LLM #Agent #Python #人工智能 #程序员 #开发者工具
