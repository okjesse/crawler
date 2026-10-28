---
name: faculty-profile
description: 抓取并整理中国高校生命科学相关学院的教师信息，生成给远赞销售用的教师画像卡和优先级名单。用于：查某位老师的画像卡、抓取某个学院的全部教师、把一个新学院的师资页接入抓取、查看抓取质量报告。
---

# 高校教师画像（远赞销售支持）

本仓库的 `fcrawl` 命令行负责抓取、抽取、校验、打分和导出。这个 skill 告诉你在什么情况下调用哪个命令，以及怎样判断结果可不可信。

## 环境准备（每个新会话一次）

```bash
cd <仓库根目录>
python3 -m venv .venv && . .venv/bin/activate
pip install -q -e '.[dev]'
fcrawl sites            # 列出已接入的学院
```

数据默认写到仓库下的 `data/`（已被 .gitignore 忽略）：原始页面缓存在 `data/raw`，SQLite 在 `data/faculty.sqlite`，导出在 `data/export/<site_id>/`。

## 任务一：给销售出某位老师的画像卡

1. `fcrawl card <姓名> [--school 学校名]`。
2. 找不到时，确认该老师所在学院是否已接入（`fcrawl sites`）；已接入就先 `fcrawl crawl <site_id>`，未接入走任务三。
3. 把画像卡原样交给销售，并提醒两点：
   - “推断实验技术与推荐产品”是关键词推断，需要沟通确认。
   - “待核问题”里列出的字段不要直接用于外联。

## 任务二：抓取或刷新一个学院

```bash
fcrawl crawl <site_id>            # 有缓存的页面不会重复请求
fcrawl crawl <site_id> --max-age 720   # 缓存超过 30 天的页面重抓
fcrawl report <site_id>           # 质量报告
```

产物在 `data/export/<site_id>/`：
- `<site_id>_teachers.csv`：销售名单，按优先级排序，Excel 直接打开。
- `cards/`：每位老师一张 Markdown 画像卡，文件名前缀是优先级分数。
- `<site_id>_report.md`：覆盖率、字段填充率、问题分布、告警。

**质量门槛**（命令退出码为 2 表示没达标）：
- 详情页覆盖率 ≥ 95%。
- 教师数不低于模板里的 `expected_min_teachers`。低于时说明该学院官网只发布了部分教师，要在报告里明确告诉用户，并建议补充来源。
- 邮箱填充率 ≥ 80%。低于时先抽查 2 到 3 个详情页，确认是页面本身没写邮箱，还是图片或脚本混淆。

## 任务三：接入一个新学院

1. 找到师资列表页 URL（学院官网“师资队伍/教工名录/导师”栏目）。
2. `fcrawl probe <列表页URL>`：查看人名链接簇。最大簇就是教师列表时，自动模式即可用。
3. 在 `src/faculty_crawler/templates/` 新建 `<学校拼音缩写>_<学院缩写>.yaml`，参考现有两份模板：
   - 有“系所/职称”分组标题的用 `mode: grouped`，填 `section`、`group` 等选择器，分组标题会变成系所和职称。
   - 博达 WebPlus 站点（URL 形如 `/9902/list.htm`、详情 `/xx/xx/cXXXXaXXXXX/page.htm`）用 `mode: flat`，`pagination: webplus`，详情 `content: .wp_articlecontent`。
   - 拿不准就用 `mode: auto`。
   - 必填 `school_domains`（校验邮箱是否本校）和 `expected_min_teachers`（覆盖率告警）。
4. `fcrawl crawl <新site_id> --limit 10`，逐张看画像卡，核对姓名、职称、邮箱、研究方向是否和网页一致。
5. 通过后跑全量，把质量报告的结论告诉用户。
6. 新站点的前 20 条需要人工全部核对一遍；之后按 3% 抽检。

## 判断结果时的注意事项

- 每个字段在 SQLite 的 `evidence` 表里都有来源 URL 和原文片段。用户质疑某个值时，先查证据再回答。
- “新进 PI”依赖入职年份，只从“XXXX 年加入/入职本校”或“XXXX-至今 本校”识别。没写年份的老师不会被标为新进，不代表不是新人。
- 同名老师会被标“站内同名，需人工确认”，不要自动合并。
- 优先级分数的规则在 `src/faculty_crawler/enrich.py`，技术到产品的映射在 `src/faculty_crawler/product_map.yaml`，产品团队可以直接改映射文件。

## 合规边界

- 只采集学校公开发布的工作信息（姓名、职称、工作邮箱和电话、研究方向、论文、项目）。
- 不采集私人手机、身份证、家庭住址；不登录、不绕过验证码；遵守 robots.txt；每个域名请求间隔默认 2.5 秒。
- 画像卡用于销售了解客户，不用于群发邮件。老师要求删除时，从数据库删除并在模板里排除。
