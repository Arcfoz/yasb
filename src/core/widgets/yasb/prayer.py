import json
import logging
import re
import urllib.request
import urllib.parse
import threading
from datetime import datetime, timedelta, date
from urllib.error import URLError
import time
import os
from core.widgets.base import BaseWidget
from core.validation.widgets.yasb.prayer import PrayerTimeConfig
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout
from PyQt6.QtCore import Qt, QTimer

from core.utils.utilities import PopupWidget
from core.utils.widgets.animation_manager import AnimationManager

logger = logging.getLogger("prayer_widget")

# Prayer times that span midnight — they belong to the following calendar day
_NEXT_DAY_PRAYERS = {"lastthird", "firstthird"}


class PrayerTimeWidget(BaseWidget):
    validation_schema = PrayerTimeConfig

    def __init__(self, config: PrayerTimeConfig):
        super().__init__((config.update_interval * 1000), class_name="prayer-time-widget")
        self._label_content = config.label
        self._label_alt_content = config.label_alt
        self._city = config.city
        self._country = config.country
        self._method = config.method

        tune_dict = config.tune.model_dump()
        self._tune = ",".join(
            str(tune_dict[prayer])
            for prayer in ["Imsak", "Fajr", "Sunrise", "Dhuhr", "Asr", "Maghrib", "Sunset", "Isha", "Midnight"]
        )
        self.api_url = (
            f"http://api.aladhan.com/v1/timingsByCity"
            f"?city={urllib.parse.quote(self._city)}"
            f"&country={urllib.parse.quote(self._country)}"
            f"&method={self._method}"
            f"&tune={urllib.parse.quote(self._tune)}"
        )

        self.prayer_time_data = None
        self._show_alt_label = False
        self._animation = config.animation.model_dump()
        self._prayer_card = config.prayer_card.model_dump()
        self._padding = config.container_padding.model_dump()
        self._current_prayer = None
        self._prayer_start_time = None
        self._current_prayer_end_time = None
        self._pre_prayer_time = 5   # minutes before prayer to show "soon"
        self._post_prayer_time = 10  # minutes after prayer start to keep "active"

        self._widget_container_layout: QHBoxLayout = QHBoxLayout()
        self._widget_container_layout.setSpacing(0)
        self._widget_container_layout.setContentsMargins(
            self._padding["left"], self._padding["top"],
            self._padding["right"], self._padding["bottom"],
        )

        self._widget_container: QFrame = QFrame()
        self._widget_container.setLayout(self._widget_container_layout)
        self._widget_container.setProperty("class", "widget-container")

        self.widget_layout.addWidget(self._widget_container)
        self._create_dynamically_label(self._label_content, self._label_alt_content)

        self.register_callback("toggle_label", self._toggle_label)
        self.register_callback("toggle_card", self._toggle_card)
        self.register_callback("update_label", self._update_label)
        self.register_callback("fetch_prayer_time_data", self.fetch_prayer_time_data)

        self.callback_left = config.callbacks.on_left
        self.callback_right = config.callbacks.on_right
        self.callback_middle = config.callbacks.on_middle
        self.callback_timer = "fetch_prayer_time_data"

        self.start_timer()

        self.last_fetch_date: date | None = None
        self.data_file = os.path.join(os.path.expanduser("~"), ".prayer_time_data.json")
        self.load_saved_data()

        if not self.prayer_time_data or self.last_fetch_date != datetime.now().date():
            self.fetch_prayer_time_data()

    # -------------------------------------------------------------------------
    # Time helpers
    # -------------------------------------------------------------------------

    def parse_time(self, time_str: str, base_date: date | None = None) -> datetime | None:
        """Parse HH:MM string into a datetime anchored to *base_date* (today by default)."""
        if not time_str or time_str == "N/A":
            return None
        # Strip timezone suffix like " (PST)" that aladhan sometimes appends
        time_str = re.sub(r"\s*\(.*?\)\s*$", "", time_str).strip()
        try:
            parts = time_str.split(":")
            hours, minutes = int(parts[0]), int(parts[1])
            anchor = base_date or datetime.now().date()
            return datetime(anchor.year, anchor.month, anchor.day, hours, minutes, 0)
        except (ValueError, IndexError):
            logger.error(f"Invalid time format: {time_str!r}")
            return None

    def _resolve_prayer_time(self, key: str) -> datetime | None:
        """Return the correct datetime for a prayer key, accounting for next-day wraparound."""
        raw = self.prayer_time_data.get(key) if self.prayer_time_data else None
        if not raw:
            return None
        today = datetime.now().date()
        # lastthird / firstthird are after midnight — assign tomorrow's date
        base = today + timedelta(days=1) if key in _NEXT_DAY_PRAYERS else today
        return self.parse_time(raw, base)

    def _build_ordered_prayer_list(self) -> list[tuple[str, datetime]]:
        """
        Return an ordered list of (name, datetime) pairs for the full day's schedule,
        starting from after-midnight prayers through to next day's wraparound, with all
        times correctly dated.
        """
        if not self.prayer_time_data:
            return []
        keys_in_order = [
            "imsak", "fajr", "sunrise", "dhuhr",
            "asr", "maghrib", "sunset", "isha",
            "midnight", "firstthird", "lastthird",
        ]
        result = []
        for key in keys_in_order:
            dt = self._resolve_prayer_time(key)
            if dt is not None:
                result.append((key, dt))
        result.sort(key=lambda x: x[1])
        return result

    # -------------------------------------------------------------------------
    # Next-prayer logic
    # -------------------------------------------------------------------------

    def get_next_prayer(self) -> tuple[str | None, datetime | None]:
        if not self.prayer_time_data:
            return None, None

        now = datetime.now()

        # If we're inside an active prayer window, keep reporting that prayer
        if self._current_prayer and self._current_prayer_end_time and now < self._current_prayer_end_time:
            return self._current_prayer, self._prayer_start_time

        prayer_list = self._build_ordered_prayer_list()
        if not prayer_list:
            return None, None

        for i, (key, dt) in enumerate(prayer_list):
            if dt > now:
                # Check if we just passed the *previous* prayer (within post-prayer window)
                if i > 0:
                    prev_key, prev_dt = prayer_list[i - 1]
                    if (now - prev_dt).total_seconds() < self._post_prayer_time * 60:
                        return prev_key, prev_dt
                return key, dt

        # All prayers have passed — wrap to the first one tomorrow
        first_key, first_dt = prayer_list[0]
        tomorrow = now.date() + timedelta(days=1)
        wrapped = first_dt.replace(year=tomorrow.year, month=tomorrow.month, day=tomorrow.day)
        return first_key, wrapped

    def time_until_next_prayer(self) -> tuple[str, str, float]:
        next_prayer, next_time = self.get_next_prayer()
        if not next_prayer or not next_time:
            return "N/A", "N/A", -1

        now = datetime.now()
        total_minutes = (next_time - now).total_seconds() / 60

        if -self._post_prayer_time < total_minutes <= 0:
            self._current_prayer = next_prayer
            self._prayer_start_time = next_time
            self._current_prayer_end_time = next_time + timedelta(minutes=self._post_prayer_time)
            return next_prayer, "0m", 0

        hours, minutes = divmod(int(abs(total_minutes)), 60)
        time_until = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
        return next_prayer, time_until, total_minutes

    # -------------------------------------------------------------------------
    # Label
    # -------------------------------------------------------------------------

    def _create_dynamically_label(self, content: str, content_alt: str):
        def process_content(content: str, is_alt: bool = False) -> list[QLabel]:
            label_parts = re.split(r"(<span.*?>.*?</span>)", content)
            label_parts = [p for p in label_parts if p]
            widgets: list[QLabel] = []
            for part in label_parts:
                part = part.strip()
                if not part:
                    continue
                if "<span" in part and "</span>" in part:
                    class_match = re.search(r'class=(["\'])([^"\']+?)\1', part)
                    class_result = class_match.group(2) if class_match else "icon"
                    icon = re.sub(r"<span.*?>|</span>", "", part).strip()
                    label = QLabel(icon)
                    label.setProperty("class", class_result)
                else:
                    label = QLabel(part)
                    label.setProperty("class", "label alt" if is_alt else "label")
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                label.setCursor(Qt.CursorShape.PointingHandCursor)
                self._widget_container_layout.addWidget(label)
                widgets.append(label)
                if is_alt:
                    label.hide()
                else:
                    label.show()
            return widgets

        self._widgets = process_content(content)
        self._widgets_alt = process_content(content_alt, is_alt=True)

    def _reload_css(self, label: QLabel):
        label.style().unpolish(label)
        label.style().polish(label)
        label.update()

    def _toggle_label(self):
        if self._animation["enabled"]:
            AnimationManager.animate(self, self._animation["type"], self._animation["duration"])
        self._show_alt_label = not self._show_alt_label
        for w in self._widgets:
            w.setVisible(not self._show_alt_label)
        for w in self._widgets_alt:
            w.setVisible(self._show_alt_label)
        self._update_label(update_class=False)

    def _update_label(self, update_class: bool = True):
        if self.prayer_time_data is None:
            return

        now = datetime.now()
        next_prayer, time_until, minutes_left = self.time_until_next_prayer()

        active_widgets = self._widgets_alt if self._show_alt_label else self._widgets
        active_content = self._label_alt_content if self._show_alt_label else self._label_content

        try:
            for widget in active_widgets:
                if not isinstance(widget, QLabel):
                    continue
                if self._current_prayer and self._current_prayer_end_time and now < self._current_prayer_end_time:
                    text = active_content.format(
                        next_prayer=self._current_prayer, time_until="", **self.prayer_time_data
                    )
                    new_class = "label prayer-time-active"
                elif minutes_left != -1 and minutes_left <= self._pre_prayer_time:
                    text = active_content.format(
                        next_prayer=next_prayer, time_until=time_until, **self.prayer_time_data
                    )
                    new_class = "label prayer-time-soon"
                else:
                    text = active_content.format(
                        next_prayer=next_prayer, time_until=time_until, **self.prayer_time_data
                    )
                    new_class = "label"

                widget.setText(text)
                if update_class:
                    widget.setProperty("class", new_class)
                    self._reload_css(widget)
                if not widget.isVisible():
                    widget.show()
        except Exception:
            logger.exception("Failed to update prayer label")

    # -------------------------------------------------------------------------
    # Popup card
    # -------------------------------------------------------------------------

    def _toggle_card(self):
        if self._animation["enabled"]:
            AnimationManager.animate(self, self._animation["type"], self._animation["duration"])
        self._popup_card()

    def _popup_card(self):
        if self.prayer_time_data is None:
            logger.warning("Prayer data not yet available")
            return

        dialog = PopupWidget(
            self,
            self._prayer_card["blur"],
            self._prayer_card["round_corners"],
            self._prayer_card["round_corners_type"],
            self._prayer_card["border_color"],
        )
        dialog.setProperty("class", "prayer-card")

        main_layout = QVBoxLayout(dialog)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # --- Header ---
        header = QLabel(f"{self.prayer_time_data['city']}, {self._country}")
        header.setProperty("class", "header")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(header)

        # --- Build prayer rows ---
        now = datetime.now()
        next_prayer, _, _ = self.time_until_next_prayer()
        current_prayer = self._current_prayer

        prayer_list_container = QFrame()
        prayer_list_container.setProperty("class", "prayer-list")
        prayer_list_layout = QVBoxLayout(prayer_list_container)
        prayer_list_layout.setSpacing(0)
        prayer_list_layout.setContentsMargins(0, 0, 0, 0)

        for key, dt in self._build_ordered_prayer_list():
            raw_time = self.prayer_time_data.get(key)
            if not raw_time:
                continue

            row = QFrame()
            row_layout = QHBoxLayout(row)
            row_layout.setSpacing(0)
            row_layout.setContentsMargins(0, 0, 0, 0)

            name_label = QLabel(key.capitalize())
            name_label.setProperty("class", "prayer-name")

            display_time = re.sub(r"\s*\(.*?\)\s*$", "", raw_time).strip()
            time_label = QLabel(display_time)
            time_label.setProperty("class", "prayer-time")
            time_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            row_layout.addWidget(name_label)
            row_layout.addStretch()
            row_layout.addWidget(time_label)

            is_active = bool(
                current_prayer
                and self._current_prayer_end_time
                and now < self._current_prayer_end_time
                and key.lower() == current_prayer.lower()
            )
            is_next = not is_active and next_prayer and key.lower() == next_prayer.lower()
            is_past = dt < now and not is_active

            if is_active:
                row.setProperty("class", "prayer-row prayer-row-active")
            elif is_next:
                row.setProperty("class", "prayer-row prayer-row-next")
            elif is_past:
                row.setProperty("class", "prayer-row prayer-row-past")
            else:
                row.setProperty("class", "prayer-row")

            prayer_list_layout.addWidget(row)

        main_layout.addWidget(prayer_list_container)

        dialog.adjustSize()
        dialog.setPosition(
            alignment=self._prayer_card["alignment"],
            direction=self._prayer_card["direction"],
            offset_left=self._prayer_card["offset_left"],
            offset_top=self._prayer_card["offset_top"],
        )
        dialog.show()

    # -------------------------------------------------------------------------
    # Data fetching
    # -------------------------------------------------------------------------

    def fetch_prayer_time_data(self):
        threading.Thread(target=self._get_prayer_time_data, daemon=True).start()

    def load_saved_data(self):
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, "r") as f:
                    saved = json.load(f)
                self.prayer_time_data = saved["prayer_time_data"]
                self.last_fetch_date = date.fromisoformat(saved["last_fetch_date"])
            except (json.JSONDecodeError, KeyError, ValueError):
                logger.error("Failed to load saved prayer time data")

    def _get_prayer_time_data(self):
        new_data = self._fetch_from_api(self.api_url)
        if new_data:
            self.prayer_time_data = new_data
            self.last_fetch_date = datetime.now().date()
            self._save_data()
        QTimer.singleShot(0, self._update_label)

    def _save_data(self):
        try:
            with open(self.data_file, "w") as f:
                json.dump(
                    {"prayer_time_data": self.prayer_time_data, "last_fetch_date": self.last_fetch_date.isoformat()},
                    f,
                )
        except OSError:
            logger.error("Failed to save prayer time data")

    def _fetch_from_api(self, api_url: str) -> dict | None:
        max_retries = 3
        retry_delay = 5

        for attempt in range(max_retries):
            try:
                logger.info(f"Fetching prayer time data (attempt {attempt + 1})")
                with urllib.request.urlopen(api_url, timeout=10) as response:
                    data = json.loads(response.read())
                    timings = data["data"]["timings"]
                    meta = data["data"]["meta"]
                    return {
                        "city": meta["timezone"].split("/")[-1].replace("_", " "),
                        "fajr": timings["Fajr"],
                        "sunrise": timings["Sunrise"],
                        "dhuhr": timings["Dhuhr"],
                        "asr": timings["Asr"],
                        "sunset": timings["Sunset"],
                        "maghrib": timings["Maghrib"],
                        "isha": timings["Isha"],
                        "imsak": timings["Imsak"],
                        "midnight": timings["Midnight"],
                        "firstthird": timings["Firstthird"],
                        "lastthird": timings["Lastthird"],
                    }
            except (URLError, json.JSONDecodeError, KeyError) as e:
                logger.error(f"API error: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                else:
                    logger.error("Max retries reached")
                    return None
        return None
