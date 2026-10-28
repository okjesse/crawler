"""归一化：职称、导师资格、人才头衔、行政职务、姓名。"""
from __future__ import annotations

import re

# 按优先级排列：先匹配更具体的
TITLE_RULES: list[tuple[str, str]] = [
    # “副/助理”必须排在“教授/研究员”之前，并用反向断言兜底
    (r"副教授", "副教授"),
    (r"副研究员", "副研究员"),
    (r"助理教授|助理研究员", "助理教授/助理研究员"),
    (r"(?<![副理])教授(?!级)", "教授"),
    (r"(?<![副理])研究员(?!助理)", "研究员"),
    (r"正高级工程师|高级工程师|高级实验师", "高级工程师/实验师"),
    (r"工程师|实验师", "工程师/实验师"),
    (r"讲师", "讲师"),
    (r"博士后|博后", "博士后"),
]
TITLE_ENUM = {t for _, t in TITLE_RULES}

# 职称层级，越大越资深（用于判断 PI）
TITLE_RANK = {
    "教授": 5, "研究员": 5, "副教授": 4, "副研究员": 4, "助理教授/助理研究员": 3,
    "高级工程师/实验师": 3, "讲师": 2, "工程师/实验师": 1, "博士后": 0,
}

HONOR_PATTERNS = [
    "中国科学院院士", "中国工程院院士", "国家杰出青年科学基金", "杰青", "国家优秀青年科学基金",
    "优青", "长江学者", "青年长江", "国家高层次人才", "国家级领军人才", "万人计划", "海外高层次人才",
    "国家海外高层次青年人才", "国家级青年人才", "国家青年人才", "青年千人", "青千", "四青", "省杰出青年", "杰出青年基金", "国家重点研发计划首席科学家", "首席科学家",
    "新世纪优秀人才", "上海市领军人才", "东方学者", "曙光学者", "浦江人才", "泰山产业创新领军人才", "启明星", "江苏特聘教授",
    "双创人才", "青蓝工程", "六大人才高峰", "兴药领军学者", "兴药优秀学者", "博士后创新人才",
    "求是特聘", "泰山学者", "珠江学者", "楚天学者", "闽江学者", "钱江学者", "黄河学者",
]

POSITION_PATTERNS = [
    "院长", "副院长", "党委书记", "党委副书记", "书记", "系主任", "系副主任", "所长", "副所长",
    "主任", "副主任", "实验室主任", "中心主任", "平台主任", "首席", "课题组长", "PI",
]

_NAME_PREFIX_RE = re.compile(r"^(博士生导师|硕士生导师|博导|硕导|教授|副教授|研究员|讲师|老师)\s*")
_NAME_SUFFIX_RE = re.compile(r"\s*(教授|副教授|研究员|副研究员|讲师|博士|老师|院士|博导|硕导)$")
CJK_NAME_RE = re.compile(r"^[一-龥]{1,4}(?:·[一-龥]{1,8})?$")
EN_NAME_RE = re.compile(r"^[A-Z][a-zA-Z\-']+(?: [A-Z][a-zA-Z\-'.]+){1,3}$")


def normalize_title(raw: str | None) -> str | None:
    if not raw:
        return None
    for pat, norm in TITLE_RULES:
        if re.search(pat, raw):
            return norm
    return None


def find_title(text: str) -> tuple[str | None, str | None]:
    """在一段文本中找到第一个职称。返回 (归一化职称, 原文)。"""
    best: tuple[int, str, str] | None = None
    for pat, norm in TITLE_RULES:
        m = re.search(pat, text)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), norm, m.group(0))
    if best is None:
        return None, None
    # 带上紧挨着的修饰前缀：特聘教授、长聘教轨副教授、讲席教授……
    pre = re.search(r"(特聘|讲席|二级|三级|长聘教轨|长聘|准聘|青年|首席|校聘|特别|正高级)+$", text[max(0, best[0] - 8): best[0]])
    raw = (pre.group(0) if pre else "") + best[2]
    return best[1], raw


def find_supervisor(text: str) -> list[str]:
    out = []
    if re.search(r"博士生导师|博导|博士研究生导师", text):
        out.append("博士生导师")
    if re.search(r"硕士生导师|硕导|硕士研究生导师", text):
        out.append("硕士生导师")
    return out


def find_honors(text: str) -> list[str]:
    """只认本人头衔：跳过“合作者/导师/团队/工作站”等语境里的提及。"""
    found: list[str] = []
    for h in HONOR_PATTERNS:
        for m in re.finditer(re.escape(h), text):
            left = re.split(r"[。；;\n，,]", text[max(0, m.start() - 12): m.start()])[-1]
            right = re.split(r"[。；;\n，,]", text[m.end(): m.end() + 6])[0]
            ctx = left + h + right
            if re.search(r"合作导师|导师为|导师是|合作|团队|工作站|师从|跟随|指导|联合|评审|推荐|委员会", ctx):
                continue
            if not any(h in f for f in found):
                found.append(h)
            break
    return found


def find_position(text: str) -> str | None:
    """找现任行政职务，跳过“曾任/原/2009年至2024年任”等卸任描述。"""
    for sent in re.split(r"[。；;\n]", text):
        if re.search(r"曾任|曾担任|历任|前任|兼任.*?(?:学会|协会|期刊|杂志)", sent):
            continue
        for m in re.finditer(r"([一-龥]{2,20}?(?:院长|副院长|系主任|系副主任|所长|实验室主任|中心主任|平台主任|党委书记))", sent):
            pos = m.group(1)[-20:]
            before = sent[max(0, m.start() - 14): m.start() + 2]
            if pos.startswith(("原", "前")) or re.search(r"原|前任|\d{4}\s*年?\s*[-至到]\s*\d{4}", before):
                continue
            if len(sent) < 120:
                return pos
    return None


def find_is_pi(text: str) -> bool | None:
    if re.search(r"课题组长|课题组组长|独立课题组|独立PI|研究组组长|实验室负责人|Principal Investigator|\bPI\b", text):
        return True
    return None


def clean_name(raw: str) -> str:
    s = re.sub(r"\s+", " ", raw.replace("　", " ")).strip()
    s = _NAME_PREFIX_RE.sub("", s)
    s = _NAME_SUFFIX_RE.sub("", s)
    # 中文名中间的空格（如“王  伟”）去掉
    if re.fullmatch(r"[一-龥 ]{2,8}", s):
        s = s.replace(" ", "")
    return s.strip()


NAV_WORD_RE = re.compile(
    r"(学院|大学|中心|首页|更多|简介|队伍|名录|教授|实验|导师|招聘|新闻|概况|动态|公告|通知|园地|建设|培养|研究|"
    r"工作|介绍|计划|服务|平台|基地|校友|就业|招生|党建|党群|展厅|建筑|典型|名师|之光|之星|下载|联系|领导|机构|"
    r"设置|学科|专业|课程|规章|制度|办事|指南|信息|公开|主页|登录|搜索|English)$")


def is_plausible_name(s: str) -> bool:
    if not s:
        return False
    if CJK_NAME_RE.match(s):
        if len(s) < 2 or "系" in s[-1:]:
            return False
        # 4 字及以上的中文串更可能是栏目名；2-3 字的只排除明确的栏目词
        if len(s) >= 4 and NAV_WORD_RE.search(s):
            return False
        return not re.fullmatch(r"(首页|更多|简介|新闻|通知|公告|English|登录|搜索|返回|下载)", s)
    return bool(EN_NAME_RE.match(s))


def school_domains(*urls: str) -> set[str]:
    """从站点 URL 推断学校主域名，例如 life.sjtu.edu.cn -> sjtu.edu.cn。"""
    out = set()
    for u in urls:
        host = re.sub(r"^https?://", "", u).split("/")[0].split(":")[0]
        parts = host.split(".")
        if len(parts) >= 3 and parts[-2:] == ["edu", "cn"]:
            out.add(".".join(parts[-3:]))
        elif len(parts) >= 2:
            out.add(".".join(parts[-2:]))
    return out
