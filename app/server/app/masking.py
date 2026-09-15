import re

PATTERNS = [
    re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"),
    re.compile(r"(?<!\d)\d{16,19}(?!\d)"),
]


def mask_text(text, extra_words=None):
    out = text
    for pat in PATTERNS:
        out = pat.sub("***", out)
    for word in (extra_words or []):
        if word:
            out = out.replace(word, "***")
    return out
