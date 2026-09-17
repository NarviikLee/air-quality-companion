"""Expression selection; native runtime widget export and retained legacy renderer."""
from enum import Enum
from pathlib import Path
from qt_compat import QWidget, QLabel, QVBoxLayout, QPushButton, Signal, Qt, QPixmap, QColor, QPainter
import sensor_data as config
from robot_ui import RobotHomeWidget


class RobotDisplayState(Enum):
    SENSOR_CHECK = 'waiting'
    MONITORING = 'monitoring'
    COMFORTABLE = 'complete'
    NORMAL = 'normal'
    BAD = 'detected'
    MOVING = 'moving'


REASONS = {'humidity_low': '습도가 낮아요', 'humidity_high': '습도가 높아요',
           'temperature_low': '온도가 낮아요', 'temperature_high': '온도가 높아요',
           'pm1_bad': 'PM1.0 농도가 높아요', 'pm25_bad': 'PM2.5 농도가 높아요',
           'pm10_bad': 'PM10 농도가 높아요', 'pm1_normal': 'PM1.0 보통',
           'pm25_normal': 'PM2.5 보통', 'pm10_normal': 'PM10 보통'}


class RobotLedController:
    def __init__(self):
        self.moving = False

    def set_moving(self, moving):
        self.moving = bool(moving)  # Placeholder for a future external status input only.

    def resolve(self, analyzer):
        if analyzer.sensor_check:
            return RobotDisplayState.SENSOR_CHECK, '센서 확인 중', '연결 및 데이터 수신을 확인하고 있어요'
        if config.ENABLE_MOVING_DISPLAY and self.moving:
            return RobotDisplayState.MOVING, '이동 중', '주변 환경 측정은 계속하고 있어요'
        if analyzer.confirmed_state is None:
            return RobotDisplayState.MONITORING, '환경 확인 중', '주변 환경 데이터를 모으고 있어요'
        state = (RobotDisplayState.COMFORTABLE, RobotDisplayState.NORMAL,
                 RobotDisplayState.BAD)[int(analyzer.confirmed_state)]
        title = ('쾌적한 상태예요', '주변 환경을 확인해 주세요', '환경 개선이 필요해요')[int(analyzer.confirmed_state)]
        if analyzer.delayed:
            detail = '수신 지연 · 마지막 확정 상태입니다'
        elif not analyzer.ready:
            detail = '측정 데이터 보충 중 · 마지막 확정 상태입니다'
        elif analyzer.candidate_state is not None:
            detail = '환경 변화 확인 중…'
        else:
            detail = REASONS.get(next(iter(analyzer.reasons), ''), '미세먼지와 온습도가 설정 범위에 있어요')
        return state, title, detail


class LegacyRasterRobotHomeWidget(QWidget):
    detail_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet('background: #080F16; color: #D6EBED;')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)
        self.face = QPushButton()
        self.face.setFlat(True)
        self.face.setFixedHeight(208)
        self.face.setStyleSheet('border: none; background: #080F16;')
        self.face.clicked.connect(self.detail_requested.emit)
        layout.addWidget(self.face)
        self.title = QLabel()
        self.detail = QLabel()
        self.hint = QLabel('얼굴을 터치하면 8개 센서 측정값을 확인할 수 있어요')
        for widget, size in ((self.title, 24), (self.detail, 17), (self.hint, 14)):
            widget.setAlignment(Qt.AlignCenter)
            widget.setStyleSheet('font-size: %dpx; color: #D6EBED;' % size)
            layout.addWidget(widget)
        self.images = {}
        folder = Path(__file__).resolve().parent / 'designs' / 'robot_led' / 'states'
        for state in RobotDisplayState:
            filename = 'monitoring' if state == RobotDisplayState.NORMAL else state.value
            image = QPixmap(str(folder / (filename + '.png')))
            if image.isNull():
                raise RuntimeError('Missing robot resource: ' + filename)
            face = image.copy(24, 76, 752, 270)
            if state == RobotDisplayState.NORMAL:
                # Tint only the existing mint eyes/mouth; retain the faceplate.
                pixels = face.toImage()
                for y in range(pixels.height()):
                    for x in range(pixels.width()):
                        color = pixels.pixelColor(x, y)
                        if color.green() > 150 and color.blue() > 120 and color.red() > 100:
                            pixels.setPixelColor(x, y, QColor('#EBC85A'))
                face = QPixmap.fromImage(pixels)
            self.images[state] = face
        self.display_state = None

    def show_state(self, state, title, detail):
        from qt_compat import QIcon, QSize
        if state != self.display_state:
            self.face.setIcon(QIcon(self.images[state]))
            self.face.setIconSize(QSize(560, 201))
            self.display_state = state
        self.title.setText(title)
        self.detail.setText(detail)
        self.face.setAccessibleName(title + ' · 센서 상세 화면 열기')
