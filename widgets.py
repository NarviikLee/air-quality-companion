"""QPainter로 그리는 얇은 원형 progress ring."""
from qt_compat import QRectF, Qt
from qt_compat import QColor, QFont, QPainter, QPen
from qt_compat import QWidget
from sensor_data import STATUS_COLORS


class CircularGauge(QWidget):
    def __init__(self, minimum=0, maximum=100, unit='', decimals=0, overview=False):
        super().__init__()
        self.minimum, self.maximum = minimum, maximum
        self.unit, self.decimals, self.overview = unit, decimals, overview
        self.value, self.status = 0, 'GOOD'
        self.setFixedSize(228 if overview else 112, 228 if overview else 112)

    def set_value(self, value, status):
        self.value, self.status = value, status
        text = '—' if value is None else f'{value:.{self.decimals}f}'
        self.setAccessibleName(f'{status}: {text} {self.unit}')
        self.update()

    def draw_text(self, painter, rect, text, size, color, bold=False):
        font = QFont(self.font())
        font.setPixelSize(size)
        font.setBold(bold)
        painter.setFont(font)
        painter.setPen(QColor(color))
        painter.drawText(rect, Qt.AlignCenter, text)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        ring = QRectF(self.rect()).adjusted(7, 7, -7, -7)
        pen = QPen(QColor('#E7EFEB'), 9 if self.overview else 6)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawEllipse(ring)
        span = self.maximum - self.minimum
        fraction = max(0, min(1, (self.value - self.minimum) / span)) if span > 0 and self.value is not None else 0
        color = STATUS_COLORS.get(self.status, '#6A7E77')
        pen.setColor(QColor(color))
        painter.setPen(pen)
        painter.drawArc(ring, 90 * 16, -round(fraction * 360 * 16))
        width = self.width()
        if self.overview:
            self.draw_text(painter, QRectF(0, 59, width, 27), 'AIR QUALITY', 19, '#6A7E77')
            self.draw_text(painter, QRectF(0, 96, width, 44), self.status,
                           30 if self.status == 'VERY BAD' else 40, color, True)
            self.draw_text(painter, QRectF(0, 151, width, 25),
                           '설정 예정' if self.status == 'MAIN' else f'{self.value:.0f} / {self.maximum:.0f}', 20, '#6A7E77')
        else:
            self.draw_text(painter, QRectF(5, 28, width - 10, 38),
                           '—' if self.value is None else f'{self.value:.{self.decimals}f}', 29, '#203C34', True)
            self.draw_text(painter, QRectF(0, 69, width, 22), self.unit, 16, '#6A7E77')
