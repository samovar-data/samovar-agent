"""Chart theme: the site's colour tokens for the light and dark schemes, fonts and radius (bundled with the plugin,
built by `samovar_dev.theme_from_css`)."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

HEX_COLOR = r"^#[0-9a-fA-F]{6}$"
FONT_LIST = r"^[^<>{};\\]*$"


class Palette(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    background: str = Field(pattern=HEX_COLOR)
    surface: str = Field(pattern=HEX_COLOR)
    text: str = Field(pattern=HEX_COLOR)
    muted: str = Field(pattern=HEX_COLOR)
    border: str = Field(pattern=HEX_COLOR)
    primary: str = Field(pattern=HEX_COLOR)
    accent: str = Field(pattern=HEX_COLOR)
    series: list[Annotated[str, Field(pattern=HEX_COLOR)]] = Field(
        min_length=2, max_length=12, description="Series colours in order; the first is the primary colour."
    )


class Theme(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1]
    font: str = Field(pattern=FONT_LIST, max_length=300)
    mono_font: str = Field(pattern=FONT_LIST, max_length=300)
    radius_px: int = Field(ge=0)
    light: Palette
    dark: Palette
