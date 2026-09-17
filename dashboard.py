import math
import time
import logging
import sensor_data as config
from air_quality_analyzer import AirQualityAnalyzer
from robot_led import RobotLedController
from robot_ui import RobotHomeWidget, install_native_shell
from qt_compat import QDateTime, Qt, QTimer, QThread, Signal, Slot
from qt_compat import QKeySequence, QShortcut
from qt_compat import QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget, QStackedWidget, QProgressBar, QPushButton
from sensor_data import (create_sensor_source, SOURCE_MODE, MAIN_MAX, SENSORS, STATUS_COLORS,
                         STATUS_MESSAGES, UPDATE_INTERVAL_MS, get_status)
from widgets import CircularGauge
from sensor_data import RETRY_INTERVAL_SECONDS
from sensor_worker import SensorWorker
from sensor_status import assess_sensor


def label(text, size, color='#203C34', bold=False):
    widget = QLabel(text)
    widget.setStyleSheet(f'font-size: {size}px; color: {color}; font-weight: {700 if bold else 400};')
    return widget


class MainWindow(QWidget):
    read_requested = Signal()
    stop_requested = Signal()

    def __init__(self, source_factory=create_sensor_source):
        super().__init__()
        if len(SENSORS) > 8 or len({s.name for s in SENSORS}) != len(SENSORS):
            raise ValueError('Use up to eight sensors with unique names.')
        self.mode_label = 'DEMO' if SOURCE_MODE == 'demo' else 'SENSOR'
        self.setWindowTitle('Air Quality Monitor')
        self.setFixedSize(800, 480)
        self.setStyleSheet('MainWindow {background: #F2F6F3;} QFrame#card {background: white; border: 1px solid #DEE8E1; border-radius: 16px;}')
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 12)
        root.setSpacing(12)
        header = QHBoxLayout()
        header.addWidget(label('AIR QUALITY MONITOR', 22, bold=True))
        header.addStretch()
        self.connection_label = label('● DEMO', 16, '#22A878', True)
        header.addWidget(self.connection_label)
        header.addSpacing(18)
        self.clock = label('00:00:00', 24, bold=True)
        header.addWidget(self.clock)
        self.home_button = QPushButton('홈')
        self.home_button.setFixedSize(42, 36)
        self.home_button.clicked.connect(self.show_robot_home)
        header.addWidget(self.home_button)
        self.exit_button = QPushButton('종료')
        self.exit_button.setFixedSize(64, 36)
        self.exit_button.setStyleSheet(
            'QPushButton {font-size: 16px; font-weight: 700; color: #8F3434; '
            'background: #FBEDED; border: 1px solid #E5BDBD; border-radius: 8px;}'
            'QPushButton:pressed {background: #EFCACA;}'
            'QPushButton:disabled {color: #947B7B;}'
        )
        self.exit_button.clicked.connect(self.close)
        header.addWidget(self.exit_button)
        root.addLayout(header)
        body = QHBoxLayout()
        body.setSpacing(8)
        overview = QFrame()
        overview.setObjectName('card')
        overview.setFixedWidth(256)
        main_layout = QVBoxLayout(overview)
        main_layout.setContentsMargins(12, 16, 12, 16)
        title = label('실내 공기 상태', 20, bold=True)
        title.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title)
        main_layout.addStretch()
        self.main_gauge = CircularGauge(maximum=MAIN_MAX, overview=True)
        main_layout.addWidget(self.main_gauge, alignment=Qt.AlignCenter)
        self.message = label('', 18)
        self.message.setWordWrap(True)
        self.message.setAlignment(Qt.AlignCenter)
        self.message.setFixedHeight(58)
        main_layout.addWidget(self.message)
        main_layout.addStretch()
        note = label('대표 항목 · 기준 미정', 16, '#6A7E77')
        note.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(note)
        left_grid = QGridLayout()
        right_grid = QGridLayout()
        for grid in (left_grid, right_grid):
            grid.setSpacing(8)
            for column in range(2):
                grid.setColumnStretch(column, 1)
            for row in range(2):
                grid.setRowStretch(row, 1)
        self.gauges = {}
        for index, spec in enumerate(SENSORS):
            card = QFrame()
            card.setObjectName('card')
            layout = QVBoxLayout(card)
            layout.setContentsMargins(3, 10, 3, 10)
            layout.setSpacing(4)
            name = label(spec.name, 16, bold=True)
            name.setAlignment(Qt.AlignCenter)
            layout.addWidget(name)
            gauge = CircularGauge(spec.minimum, spec.maximum, spec.unit, spec.decimals)
            gauge.set_value(None, 'CARD_UNKNOWN')
            layout.addWidget(gauge, alignment=Qt.AlignCenter)
            state = label('—', 13, STATUS_COLORS['CARD_UNKNOWN'])
            state.setFixedHeight(22)
            state.setAlignment(Qt.AlignCenter)
            layout.addWidget(state)
            self.gauges[spec.name] = (gauge, state)
            # Preserve row order: two sensors on each side of the main gauge.
            grid = left_grid if index % 4 < 2 else right_grid
            grid.addWidget(card, index // 4, index % 2)
        body.addLayout(left_grid, 1)
        body.addWidget(overview)
        body.addLayout(right_grid, 1)
        self.pages = QStackedWidget()
        self.dashboard_page = QWidget()
        self.dashboard_page.setLayout(body)
        body.setContentsMargins(0, 0, 0, 0)
        self.pages.addWidget(self.dashboard_page)
        self.connection_page = QFrame()
        self.connection_page.setObjectName('card')
        connection_layout = QVBoxLayout(self.connection_page)
        connection_layout.setContentsMargins(32, 24, 32, 24)
        connection_layout.setSpacing(16)
        connection_layout.addStretch()
        self.connection_title = label('', 32, bold=True)
        self.connection_detail = label('', 22, '#6A7E77')
        self.retry_label = label('', 20, '#6A7E77')
        for item in (self.connection_title, self.connection_detail):
            item.setAlignment(Qt.AlignCenter)
            connection_layout.addWidget(item)
        self.loading_bar = QProgressBar()
        self.loading_bar.setRange(0, 0)
        self.loading_bar.setTextVisible(False)
        self.loading_bar.setFixedSize(280, 8)
        self.loading_bar.setStyleSheet('QProgressBar {border: none; background: #E7EFEB; border-radius: 4px;} QProgressBar::chunk {background: #22A878; border-radius: 4px;}')
        connection_layout.addWidget(self.loading_bar, alignment=Qt.AlignCenter)
        self.retry_label.setAlignment(Qt.AlignCenter)
        connection_layout.addWidget(self.retry_label)
        connection_layout.addStretch()
        self.pages.addWidget(self.connection_page)
        self.robot_home_page = RobotHomeWidget()
        self.robot_home_page.detail_requested.connect(self.show_sensor_detail)
        self.pages.addWidget(self.robot_home_page)
        self.robot_controller = RobotLedController()
        self.pages.setCurrentWidget(self.robot_home_page)
        root.addWidget(self.pages, 1)
        footer = label(('더미 데이터' if SOURCE_MODE == 'demo' else '시리얼 수신') + ' · 카드: 최신 수신값 / 표정: 30초 평균·10초 확인 · 참고용', 12, '#6A7E77')
        footer.setFixedHeight(22)
        root.addWidget(footer)
        install_native_shell(self, root)
        self._busy = False
        self.analyzer = AirQualityAnalyzer()
        self.last_frame_delayed = False
        self.request_started_at = None
        self.last_received_at = None
        self._closing = False
        self.last_error = ''
        self.source_factory = source_factory
        self._recovering = False
        self.operation_deadline = None
        self.shutdown_deadline = None
        self.create_worker()
        self.health_timer = QTimer(self)
        self.health_timer.timeout.connect(self.check_worker_health)
        self.health_timer.start(250)
        self.retry_deadline = None
        self.retry_count = 0
        self.update_clock()
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.update_clock)
        self.clock_timer.start(1000)
        self.data_timer = QTimer(self)
        self.data_timer.timeout.connect(self.update_sensors)
        self.data_timer.setSingleShot(True)
        self.show_connection_state(False)
        self.refresh_robot()
        self.update_sensors()
        self.escape = QShortcut(QKeySequence('Esc'), self)
        self.escape.activated.connect(self.showNormal)

    def create_worker(self):
        self.sensor_thread = QThread(self)
        self.worker = SensorWorker(self.source_factory)
        self.worker.moveToThread(self.sensor_thread)
        self.read_requested.connect(self.worker.read)
        self.stop_requested.connect(self.worker.stop)
        self.worker.received.connect(self.on_received)
        self.worker.failed.connect(self.on_failed)
        self.worker.checking.connect(self.on_checking)
        # Cleanup also runs when the thread event loop exits unexpectedly.
        self.sensor_thread.finished.connect(self.worker.stop, Qt.DirectConnection)
        self.sensor_thread.finished.connect(self.worker.deleteLater)
        self.sensor_thread.finished.connect(self.on_thread_finished)
        self.sensor_thread.start()

    def update_clock(self):
        self.clock.setText(QDateTime.currentDateTime().toString('HH:mm:ss'))
        if self.retry_deadline is not None:
            remaining = max(0, math.ceil(self.retry_deadline - time.monotonic()))
            self.retry_label.setText(f'{remaining}초 후 자동 재시도 · 재시도 {self.retry_count}회')

    def update_sensors(self):
        if self._busy or self._closing or self._recovering:
            return
        self.data_timer.stop()
        if self.retry_deadline is not None:
            self.retry_count += 1
        self.retry_deadline = None
        self.retry_label.setText('연결 및 데이터 확인 중…')
        self._busy = True
        self.request_started_at = time.monotonic()
        logging.getLogger(__name__).debug('Sensor request started %.6f', self.request_started_at)
        from sensor_data import SERIAL_TIMEOUT_SECONDS, SERIAL_WRITE_TIMEOUT_SECONDS
        self.operation_deadline = time.monotonic() + max(5, SERIAL_TIMEOUT_SECONDS + SERIAL_WRITE_TIMEOUT_SECONDS + 2)
        self.read_requested.emit()

    @Slot()
    def on_checking(self):
        if not self._closing and not self._recovering:
            self.show_connection_state(False)

    def check_worker_health(self):
        now = time.monotonic()
        self.analyzer.check_stale(now)
        if not self._closing:
            self.refresh_robot()
            self.refresh_reception_status(now)
        if self._closing:
            if self.shutdown_deadline is not None and now > self.shutdown_deadline:
                self.connection_detail.setText('장치 응답 지연으로 종료를 기다리고 있습니다.')
            return
        if self.operation_deadline is not None and now > self.operation_deadline and not self._recovering:
            self._recovering = True
            self.data_timer.stop()
            self.show_connection_state(False)
            self.connection_detail.setText('통신 작업 지연 · 연결을 복구하고 있습니다.')
            self.last_error = 'Communication worker deadline exceeded'
            self.worker.cancel_event.set()
            self.sensor_thread.requestInterruption()
            self.stop_requested.emit()

    def show_connection_state(self, no_port):
        self.connection_title.setText('시리얼 연결을 확인해주세요' if no_port else 'Waiting · 센서 연결 확인 중')
        self.connection_detail.setText('시리얼 포트가 없습니다. 케이블과 연결 상태를 확인해주세요.'
                                       if no_port else '연결 및 데이터 수신을 확인하고 있습니다.')
        self.loading_bar.setVisible(not no_port)
        self.connection_label.setText('● ' + ('포트 없음' if no_port else '확인 중'))
        self.connection_label.setStyleSheet('font-size: 16px; color: #C07827; font-weight: 700;')
        # Connection status must never override the user's home/detail choice.

    @Slot(str, str)
    def on_failed(self, state, detail):
        self._busy = False
        if self._closing or self._recovering:
            return
        self.operation_deadline = None
        self.last_error = detail
        self.last_frame_delayed = True
        self.analyzer.record_failure(no_port=state == 'no_port')
        self.show_connection_state(state == 'no_port')
        self.refresh_robot()
        delay = max(1, RETRY_INTERVAL_SECONDS)
        self.retry_deadline = time.monotonic() + delay
        self.update_clock()
        self.data_timer.start(round(delay * 1000))

    @Slot(object, object)
    def on_received(self, values, main_value):
        self._busy = False
        if self._closing or self._recovering:
            return
        self.operation_deadline = None
        self.last_error = ''
        self.last_frame_delayed = False
        self.retry_deadline = None
        self.retry_count = 0
        self.last_received_at = getattr(values, 'timestamp', time.monotonic())
        self.analyzer.accept_sample(values, self.last_received_at)
        self.display_values(values, main_value)
        self.connection_label.setText('● ' + self.mode_label)
        self.connection_label.setStyleSheet('font-size: 16px; color: #22A878; font-weight: 700;')
        self.refresh_robot()
        self.schedule_normal_read()

    def show_robot_home(self):
        self.pages.setCurrentWidget(self.robot_home_page)

    def show_sensor_detail(self):
        if not self.analyzer.sensor_check and not self._closing:
            self.pages.setCurrentWidget(self.dashboard_page)

    def refresh_robot(self):
        self.robot_home_page.show_state(*self.robot_controller.resolve(self.analyzer))

    def refresh_reception_status(self, now):
        if self.last_received_at is None:
            return
        elapsed = max(0, now - self.last_received_at)
        delayed = self.last_frame_delayed or elapsed >= config.SENSOR_STALE_TIMEOUT_SEC
        self.connection_label.setText(('수신 지연 ' if delayed else '갱신 ') + '%d초 전' % elapsed)
        self.connection_label.setStyleSheet('font-size: 14px; color: %s;' % ('#C07827' if delayed else '#22A878'))

    def schedule_normal_read(self):
        now = time.monotonic()
        start = self.request_started_at if self.request_started_at is not None else now
        interval = config.SAMPLE_INTERVAL_SEC
        steps = max(1, math.floor((now - start) / interval) + 1)
        self.data_timer.start(max(1, math.ceil((start + steps * interval - now) * 1000)))

    def closeEvent(self, event):
        if self.sensor_thread.isRunning():
            event.ignore()
            if not self._closing:
                self._closing = True
                self.exit_button.setEnabled(False)
                self.shutdown_deadline = time.monotonic() + 3
                self.data_timer.stop()
                self.retry_deadline = None
                self.show_connection_state(False)
                self.pages.setCurrentWidget(self.connection_page)
                self.connection_title.setText('종료 중')
                self.connection_detail.setText('데이터 작업을 정리하고 있습니다.')
                self.retry_label.setText('잠시 기다려주세요')
                self.sensor_thread.requestInterruption()
                self.worker.cancel_event.set()
                self.stop_requested.emit()
        else:
            self.sensor_thread.wait()
            event.accept()

    @Slot()
    def on_thread_finished(self):
        self.sensor_thread.wait()
        if self._closing:
            self.close()
        else:
            self._busy = False
            self._recovering = True
            self.operation_deadline = None
            self.on_recovery_notice()
            QTimer.singleShot(3000, self.restart_worker)

    def on_recovery_notice(self):
        self.analyzer.reset()
        self.last_frame_delayed = True
        self.refresh_robot()
        self.data_timer.stop()
        self.retry_deadline = None
        self.show_connection_state(False)
        self.last_error = 'Communication thread stopped; restarting'
        self.connection_detail.setText('통신 작업 종료 감지 · 자동 복구 대기 중')
        self.retry_label.setText('3초 후 통신 작업을 다시 시작합니다')

    def restart_worker(self):
        if self._closing:
            return
        self.sensor_thread.deleteLater()
        self.create_worker()
        self._recovering = False
        self.update_sensors()

    def display_values(self, values, main_value):
        if main_value is None:
            self.main_gauge.set_value(0, 'MAIN')
            self.message.setText('센서 데이터 수신 중')
        else:
            status = get_status('MAIN', main_value)
            self.main_gauge.set_value(main_value, status)
            self.message.setText(STATUS_MESSAGES[status])
        for name, (gauge, state) in self.gauges.items():
            assessment = assess_sensor(name, values[name])
            status = assessment.level
            gauge.set_value(values[name], status)
            gauge.setAccessibleName(f'{name}: {values[name]} {gauge.unit}, {assessment.message}')
            gauge.setToolTip(assessment.detail)
            state.setText('—' if assessment.message == '기준 미정' else assessment.message)
            state.setAccessibleName(assessment.message)
            state.setToolTip(assessment.detail)
            state.setStyleSheet(f'font-size: 13px; font-weight: 400; color: {STATUS_COLORS[status]};')
