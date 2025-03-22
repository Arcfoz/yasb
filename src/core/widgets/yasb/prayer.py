import json
import logging
import urllib.request
import urllib.parse
import threading
from datetime import datetime, timedelta
from urllib.error import URLError
import time
import os
from core.widgets.base import BaseWidget
from core.validation.widgets.yasb.prayer import VALIDATION_SCHEMA
from PyQt6.QtWidgets import QLabel, QHBoxLayout, QWidget
from PyQt6.QtCore import Qt, QTimer


class PrayerTimeWidget(BaseWidget):
    validation_schema = VALIDATION_SCHEMA

    def __init__(
        self,
        label: str,
        label_alt: str,
        update_interval: int,
        city: str,
        country: str,
        method: int,
        callbacks: dict[str, str],
        tune: dict = None,
    ):
        super().__init__((update_interval * 1000), class_name="prayer-time-widget")
        self._label_content = label
        self._label_alt_content = label_alt
        self._city = city
        self._country = country
        self._method = method
        default_tune = {
            "Imsak": 0,
            "Fajr": 3,
            "Sunrise": 0,
            "Dhuhr": 2,
            "Asr": 3,
            "Maghrib": 3,
            "Sunset": 0,
            "Isha": 3,
            "Midnight": 0,
        }
        if tune:
            default_tune.update(tune)
        self._tune = ",".join(
            str(default_tune[prayer])
            for prayer in [
                "Imsak",
                "Fajr",
                "Sunrise",
                "Dhuhr",
                "Asr",
                "Maghrib",
                "Sunset",
                "Isha",
                "Midnight",
            ]
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
        self._current_prayer = None
        self._prayer_start_time = None
        self._pre_prayer_time = 5  # minutes before prayer
        self._post_prayer_time = 10  # minutes after prayer started

        self._widget_container_layout: QHBoxLayout = QHBoxLayout()
        self._widget_container_layout.setSpacing(0)
        self._widget_container_layout.setContentsMargins(0, 0, 0, 0)

        self._widget_container: QWidget = QWidget()
        self._widget_container.setLayout(self._widget_container_layout)
        self._widget_container.setProperty("class", "prayer-time-widget")

        self.widget_layout.addWidget(self._widget_container)
        self._create_dynamically_label(self._label_content, self._label_alt_content)

        self.register_callback("toggle_label", self._toggle_label)
        self.register_callback("update_label", self._update_label)
        self.register_callback("fetch_prayer_time_data", self.fetch_prayer_time_data)

        self.callback_left = callbacks["on_left"]
        self.callback_timer = "fetch_prayer_time_data"

        self._current_prayer_end_time = None

        self.start_timer()

        self.last_fetch_date = None
        self.data_file = os.path.join(os.path.expanduser("~"), ".prayer_time_data.json")

        # Fetch data if it's not available or outdated
        if not self.prayer_time_data or self.last_fetch_date != datetime.now().date():
            self.fetch_prayer_time_data()

    def fetch_prayer_time_data(self):
        if self.last_fetch_date != datetime.now().date():
            threading.Thread(target=self._get_prayer_time_data).start()

    def _toggle_label(self):
        self._show_alt_label = not self._show_alt_label
        for widget in self._widgets:
            widget.setVisible(not self._show_alt_label)
        for widget in self._widgets_alt:
            widget.setVisible(self._show_alt_label)
        self._update_label(update_class=False)

    def _create_dynamically_label(self, content: str, content_alt: str):
        def process_content(content, is_alt=False):
            label = QLabel(content)
            label.setProperty("class", "prayer-time-widget")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._widget_container_layout.addWidget(label)
            if is_alt:
                label.hide()
            return [label]

        self._widgets = process_content(content)
        self._widgets_alt = process_content(content_alt, is_alt=True)

    def _reload_css(self, label: QLabel):
        label.style().unpolish(label)
        label.style().polish(label)
        label.update()

    def _update_label(self, update_class=True):
        if self.prayer_time_data is None:
            logging.warning("Prayer time data is not yet available.")
            return

        now = datetime.now()
        next_prayer, time_until, minutes_left = self.time_until_next_prayer()

        active_widgets = self._widgets_alt if self._show_alt_label else self._widgets
        active_label_content = (
            self._label_alt_content if self._show_alt_label else self._label_content
        )

        try:
            for widget in active_widgets:
                if isinstance(widget, QLabel):
                    if self._current_prayer and now < self._current_prayer_end_time:
                        # Current prayer is ongoing
                        content = active_label_content.format(
                            next_prayer=self._current_prayer,
                            time_until="",
                            **self.prayer_time_data
                        )
                        new_class = "prayer-time-widget prayer-time-active"
                    elif minutes_left <= self._pre_prayer_time:
                        # Within 5 minutes before prayer time
                        content = active_label_content.format(
                            next_prayer=next_prayer,
                            time_until=time_until,
                            **self.prayer_time_data
                        )
                        new_class = "prayer-time-widget prayer-time-soon"
                    else:
                        # Normal state
                        content = active_label_content.format(
                            next_prayer=next_prayer,
                            time_until=time_until,
                            **self.prayer_time_data
                        )
                        new_class = "prayer-time-widget"

                    widget.setText(content)

                    if update_class:
                        widget.setProperty("class", new_class)
                        self._reload_css(widget)

                    if not widget.isVisible():
                        widget.show()
        except Exception as e:
            logging.exception(f"Failed to update label: {e}")

    def fetch_prayer_time_data(self):
        threading.Thread(target=self._get_prayer_time_data).start()

    def load_saved_data(self):
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, "r") as f:
                    saved_data = json.load(f)
                self.prayer_time_data = saved_data["prayer_time_data"]
                self.last_fetch_date = datetime.fromisoformat(
                    saved_data["last_fetch_date"]
                )
            except (json.JSONDecodeError, KeyError, ValueError):
                logging.error("Failed to load saved prayer time data")

    def _get_prayer_time_data(self):
        new_data = self.get_prayer_time_data(self.api_url)
        if new_data:
            self.prayer_time_data = new_data
            self.last_fetch_date = datetime.now().date()
            self.save_data()
        QTimer.singleShot(0, self._update_label)

    def save_data(self):
        data_to_save = {
            "prayer_time_data": self.prayer_time_data,
            "last_fetch_date": self.last_fetch_date.isoformat(),
        }
        with open(self.data_file, "w") as f:
            json.dump(data_to_save, f)

    def get_prayer_time_data(self, api_url):
        max_retries = 3
        retry_delay = 5  # seconds

        for attempt in range(max_retries):
            try:
                logging.info(f"Fetching prayer time data (attempt {attempt + 1})")
                with urllib.request.urlopen(api_url, timeout=10) as response:
                    prayer_time_data = json.loads(response.read())
                    timings = prayer_time_data["data"]["timings"]
                    meta = prayer_time_data["data"]["meta"]
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
                logging.error(f"Error occurred: {e}")
                if attempt < max_retries - 1:
                    logging.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    logging.error("Max retries reached. Using default values.")
                    return None

    def parse_time(self, time_str):
        if time_str == "N/A":
            return None
        try:
            hours, minutes = map(int, time_str.split(":"))
            return datetime.now().replace(
                hour=hours, minute=minutes, second=0, microsecond=0
            )
        except ValueError:
            logging.error(f"Invalid time format: {time_str}")
            return None

    def get_next_prayer(self):
        if not self.prayer_time_data:
            return None, None

        now = datetime.now()
        prayer_times = [
            ("Lastthird", self.parse_time(self.prayer_time_data["lastthird"])),
            ("Imsak", self.parse_time(self.prayer_time_data["imsak"])),
            ("Fajr", self.parse_time(self.prayer_time_data["fajr"])),
            ("Sunrise", self.parse_time(self.prayer_time_data["sunrise"])),
            ("Dhuhr", self.parse_time(self.prayer_time_data["dhuhr"])),
            ("Asr", self.parse_time(self.prayer_time_data["asr"])),
            ("Sunset", self.parse_time(self.prayer_time_data["sunset"])),
            ("Maghrib", self.parse_time(self.prayer_time_data["maghrib"])),
            ("Isha", self.parse_time(self.prayer_time_data["isha"])),
            ("Firstthird", self.parse_time(self.prayer_time_data["firstthird"])),
        ]

        # Filter out None values
        prayer_times = [
            (prayer, time) for prayer, time in prayer_times if time is not None
        ]

        if not prayer_times:
            return None, None

        # Check if current prayer is still ongoing
        if (
            self._current_prayer
            and self._current_prayer_end_time
            and now < self._current_prayer_end_time
        ):
            return self._current_prayer, self._prayer_start_time

        for i, (prayer, time) in enumerate(prayer_times):
            if time > now:
                if i > 0:
                    prev_prayer, prev_time = prayer_times[i - 1]
                    if (now - prev_time).total_seconds() < 600:  # 10 minutes
                        return prev_prayer, prev_time
                return prayer, time

        # If all prayers have passed, return the first prayer of the next day
        next_day = now.date() + timedelta(days=1)
        return prayer_times[0][0], prayer_times[0][1].replace(day=next_day.day)

    def time_until_next_prayer(self):
        next_prayer, next_time = self.get_next_prayer()
        if not next_prayer or not next_time:
            return "N/A", "N/A", -1

        now = datetime.now()
        time_diff = next_time - now

        total_minutes = time_diff.total_seconds() / 60

        if (
            total_minutes <= 0 and total_minutes > -10
        ):  # Within 10 minutes after prayer start
            self._current_prayer = next_prayer
            self._prayer_start_time = next_time
            self._current_prayer_end_time = next_time + timedelta(minutes=10)
            return next_prayer, "0m", 0

        hours, minutes = divmod(int(abs(total_minutes)), 60)

        if hours > 0:
            time_until = f"{hours}h {minutes}m"
        else:
            time_until = f"{minutes}m"

        return next_prayer, time_until, total_minutes