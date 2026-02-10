from pydantic import Field

from core.validation.widgets.base_model import (
    AnimationConfig,
    CallbacksConfig,
    CustomBaseModel,
    PaddingConfig,
)


class PrayerCardConfig(CustomBaseModel):
    blur: bool = True
    round_corners: bool = True
    round_corners_type: str = "normal"
    border_color: str = "System"
    alignment: str = "right"
    direction: str = "down"
    distance: int = 6  # deprecated
    offset_top: int = 6
    offset_left: int = 0
    icon_size: int = 64


class PrayerTuneConfig(CustomBaseModel):
    Imsak: int = 0
    Fajr: int = 0
    Sunrise: int = 0
    Dhuhr: int = 0
    Asr: int = 0
    Maghrib: int = 0
    Sunset: int = 0
    Isha: int = 0
    Midnight: int = 0


class PrayerTimeConfig(CustomBaseModel):
    label: str = "\uf017 {next_prayer} in {time_until}"
    label_alt: str = "\uf017 {next_prayer} in {time_until}"
    update_interval: int = Field(default=3600, ge=60, le=36000000)
    city: str = "Jakarta"
    country: str = "ID"
    method: int = Field(default=8, ge=0, le=99)
    tune: PrayerTuneConfig = PrayerTuneConfig()
    prayer_card: PrayerCardConfig = PrayerCardConfig()
    animation: AnimationConfig = AnimationConfig()
    container_padding: PaddingConfig = PaddingConfig()
    callbacks: CallbacksConfig = CallbacksConfig()
