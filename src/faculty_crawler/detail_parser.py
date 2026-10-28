"""详情页抽取：标题行切段 + 正则/词表启发式，每个字段登记证据。"""
from __future__ import annotations

import re
from datetime import date
from urllib.parse import urlsplit

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from .html_utils import absolutize, html_to_text
from .models import Teacher
from .normalize import find_honors, find_is_pi, find_position, find_supervisor, find_title, normalize_title
from .sites import DetailRule

SECTION_KEYS: dict[str, list[str]] = {
    "basic": ["基本信息", "个人信息", "联系方式", "联系信息", "Contact"],
    "bio": ["个人简介", "简介", "个人简历", "简历", "人物简介", "基本情况", "Biography", "Profile"],
    "experience": ["学术经历", "教育经历", "工作经历", "教育背景", "学习经历", "教育与工作经历", "工作履历", "学习与工作经历", "Education", "Experience"],
    "research": ["研究方向", "研究领域", "研究兴趣", "主要研究方向", "课题组研究方向", "研究方向包括", "研究内容", "研究简介", "Research Interests", "Research"],
    "papers": ["代表论著", "代表性论文", "代表论文", "代表性研究论文", "发表论文", "论文发表", "主要论文", "近年发表论文", "近年发表文章",
               "近期发表论文", "代表性成果", "学术成果", "科研成果", "发表文章", "代表作", "Publications", "Selected Publications"],
    "projects": ["承担项目", "科研项目", "主持项目", "主持科研项目", "在研项目", "科研基金", "主持的科研项目", "承担课题", "Grants", "Projects", "Funding"],
    "honors": ["荣誉奖励", "获奖情况", "荣誉称号", "学术兼职", "社会兼职", "奖励与荣誉", "Awards"],
    "teaching": ["讲授课程", "教学工作", "主讲课程", "教学"],
    "recruit": ["招生信息", "招生寄语", "招生招聘", "招聘信息", "人才招聘", "加入我们", "Join Us", "Openings"],
}
_HEADING_LOOKUP = {kw.lower(): key for key, kws in SECTION_KEYS.items() for kw in kws}
_HEADING_INLINE_RE = re.compile(
    r"^(" + "|".join(sorted((re.escape(k) for k in _HEADING_LOOKUP), key=len, reverse=True)) + r")\s*(?:[（(][^）)]{0,20}[）)])?\s*[：:]\s*(.*)$",
    re.I,
)
DIR_NOISE_RE = re.compile(r"发表|论文|文章|招生|招聘|欢迎|诚邀|主持|项目|联系方式|寄语|邮箱|电话|E-?mail", re.I)
DIR_PREFIX_RE = re.compile(r"^\s*(?:方向[一二三四五六七八九十\d]+[：:、.]?|[⑴⑵⑶⑷⑸⑹⑺⑻⑼⑽]|[（(]\d{1,2}[）)]|\d{1,2}[.、)）]|[一二三四五六七八九十][、.])\s*")


EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+\s*(?:@|＠|\[at\]|\(at\)|（at）| at |#)\s*[A-Za-z0-9.\-]+\.(?:edu\.cn|com\.cn|ac\.cn|org\.cn|com|cn|edu|org|net)", re.I)
PHONE_RE = re.compile(r"(?:电话|Tel|TEL|Phone|联系电话|办公电话)[：:\s]*((?:\+?86[-\s]?)?(?:0\d{2,3}[-\s]?)?\d{7,8}(?:[-转]\d{1,5})?)")
OFFICE_RE = re.compile(r"(?:办公室|办公地点|地址|通讯地址|办公地址|Office|Address)[：:\s]*([^\n]{4,60})")
LAB_RE = re.compile(r"([一-龥A-Za-z0-9]{2,20}(?:实验室|课题组|研究组|研究室|Lab|Laboratory))")
EXP_YEAR_RE = re.compile(r"((?:19|20)\d{2})\s*(?:年)?\s*(?:[.\-/]?\s*\d{1,2}\s*月?)?\s*(?:[-–—~～]|至|到)+\s*(?:今|至今|现在|present|Present|now)")
JOIN_RE = re.compile(r"((?:19|20)\d{2})\s*年\s*(?:\d{1,2}\s*月)?\s*(?:起|开始)?\s*(?:在|于|任|担任|为)?\s*(?:加入|入职|就职于|任职于|回国|全职加入|受聘|工作|任教)?")
RECRUIT_RE = re.compile(r"[^。\n]{0,30}(?:招收|招聘|欢迎[^。\n]{0,20}加入|诚聘|招募|长期招)[^。\n]{0,60}(?:博士后|研究生|博士生|硕士生|科研助理|技术员|实验员|工程师|本科生)[^。\n]{0,40}")
NOISE_LINES = re.compile(r"^(首页|English|中文|登录|论文下载|支撑材料|返回|更多|打印|关闭|分享|上一篇|下一篇|•|·|-->)$")


def _heading(line: str) -> tuple[str, str] | None:
    """判断一行是否为小标题；返回 (段落类型, 同行内容)。"""
    norm = re.sub(r"^\s*(?:[一二三四五六七八九十]+[、.]|\d{1,2}[.、])\s*", "", line)
    norm = re.sub(r"\s*[（(][^）)]{0,20}[）)]\s*", "", norm)
    norm = re.sub(r"[：:\s]+$", "", norm)
    key = _HEADING_LOOKUP.get(norm.lower())
    if key and len(norm) <= 24:
        return key, ""
    m = _HEADING_INLINE_RE.match(line.strip())
    if m:
        return _HEADING_LOOKUP[m.group(1).lower()], m.group(2).strip()
    return None


# 常见 CMS 的正文容器（博达、方正、自研站点等）
CONTENT_CANDIDATES = [
    ".wp_articlecontent", "#vsb_content", ".v_news_content", ".TRS_Editor", ".Article_Content",
    ".article-content", ".article_content", ".article", "article", "#content", ".content", ".main-content",
    ".detail", ".con", ".main",
]


def content_text(html: str, rule: DetailRule) -> tuple[str, HTMLParser]:
    tree = HTMLParser(html)
    for sel in rule.drop:
        for n in tree.css(sel):
            n.decompose()
    node = tree.css_first(rule.content) if rule.content else None
    if node is None and not rule.content:
        # 没有模板：选一个足够大的正文容器；容器太小（只是一块简介）就用整页
        body_text = html_to_text(tree)
        best, best_len = None, 0
        for sel in CONTENT_CANDIDATES:
            for cand in tree.css(sel)[:3]:
                n = len(html_to_text(cand))
                if n > best_len:
                    best, best_len = cand, n
        if best is not None and best_len >= 0.4 * len(body_text) and best_len >= 150:
            node = best
    text = html_to_text(node if node is not None else tree)
    return text, tree


def split_sections(text: str) -> dict[str, str]:
    """按“小标题行”切段；同一类标题出现多次（导航+正文）时保留内容最长的一段。"""
    lines = [ln.strip() for ln in text.split("\n")]
    lines = [ln for ln in lines if ln and not NOISE_LINES.match(ln)]
    heads: list[tuple[int, str, str]] = []
    for i, ln in enumerate(lines):
        h = _heading(ln)
        if h:
            heads.append((i, h[0], h[1]))
    sections: dict[str, str] = {}
    sections["_preamble"] = "\n".join(lines[: heads[0][0]]) if heads else "\n".join(lines)
    for j, (i, key, inline) in enumerate(heads):
        end = heads[j + 1][0] if j + 1 < len(heads) else len(lines)
        body = "\n".join(([inline] if inline else []) + lines[i + 1 : end]).strip()
        if len(body) > len(sections.get(key, "")):
            sections[key] = body
    return sections


def research_items(body: str) -> list[str]:
    """把研究方向段落拆成条目。

    多行时只保留“标题行”（短、括号外无逗号、无问句），跳过描述段落；
    只有一整句时，在括号外按顿号/逗号拆。
    """
    def clean(x: str) -> str:
        x = DIR_PREFIX_RE.sub("", x).strip(" 。；;，,、：:")
        return re.sub(r"^(?:主要)?(?:从事|致力于|包括|聚焦于?)", "", x).strip()

    def is_title(x: str) -> bool:
        return (4 <= len(x) <= 50 and not re.search(r"[？?。！!]", x)
                and len(_split_top_level(x, "，,")) == 1 and not DIR_NOISE_RE.search(x))

    lines: list[str] = []
    for ln in body.split("\n"):
        ln = ln.strip()
        if not ln:
            continue
        pieces = re.split(r"[；;]|(?=[⑴⑵⑶⑷⑸⑹⑺⑻⑼⑽])|(?=[（(]\d{1,2}[）)])", ln)
        pieces = [clean(p) for p in pieces if p and p.strip()]
        # 一行里用分号列了多个短条目才拆；否则整行作为一个候选
        if len(pieces) > 1 and all(is_title(p) for p in pieces if p):
            lines += [p for p in pieces if p]
        else:
            lines.append(clean(ln))
    titles = [x for x in lines if is_title(x)]
    single_list = len(lines) == 1 and len(titles) == 1 and len(_split_top_level(titles[0])) > 1 and len(titles[0]) > 30
    if len(titles) >= 2 or (titles and len(lines) == 1 and not single_list):
        items = titles
    else:
        first = re.split(r"[。！!？?]", body.strip())[0]
        items = [clean(x) for x in _split_top_level(first)]
        items = [x for x in items if 4 <= len(x) <= 50 and not DIR_NOISE_RE.search(x)]
        items = items or titles
    # 去掉被截断的重复项（“...”结尾且有完整版本）
    items = [x for x in items if not (x.endswith(("...", "…")) and any(o != x and o.startswith(x.rstrip(".…")) for o in items))]
    return _dedupe(items)[:8]


def _split_top_level(s: str, seps: str = "、，,") -> list[str]:
    out, buf, depth = [], [], 0
    for ch in s:
        if ch in "（(":
            depth += 1
        elif ch in "）)":
            depth = max(depth - 1, 0)
        if ch in seps and depth == 0:
            out.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    out.append("".join(buf))
    return out


def _dedupe(seq: list[str]) -> list[str]:
    seen, out = set(), []
    for x in seq:
        k = re.sub(r"\s+", "", x)
        if k and k not in seen:
            seen.add(k)
            out.append(x)
    return out


def _clean_email(raw: str) -> str:
    e = re.sub(r"\s*(?:＠|\[at\]|\(at\)|（at）| at |#)\s*", "@", raw, flags=re.I)
    return e.replace(" ", "").strip(".").lower()


def _list_items(body: str, min_len: int = 6, max_items: int = 30) -> list[str]:
    items = []
    for ln in body.split("\n"):
        # 只去掉行首的项目符号和序号（1. 1、 (1) [1]），保留年份
        ln = re.sub(r"^\s*(?:[•·▪◆■●\-–]+|\(?\[?\d{1,2}[\].)、）]|（\d{1,2}）)\s*", "", ln).strip()
        if len(ln) >= min_len:
            items.append(ln)
    return _dedupe(items)[:max_items]


def extract_detail(t: Teacher, html: str, url: str, rule: DetailRule, school_domains: set[str]) -> None:
    text, tree = content_text(html, rule)
    sec = split_sections(text)
    head = "\n".join(x for x in (sec.get("_preamble", ""), sec.get("basic", ""), sec.get("bio", "")) if x)
    whole = text

    # --- 职称（详情页优先，覆盖列表页） ---
    norm, raw = find_title(head[:1500]) if head else (None, None)
    if norm:
        t.add("title_raw", raw, url, snippet=raw or "", method="heuristic", confidence=0.85, overwrite=True)
        t.add("title", norm, url, snippet=raw or "", method="heuristic", confidence=0.85, overwrite=True)

    # --- 邮箱：优先学校域名 ---
    emails = _dedupe([_clean_email(m.group(0)) for m in EMAIL_RE.finditer(whole)])
    if emails:
        emails.sort(key=lambda e: (not any(e.endswith(d) for d in school_domains), len(e)))
        best = emails[0]
        conf = 0.95 if any(best.endswith(d) for d in school_domains) else 0.7
        t.add("email", best, url, snippet=best, method="heuristic", confidence=conf, overwrite=True)
        if len(emails) > 1:
            t.raw["other_emails"] = emails[1:5]

    # --- 电话、办公室 ---
    m = PHONE_RE.search(whole)
    if m and len(re.sub(r"\D", "", m.group(1))) >= 7:
        t.add("phone", m.group(1).strip(), url, snippet=m.group(0), method="heuristic", confidence=0.85)
    m = OFFICE_RE.search(head or whole)
    if m:
        office = re.split(r"\s{2,}|邮箱|电话|E-?mail", m.group(1))[0].strip(" ：:，,")
        if 3 <= len(office) <= 60 and "@" not in office:
            t.add("office", office, url, snippet=m.group(0), method="heuristic", confidence=0.75)

    # --- 导师资格、头衔、职务 ---
    sup = find_supervisor(head or whole[:2000]) or find_supervisor(whole[:6000])
    if sup:
        t.add("supervisor", sup, url, snippet="、".join(sup), method="heuristic", confidence=0.85)
    honors = find_honors(whole)
    if honors:
        t.add("honors", honors, url, snippet="、".join(honors), method="heuristic", confidence=0.7)
    pos = find_position(head or whole[:2000])
    if pos:
        t.add("position", pos, url, snippet=pos, method="heuristic", confidence=0.6)

    if find_is_pi(whole[:6000]):
        t.add("is_pi", True, url, snippet="课题组长/独立PI", method="heuristic", confidence=0.7)

    # --- 研究方向 ---
    research = sec.get("research", "")
    if not research:
        # 没有小标题：找“研究方向/主要从事”后面的内容，跳过“对相关研究方向感兴趣”这类招生句
        for m in re.finditer(r"(?:研究方向|研究领域|研究兴趣|主要从事|致力于)(?:主要)?(?:为|是|包括|有)?[：:]?", whole):
            ctx = whole[max(0, m.start() - 8): m.start()]
            if re.search(r"相关|感兴趣|对", ctx):
                continue
            tail = whole[m.end(): m.end() + 600].lstrip()
            stop = re.search(r"\n(?:近年|代表|发表|主持|联系|招生|欢迎|诚邀|获奖|荣誉)", tail)
            block = tail[: stop.start()] if stop else tail
            # 同一行接着写的是一句话，截到句号；换行后的编号列表整段保留
            first, _, rest = block.partition("\n")
            research = first.split("。")[0] if first.strip() else rest
            if re.match(r"\s*(?:[⑴（(]\d?|\d[.、])", first):
                research = block  # 第一行就是编号条目
            elif first.strip() and re.match(r"\s*(?:[⑴（(]|\d[.、])", rest or ""):
                research = rest
            break
    if research:
        dirs = research_items(research)
        conf = 0.85 if sec.get("research") else 0.6
        t.add("research_directions", dirs, url, snippet=research[:200], method="heuristic", confidence=conf)
        t.add("research_text", research[:2000], url, snippet=research[:200], method="heuristic", confidence=conf)

    # --- 简介、经历、论文、项目 ---
    bio = sec.get("bio") or sec.get("_preamble", "")
    if bio:
        t.add("bio_text", bio[:3000], url, snippet=bio[:200], method="heuristic", confidence=0.7)
    exp = sec.get("experience", "")
    if exp:
        t.add("experience", _list_items(exp, min_len=6, max_items=20), url, snippet=exp[:200], method="heuristic")
    if sec.get("papers"):
        papers = [p for p in _list_items(sec["papers"], min_len=30, max_items=30)]
        t.add("papers", papers, url, snippet=sec["papers"][:200], method="heuristic", confidence=0.8)
    elif re.search(r"代表性?论文|发表论文", whole):
        tail = whole[re.search(r"代表性?论文|发表论文", whole).end():]
        papers = [p for p in _list_items(tail, min_len=30, max_items=30) if re.search(r"(19|20)\d{2}", p)]
        t.add("papers", papers, url, snippet=tail[:200], method="heuristic", confidence=0.7)
    if sec.get("projects"):
        t.add("projects", _list_items(sec["projects"], min_len=6, max_items=20), url,
              snippet=sec["projects"][:200], method="heuristic", confidence=0.8)
    else:
        projs = _dedupe(re.findall(r"[^。\n]{0,40}(?:国家自然科学基金|国家重点研发计划|973|863|省自然科学基金|重大专项)[^。\n]{0,60}", whole))
        if projs:
            t.add("projects", projs[:15], url, snippet=projs[0], method="heuristic", confidence=0.6)

    # --- 入职年份（新进教师信号） ---
    joined = _joined_year(exp or whole, t.school)
    if joined:
        t.add("joined_year", joined[0], url, snippet=joined[1], method="heuristic", confidence=0.7)

    # --- 实验室 ---
    m = LAB_RE.search(head or whole[:3000])
    if m and not re.search(r"重点实验室|国家实验室", m.group(1)):
        t.add("lab_name", m.group(1), url, snippet=m.group(0), method="heuristic", confidence=0.5)
    for a in tree.css("a"):
        href = absolutize(url, (a.attributes or {}).get("href"))
        label = a.text(strip=True)
        if not href or not href.startswith("http") or href.rstrip("/") == url.rstrip("/"):
            continue
        if re.search(r"返回|首页|学院|学校|登录|English|中文", label):
            continue
        path = urlsplit(href).path.strip("/")
        looks_lab = re.search(r"课题组|实验室|研究组|个人网站|lab\b|laboratory|group|homepage|website", label, re.I) \
            or re.search(r"lab|group", urlsplit(href).netloc + "/" + path, re.I)
        if looks_lab and path not in ("", "index.html", "index.htm"):
            t.add("lab_url", href, url, snippet=label, method="heuristic", confidence=0.6)
            break
        host = urlsplit(href).netloc.lower()
        if looks_lab and host != urlsplit(url).netloc and not (host.startswith("www.") and host.endswith(".edu.cn") and not path):
            # 独立域名的课题组网站；排除学校主站首页（如 www.sjtu.edu.cn/）
            t.add("lab_url", href, url, snippet=label, method="heuristic", confidence=0.6)
            break

    # --- 招生/招聘 ---
    rec = _dedupe([m.group(0).strip() for m in RECRUIT_RE.finditer(whole)])
    if sec.get("recruit"):
        rec = _dedupe([sec["recruit"][:300]] + rec)
    if rec:
        t.add("recruiting", rec[:5], url, snippet=rec[0], method="heuristic", confidence=0.7)

    t.raw["sections"] = sorted(k for k in sec if not k.startswith("_"))
    t.raw["text_len"] = len(whole)


def _joined_year(text: str, school: str) -> tuple[int, str] | None:
    """从经历里找“XXXX-至今 本校”或“XXXX年起在本校工作/加入本校”，取最早的一次。"""
    this_year = date.today().year
    short = school.replace("大学", "") if len(school.replace("大学", "")) >= 3 else school
    cands: list[tuple[int, str]] = []
    for ln in text.split("\n"):
        # 只看匹配点之后的一小段，避免同一行里其他单位的经历被算到本校
        for m in EXP_YEAR_RE.finditer(ln):
            ctx = re.split(r"[。；;]", ln[m.start(): m.end() + 30])[0]
            if school in ctx or short in ctx:
                cands.append((int(m.group(1)), ctx.strip()))
        for m in JOIN_RE.finditer(ln):
            if not re.search(r"起|开始|加入|入职|就职|任职|回国|受聘|任教", m.group(0)):
                continue
            ctx = re.split(r"[。；;]", ln[m.start(): m.end() + 30])[0]
            if (school in ctx or short in ctx or "本院" in ctx or "我院" in ctx) and not re.search(r"毕业|获.{0,8}学位|攻读", ctx):
                cands.append((int(m.group(1)), ctx.strip()))
    cands = [c for c in cands if 1950 <= c[0] <= this_year]
    if not cands:
        return None
    return min(cands, key=lambda c: c[0])


def normalize_list_title(t: Teacher, stub_title: str | None, url: str) -> None:
    if not stub_title:
        return
    norm = normalize_title(stub_title)
    t.add("title_raw", stub_title, url, snippet=stub_title, method="template", confidence=0.9)
    if norm:
        t.add("title", norm, url, snippet=stub_title, method="template", confidence=0.9)
