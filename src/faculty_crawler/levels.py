"""抓取分级：L1/L2/L3 及模块开关。配置见 levels.yaml，可用 data/levels.yaml 或指定文件覆盖。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from . import config

DEFAULT_PATH = config.PKG_DIR / "levels.yaml"


class LevelError(ValueError):
    pass


def _deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in (over or {}).items():
        out[k] = _deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load_config(path: str | Path | None = None) -> dict:
    cfg = yaml.safe_load(DEFAULT_PATH.read_text("utf-8"))
    for p in ([Path(path)] if path else []) + [config.DATA_DIR / "levels.yaml"]:
        if p and p.exists():
            cfg = _deep_merge(cfg, yaml.safe_load(p.read_text("utf-8")) or {})
            break
    return cfg


def _env_present(var: str) -> bool:
    if os.environ.get(var):
        return True
    env = config.DATA_DIR / ".env"
    return env.exists() and any(ln.startswith(f"{var}=") and ln.split("=", 1)[1].strip()
                                for ln in env.read_text("utf-8").splitlines())


@dataclass
class Plan:
    level: str
    modules: list[str]
    params: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)  # 自动补依赖、因缺 Key 跳过等

    def has(self, module: str) -> bool:
        return module in self.modules

    def describe(self) -> str:
        return f"{self.level}：{'、'.join(self.modules)}"


def resolve_plan(level: str | None = None, with_: list[str] | None = None, without: list[str] | None = None,
                 path: str | Path | None = None) -> Plan:
    cfg = load_config(path)
    mods: dict = cfg["modules"]
    levels: dict = cfg["levels"]
    level = (level or cfg.get("default_level") or "L2").upper()
    if level not in levels:
        raise LevelError(f"未知级别 {level}，可选：{', '.join(levels)}")
    if levels[level].get("status") == "planned":
        planned = [m for m in levels[level].get("modules", []) if (mods.get(m) or {}).get("status") == "planned"]
        raise LevelError(f"级别 {level}（{levels[level].get('name')}）还在规划中：{levels[level].get('note', '')}"
                         f"。待启用模块：{', '.join(planned)}。现在可以用 L3 加 --with 选择已可用的模块。")
    wanted = list(levels[level].get("modules", []))
    for m in with_ or []:
        if m not in wanted:
            wanted.append(m)
    plan = Plan(level=level, modules=[], params=dict(levels[level].get("params") or {}))

    def depends_on(m: str, target: str, seen: set | None = None) -> bool:
        seen = seen or set()
        for dep in (mods.get(m) or {}).get("requires") or []:
            if dep == target or (dep not in seen and depends_on(dep, target, seen | {dep})):
                return True
        return False

    for m in without or []:
        if m not in mods:
            raise LevelError(f"未知模块 {m}")
        if m in wanted:
            wanted.remove(m)
        # 去掉一个模块时，连带去掉依赖它的模块
        for other in list(wanted):
            if depends_on(other, m):
                wanted.remove(other)
                plan.notes.append(f"{other} 依赖 {m}，一并去掉")

    def add(m: str, why: str | None = None) -> None:
        if m in plan.modules:
            return
        spec = mods.get(m)
        if spec is None:
            raise LevelError(f"未知模块 {m}，可选：{', '.join(k for k, v in mods.items() if v.get('status') != 'planned')}")
        if spec.get("status") == "planned":
            raise LevelError(f"模块 {m}（{spec.get('name')}）还在规划中，暂不能启用。{spec.get('note', '')}".strip())
        for dep in spec.get("requires") or []:
            if dep in (without or []):
                raise LevelError(f"模块 {m} 依赖 {dep}，不能同时去掉 {dep}")
            add(dep, why=m)
        if why:
            plan.notes.append(f"{m} 由 {why} 依赖自动加入")
        env = spec.get("needs_env")
        if env and not _env_present(env):
            plan.notes.append(f"{m}（{spec.get('name')}）需要环境变量 {env}，未设置，本次跳过")
            return
        plan.modules.append(m)

    for m in wanted:
        add(m)
    plan.params.setdefault("since_years", 8)
    plan.params.setdefault("max_papers", 300)
    plan.params.setdefault("fulltext_max_papers", 6)
    plan.params.setdefault("lab_site_max_pages", 5)
    return plan


def describe_levels(path: str | Path | None = None) -> str:
    cfg = load_config(path)
    mods, levels = cfg["modules"], cfg["levels"]
    lines = ["抓取级别：", ""]
    for lv, spec in levels.items():
        mark = "（默认）" if lv == cfg.get("default_level") else ""
        mark += " [规划中]" if spec.get("status") == "planned" else ""
        lines.append(f"{lv} {spec.get('name', '')}{mark}：{spec.get('desc', '')}")
        lines.append(f"    模块：{'、'.join(spec.get('modules', []))}")
        if spec.get("note"):
            lines.append(f"    说明：{spec['note']}")
    lines += ["", "模块："]
    for m, spec in mods.items():
        status = "规划中" if spec.get("status") == "planned" else "可用"
        env = spec.get("needs_env")
        if env and status == "可用":
            status += "，已配置 " + env if _env_present(env) else f"，缺少 {env}"
        req = f"；依赖 {', '.join(spec['requires'])}" if spec.get("requires") else ""
        lines.append(f"  {m:18s} [{status}] {spec.get('name', '')}：{spec.get('desc', '')}{req}")
        if spec.get("cost"):
            lines.append(f"  {'':18s} 开销：{spec['cost']}")
        if spec.get("note"):
            lines.append(f"  {'':18s} 说明：{spec['note']}")
    return "\n".join(lines)
