"""OPTIONAL read-only IMAP source. The app never needs it: the default path uses only
PORTKEY_API_KEY and the bundled sample mailbox.

Enabled only when IMAP_HOST, IMAP_USER and IMAP_APP_PASSWORD are all set (IMAP_PORT and
IMAP_FOLDER are optional). Credentials are read from the environment at connect time,
are never stored, logged, returned by the API or written to the audit trail.

Read-only by construction:
  - IMAP4_SSL only (certificate checked), SELECT with readonly=True (EXAMINE)
  - only UID SEARCH and UID FETCH are ever sent; every FETCH uses BODY.PEEK (never sets \\Seen)
  - _ReadOnly refuses any other command (STORE, COPY, MOVE, EXPUNGE, APPEND, DELETE, ...)
  - nothing is ever sent, moved, flagged or deleted

Imported emails are written to data/local_mail/ and are untrusted like every other
email: quarantine, grounding, permission and rules all apply.
"""

from __future__ import annotations

import imaplib
import os
import re
import ssl
from datetime import date
from email import message_from_bytes, policy
from email.utils import parseaddr, parsedate_to_datetime
from typing import Any

from tracker.email_source import EMAIL_ID_RE, EmailMessage, EmailSource, parse_eml, save_local_email

REQUIRED_ENV = ("IMAP_HOST", "IMAP_USER", "IMAP_APP_PASSWORD")
MAX_RESULTS = 50
_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_SAFE_TEXT = re.compile(r'["\\\r\n]')


def configured() -> bool:
    return all(os.environ.get(k, "").strip() for k in REQUIRED_ENV)


class ImapError(Exception):
    """A failure with a message that is safe to show (never contains credentials)."""


class _ReadOnly:
    """Wraps an imaplib connection and allows only read-only commands."""

    def __init__(self, conn: imaplib.IMAP4):
        self._c = conn

    def select_readonly(self, folder: str) -> None:
        typ, _ = self._c.select(f'"{_SAFE_TEXT.sub("", folder)}"', readonly=True)
        if typ != "OK":
            raise ImapError("Could not open the mail folder read-only.")

    def uid_search(self, *criteria: str) -> list[bytes]:
        typ, data = self._c.uid("SEARCH", None, *criteria)
        if typ != "OK":
            raise ImapError("Search failed.")
        return (data[0] or b"").split()

    def uid_fetch(self, uids: str, spec: str) -> list[Any]:
        if "BODY.PEEK[" not in spec or re.search(r"BODY\[", spec) or "RFC822" in spec.upper():
            raise ImapError("Refused: only BODY.PEEK fetches are allowed (they never mark mail as read).")
        if not re.fullmatch(r"[0-9,]+", uids):
            raise ImapError("Bad UID list.")
        typ, data = self._c.uid("FETCH", uids, spec)
        if typ != "OK":
            raise ImapError("Fetch failed.")
        return data

    def logout(self) -> None:
        try:
            self._c.logout()
        except Exception:  # noqa: BLE001
            pass


def _connect() -> _ReadOnly:
    if not configured():
        raise ImapError("IMAP is not configured (IMAP_HOST, IMAP_USER, IMAP_APP_PASSWORD).")
    host = os.environ["IMAP_HOST"].strip()
    port = int(os.environ.get("IMAP_PORT", "993") or 993)
    try:
        conn = imaplib.IMAP4_SSL(host, port, ssl_context=ssl.create_default_context(), timeout=20)
        conn.login(os.environ["IMAP_USER"].strip(), os.environ["IMAP_APP_PASSWORD"])
    except (imaplib.IMAP4.error, OSError) as exc:
        raise ImapError(f"Could not sign in to the mail server ({type(exc).__name__}).") from None
    ro = _ReadOnly(conn)
    ro.select_readonly(os.environ.get("IMAP_FOLDER", "INBOX") or "INBOX")
    return ro


def _imap_date(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.day:02d}-{_MONTHS[d.month - 1]}-{d.year}"


def search(since: str | None = None, sender: str | None = None, subject: str | None = None) -> list[dict[str, Any]]:
    """Headers of matching messages (newest first, at most MAX_RESULTS). Nothing is marked read."""
    criteria: list[str] = []
    if since:
        criteria += ["SINCE", _imap_date(since)]
    if sender:
        criteria += ["FROM", f'"{_SAFE_TEXT.sub("", sender)[:100]}"']
    if subject:
        criteria += ["SUBJECT", f'"{_SAFE_TEXT.sub("", subject)[:100]}"']
    conn = _connect()
    try:
        uids = conn.uid_search(*(criteria or ["ALL"]))[-MAX_RESULTS:][::-1]
        if not uids:
            return []
        data = conn.uid_fetch(",".join(u.decode() for u in uids),
                              "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
    finally:
        conn.logout()
    out = []
    for item in data:
        if not isinstance(item, tuple):
            continue
        uid = re.search(rb"UID (\d+)", item[0])
        hdr = message_from_bytes(item[1], policy=policy.default)
        name, addr = parseaddr(str(hdr.get("From", "")))
        try:
            when = parsedate_to_datetime(str(hdr.get("Date"))).date().isoformat()
        except (TypeError, ValueError):
            when = ""
        out.append({"uid": uid.group(1).decode() if uid else "", "from_name": name, "from_email": addr.lower(),
                    "subject": str(hdr.get("Subject", ""))[:200], "date": when})
    return out


def import_messages(uids: list[str]) -> list[str]:
    """Fetch the chosen messages (BODY.PEEK) and store them as untrusted emails in data/local_mail/."""
    uids = [u for u in uids if re.fullmatch(r"\d{1,10}", str(u))][:MAX_RESULTS]
    if not uids:
        return []
    conn = _connect()
    try:
        data = conn.uid_fetch(",".join(uids), "(BODY.PEEK[])")
    finally:
        conn.logout()
    ids = []
    for item in data:
        if not isinstance(item, tuple):
            continue
        m = re.search(rb"UID (\d+)", item[0])
        if not m:
            continue
        email_id = f"imap-{m.group(1).decode()}"
        if not EMAIL_ID_RE.match(email_id):
            continue
        msg = parse_eml(item[1], email_id)
        save_local_email(email_id=email_id, from_name=msg.from_name, from_email=msg.from_email,
                         subject=msg.subject, body=msg.body, date=msg.date or date.today().isoformat(),
                         origin="imap")
        ids.append(email_id)
    return ids


class ImapSource(EmailSource):
    """EmailSource view of the server: list_ids/get fetch live (read-only). The app imports
    chosen messages instead (import_messages), so processing never depends on the server."""

    name = "imap"

    def list_ids(self) -> list[str]:
        return [f"imap-{m['uid']}" for m in search()]

    def get(self, email_id: str) -> EmailMessage | None:
        if not email_id.startswith("imap-") or not email_id[5:].isdigit():
            return None
        conn = _connect()
        try:
            data = conn.uid_fetch(email_id[5:], "(BODY.PEEK[])")
        finally:
            conn.logout()
        for item in data:
            if isinstance(item, tuple):
                return parse_eml(item[1], email_id)
        return None
