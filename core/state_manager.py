"""
State Manager — SQLite-backed deduplication and run logging.
Tracks every finding ever seen so we never send duplicate alerts.
"""
import sqlite3
import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from dataclasses import asdict

DB_PATH = Path(__file__).parent.parent / "data" / "state.db"

logger = logging.getLogger(__name__)


def _hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


class StateManager:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or str(DB_PATH)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS seen_findings (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    professor_id TEXT NOT NULL,
                    url_hash    TEXT NOT NULL,
                    text_hash   TEXT NOT NULL,
                    source      TEXT NOT NULL,
                    first_seen  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    alert_sent  BOOLEAN DEFAULT FALSE,
                    UNIQUE(url_hash, text_hash)
                );

                CREATE TABLE IF NOT EXISTS run_log (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    professors_checked  INTEGER DEFAULT 0,
                    findings_raw        INTEGER DEFAULT 0,
                    findings_new        INTEGER DEFAULT 0,
                    errors              TEXT DEFAULT ''
                );
            """)
        logger.debug("Database initialized at %s", self.db_path)

    def is_new(self, finding) -> bool:
        """Return True if this (url, text) pair has never been seen before."""
        url_h = _hash(finding.url)
        txt_h = _hash(finding.text_snippet)
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id FROM seen_findings WHERE url_hash=? AND text_hash=?",
                (url_h, txt_h),
            ).fetchone()
        return row is None

    def record(self, finding):
        """Insert a finding into the DB and mark alert as sent."""
        url_h = _hash(finding.url)
        txt_h = _hash(finding.text_snippet)
        with self._conn() as conn:
            try:
                conn.execute(
                    """INSERT INTO seen_findings
                       (professor_id, url_hash, text_hash, source, alert_sent)
                       VALUES (?, ?, ?, ?, ?)""",
                    (finding.professor_id, url_h, txt_h, finding.source, True),
                )
            except sqlite3.IntegrityError:
                pass  # already exists — race condition guard

    def log_run(self, professors_checked: int, findings_new: int,
                findings_raw: int = 0, errors: list = None):
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO run_log
                   (professors_checked, findings_raw, findings_new, errors)
                   VALUES (?, ?, ?, ?)""",
                (professors_checked, findings_raw, findings_new,
                 json.dumps(errors or [])),
            )
        logger.info(
            "Run logged — checked=%d raw=%d new=%d errors=%d",
            professors_checked, findings_raw, findings_new, len(errors or []),
        )

    def recent_alerts(self, limit: int = 20) -> list[dict]:
        """Return last N alerts for reporting."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT professor_id, source, first_seen
                   FROM seen_findings
                   ORDER BY first_seen DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [{"professor_id": r[0], "source": r[1], "first_seen": r[2]} for r in rows]
