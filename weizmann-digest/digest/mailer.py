"""Sends the digest over SMTP.

Deliberately plain: any SMTP server works - Weizmann's own relay, a
transactional service like Resend or Brevo, or a dedicated Gmail account with
an app password. Credentials come from environment variables, never the repo.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from email.utils import formataddr, formatdate

log = logging.getLogger(__name__)


def send(
    subject: str,
    html_body: str,
    text_body: str,
    recipients: list[str],
    settings: dict,
    display_name: str = "Weizmann Publications Digest",
) -> None:
    if not recipients:
        raise ValueError("No recipients configured - check `recipients` in config.yaml")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr((display_name, settings["sender"]))
    message["To"] = ", ".join(recipients)
    message["Date"] = formatdate(localtime=True)

    # Plain text first, HTML second: clients show the last part they can render.
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")

    port = int(settings["port"])
    log.info("Sending to %s via %s:%d", ", ".join(recipients), settings["host"], port)

    if port == 465:
        server = smtplib.SMTP_SSL(settings["host"], port, timeout=60)
    else:
        server = smtplib.SMTP(settings["host"], port, timeout=60)

    with server:
        if port != 465:
            server.starttls()
        server.login(settings["user"], settings["password"])
        server.send_message(message)

    log.info("Sent.")
