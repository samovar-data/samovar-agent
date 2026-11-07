"""The chart theme: the site's colours, bundled with the plugin (the platform publishes no theme document, so charts
never fetch one)."""

from functools import cache
from importlib import resources

from samovar_agent.domain.theme import Theme

DEFAULT_THEME = "theme.default.json"


@cache
def bundled_theme() -> Theme:
    text = resources.files("samovar_agent.charts").joinpath(DEFAULT_THEME).read_text(encoding="utf-8")
    return Theme.model_validate_json(text)
