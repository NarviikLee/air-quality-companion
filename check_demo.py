"""Offscreen smoke check: python check_demo.py. Writes demo_preview.png."""
import os
import time
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from qt_compat import QPoint
from qt_compat import QFont, QFontDatabase
from qt_compat import QTest
from qt_compat import QApplication, QLabel, QWidget
import sensor_data
sensor_data.SOURCE_MODE = 'demo'
from dashboard import MainWindow


def settle():
    deadline = time.monotonic() + 3
    while window._busy and time.monotonic() < deadline:
        QTest.qWait(20)
    assert not window._busy


app = QApplication([])
if os.name == 'nt':
    QFontDatabase.addApplicationFont(os.path.join(os.environ['WINDIR'], 'Fonts', 'malgun.ttf'))
    app.setFont(QFont('Malgun Gothic'))
window = MainWindow()
window.show()
settle()
source = sensor_data.DummySensorSource()
assert (window.width(), window.height()) == (800, 480)
assert len(window.gauges) == 8
assert window.pages.currentWidget() is window.robot_home_page
from robot_led import RobotDisplayState
state_copy = {
    RobotDisplayState.SENSOR_CHECK: ('센서 확인 중', '연결 및 데이터 수신을 확인하고 있어요'),
    RobotDisplayState.MONITORING: ('환경 확인 중', '주변 환경 데이터를 모으고 있어요'),
    RobotDisplayState.COMFORTABLE: ('쾌적한 상태예요', '미세먼지와 온습도가 설정 범위에 있어요'),
    RobotDisplayState.NORMAL: ('주변 환경을 확인해 주세요', '온도·습도 또는 먼지 상태를 확인해 주세요'),
    RobotDisplayState.BAD: ('환경 개선이 필요해요', '미세먼지 농도가 높아요'),
    RobotDisplayState.MOVING: ('이동 중', '주변 환경 측정은 계속하고 있어요'),
    RobotDisplayState.PURIFYING: ('공기 정화 중', '주변 환경 측정은 계속하고 있어요'),
}
assert set(state_copy) == set(RobotDisplayState)
for state in RobotDisplayState:
    title, detail = state_copy[state]
    window.robot_home_page.show_state(state, title, detail)
    window.robot_home_page.face.animation_started_at = time.monotonic() - 1.2
    app.processEvents()
    assert window.robot_home_page.display_state is state
    assert window.robot_home_page.face.expression == state.value
    for widget in window.findChildren(QWidget):
        if widget.isVisible():
            origin = widget.mapTo(window, QPoint(0, 0))
            assert 0 <= origin.x() and 0 <= origin.y()
            assert origin.x() + widget.width() <= 800
            assert origin.y() + widget.height() <= 480
            if isinstance(widget, QLabel) and not widget.wordWrap():
                assert widget.fontMetrics().horizontalAdvance(widget.text()) <= widget.width(), widget.text()
    assert window.grab().save(f'demo_state_{state.value}.png')
window.refresh_robot()
app.processEvents()
assert window.grab().save('demo_robot_home.png')
window.show_sensor_detail()
app.processEvents()
assert window.detail_return_timer.isActive()
# Keep the detail page visible while this offscreen test performs long checks.
window.detail_return_timer.stop()
# Exercise card colors and the longest messages, independent of random demo data.
from sensor_status import assess_sensor
for pm1, pm25, pm10, humidity, temperature in [
        (10, 15, 30, 30, 20),
        (10.1, 15.1, 30.1, 55, 19),
        (25.1, 35.1, 80.1, 60, 27),
        (50.1, 75.1, 150.1, 29, 26),
]:
    values = dict(source.values, **{'PM1.0': pm1, 'PM2.5': pm25, 'PM10': pm10,
                                  'Humidity': humidity, 'Temperature': temperature})
    window.display_values(values, sensor_data.MAIN_VALUE)
    app.processEvents()
    for name, (gauge, state) in window.gauges.items():
        assessment = assess_sensor(name, values[name])
        assert gauge.status == assessment.level
        assert state.text() == ('—' if assessment.message == '기준 미정' else assessment.message)
        assert state.accessibleName() == assessment.message
        assert sensor_data.STATUS_COLORS[gauge.status] in state.styleSheet()
        assert state.fontMetrics().horizontalAdvance(state.text()) <= state.width(), state.text()
for widget in window.findChildren(QWidget):
    if not widget.isVisible():
        continue
    origin = widget.mapTo(window, QPoint(0, 0))
    assert origin.x() >= 0 and origin.y() >= 0
    assert origin.x() + widget.width() <= 800, repr(widget)
    assert origin.y() + widget.height() <= 480, repr(widget)
    if isinstance(widget, QLabel) and not widget.wordWrap():
        assert widget.fontMetrics().horizontalAdvance(widget.text()) <= widget.width(), widget.text()
for value, expected in [(0, 'GOOD'), (30, 'GOOD'), (31, 'NORMAL'),
                        (55, 'NORMAL'), (56, 'BAD'), (80, 'BAD'), (81, 'VERY BAD')]:
    window.display_values(source.values, value)
    assert window.main_gauge.status == expected
    app.processEvents()
sensor_data.AUTO_UPDATE = False
before = source.read()
assert source.read() == before
sensor_data.AUTO_UPDATE = True
ticks = []
window.data_timer.timeout.connect(lambda: ticks.append(True))
QTest.qWait(2200)
assert ticks, 'Data timer did not fire'
assert source.read() != before
for _ in range(1000):
    values, score = source.read()
    assert 0 <= score <= sensor_data.MAIN_MAX
    for spec in sensor_data.SENSORS:
        assert spec.minimum <= values[spec.name] <= spec.maximum
window.display_values({s.name: s.initial for s in sensor_data.SENSORS}, sensor_data.MAIN_VALUE)
app.processEvents()
assert window.grab().save('demo_preview.png')
for mode in ('waiting', 'no_port'):
    settle()
    sensor_data.DEMO_CONNECTION = mode
    window.update_sensors()
    settle()
    assert window.pages.currentWidget() is window.dashboard_page
    assert window.last_frame_delayed
    for widget in window.findChildren(QWidget):
        if not widget.isVisible():
            continue
        origin = widget.mapTo(window, QPoint(0, 0))
        assert 0 <= origin.x() and 0 <= origin.y()
        assert origin.x() + widget.width() <= 800
        assert origin.y() + widget.height() <= 480
        if isinstance(widget, QLabel) and not widget.wordWrap():
            assert widget.fontMetrics().horizontalAdvance(widget.text()) <= widget.width(), widget.text()
    assert window.grab().save(f'demo_{mode}.png')
    count = window.retry_count
    QTest.qWait(3300)
    settle()
    assert window.retry_count > count
    sensor_data.DEMO_CONNECTION = 'ok'
    QTest.qWait(3300)
    settle()
    assert window.pages.currentWidget() is window.dashboard_page
    assert window.retry_deadline is None
sensor_data.DEMO_CONNECTION = 'waiting'
sensor_data.DEMO_RECOVER_AFTER = 2
source = sensor_data.DummySensorSource()
for _ in range(2):
    try:
        source.read()
    except sensor_data.DataUnavailableError:
        pass
    else:
        raise AssertionError('Expected unavailable data')
assert len(source.read()[0]) == 8
window.pages.setCurrentWidget(window.dashboard_page)
window.detail_return_timer.start(20)
QTest.qWait(50)
assert window.pages.currentWidget() is window.robot_home_page
window.close()
QTest.qWait(200)
assert not window.sensor_thread.isRunning()
window.sensor_thread.wait()
app.processEvents()
print('PASS: all robot states, PM1.0/PM2.5/PM10 boundaries, 800x480 bounds, labels, timer, data ranges')
