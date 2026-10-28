"""中文姓名 → 英文论文署名变体，以及论文作者与目标老师的姓名匹配。"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from pypinyin import Style, lazy_pinyin

COMPOUND_SURNAMES = [
    "欧阳", "司马", "诸葛", "上官", "东方", "皇甫", "尉迟", "公孙", "慕容", "令狐", "长孙", "宇文",
    "司徒", "夏侯", "澹台", "端木", "轩辕", "钟离", "闻人", "南宫", "西门", "百里", "呼延", "申屠",
]
# 多音字姓氏的读音
SURNAME_READING = {
    "单": "shan", "曾": "zeng", "解": "xie", "区": "ou", "仇": "qiu", "朴": "piao", "查": "zha",
    "缪": "miao", "翟": "zhai", "盖": "ge", "乐": "yue", "覃": "qin", "召": "shao", "繁": "po",
    "员": "yun", "种": "chong", "秘": "bi", "冼": "xian", "隗": "wei", "过": "guo", "华": "hua",
    "任": "ren", "沈": "shen", "长孙": "zhangsun", "尉迟": "yuchi", "万俟": "moqi", "柏": "bai",
}
# ü 的几种写法
V_VARIANTS = {"lv": ["lv", "lu", "lyu"], "nv": ["nv", "nu", "nyu"], "lve": ["lve", "lue"], "nve": ["nve", "nue"]}


def _ascii(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def norm_token(s: str) -> str:
    return re.sub(r"[^a-z]", "", _ascii(s or ""))


@dataclass
class NameForms:
    zh: str
    surnames: list[str] = field(default_factory=list)  # ["cao"], ["lv","lu","lyu"]
    given: str = ""  # "shixuan"
    given_syllables: list[str] = field(default_factory=list)  # ["shi","xuan"]
    initials: set[str] = field(default_factory=set)  # {"s", "sx"}
    alt_given: set[str] = field(default_factory=set)  # 从主页论文学到的其他名字写法，如 "pohsiang"
    learned_initials: set[str] = field(default_factory=set)  # 从主页学到、拼音推不出的缩写，如 "ph"、"ge"

    def query_names(self) -> list[str]:
        """Europe PMC AUTH 检索用的署名：Liu Shixuan / Liu S / Liu SX。"""
        out = []
        for sn in self.surnames[:2]:
            cap = sn.capitalize()
            out.append(f"{cap} {self.given.capitalize()}")
            for g in sorted(self.alt_given):
                out.append(f"{cap} {g.capitalize()}")
            for ini in sorted(self.initials, key=len):
                out.append(f"{cap} {ini.upper()}")
        return list(dict.fromkeys(out))


def name_forms(zh_name: str, en_hint: str | None = None) -> NameForms:
    zh = re.sub(r"\s+", "", zh_name)
    if any(zh.startswith(c) for c in COMPOUND_SURNAMES) and len(zh) >= 3:
        sur, giv = zh[:2], zh[2:]
    else:
        sur, giv = zh[:1], zh[1:]
    sur_py = SURNAME_READING.get(sur) or "".join(lazy_pinyin(sur, style=Style.NORMAL, v_to_u=False))
    giv_syl = [p for p in lazy_pinyin(giv, style=Style.NORMAL, v_to_u=False) if p]
    surnames = V_VARIANTS.get(sur_py, [sur_py])
    nf = NameForms(zh=zh, surnames=surnames, given="".join(giv_syl), given_syllables=giv_syl)
    nf.initials = {giv_syl[0][0]} if giv_syl else set()
    if len(giv_syl) > 1:
        nf.initials.add("".join(s[0] for s in giv_syl))
    # 主页上的英文名（如 “Yan Feng”“Rubing Liang”）作为额外写法
    if en_hint:
        toks = [norm_token(t) for t in re.split(r"[\s,]+", en_hint) if norm_token(t)]
        if len(toks) >= 2:
            for last, first in ((toks[-1], "".join(toks[:-1])), (toks[0], "".join(toks[1:]))):
                if last in nf.surnames and first and first != nf.given:
                    nf.given = nf.given or first
    return nf


def match_author(nf: NameForms, last: str | None, first: str | None, initials: str | None) -> str | None:
    """返回 'full'（姓+完整名）、'initial'（姓+首字母）或 None。"""
    ln = norm_token(last or "")
    if ln not in nf.surnames:
        return None
    fn = norm_token(first or "")
    if fn and ((nf.given and fn == nf.given) or fn in nf.alt_given):
        return "full"
    ini = norm_token(initials or "")
    # 主页上本人用过的非拼音署名（如 Po-Hsiang → PH、Guang-E → GE）
    if ini and ini in nf.learned_initials:
        return "full" if fn and len(fn) > 2 else "initial"
    if fn and len(fn) > 2 and fn != nf.given and fn not in nf.alt_given:
        return None  # 有完整名但不同，说明是另一个人
    if ini and ini in nf.initials:
        return "initial"
    if fn and fn in nf.initials:
        return "initial"
    return None


def learn_from_seeds(nf: NameForms, seed_text: str) -> NameForms:
    """从主页所列论文的作者串里学习本人的英文署名（如 Chen GE*、Wang, P. H.、Hao Zuo）。

    只接受在过半条目中出现、或带通讯/共一标记（* #）的写法，避免把同姓合作者学进来。
    """
    lines = [ln for ln in seed_text.split("\n") if ln.strip()]
    if not lines:
        return nf
    sur = "|".join(re.escape(s.capitalize()) for s in nf.surnames) + "|" + "|".join(s.upper() for s in nf.surnames)
    pats = [
        # 姓在前：Chen GE*、Wang, P. H.、Sheng, Meng-jun、Liu Shixuan
        re.compile(rf"\b(?:{sur})\s*,?\s+((?:[A-Z]\.?\s?-?\s?){{1,3}}(?![a-z])|[A-Z][a-z]+(?:-[A-Za-z]+)?)\s*([*#†]?)"),
        # 名在前：Hao Zuo1、Shixuan Liu*
        re.compile(rf"\b([A-Z][a-z]+(?:-[A-Za-z]+)?)\s+(?:{sur})\b\s*\d*\s*([*#†]?)"),
    ]
    counts: dict[tuple[str, str], int] = {}
    starred: set[tuple[str, str]] = set()
    for ln in lines:
        seen_line = set()
        for kind, pat in enumerate(pats):
            for m in pat.finditer(ln):
                tok = norm_token(m.group(1))
                if not tok:
                    continue
                form = ("init", tok) if (len(tok) <= 3 and kind == 0 and m.group(1).replace(".", "").replace(" ", "").replace("-", "").isupper()) else ("given", tok)
                if form in seen_line:
                    continue
                seen_line.add(form)
                counts[form] = counts.get(form, 0) + 1
                if m.group(2):
                    starred.add(form)
    need = max(2, (len(lines) + 1) // 2)
    for form, n in counts.items():
        if n >= need or (form in starred and n >= 1):
            kind, tok = form
            # 学到的写法必须和本人拼音首字母兼容，避免把同姓的导师/合作者（如 Yong Zhang）学进来
            if not compatible_first(nf.given, tok):
                continue
            if kind == "init":
                if len(tok) > len(nf.given_syllables) + 1:
                    continue
                if tok not in nf.initials and len(tok) >= 2:
                    nf.learned_initials.add(tok)
                nf.initials.add(tok)
            elif tok != nf.given and tok not in COMMON_WORDS:
                nf.alt_given.add(tok)
    return nf


# 拼音声母 → 其他拼写体系（威妥玛、粤语、港台常用）可能的首字母
INITIAL_COMPAT = {
    "b": "bp", "p": "p", "d": "dt", "t": "t", "g": "gk", "k": "k", "j": "jc", "q": "qc", "x": "xh",
    "z": "ztc", "c": "ct", "s": "s", "r": "rj", "h": "hfw", "f": "f", "w": "wv", "y": "yi", "l": "l",
    "m": "m", "n": "n", "a": "a", "e": "e", "o": "o",
}


def compatible_first(given_pinyin: str, other: str) -> bool:
    if not given_pinyin or not other:
        return True
    return other[0] in INITIAL_COMPAT.get(given_pinyin[0], given_pinyin[0])


COMMON_WORDS = {"et", "al", "and", "the", "cell", "nature", "science", "journal", "in", "of"}
