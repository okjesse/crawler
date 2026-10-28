"""学校中文名 → 英文名、别名、域名（ROR API + 本地缓存 + 人工覆盖表）。"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

import httpx
import yaml

from . import config
from .fetcher import _ssl_context

log = logging.getLogger(__name__)
OVERRIDE_PATH = config.PKG_DIR / "institutions.yaml"


@dataclass
class Institution:
    zh: str
    en: str | None = None
    aliases: list[str] = field(default_factory=list)  # 英文写法，用于匹配论文单位
    ror: str | None = None
    domains: list[str] = field(default_factory=list)
    city: str | None = None

    def aff_patterns(self) -> list[str]:
        pats = [p.lower() for p in [self.en, *self.aliases] if p and len(p) >= 4]
        return list(dict.fromkeys(pats))


def _cache_path() -> Path:
    config.ensure_dirs()
    return config.DATA_DIR / "institutions_cache.json"


def _load_cache() -> dict:
    p = _cache_path()
    return json.loads(p.read_text("utf-8")) if p.exists() else {}


def _overrides() -> dict:
    return yaml.safe_load(OVERRIDE_PATH.read_text("utf-8")) or {} if OVERRIDE_PATH.exists() else {}


def resolve(zh_name: str) -> Institution:
    ov = _overrides().get(zh_name)
    if ov:
        return Institution(zh=zh_name, **ov)
    cache = _load_cache()
    if zh_name in cache:
        return Institution(**cache[zh_name])
    inst = Institution(zh=zh_name)
    try:
        with httpx.Client(timeout=20, verify=_ssl_context()) as c:
            r = c.get("https://api.ror.org/v2/organizations", params={"query": zh_name})
            r.raise_for_status()
            for item in r.json().get("items", [])[:10]:
                names = item.get("names", [])
                if not any(n["value"] == zh_name for n in names):
                    continue
                inst.ror = item["id"]
                for n in names:
                    if "ror_display" in n.get("types", []):
                        inst.en = n["value"]
                    elif n.get("lang") in (None, "en") and n["value"].isascii() and "acronym" not in n.get("types", []):
                        inst.aliases.append(n["value"])
                inst.domains = item.get("domains", []) or []
                locs = item.get("locations") or []
                if locs:
                    inst.city = locs[0].get("geonames_details", {}).get("name")
                break
    except httpx.HTTPError as e:
        log.warning("ROR 查询失败 %s: %s", zh_name, e)
    if inst.en:
        # 常见的论文单位缩写写法
        inst.aliases += [inst.en.replace("University", "Univ"), inst.en.replace(" Tong", "tong")]
        inst.aliases = [a for a in dict.fromkeys(inst.aliases) if a != inst.en]
        cache[zh_name] = asdict(inst)
        _cache_path().write_text(json.dumps(cache, ensure_ascii=False, indent=1), "utf-8")
    return inst
