"""Short ASCII file names for outputs: `<latin-slug>-<id8>.<ext>`; the human title stays inside the file."""

import re

LATIN = "a b v g d e e zh z i y k l m n o p r s t u f kh ts ch sh shch _ y _ e yu ya".split()
CYRILLIC = {char: ("" if latin == "_" else latin) for char, latin in zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя", LATIN)}
NOT_SLUG = re.compile(r"[^a-z0-9]+")
MAX_SLUG = 40


def ascii_slug(title: str, fallback: str) -> str:
    latin = "".join(CYRILLIC.get(char, char) for char in title.lower())
    slug = NOT_SLUG.sub("-", latin).strip("-")[:MAX_SLUG].strip("-")
    return slug or fallback


def output_name(title: str, query_id: str, fallback: str) -> str:
    return f"{ascii_slug(title, fallback)}-{query_id[:8]}"
