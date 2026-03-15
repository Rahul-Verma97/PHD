"""
Alert Engine — sends consolidated alerts via Telegram (preferred) and/or Email.
One message per run containing all new findings.
"""
import os
import json
import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

ALERT_LOG = Path(__file__).parent.parent / "data" / "alerts_log.json"
EMOJI = {"high": "🔴", "low": "🟡"}


class AlertEngine:
    def __init__(self):
        self.telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.telegram_chat  = os.getenv("TELEGRAM_CHAT_ID", "")
        self.gmail_address  = os.getenv("GMAIL_ADDRESS", "")
        self.gmail_password = os.getenv("GMAIL_APP_PASSWORD", "")
        self.dry_run        = os.getenv("DRY_RUN", "false").lower() == "true"

    # ── Public API ─────────────────────────────────────────────────────────────

    def send(self, findings: list):
        if not findings:
            return

        if self.dry_run:
            logger.info("[DRY RUN] Would send %d alerts:", len(findings))
            for f in findings:
                logger.info("  %s | %s | %s", f.professor_name, f.source, f.url)
            return

        self._log_to_file(findings)

        if self.telegram_token and self.telegram_chat:
            self._send_telegram(findings)
        else:
            logger.warning("Telegram not configured — skipping Telegram alert")

        if self.gmail_address and self.gmail_password:
            self._send_email(findings)
        else:
            logger.warning("Gmail not configured — skipping email alert")

    # ── Telegram ───────────────────────────────────────────────────────────────

    def _send_telegram(self, findings: list):
        # Split into chunks of 5 to avoid hitting Telegram's 4096-char limit
        chunks = [findings[i:i+5] for i in range(0, len(findings), 5)]
        for chunk in chunks:
            msg = self._build_telegram_message(chunk)
            try:
                resp = requests.post(
                    f"https://api.telegram.org/bot{self.telegram_token}/sendMessage",
                    json={
                        "chat_id": self.telegram_chat,
                        "text": msg,
                        "parse_mode": "Markdown",
                        "disable_web_page_preview": True,
                    },
                    timeout=15,
                )
                resp.raise_for_status()
                logger.info("Telegram alert sent (%d findings in this chunk)", len(chunk))
            except Exception as e:
                logger.error("Telegram alert failed: %s", e)

    def _build_telegram_message(self, findings: list) -> str:
        lines = [f"*PhD Hiring Monitor* — {datetime.utcnow().strftime('%Y-%m-%d')}",
                 f"Found *{len(findings)}* new signal(s)\n"]
        for f in findings:
            emoji = EMOJI.get(f.confidence, "⚪")
            lines.append(
                f"{emoji} *{f.professor_name}* ({f.university if hasattr(f, 'university') else ''})\n"
                f"Source: `{f.source}`  |  Confidence: `{f.confidence}`\n"
                f"[View post/page]({f.url})\n"
                f"_{f.text_snippet[:200].strip()}_\n"
            )
        return "\n".join(lines)

    # ── Email ──────────────────────────────────────────────────────────────────

    def _send_email(self, findings: list):
        subject = f"[PhD Monitor] {len(findings)} hiring signal(s) — {datetime.utcnow().strftime('%Y-%m-%d')}"
        body = self._build_email_body(findings)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = self.gmail_address
        msg["To"]      = self.gmail_address
        msg.attach(MIMEText(body, "html"))

        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(self.gmail_address, self.gmail_password)
                server.sendmail(self.gmail_address, self.gmail_address, msg.as_string())
            logger.info("Email alert sent to %s", self.gmail_address)
        except Exception as e:
            logger.error("Email alert failed: %s", e)

    def _build_email_body(self, findings: list) -> str:
        rows = ""
        for f in findings:
            color = "#cc0000" if f.confidence == "high" else "#cc8800"
            rows += f"""
            <tr>
              <td style="padding:8px;border-bottom:1px solid #eee">
                <b>{f.professor_name}</b><br>
                <small>{f.source} &bull; <span style="color:{color}">{f.confidence.upper()}</span></small>
              </td>
              <td style="padding:8px;border-bottom:1px solid #eee">
                <a href="{f.url}">{f.url[:60]}…</a>
              </td>
              <td style="padding:8px;border-bottom:1px solid #eee;color:#555;font-size:13px">
                {f.text_snippet[:250]}
              </td>
            </tr>"""

        return f"""
        <html><body style="font-family:Arial,sans-serif;max-width:900px;margin:auto">
          <h2 style="color:#333">PhD Hiring Monitor</h2>
          <p><b>{len(findings)} new hiring signal(s)</b> detected on {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</p>
          <table style="width:100%;border-collapse:collapse">
            <thead>
              <tr style="background:#f4f4f4">
                <th style="padding:8px;text-align:left">Professor</th>
                <th style="padding:8px;text-align:left">Link</th>
                <th style="padding:8px;text-align:left">Snippet</th>
              </tr>
            </thead>
            <tbody>{rows}</tbody>
          </table>
          <p style="color:#999;font-size:12px;margin-top:20px">
            PhD Monitor — running on GitHub Actions
          </p>
        </body></html>
        """

    # ── File log ───────────────────────────────────────────────────────────────

    def _log_to_file(self, findings: list):
        ALERT_LOG.parent.mkdir(parents=True, exist_ok=True)
        existing = []
        if ALERT_LOG.exists():
            try:
                existing = json.loads(ALERT_LOG.read_text())
            except Exception:
                pass

        for f in findings:
            existing.append({
                "professor_id":   f.professor_id,
                "professor_name": f.professor_name,
                "source":         f.source,
                "url":            f.url,
                "confidence":     f.confidence,
                "snippet":        f.text_snippet[:300],
                "found_at":       f.found_at.isoformat(),
            })

        ALERT_LOG.write_text(json.dumps(existing, indent=2))
        logger.debug("Alert log updated: %s", ALERT_LOG)
