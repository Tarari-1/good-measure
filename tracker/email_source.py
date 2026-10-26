"""Where emails come from. Every email is UNTRUSTED data.

EmailSource is the interface the MCP server and the backend use. Today there is
SampleMailboxSource reads the fictional .eml files in data/mailbox/;
LocalMailSource reads emails the user pasted or imported (data/local_mail/); and the
optional read-only IMAP source lives in tracker/imap_source.py.

Sources are read-only by contract: there is no method to send, move, flag or
delete mail, and none may be added.
"""

from __future__ import annotations

import email
import email.policy
import re
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path
from typing import Any

from config import settings

EMAIL_ID_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{0,40}$")


@dataclass(frozen=True)
class EmailMessage:
    id: str
    from_name: str
    from_email: str
    to: str
    subject: str
    date: str  # ISO date, e.g. 2026-10-21
    body: str

    def summary(self) -> dict[str, Any]:
        """Header fields plus a short snippet (for lists)."""
        snippet = " ".join(self.body.split())[:140]
        return {"id": self.id, "from_name": self.from_name, "from_email": self.from_email,
                "subject": self.subject, "date": self.date, "snippet": snippet}

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class EmailSource(ABC):
    """Read-only access to a mailbox."""

    name: str = "abstract"

    @abstractmethod
    def list_ids(self) -> list[str]:
        """All message ids, oldest first."""

    @abstractmethod
    def get(self, email_id: str) -> EmailMessage | None:
        """One message, or None if the id is unknown."""

    def list_messages(self) -> list[EmailMessage]:
        return [m for m in (self.get(i) for i in self.list_ids()) if m is not None]


def parse_eml(raw: bytes, email_id: str) -> EmailMessage:
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    from_name, from_email = parseaddr(str(msg.get("From", "")))
    try:
        date = parsedate_to_datetime(str(msg.get("Date"))).date().isoformat()
    except (TypeError, ValueError):
        date = ""
    part = msg.get_body(preferencelist=("plain",))
    body = part.get_content() if part is not None else ""
    return EmailMessage(
        id=email_id, from_name=from_name, from_email=from_email.lower(), to=str(msg.get("To", "")),
        subject=str(msg.get("Subject", "")), date=date, body=body.replace("\r\n", "\n").strip(),
    )


class SampleMailboxSource(EmailSource):
    """The default source: fictional .eml files in a folder. The file stem is the id."""

    name = "sample_mailbox"

    def __init__(self, folder: Path | None = None):
        self.folder = Path(folder or settings.MAILBOX_DIR)

    def list_ids(self) -> list[str]:
        ids = [p.stem for p in self.folder.glob("*.eml") if EMAIL_ID_RE.match(p.stem)]
        msgs = [self.get(i) for i in ids]
        return [m.id for m in sorted((m for m in msgs if m), key=lambda m: (m.date, m.id))]

    def get(self, email_id: str) -> EmailMessage | None:
        if not isinstance(email_id, str) or not EMAIL_ID_RE.match(email_id):
            return None
        path = self.folder / f"{email_id}.eml"
        if not path.is_file():
            return None
        return parse_eml(path.read_bytes(), email_id)


class CompositeSource(EmailSource):
    """Several read-only sources seen as one mailbox (ids must not clash)."""

    def __init__(self, sources: list[EmailSource]):
        self.sources = sources
        self.name = "+".join(s.name for s in sources)

    def list_ids(self) -> list[str]:
        msgs = [m for src in self.sources for m in src.list_messages()]
        return [m.id for m in sorted(msgs, key=lambda m: (m.date, m.id))]

    def get(self, email_id: str) -> EmailMessage | None:
        for src in self.sources:
            msg = src.get(email_id)
            if msg is not None:
                return msg
        return None


class LocalMailSource(SampleMailboxSource):
    """Emails a user pasted in the Inbox or imported read-only from IMAP (data/local_mail/).

    They are just as untrusted as any other email and go through every defense.
    """

    name = "local_mail"

    def __init__(self, folder: Path | None = None):
        super().__init__(folder or settings.LOCAL_MAIL_DIR)

    def list_ids(self) -> list[str]:
        return super().list_ids() if self.folder.exists() else []


def save_local_email(*, email_id: str, from_name: str, from_email: str, subject: str, body: str, date: str,
                     origin: str) -> EmailMessage:
    """Write one pasted/imported email as an .eml file in data/local_mail/ (never anywhere else)."""
    from email.message import EmailMessage as _Msg
    from email.utils import formataddr

    if not EMAIL_ID_RE.match(email_id):
        raise ValueError("bad email id")
    msg = _Msg()
    msg["From"] = formataddr((from_name, from_email)) if from_name else from_email
    msg["To"] = "tracker-inbox@brightfutures.example"
    msg["Subject"] = subject
    msg["Date"] = _rfc_date(date)
    msg["X-Tracker-Origin"] = origin
    msg.set_content(body + "\n")
    settings.LOCAL_MAIL_DIR.mkdir(parents=True, exist_ok=True)
    (settings.LOCAL_MAIL_DIR / f"{email_id}.eml").write_bytes(bytes(msg))
    return parse_eml(bytes(msg), email_id)


def _rfc_date(iso: str) -> str:
    from datetime import datetime
    from email.utils import format_datetime

    return format_datetime(datetime.fromisoformat(f"{iso}T12:00:00"))


def default_source() -> EmailSource:
    """The bundled sample mailbox plus any pasted/imported emails."""
    return CompositeSource([SampleMailboxSource(), LocalMailSource()])
