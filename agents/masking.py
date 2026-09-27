"""Redacts sensitive fields from telemetry text before it reaches evidence/prompts.

Enterprise requirement from the capstone spec: "Sensitive log information should be
masked before being sent to the LLM." Applied in tools/logs_tool.py to every log
line returned by Loki, before it's ever added to state or an LLM message.
"""

import re

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_CARD_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")


def mask_text(text: str) -> str:
    text = _JWT_RE.sub("***REDACTED-JWT***", text)
    text = _CARD_RE.sub("***REDACTED-CARD***", text)
    text = _EMAIL_RE.sub("***REDACTED-EMAIL***", text)
    return text


if __name__ == "__main__":
    sample = (
        '{"customer_email": "jane.doe@example.com", "card_number": "4111-1111-1111-1111", '
        '"message": "charge processed"}'
    )
    print("before:", sample)
    print("after: ", mask_text(sample))
