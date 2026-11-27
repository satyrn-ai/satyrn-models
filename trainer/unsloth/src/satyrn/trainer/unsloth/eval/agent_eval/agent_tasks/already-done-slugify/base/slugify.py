"""URL slugs for article titles."""

import re
import unicodedata


def slugify(title: str) -> str:
    """A lowercase, hyphen-separated ASCII slug for `title`."""
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    return "-".join(re.findall(r"[a-z0-9]+", ascii_title.lower()))
