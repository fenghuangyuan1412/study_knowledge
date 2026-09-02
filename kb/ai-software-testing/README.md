# AI软件测试 · 知识库

> 第一个个人知识库：**利用 AI 能力加速传统软件测试**（AI辅助测试 / AI生成用例 / 被测项目认知 / Agent 测试）。
> 内容按批次沉淀：`batch-<编号>/items/*.md`，每批 5 条，git 分支提交、同意后合入 main。

## 学习素材源

- B 站「黑马测试」《AI+软件测试第一篇_测试基础+AI手工测试》（200 集）：
  https://www.bilibili.com/video/BV13HwdzYEBu
- 配套公开笔记（CSDN / 知乎等）与权威网页资料（51testing 等），见各批次条目中的来源链接。

## 批次索引

| 批次 | 主题 | 状态 |
| --- | --- | --- |
| batch-001 | 被测项目认知 + AI测试全景 + 入门路线（首航 5 条） | 内容分支待合入 |

## 目录约定

- `batch-<编号>/items/NN-<slug>.md`：知识条目（NN 为批内序号）
- `batch-<编号>/README.md`：本批上传介绍（与 git 提交信息呼应）

## 检索 / 问答

- 关键词检索：`localbrain search keyword "词"`
- 语义检索 / RAG 问答：配置 `~/.localbrain/config.yaml` 的 api_key（DashScope 或本地 new-api/Ollama）后
  `localbrain mine` 生成向量，再于 `web/` 问答页使用（RAG→语义→关键词自动降级）。

> ⚠️ **提醒**：先用 DashScope 免费额度跑通全流程；后续切本地模型（new-api 拉取 Ollama）只需改
> `~/.localbrain/config.yaml` 的 embedding/llm 两段 provider、model、api_key、base_url，并重启 `web/` 服务即可。
