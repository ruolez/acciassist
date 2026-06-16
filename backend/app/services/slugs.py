from collections.abc import Iterable

from slugify import slugify


def slugify_unique(text: str, existing: Iterable[str]) -> str:
    """Slugify ``text`` and append ``-N`` until it no longer collides with ``existing``."""
    taken = set(existing)
    base = slugify(text) or "item"
    if base not in taken:
        return base
    n = 2
    while f"{base}-{n}" in taken:
        n += 1
    return f"{base}-{n}"
