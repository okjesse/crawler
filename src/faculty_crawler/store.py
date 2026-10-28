"""SQLite 存储：教师主表（JSON）+ 字段证据表 + 运行记录。"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .models import SiteReport, Teacher

SCHEMA = """
CREATE TABLE IF NOT EXISTS teacher (
  key TEXT PRIMARY KEY,
  site_id TEXT NOT NULL,
  school TEXT, college TEXT, name TEXT, title TEXT, email TEXT,
  priority INTEGER, confidence REAL,
  active INTEGER NOT NULL DEFAULT 1,
  first_seen TEXT, last_seen TEXT,
  data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_teacher_site ON teacher(site_id);
CREATE INDEX IF NOT EXISTS ix_teacher_name ON teacher(name);
CREATE TABLE IF NOT EXISTS evidence (
  teacher_key TEXT NOT NULL, field TEXT, value TEXT, source_url TEXT,
  snippet TEXT, method TEXT, confidence REAL, fetched_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_evidence_key ON evidence(teacher_key);
CREATE TABLE IF NOT EXISTS run (
  id INTEGER PRIMARY KEY AUTOINCREMENT, site_id TEXT, started_at TEXT, finished_at TEXT, report TEXT
);
"""


class Store:
    def __init__(self, path: Path | None = None) -> None:
        config.ensure_dirs()
        self.path = path or config.DB_PATH
        self.db = sqlite3.connect(self.path)
        self.db.executescript(SCHEMA)

    def save_site(self, site_id: str, teachers: list[Teacher], report: SiteReport, mark_inactive: bool = True) -> None:
        now = datetime.now(timezone.utc).isoformat()
        cur = self.db.cursor()
        seen = []
        for t in teachers:
            seen.append(t.key)
            row = cur.execute("SELECT first_seen FROM teacher WHERE key=?", (t.key,)).fetchone()
            first = row[0] if row else now
            cur.execute(
                "INSERT OR REPLACE INTO teacher(key,site_id,school,college,name,title,email,priority,confidence,active,first_seen,last_seen,data)"
                " VALUES (?,?,?,?,?,?,?,?,?,1,?,?,?)",
                (t.key, site_id, t.school, t.college, t.name, t.title, t.email, t.priority, t.confidence,
                 first, now, t.model_dump_json()),
            )
            cur.execute("DELETE FROM evidence WHERE teacher_key=?", (t.key,))
            cur.executemany(
                "INSERT INTO evidence VALUES (?,?,?,?,?,?,?,?)",
                [(t.key, e.field, e.value, e.source_url, e.snippet, e.method, e.confidence, e.fetched_at.isoformat())
                 for e in t.evidence],
            )
        # 本次没出现的老师标记为不活跃（调离/退休/页面改版），不删除
        if seen and mark_inactive:
            q = ",".join("?" * len(seen))
            cur.execute(f"UPDATE teacher SET active=0 WHERE site_id=? AND key NOT IN ({q})", (site_id, *seen))
        cur.execute("INSERT INTO run(site_id,started_at,finished_at,report) VALUES (?,?,?,?)",
                    (site_id, report.started_at.isoformat(),
                     (report.finished_at or report.started_at).isoformat(), report.model_dump_json()))
        self.db.commit()

    def teachers(self, site_id: str | None = None, active_only: bool = True) -> list[Teacher]:
        sql = "SELECT data FROM teacher WHERE 1=1"
        args: list = []
        if site_id:
            sql += " AND site_id=?"
            args.append(site_id)
        if active_only:
            sql += " AND active=1"
        sql += " ORDER BY priority DESC, name"
        return [Teacher.model_validate_json(r[0]) for r in self.db.execute(sql, args)]

    def recent_keys(self, site_id: str, max_age_days: float) -> set[str]:
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat()
        rows = self.db.execute("SELECT key FROM teacher WHERE site_id=? AND last_seen>=?", (site_id, cutoff))
        return {r[0] for r in rows}

    def get_input(self, name: str, school: str, profile_url: str | None) -> Teacher | None:
        for (data,) in self.db.execute("SELECT data FROM teacher WHERE site_id='input' AND name=? AND school=?", (name, school)):
            t = Teacher.model_validate_json(data)
            if not profile_url or (t.profile_url or "").rstrip("/") in (profile_url.rstrip("/"), "") or t.raw.get("input_url") == profile_url:
                return t
        return None

    def find(self, name: str) -> list[Teacher]:
        rows = self.db.execute("SELECT data FROM teacher WHERE name LIKE ? AND active=1", (f"%{name}%",))
        return [Teacher.model_validate_json(r[0]) for r in rows]

    def last_report(self, site_id: str) -> SiteReport | None:
        r = self.db.execute("SELECT report FROM run WHERE site_id=? ORDER BY id DESC LIMIT 1", (site_id,)).fetchone()
        return SiteReport.model_validate(json.loads(r[0])) if r else None
