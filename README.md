# 高校教师画像抓取（远赞销售支持）

给定教师信息（姓名、学校，最好带个人主页和邮箱），抓取详细画像：主页信息、近 5 年英文论文、论文致谢中的基金、ORCID、实验技术与远赞产品匹配、销售信号和优先级。输出销售名单和教师画像卡，每个字段都保留来源 URL 和原文片段。教师名单由外部程序提供；本仓库也带一个按学院抓名单的备用功能。

设计思路见 `docs/01-设计思路.md`，试点结果见 `docs/02-试点报告.md`，Claude Skill 见 `.claude/skills/faculty-profile/SKILL.md`。

## 快速开始

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
fcrawl profile 曹博 --school 上海交通大学 --college 生命科学技术学院 --url http://life.sjtu.edu.cn/teacher/caobo
fcrawl enrich 名单.csv --name 批次名   # 批量：csv/json/jsonl/xlsx，中英文表头都认
fcrawl sites                     # 备用：已接入的学院
fcrawl crawl sjtu_life           # 备用：抓取学院名单
fcrawl report sjtu_life          # 质量报告
fcrawl card 曹博                  # 某位老师的画像卡
fcrawl probe <列表页URL>          # 接入新学院前先分析页面
python -m pytest -q              # 单元测试
```

导出在 `data/export/<site_id>/`：销售名单 CSV、每人一张 Markdown 画像卡、质量报告。

## 目录

| 路径 | 作用 |
|---|---|
| `src/faculty_crawler/inputs.py` | 读取外部教师名单 |
| `src/faculty_crawler/profile.py` | 单个老师的画像主流程 |
| `src/faculty_crawler/names.py` | 中文姓名 → 英文署名变体、从主页论文学习署名 |
| `src/faculty_crawler/institutions.py` | 中文校名 → 英文名、别名、域名（ROR） |
| `src/faculty_crawler/sources/europepmc.py` | 论文检索与归属消歧 |
| `src/faculty_crawler/sources/openalex.py` | h 指数等学术指标（需 API Key） |
| `src/faculty_crawler/fetcher.py` | 礼貌抓取：按域名限速、重试退避、robots、原始页面落盘缓存、http/https 自动切换 |
| `src/faculty_crawler/templates/*.yaml` | 每个学院一份站点模板 |
| `src/faculty_crawler/list_parser.py` | 列表页解析：模板模式和自动模式（人名链接聚类） |
| `src/faculty_crawler/detail_parser.py` | 详情页抽取：小标题切段加启发式规则 |
| `src/faculty_crawler/normalize.py` | 职称、头衔、职务、姓名归一化 |
| `src/faculty_crawler/product_map.yaml` | 实验技术到远赞产品的映射，可直接编辑 |
| `src/faculty_crawler/enrich.py` | 技术标签、产品推荐、销售信号与优先级 |
| `src/faculty_crawler/validate.py` | 字段校验、置信度、站点质量报告 |
| `src/faculty_crawler/store.py` | SQLite：教师、字段证据、运行记录 |
| `src/faculty_crawler/export.py` | CSV、画像卡、质量报告 |

## 抓取礼貌参数

可选：`OPENALEX_API_KEY`（OpenAlex 免费 Key，也可写在 `data/.env`）。

环境变量可调：`FC_MIN_INTERVAL`（同域名请求间隔秒数，默认 2.5）、`FC_TIMEOUT`、`FC_MAX_RETRIES`、`FC_RESPECT_ROBOTS`、`FC_DATA_DIR`。
