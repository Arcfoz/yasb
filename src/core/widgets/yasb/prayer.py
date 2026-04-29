import json
import logging
import re
import urllib.parse
from datetime import datetime, timedelta, date

from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from core.utils.utilities import PopupWidget, refresh_widget_style
from core.validation.widgets.yasb.prayer import PrayerTimeConfig
from core.widgets.base import BaseWidget

logger = logging.getLogger("prayer_widget")

_NEXT_DAY_PRAYERS = {"lastthird", "firstthird"}

HEADER = (b"User-Agent", b"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:129.0) Gecko/20100101 Firefox/129.0")
CACHE_CONTROL = (b"Cache-Control", b"no-cache")


class PrayerDataFetcher(QNetworkAccessManager):
    finished = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)

    def fetch(self, url: str):
        request = QNetworkRequest(QUrl(url))
        request.setRawHeader(*HEADER)
        request.setRawHeader(*CACHE_CONTROL)
        reply = self.get(request)
        reply.finished.connect(lambda: self._handle_reply(reply))  # type: ignore

    def _handle_reply(self, reply: QNetworkReply):
        try:
            if reply.error() == QNetworkReply.NetworkError.NoError:
                data = json.loads(reply.readAll().data().decode())
                timings = data["data"]["timings"]
                meta = data["data"]["meta"]
                result = {
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
                self.finished.emit(result)
            else:
                logger.error("Prayer API network error: %s", reply.error().name)
                self.finished.emit({})
        except (json.JSONDecodeError, KeyError) as e:
            logger.error("Prayer API response parse error: %s", e)
            self.finished.emit({})
        finally:
            reply.deleteLater()


class PrayerTimeWidget(BaseWidget):
    validation_schema = PrayerTimeConfig

    def __init__(self, config: PrayerTimeConfig):
        super().__init__(class_name="prayer-time-widget")
        self.config = config
        self._label_content = config.label
        self._label_alt_content = config.label_alt
        self._city = config.city
        self._country = config.country
        self._method = config.method

        tune_dict = config.tune.model_dump()
        tune_str = ",".join(
            str(tune_dict[p])
            for p in ["Imsak", "Fajr", "Sunrise", "Dhuhr", "Asr", "Maghrib", "Sunset", "Isha", "Midnight"]
        )
        self._api_url = (
            f"http://api.aladhan.com/v1/timingsByCity"
            f"?city={urllib.parse.quote(self._city)}"
            f"&country={urllib.parse.quote(self._country)}"
            f"&method={self._method}"
            f"&tune={urllib.parse.quote(tune_str)}"
        )

        self._fetcher = PrayerDataFetcher(self)
        self._fetcher.finished.connect(self._on_data_fetched)

        self._fetch_timer = QTimer(self)
        self._fetch_timer.timeout.connect(self._do_fetch)
        self._fetch_timer.start(config.update_interval * 1000)

        self._update_timer = QTimer(self)
        self._update_timer.timeout.connect(self._update_label)
        self._update_timer.start(60_000)

        self._retry_timer = QTimer(self)
        self._retry_timer.setSingleShot(True)
        self._retry_timer.timeout.connect(self._do_fetch)

        self.prayer_time_data: dict | None = None
        self._show_alt_label = False
        self._current_prayer: str | None = None
        self._prayer_start_time: datetime | None = None
        self._current_prayer_end_time: datetime | None = None
        self._pre_prayer_time = 5
        self._post_prayer_time = 10
        self.last_fetch_date: date | None = None

        self._init_container()
        self._create_dynamically_label(self._label_content, self._label_alt_content)

        self.register_callback("toggle_label", self._toggle_label)
        self.register_callback("toggle_card", self._toggle_card)
        self.register_callback("update_label", self._update_label)

        self.callback_left = config.callbacks.on_left
        self.callback_right = config.callbacks.on_right
        self.callback_middle = config.callbacks.on_middle

        self._load_saved_data()

        if self.prayer_time_data:
            self._update_label()

        if not self.prayer_time_data or self.last_fetch_date != datetime.now().date():
            QTimer.singleShot(0, self._do_fetch)

    # -------------------------------------------------------------------------
    # Networking
    # -------------------------------------------------------------------------

    def _do_fetch(self):
        self._fetcher.fetch(self._api_url)

    @pyqtSlot(dict)
    def _on_data_fetched(self, data: dict):
        if not data:
            if not self._retry_timer.isActive():
                logger.warning("Prayer API returned empty data. Retrying in 10 seconds.")
                self._retry_timer.start(10_000)
            return
        self.prayer_time_data = data
        self.last_fetch_date = datetime.now().date()
        self._save_data()
        self._update_label()

    # -------------------------------------------------------------------------
    # Persistence
    # -------------------------------------------------------------------------

    def _data_file(self) -> str:
        import os
        return os.path.join(os.path.expanduser("~"), ".prayer_time_data.json")

    def _load_saved_data(self):
        import os
        path = self._data_file()
        if not os.path.exists(path):
            return
        try:
            with open(path) as f:
                saved = json.load(f)
            self.prayer_time_data = saved["prayer_time_data"]
            self.last_fetch_date = date.fromisoformat(saved["last_fetch_date"])
        except (json.JSONDecodeError, KeyError, ValueError):
            logger.error("Failed to load saved prayer time data")

    def _save_data(self):
        try:
            with open(self._data_file(), "w") as f:
                json.dump(
                    {
                        "prayer_time_data": self.prayer_time_data,
                        "last_fetch_date": self.last_fetch_date.isoformat(),
                    },
                    f,
                )
        except OSError:
            logger.error("Failed to save prayer time data")

    # -------------------------------------------------------------------------
    # Time helpers
    # -------------------------------------------------------------------------

    def parse_time(self, time_str: str, base_date: date | None = None) -> datetime | None:
        if not time_str or time_str == "N/A":
            return None
        time_str = re.sub(r"\s*\(.*?\)\s*$", "", time_str).strip()
        try:
            parts = time_str.split(":")
            hours, minutes = int(parts[0]), int(parts[1])
            anchor = base_date or datetime.now().date()
            return datetime(anchor.year, anchor.month, anchor.day, hours, minutes, 0)
        except (ValueError, IndexError):
            logger.error("Invalid time format: %r", time_str)
            return None

    def _resolve_prayer_time(self, key: str) -> datetime | None:
        raw = self.prayer_time_data.get(key) if self.prayer_time_data else None
        if not raw:
            return None
        today = datetime.now().date()
        base = today + timedelta(days=1) if key in _NEXT_DAY_PRAYERS else today
        return self.parse_time(raw, base)

    def _build_ordered_prayer_list(self) -> list[tuple[str, datetime]]:
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

        if self._current_prayer and self._current_prayer_end_time and now < self._current_prayer_end_time:
            return self._current_prayer, self._prayer_start_time

        prayer_list = self._build_ordered_prayer_list()
        if not prayer_list:
            return None, None

        for i, (key, dt) in enumerate(prayer_list):
            if dt > now:
                if i > 0:
                    prev_key, prev_dt = prayer_list[i - 1]
                    if (now - prev_dt).total_seconds() < self._post_prayer_time * 60:
                        return prev_key, prev_dt
                return key, dt

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

    def _toggle_label(self):
        self._show_alt_label = not self._show_alt_label
        for w in self._widgets:
            w.setVisible(not self._show_alt_label)
        for w in self._widgets_alt:
            w.setVisible(self._show_alt_label)
        self._update_label(update_class=False)

    @pyqtSlot()
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
                    refresh_widget_style(widget)
                if not widget.isVisible():
                    widget.show()
        except Exception:
            logger.exception("Failed to update prayer label")

    # -------------------------------------------------------------------------
    # Popup card
    # -------------------------------------------------------------------------

    def _toggle_card(self):
        self._popup_card()

    def _popup_card(self):
        if self.prayer_time_data is None:
            logger.warning("Prayer data not yet available")
            return

        prayer_card = self.config.prayer_card

        dialog = PopupWidget(
            self,
            prayer_card.blur,
            prayer_card.round_corners,
            prayer_card.round_corners_type,
            prayer_card.border_color,
        )
        dialog.setProperty("class", "prayer-card")

        main_layout = QVBoxLayout(dialog)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        header = QLabel(f"{self.prayer_time_data['city']}, {self._country}")
        header.setProperty("class", "header")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(header)

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
            alignment=prayer_card.alignment,
            direction=prayer_card.direction,
            offset_left=prayer_card.offset_left,
            offset_top=prayer_card.offset_top,
        )
        dialog.show()
