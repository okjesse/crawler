"""课题组网站：成员、招聘、仪器设备。同一网站最多抓几个页面。"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from .detail_parser import RECRUIT_RE
from .fetcher import FetchError, Fetcher
from .html_utils import absolutize, html_to_text
from .normalize import is_plausible_name

SUBPAGE_RE = re.compile(r"成员|人员|团队|队伍|members?|people|team|招聘|加入|join|position|opening|仪器|设备|平台|equipment|facilit|instrument", re.I)
ROLE_RE = {
    "博士后": r"博士后|博后|post-?doc",
    "博士生": r"博士生|博士研究生|ph\.?d\.? (student|candidate)",
    "硕士生": r"硕士生|硕士研究生|master'?s? student",
    "技术员/科研助理": r"技术员|实验员|科研助理|research assistant|technician|lab manager",
    "本科生": r"本科生|undergraduate",
}
INSTRUMENTS = {
    "流式细胞仪": r"流式细胞仪|flow cytometer|facs(?![a-z])",
    "激光共聚焦显微镜": r"共聚焦|confocal",
    "荧光定量 PCR 仪": r"荧光定量pcr|实时荧光定量|qpcr ?仪|real-time pcr (system|instrument)",
    "PCR 仪": r"pcr ?仪|thermal cycler|梯度pcr",
    "离心机": r"离心机|centrifuge",
    "酶标仪": r"酶标仪|microplate reader|plate reader",
    "移液工作站": r"移液工作站|液体工作站|液体处理|liquid handl",
    "细胞培养箱": r"培养箱|co2 incubator",
    "生物安全柜/超净台": r"生物安全柜|超净台|biosafety cabinet|laminar flow",
    "测序仪": r"测序仪|sequencer|nanopore|illumina",
    "质谱仪": r"质谱|mass spectromet",
    "液相色谱": r"液相色谱|hplc|uplc|fplc|akta",
    "发酵罐/生物反应器": r"发酵罐|bioreactor|fermenter",
    "凝胶成像": r"凝胶成像|gel (doc|imag)",
    "冷冻电镜": r"冷冻电镜|cryo-?em",
}
ROLE_WORDS = {"博士生", "硕士生", "博士后", "研究生", "本科生", "技术员", "实验员", "教授", "副教授", "讲师", "研究员",
              "副研究员", "导师", "成员", "团队", "毕业生", "在读", "校友", "合作者", "访问学者", "科研助理", "博士", "硕士",
              "学生", "老师", "负责人", "组长", "秘书", "首页", "联系", "招聘", "加入", "新闻", "论文", "仪器", "设备"}
CAPTCHA_RE = re.compile(r"人机验证|滑动验证|请输入验证码|安全验证|captcha|verify you are human|access denied", re.I)
LAB_NAME_RE = re.compile(r"([\u4e00-\u9fa5A-Za-z0-9“”\"]{2,16}(?:课题组|实验室|研究组|研究室))")
EN_NAME_RE = re.compile(r"\b([A-Z][a-z]+(?:[- ][A-Z][a-z]+)?\s[A-Z][a-z]{1,15})\b")


def _members(text: str) -> list[str]:
    names = []
    for ln in text.split("\n"):
        ln = ln.strip()
        if not ln or len(ln) > 60:
            continue
        for tok in re.split(r"[\s,，、/|;；()（）:：]+", ln):
            if 2 <= len(tok) <= 4 and tok not in ROLE_WORDS and is_plausible_name(tok):
                names.append(tok)
    return list(dict.fromkeys(names))


def scrape(web: Fetcher, lab_url: str, profile_url: str | None, max_pages: int = 5) -> dict:
    host = urlsplit(lab_url).netloc
    result = {"url": lab_url, "pages": [], "members": [], "roles": {}, "recruiting": [], "instruments": {},
              "errors": [], "lab_name": None}
    queue, seen = [lab_url], set()
    while queue and len(result["pages"]) < max_pages:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        try:
            page = web.get(url)
            if page.status != 200:
                raise FetchError(f"HTTP {page.status}")
        except FetchError as e:
            result["errors"].append(f"{url}: {e}")
            continue
        tree = HTMLParser(page.html)
        for sel in ("script", "style", "nav", "footer"):
            for n in tree.css(sel):
                n.decompose()
        text = html_to_text(tree)
        if CAPTCHA_RE.search(text[:500]) and len(text) < 800:
            # 合规边界：遇到人机验证不绕过，记录后停止抓这个网站
            result["errors"].append(f"{url}: 需要人机验证，已跳过（不绕过验证码）")
            break
        result["pages"].append(page.final_url)
        if not result["lab_name"]:
            m = LAB_NAME_RE.search(text[:800])
            if m:
                result["lab_name"] = m.group(1).strip("“”\"")
        is_member_page = url != lab_url and bool(re.search(r"成员|人员|团队|member|people|team", url + text[:200], re.I))
        if is_member_page or url == lab_url:
            result["members"] += _members(text) if is_member_page else []
        low = text.lower()
        for role, pat in ROLE_RE.items():
            n = len(re.findall(pat, low))
            if n:
                result["roles"][role] = max(result["roles"].get(role, 0), n)
        for m in RECRUIT_RE.finditer(text):
            s = m.group(0).strip()
            if s not in result["recruiting"]:
                result["recruiting"].append(s)
        for inst, pat in INSTRUMENTS.items():
            if re.search(pat, low) and inst not in result["instruments"]:
                result["instruments"][inst] = page.final_url
        if url == lab_url:
            for a in tree.css("a"):
                label = a.text(strip=True)
                href = absolutize(page.final_url, (a.attributes or {}).get("href"))
                if href and urlsplit(href).netloc == host and SUBPAGE_RE.search(label + " " + href) and href not in seen:
                    queue.append(href)
    result["members"] = list(dict.fromkeys(result["members"]))[:60]
    result["recruiting"] = result["recruiting"][:5]
    return result
