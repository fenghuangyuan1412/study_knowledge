# 毛选知识库

> 《毛泽东选集》研读知识库，含两层能力：
>
> - **研读层**：选取经典篇目，沉淀「原文要点 + 解读」，供本地 Web 问答检索；
> - **全文层**：1–7 卷全文语料 + 本地 SQLite 索引，可按卷 / 篇 / 关键词 / 混合模式检索原文与段落，支持段落级溯源。
>
> 内容为个人学习整理：引文为短句摘引（核对见各篇 / 语料来源），解读为学习笔记。

## 学习方向

- 以方法论为主轴研读：认识论（实践论）、辩证法（矛盾论）、战略思维（论持久战）、调查研究（反对本本主义）、宗旨与价值观（为人民服务）
- 目的不是背条文，而是把其中的**思维方法**迁移到学习、工作（软件测试/AI）与个人成长中

## 全文语料与可溯源检索（skill 接入）

- **能力来源**：
  - `mao-selected-works`（ClawHub：henryczq）——《毛选》1–7 卷全文语料（387 篇 Markdown，按 `卷-序号-标题.md` 组织）+ 检索脚本：`build_index.py` 建立 SQLite FTS5 文档/段落索引，`search.py` 支持按卷（catalog）、看全文（show）、关键词（search）与混合检索（hybrid，可选 bge-m3 向量 + bge-reranker-v2-m3 重排）；
  - `wenshu`（文枢，ekstasisSH）——段落级锚点、引文格式化（GB/T 7714 + BibTeX）、理论谱系、检索问答：回答带出处锚点、可回原文核对、引文不编造（官方以《毛选》1–4 卷 1991 年版实证：1559 页 → 137 篇 / 1402 个段落锚点）。
- **语料与索引存放**：随 skill 安装在本机 agent 的 skills 目录（**不入 git**，版权与体积考虑）；仓库内只维护本说明。
- **常用命令**（进入 skill 目录后执行）：

```bash
python scripts/build_index.py                                    # 建立 / 重建索引
python scripts/search.py catalog --volume 第一卷                # 按卷列出篇目
python scripts/search.py show --title 实践论                     # 查看某篇全文
python scripts/search.py search "实事求是"                       # 关键词检索段落
python scripts/search.py search "关键词" --mode hybrid           # 混合检索（需开启 RAG）
python scripts/config.py set rag.enabled true                    # 开启向量 / 混合检索
```

API Key 一律走环境变量（如 `MAO_SKILL_API_KEY`），不写入配置文件提交。

- **与研读层配合**：精读条目需要核对原文 / 摘引完整句子时，用全文检索定位原文段落；写作引用时用文枢生成带锚点的可溯源引文。

## 批次索引

| 批次 | 主题 | 状态 |
| --- | --- | --- |
| batch-001 | 五篇精读：实践论 / 矛盾论 / 论持久战 / 反对本本主义 / 为人民服务（要点+解读） | 已入库 |

## 目录约定

- `batch-<编号>/items/NN-<slug>.md`：知识条目
- `batch-<编号>/README.md`：本批上传介绍

## 检索 / 问答

- **Web 问答（研读层）**：本知识库为 localbrain 独立数据实例，在 Web 页面顶部切换「毛选」即可问答。
- **全文检索（原文定位 / 溯源）**：使用上文 skill 命令在本机查询 1–7 卷原文与段落。
