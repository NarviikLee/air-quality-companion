"""Native Qt rendering based on designs/robot_led; no raster or timer dependency."""
from qt_compat import QWidget, QLabel, QPushButton, Signal, Qt, QColor, QPainter, QPen, QRectF, QPainterPath, QLinearGradient


class RobotFaceWidget(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.expression = 'waiting'
        self.setFlat(True)

    def set_expression(self, expression):
        if expression != self.expression:
            self.expression = expression
            self.update()

    @staticmethod
    def box(p, rect, color, radius):
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(color))
        p.drawRoundedRect(QRectF(*rect), radius, radius)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.scale(self.width() / 752, self.height() / 304)
        self.paint_panel(p)
        accent = {'waiting': '#B7C2D8', 'normal': '#EBC85A', 'detected': '#FFBA70',
                  'complete': '#97E9AA', 'moving': '#80CFFF'}.get(self.expression, '#62DDCC')
        for x in (175, 451):
            self.paint_eye(p, x, accent)
        self.paint_mouth(p, accent)
        if self.hasFocus() and self.isEnabled():
            p.setPen(QPen(QColor('#66F4E1'), 1))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(2, 2, 748, 300), 34, 34)
        p.end()


    def paint_panel(self, p):
        gradient = QLinearGradient(0, 0, 0, 304)
        gradient.setColorAt(0, QColor('#101F2B'))
        gradient.setColorAt(1, QColor('#080F16'))
        p.setPen(Qt.NoPen)
        p.setBrush(gradient)
        p.drawRoundedRect(QRectF(0, 0, 752, 304), 35, 35)
        p.setPen(QPen(QColor('#3E6570'), 2))
        for x, direction in ((22, 1), (730, -1)):
            p.drawLine(x, 40, x, 22)
            p.drawLine(x, 22, x + direction * 22, 22)
            p.drawLine(x, 264, x, 282)
            p.drawLine(x, 282, x + direction * 22, 282)

    def paint_eye(self, p, x, accent):
        if self.expression == 'waiting':
            self.box(p, (x, 128, 126, 15), accent, 7)
            return
        if self.expression == 'complete':
            path = QPainterPath()
            path.moveTo(x, 162)
            path.cubicTo(x + 18, 63, x + 108, 63, x + 126, 162)
            pen = QPen(QColor(accent), 13)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)
            return
        x += 18 if self.expression == 'moving' else 0
        for margin, alpha in ((16, 18), (10, 30), (5, 60)):
            glow = QColor(accent)
            glow.setAlpha(alpha)
            self.box(p, (x - margin, 74 - margin, 126 + 2 * margin, 120 + 2 * margin), glow, 40)
        gradient = QLinearGradient(x, 74, x, 194)
        gradient.setColorAt(0, QColor(accent).lighter(135))
        gradient.setColorAt(1, QColor(accent).darker(115))
        p.setPen(Qt.NoPen)
        p.setBrush(gradient)
        if self.expression == 'detected':
            p.drawEllipse(QRectF(x, 70, 126, 128))
        else:
            p.drawRoundedRect(QRectF(x, 74, 126, 120), 34, 34)
            p.setPen(QPen(QColor('#3046A89F'), 1))
            for y in range(80, 191, 6):
                p.drawLine(x + 12, y, x + 114, y)

    def paint_mouth(self, p, accent):
        if self.expression == 'complete':
            path = QPainterPath()
            path.moveTo(353, 234)
            path.cubicTo(362, 253, 390, 253, 399, 234)
            p.setPen(QPen(QColor(accent), 7))
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)
        elif self.expression == 'detected':
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(accent))
            p.drawEllipse(QRectF(366, 227, 20, 25))
        else:
            for i, height in enumerate((6, 10, 12, 12, 10, 6)):
                self.box(p, (330 + i * 16, 235 + (12 - height) / 2, 11, height), accent, 3)


class RobotHomeWidget(QWidget):
    detail_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.face = RobotFaceWidget(self)
        self.face.setGeometry(24, 15, 752, 304)
        self.face.clicked.connect(self.request_detail)
        self.title, self.detail, self.hint = QLabel(self), QLabel(self), QLabel(self)
        for widget, y, height, size, color in (
                (self.title, 315, 34, 23, '#D6EBED'),
                (self.detail, 350, 24, 16, '#91AFBA'),
                (self.hint, 377, 24, 15, '#819BA6')):
            widget.setGeometry(24, y, 752, height)
            widget.setAlignment(Qt.AlignCenter)
            widget.setStyleSheet('font-size: %dpx; color: %s;' % (size, color))
        self.display_state = None
        self.face.setEnabled(False)

    def request_detail(self):
        if self.face.isEnabled():
            self.detail_requested.emit()

    def show_state(self, state, title, detail):
        self.display_state = state
        self.face.set_expression(state.value)
        enabled = state.value != 'waiting'
        self.face.setEnabled(enabled)
        self.title.setText(title)
        self.detail.setText(detail)
        self.hint.setText('화면을 터치하면 측정값을 확인할 수 있습니다' if enabled else '센서 연결 후 측정값을 확인할 수 있습니다')
        self.face.setAccessibleName(title + (' · 센서 상세 화면 열기' if enabled else ' · 연결 대기'))


class SensorDetailCard(QWidget):
    def __init__(self, spec, parent=None):
        super().__init__(parent)
        self.value, self.status = None, 'CARD_UNKNOWN'
        self.unit, self.decimals = spec.unit, spec.decimals
        self.name = QLabel({'Temperature': '온도', 'Humidity': '습도'}.get(spec.name, spec.name), self)
        self.name.setGeometry(16, 21, 150, 25)
        self.name.setStyleSheet('font-size: 17px; color: #91AFBA;')
        self.number = QLabel('—', self)
        self.number.setGeometry(16, 46, 150, 44)
        self.number.setStyleSheet('font-size: 34px; font-weight: 700; color: #C8FFF2;')
        self.units = QLabel(spec.unit, self)
        self.units.setGeometry(16, 98, 65, 22)
        self.units.setStyleSheet('font-size: 14px; color: #819DA8;')
        self.assessment_label = QLabel('—', self)
        self.assessment_label.setGeometry(84, 98, 82, 22)
        self.assessment_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

    def set_value(self, value, status):
        self.value, self.status = value, status
        self.number.setText('—' if value is None else f'{value:.{self.decimals}f}')
        self.update()

    def paintEvent(self, event):
        from sensor_data import STATUS_COLORS
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        RobotFaceWidget.box(p, (0, 0, self.width(), self.height()), '#12232E', 15)
        p.setPen(QPen(QColor(STATUS_COLORS.get(self.status, '#57D8C8')), 2))
        p.drawLine(16, 16, 32, 16)
        p.end()


def install_native_shell(window, root):
    """Replace visible presentation only; preserve acquisition/close objects."""
    from qt_compat import QFrame
    # Keep legacy widgets owned by the window, but remove their visible layouts.
    def hide_layout(layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget() is not None:
                item.widget().hide()
            elif item.layout() is not None:
                hide_layout(item.layout())
    hide_layout(root)
    root.setContentsMargins(0, 0, 0, 0)
    root.setSpacing(0)
    window.setStyleSheet('MainWindow {background: #080F16;} QLabel {color: #D6EBED;} QPushButton {color: #B9DFE1; background: #172A35; border: none; border-radius: 16px; font-size: 16px;} QPushButton:pressed {background: #294652;}')
    header = QWidget(window)
    header.setFixedHeight(62)
    marker = QFrame(header)
    marker.setGeometry(24, 24, 5, 20)
    marker.setStyleSheet('background: #66F4E1; border-radius: 2px;')
    brand = QLabel('AIR / COMPANION', header)
    brand.setGeometry(40, 16, 284, 35)
    brand.setStyleSheet('font-size: 19px; color: #D3E4E9; font-weight: 700;')
    for widget, rect in ((window.connection_label, (350, 16, 180, 35)),
                         (window.clock, (570, 16, 126, 35)),
                         (window.exit_button, (714, 17, 62, 34))):
        widget.setParent(header)
        widget.setMinimumSize(0, 0)
        widget.setMaximumSize(16777215, 16777215)
        widget.setGeometry(*rect)
        widget.show()
    window.clock.setStyleSheet('font-size: 20px; color: #D3E4E9;')
    window.clock.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    window.exit_button.setStyleSheet('font-size: 16px; color: #B9DFE1; background: #172A35; border-radius: 16px;')
    divider = QFrame(header)
    divider.setGeometry(24, 61, 752, 1)
    divider.setStyleSheet('background: #1C303B;')
    root.addWidget(header)
    root.addWidget(window.pages)
    window.pages.setFixedHeight(404)
    window.pages.show()
    root.addStretch(1)
    old_page = window.dashboard_page
    window.pages.removeWidget(old_page)
    old_page.hide()
    window.legacy_detail_page = old_page
    detail = QWidget()
    title = QLabel('주변 공기 측정값', detail)
    title.setGeometry(24, 15, 430, 38)
    title.setStyleSheet('font-size: 26px; font-weight: 700; color: #D6EBED;')
    window.home_button.setParent(detail)
    window.home_button.setMinimumSize(0, 0)
    window.home_button.setMaximumSize(16777215, 16777215)
    window.home_button.setText('← 얼굴로')
    window.home_button.setGeometry(648, 16, 128, 40)
    window.home_button.show()
    import sensor_data as config
    specs = {spec.name: spec for spec in config.SENSORS}
    window.gauges = {}
    for i, name in enumerate(('PM1.0', 'PM2.5', 'PM10', 'Bio', 'Temperature', 'Humidity', 'VOC', 'NOx')):
        if name not in specs:
            continue
        card = SensorDetailCard(specs[name], detail)
        card.setGeometry(24 + (i % 4) * 190, 72 + (i // 4) * 140, 182, 128)
        window.gauges[name] = (card, card.assessment_label)
    note = QLabel('카드: 최신 수신값 · 표정: 평균 상태 · 참고용', detail)
    note.setGeometry(24, 365, 752, 30)
    note.setAlignment(Qt.AlignCenter)
    note.setStyleSheet('font-size: 16px; color: #819BA6;')
    window.dashboard_page = detail
    window.pages.addWidget(detail)
    window.pages.setCurrentWidget(window.robot_home_page)

