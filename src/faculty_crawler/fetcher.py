"""礼貌抓取：按域名限速、重试退避、robots、原始页面落盘缓存。"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import ssl
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx

from . import config
from .html_utils import decode_html

log = logging.getLogger(__name__)


@dataclass
class Page:
    url: str  # 请求的 URL
    final_url: str  # 跳转后的 URL
    status: int
    html: str
    from_cache: bool = False


class FetchError(RuntimeError):
    pass


def _ssl_context() -> ssl.SSLContext | bool:
    """优先使用环境变量里的 CA（企业代理或云环境会注入自己的 CA）。"""
    for var in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE"):
        path = os.environ.get(var)
        if path and Path(path).exists():
            return ssl.create_default_context(cafile=path)
    ccr = Path("/root/.ccr/ca-bundle.crt")
    if ccr.exists():
        return ssl.create_default_context(cafile=str(ccr))
    return True


def _swap_scheme(url: str) -> str:
    parts = urlsplit(url)
    scheme = "https" if parts.scheme == "http" else "http"
    return urlunsplit((scheme, *parts[1:]))


class Fetcher:
    def __init__(self, *, min_interval: float | None = None, use_cache: bool = True,
                 cache_dir: Path | None = None, respect_robots: bool | None = None,
                 max_age_hours: float | None = None) -> None:
        config.ensure_dirs()
        self.min_interval = config.MIN_INTERVAL_SEC if min_interval is None else min_interval
        self.use_cache = use_cache
        self.cache_dir = cache_dir or config.RAW_DIR
        self.respect_robots = config.RESPECT_ROBOTS if respect_robots is None else respect_robots
        self.max_age_hours = max_age_hours
        self._last_hit: dict[str, float] = {}
        self._robots: dict[str, RobotFileParser | None] = {}
        self._scheme_pref: dict[str, str] = {}  # 某域名只能走某个协议时记住它
        self.client = httpx.Client(
            timeout=config.TIMEOUT_SEC, follow_redirects=True, verify=_ssl_context(),
            headers={"Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6"},
        )
        self.stats = {"network": 0, "cache": 0, "errors": 0}

    # ---------- 缓存 ----------
    def _cache_path(self, url: str) -> Path:
        h = hashlib.sha1(url.encode("utf-8")).hexdigest()
        host = urlsplit(url).netloc.replace(":", "_")
        return self.cache_dir / host / f"{h}.json"

    def _read_cache(self, url: str) -> Page | None:
        p = self._cache_path(url)
        if not p.exists():
            return None
        if self.max_age_hours is not None:
            age_h = (time.time() - p.stat().st_mtime) / 3600
            if age_h > self.max_age_hours:
                return None
        try:
            d = json.loads(p.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return Page(url=url, final_url=d["final_url"], status=d["status"], html=d["html"], from_cache=True)

    def _write_cache(self, page: Page) -> None:
        p = self._cache_path(page.url)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({
            "url": page.url, "final_url": page.final_url, "status": page.status,
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "html": page.html,
        }, ensure_ascii=False), "utf-8")

    # ---------- 礼貌 ----------
    def _throttle(self, host: str) -> None:
        last = self._last_hit.get(host)
        if last is not None:
            wait = self.min_interval * random.uniform(0.8, 1.3) - (time.monotonic() - last)
            if wait > 0:
                time.sleep(wait)
        self._last_hit[host] = time.monotonic()

    def allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        parts = urlsplit(url)
        host = parts.netloc
        if host not in self._robots:
            rp: RobotFileParser | None = RobotFileParser()
            try:
                r = self._get_raw(f"{parts.scheme}://{host}/robots.txt", host)
                if r.status_code == 200 and "text/plain" in r.headers.get("content-type", ""):
                    rp.parse(r.text.splitlines())
                else:
                    rp = None  # 没有 robots.txt 视为允许
            except httpx.HTTPError:
                rp = None
            self._robots[host] = rp
        rp = self._robots[host]
        return True if rp is None else rp.can_fetch("*", url)

    def _get_raw(self, url: str, host: str, headers: dict | None = None) -> httpx.Response:
        self._throttle(host)
        self.stats["network"] += 1
        return self.client.get(url, headers={"User-Agent": random.choice(config.USER_AGENTS), **(headers or {})})

    # ---------- 主入口 ----------
    def get(self, url: str, *, force: bool = False, headers: dict | None = None) -> Page:
        if self.use_cache and not force:
            cached = self._read_cache(url)
            if cached:
                self.stats["cache"] += 1
                return cached
        host = urlsplit(url).netloc
        target = url
        if self._scheme_pref.get(host) and urlsplit(url).scheme != self._scheme_pref[host]:
            target = _swap_scheme(url)
        if not self.allowed(target):
            raise FetchError(f"robots.txt 不允许抓取: {target}")

        last_err: Exception | None = None
        for attempt in range(config.MAX_RETRIES):
            try:
                r = self._get_raw(target, host, headers)
                if r.status_code in (429, 500, 502, 503, 504):
                    raise httpx.HTTPStatusError(f"HTTP {r.status_code}", request=r.request, response=r)
                charset = r.charset_encoding
                html = decode_html(r.content, charset)
                page = Page(url=url, final_url=str(r.url), status=r.status_code, html=html)
                if r.status_code == 200 and self.use_cache:
                    self._write_cache(page)
                return page
            except (httpx.ConnectError, httpx.ProxyError) as e:
                # 部分网络环境下 http 或 https 之一不通，切换协议再试一次
                last_err = e
                alt = _swap_scheme(target)
                log.info("连接失败，切换协议重试: %s -> %s", target, alt)
                target = alt
                self._scheme_pref[host] = urlsplit(alt).scheme
            except httpx.HTTPError as e:
                last_err = e
                backoff = (2 ** attempt) * 2 + random.random()
                log.warning("抓取失败(%s)，%0.1fs 后重试: %s", e, backoff, target)
                time.sleep(backoff)
        self.stats["errors"] += 1
        raise FetchError(f"抓取失败: {url}: {last_err}")

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "Fetcher":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
