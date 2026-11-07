"""Builds the bundled chart theme from the site's CSS tokens (the site stylesheet: `:root` and the dark
`prefers-color-scheme` block).

    uv run python -m samovar_dev.theme_from_css <site style.css> src/samovar_agent/charts/theme.default.json
"""

import re
import sys
from pathlib import Path

from samovar_agent.domain.theme import Palette, Theme

TOKEN = re.compile(r"--([a-z0-9-]+):\s*([^;]+);")
SERIES = ("primary", "accent", "info", "ok", "warn", "bad", "muted")


def blocks(css: str) -> tuple[dict[str, str], dict[str, str]]:
    """Tokens of the first `:root {...}` block and of the dark-scheme block."""
    light_start = css.index(":root {")
    light = dict(TOKEN.findall(css[light_start : css.index("}", light_start)]))
    dark_start = css.index("@media (prefers-color-scheme: dark)")
    dark_body = css[dark_start : css.index("}", css.index("{", css.index("{", dark_start) + 1))]
    return light, dict(TOKEN.findall(dark_body))


def palette(tokens: dict[str, str]) -> Palette:
    return Palette(
        background=tokens["bg"],
        surface=tokens["surface"],
        text=tokens["text"],
        muted=tokens["muted"],
        border=tokens["border"],
        primary=tokens["primary"],
        accent=tokens["accent"],
        series=[tokens[name] for name in SERIES],
    )


def convert(css: str) -> Theme:
    light, dark = blocks(css)
    return Theme(
        schema_version=1,
        font=light["font"].strip(),
        mono_font=light["mono"].strip(),
        radius_px=int(light["radius"].removesuffix("px")),
        light=palette(light),
        dark=palette({**light, **dark}),
    )


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: theme_from_css <style.css> <output theme.json> [more outputs]", file=sys.stderr)
        return 2
    text = convert(Path(argv[0]).read_text(encoding="utf-8")).model_dump_json(indent=2) + "\n"
    for output in argv[1:]:
        Path(output).write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
