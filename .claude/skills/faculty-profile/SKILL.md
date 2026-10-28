---
name: faculty-profile
description: 根据已有的高校教师信息（姓名、学校，最好带个人主页和邮箱），抓取教师详细画像给远赞销售使用：主页信息、近 5 年英文论文、论文致谢中的基金、实验技术与推荐耗材、销售信号和优先级。用于：查某位老师的详细画像、批量处理外部程序导出的教师名单、解释某个字段的来源。
---

# 教师详细画像（远赞销售支持）

教师名单由外部程序产出。这个 skill 负责“已知是谁，查清楚他/她”：给定教师记录，输出带来源的画像卡和销售名单。所有逻辑在本仓库的 `fcrawl` 命令行里，skill 只负责调用和解读。

## 环境准备（每个新会话一次）

```bash
cd <仓库根目录>
python3 -m venv .venv && . .venv/bin/activate
pip install -q -e '.[dev]'
```

可选：设置 `OPENALEX_API_KEY`（免费，见“账号与费用”），启用 h 指数和研究主题。未设置时自动跳过，不影响其他字段。

数据写在仓库下的 `data/`（已被 git 忽略）：页面和 API 缓存在 `data/raw`，数据库在 `data/faculty.sqlite`，导出在 `data/export/`。

## 输入格式

CSV、TSV、JSON、JSONL、XLSX 都可以，表头中英文都认：

| 字段 | 可用表头 | 是否必填 |
|---|---|---|
| 姓名 | 姓名 / name / 教师姓名 | 必填 |
| 学校 | 学校 / school / 高校 / university | 必填，用中文全称 |
| 学院 | 学院 / college / 院系 | 强烈建议，用于论文院系比对 |
| 个人主页 | 个人主页 / url / profile_url / 主页链接 | 强烈建议，没有就只能查论文 |
| 邮箱 | 邮箱 / email | 建议，是论文归属最强的锚点 |
| 职称、系所、英文名、电话、编号 | 职称 / 系所 / 英文名 / 电话 / id | 可选 |

其他列原样保留在记录的 `extra` 里。

## 任务一：查一位老师

```bash
fcrawl profile 曹博 --school 上海交通大学 --college 生命科学技术学院 \
  --url http://life.sjtu.edu.cn/teacher/caobo [--email ...] [--out]
```

把输出的画像卡交给用户时，主动说明：
- “归属依据”一行。显示“仅姓名与单位”时，论文可能混入同名同校的其他老师，提醒销售核对。
- “待确认问题”里的条目。
- 推荐产品是根据研究方向和论文关键词推断的，需要沟通确认。

## 任务二：批量处理名单

```bash
fcrawl enrich 名单.xlsx --name 2026Q4_华东      # 输出到 data/export/2026Q4_华东/
fcrawl enrich 名单.csv --limit 20               # 先试 20 个
fcrawl enrich 名单.csv --max-age-days 30        # 30 天内处理过的直接复用（默认）
fcrawl enrich 名单.csv --force                  # 全部重查
```

产物：`teachers.csv`（按优先级排序，Excel 可直接打开）和 `cards/`（每人一张 Markdown 画像卡，文件名前缀是优先级分数）。中途中断后重新执行同一命令即可续跑，页面和 API 结果都有本地缓存。

批量结束后给用户一个简短质量小结：处理人数、有主页的比例、邮箱填充率、找到论文的比例、“仅姓名与单位”归属的人数、待确认论文最多的几位。

## 每个字段从哪里来

| 字段 | 来源 | 可信度说明 |
|---|---|---|
| 职称、邮箱、电话、办公室、研究方向、经历、主页论文、项目、招生招聘、人才头衔、入职年份 | 个人主页 | 规则抽取；输入里给了职称和邮箱时以输入为准 |
| 近 5 年论文、期刊、作者位次、MeSH 主题词、论文致谢基金号 | Europe PMC（含 PubMed） | 逐篇核对作者本人单位；邮箱、主页论文、ORCID 锚点最可靠 |
| 邮箱（主页没有时） | 论文作者单位里的邮箱 | 只取本人那一条单位 |
| h 指数、论文总数、研究主题 | OpenAlex | 需 API Key；按 ORCID 或姓名加机构匹配 |
| 实验技术、推荐产品 | 关键词规则，映射表在 `src/faculty_crawler/product_map.yaml` | 推断，需确认 |
| 优先级、销售信号 | 规则，见 `src/faculty_crawler/enrich.py` | 可按销售反馈调整 |

用户质疑某个值时，查数据库 `evidence` 表（`sqlite3 data/faculty.sqlite "select field,value,source_url,snippet from evidence where teacher_key like '%姓名%'"`），给出来源链接和原文片段。

## 论文归属规则（正确性的关键）

1. 检索：姓名拼音的全名和首字母写法，加学校英文名（由 ROR 自动解析，特殊情况在 `src/faculty_crawler/institutions.yaml` 补充）。
2. 强锚点：作者单位里出现已知邮箱，或论文标题与主页所列论文一致。拿到 ORCID 后再按 ORCID 补查本人全部论文。
3. 其余论文必须同时满足：作者本人单位是该校；院系与锚点论文一致，或与学院名对应的英文关键词一致。ORCID 不同的一律排除。
4. 达不到第 3 条的列为“待确认”，不计入统计，在画像卡中显示数量。

## 备用：按学院抓名单

外部程序没覆盖到的学院，可以用模板抓列表：`fcrawl sites`、`fcrawl probe <列表页URL>`、`fcrawl crawl <site_id>`、`fcrawl report <site_id>`。模板写法参考 `src/faculty_crawler/templates/`。

## 账号与费用

- Europe PMC、ROR：免费，无需账号。
- OpenAlex：免费 API Key，每天 1 美元额度（约 1 万次请求），按邮箱申请，激活后设置 `OPENALEX_API_KEY`。
- 全量（约 10 万老师）建议：多申请一个 OpenAlex Key 或购买付费额度；见 `docs/02-试点报告.md` 的资源清单。

## 合规边界

- 只用学校公开发布的工作信息和公开学术数据库，不采集私人手机、身份证、家庭住址。
- 不登录、不绕过验证码；学校网站遵守 robots.txt，同一域名请求间隔默认 2.5 秒。
- 画像卡用于销售了解客户，不用于群发邮件；老师要求删除时从数据库删除。
