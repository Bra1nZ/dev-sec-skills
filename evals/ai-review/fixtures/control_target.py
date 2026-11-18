"""Name normalization for report keys."""

import unicodedata


def normalize(name):
    collapsed = " ".join(name.split())
    return unicodedata.normalize("NFC", collapsed).strip()
