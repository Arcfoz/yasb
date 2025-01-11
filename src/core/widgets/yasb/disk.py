import os
import psutil
import re
from core.widgets.base import BaseWidget
from core.validation.widgets.yasb.disk import VALIDATION_SCHEMA
from PyQt6.QtWidgets import QLabel, QHBoxLayout, QWidget, QProgressBar, QVBoxLayout
from PyQt6.QtCore import Qt, QPoint, pyqtSignal
from core.utils.utilities import PopupWidget, blink_on_click

class ClickableDiskWidget(QWidget):
    clicked = pyqtSignal()

    def __init__(self, label, parent=None):
        super().__init__(parent)
        self.label = label

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)  
        
class DiskWidget(BaseWidget):
    validation_schema = VALIDATION_SCHEMA

    def __init__(
            self,
            label: str,
            label_alt: str,
            volume_label: str,
            decimal_display: int,
            update_interval: int,
            group_label: dict[str, str],
            container_padding: dict[str, int],
            callbacks: dict[str, str],
    ):
        super().__init__(int(update_interval * 1000), class_name="disk-widget")
        self._decimal_display = decimal_display
        self._show_alt_label = False
        self._label_content = label
        self._label_alt_content = label_alt
        self._volume_label = volume_label.upper()
        self._padding = container_padding
        self._group_label = group_label

        # Construct container
        self._widget_container_layout: QHBoxLayout = QHBoxLayout()
        self._widget_container_layout.setSpacing(0)
        self._widget_container_layout.setContentsMargins(self._padding['left'],self._padding['top'],self._padding['right'],self._padding['bottom'])
        # Initialize container
        self._widget_container: QWidget = QWidget()
        self._widget_container.setLayout(self._widget_container_layout)
        self._widget_container.setProperty("class", "widget-container")
        # Add the container to the main widget layout
        self.widget_layout.addWidget(self._widget_container)

        self._create_dynamically_label(self._label_content, self._label_alt_content)

        self.register_callback("toggle_label", self._toggle_label)
        self.register_callback("toggle_group", self._toggle_group)
        self.register_callback("update_label", self._update_label)
        self.callback_left = callbacks['on_left']
        self.callback_right = callbacks['on_right']
        self.callback_middle = callbacks['on_middle']
        self.callback_timer = "update_label"
        if not self._group_label['enabled']:
            self.start_timer()
        

    def _toggle_label(self):
        self._show_alt_label = not self._show_alt_label
        for widget in self._widgets:
            widget.setVisible(not self._show_alt_label)
        for widget in self._widgets_alt:
            widget.setVisible(self._show_alt_label)
        self._update_label()
        
    def _toggle_group(self):
        if self._group_label['enabled']:
            blink_on_click(self)
            self.show_group_label()
        
    def _create_dynamically_label(self, content: str, content_alt: str):
        def process_content(content, is_alt=False):
            label_parts = re.split('(<span.*?>.*?</span>)', content)
            label_parts = [part for part in label_parts if part]
            widgets = []
            for part in label_parts:
                part = part.strip()
                if not part:
                    continue
                if '<span' in part and '</span>' in part:
                    class_name = re.search(r'class=(["\'])([^"\']+?)\1', part)
                    class_result = class_name.group(2) if class_name else 'icon'
                    icon = re.sub(r'<span.*?>|</span>', '', part).strip()
                    label = QLabel(icon)
                    label.setProperty("class", class_result)
                else:
                    label = QLabel(part)
                    label.setProperty("class", "label")
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)  
                if self._group_label['enabled']:
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

    def _update_label(self):
        active_widgets = self._widgets_alt if self._show_alt_label else self._widgets
        active_label_content = self._label_alt_content if self._show_alt_label else self._label_content
        label_parts = re.split('(<span.*?>.*?</span>)', active_label_content)
        label_parts = [part for part in label_parts if part]
        widget_index = 0

        try:
            disk_space = self._get_space()
        except Exception:
            disk_space = None

        for part in label_parts:
            part = part.strip()
            if part and widget_index < len(active_widgets) and isinstance(active_widgets[widget_index], QLabel):
                if '<span' in part and '</span>' in part:
                    # Ensure the icon is correctly set
                    icon = re.sub(r'<span.*?>|</span>', '', part).strip()
                    active_widgets[widget_index].setText(icon)
                else:
                    # Update label with formatted content
                    formatted_text = part.format(space=disk_space, volume_label=self._volume_label) if disk_space else part
                    active_widgets[widget_index].setText(formatted_text)
                widget_index += 1

           
    def show_group_label(self):  
        self.dialog = PopupWidget(self, self._group_label['blur'], self._group_label['round_corners'], self._group_label['round_corners_type'], self._group_label['border_color'])
        self.dialog.setProperty("class", "disk-group")
        self.dialog.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.dialog.setWindowFlag(Qt.WindowType.Popup)
        self.dialog.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
        
        layout = QVBoxLayout()
        for label in self._group_label['volume_labels']:
            disk_space = self._get_space(label)
            if disk_space is None:
                continue
            row_widget = QWidget()
            row_widget.setProperty("class", "disk-group-row")
            
            clicable_row = ClickableDiskWidget(label)
            clicable_row.clicked.connect(lambda lbl=label: self.open_explorer(lbl))
            clicable_row.setCursor(Qt.CursorShape.PointingHandCursor)
       
            v_layout = QVBoxLayout(clicable_row)
            h_layout = QHBoxLayout()
            
            label_widget = QLabel(f"{label}:")
            label_widget.setProperty("class", "disk-group-label")
            h_layout.addWidget(label_widget)

            label_size = QLabel()
            label_size.setProperty("class", "disk-group-label-size")

            # show size in TB if it's more than 1000GB
            total_gb = float(disk_space['total']['gb'].strip('GB'))
            free_gb = float(disk_space['free']['gb'].strip('GB'))
            if total_gb > 1000:
                total_size = disk_space['total']['tb']
            else:
                total_size = disk_space['total']['gb']     
                
            if free_gb > 1000:
                free_size = disk_space['free']['tb']
            else:
                free_size = disk_space['free']['gb']         
            label_size.setText(f"{free_size} / {total_size}")
            h_layout.addStretch()    
            h_layout.addWidget(label_size)

            v_layout.addLayout(h_layout)

            progress_bar = QProgressBar()
            progress_bar.setTextVisible(False)
            progress_bar.setProperty("class", "disk-group-label-bar")
            if disk_space:
                progress_bar.setValue(int(float(disk_space['used']['percent'].strip('%'))))
            v_layout.addWidget(progress_bar)

            row_widget_layout = QVBoxLayout(row_widget)
            row_widget_layout.setContentsMargins(0, 0, 0, 0)
            row_widget_layout.setSpacing(0)
            row_widget_layout.addWidget(clicable_row)

            layout.addWidget(row_widget)
                
        self.dialog.setLayout(layout)
        

        # Position the dialog 
        self.dialog.adjustSize()
        widget_global_pos = self.mapToGlobal(QPoint(0, self.height() + self._group_label['distance']))
        if self._group_label['direction'] == 'up':
            global_y = self.mapToGlobal(QPoint(0, 0)).y() - self.dialog.height() - self._group_label['distance']
            widget_global_pos = QPoint(self.mapToGlobal(QPoint(0, 0)).x(), global_y)

        if self._group_label['alignment'] == 'left':
            global_position = widget_global_pos
        elif self._group_label['alignment'] == 'right':
            global_position = QPoint(
                widget_global_pos.x() + self.width() - self.dialog.width(),
                widget_global_pos.y()
            )
        elif self._group_label['alignment'] == 'center':
            global_position = QPoint(
                widget_global_pos.x() + (self.width() - self.dialog.width()) // 2,
                widget_global_pos.y()
            )
        else:
            global_position = widget_global_pos
        
        self.dialog.move(global_position)
        self.dialog.show()        
    
    def open_explorer(self, label):
        os.startfile(f"{label}:\\")
        
    def _get_space(self, volume_label=None):
        if volume_label is None:
            volume_label = self._volume_label

        partitions = psutil.disk_partitions()
        specific_partitions = [partition for partition in partitions if partition.device in (f'{volume_label}:\\')]
        if not specific_partitions:
            return
    
        for partition in specific_partitions:
            usage = psutil.disk_usage(partition.mountpoint)
            percent_used = usage.percent
            percent_free = 100 - percent_used
            return {
                "total": {
                    'mb': f"{usage.total / (1024 ** 2):.{self._decimal_display}f}MB",
                    'gb': f"{usage.total / (1024 ** 3):.{self._decimal_display}f}GB",
                    'tb': f"{usage.total / (1024 ** 4):.{self._decimal_display}f}TB"
                },
                "free": {
                    'mb': f"{usage.free / (1024 ** 2):.{self._decimal_display}f}MB",
                    'gb': f"{usage.free / (1024 ** 3):.{self._decimal_display}f}GB",
                    'tb': f"{usage.free / (1024 ** 4):.{self._decimal_display}f}TB",
                    'percent': f"{percent_free:.{self._decimal_display}f}%"
                },
                "used": {
                    'mb': f"{usage.used / (1024 ** 2):.{self._decimal_display}f}MB",
                    'gb': f"{usage.used / (1024 ** 3):.{self._decimal_display}f}GB",
                    'tb': f"{usage.used / (1024 ** 4):.{self._decimal_display}f}TB",
                    'percent': f"{percent_used:.{self._decimal_display}f}%"
                }
            }
        return None  