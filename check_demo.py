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
for state in RobotDisplayState:
    window.robot_home_page.show_state(state, '주변 환경을 확인해 주세요', '측정 데이터 보충 중 · 마지막 확정 상태입니다')
    app.processEvents()
    for widget in window.findChildren(QWidget):
        if widget.isVisible():
            origin = widget.mapTo(window, QPoint(0, 0))
            assert 0 <= origin.x() and 0 <= origin.y()
            assert origin.x() + widget.width() <= 800
            assert origin.y() + widget.height() <= 480
            if isinstance(widget, QLabel) and not widget.wordWrap():
                assert widget.fontMetrics().horizontalAdvance(widget.text()) <= widget.width(), widget.text()
window.refresh_robot()
app.processEvents()
assert window.grab().save('demo_robot_home.png')
window.show_sensor_detail()
app.processEvents()
# Exercise card colors and the longest messages, independent of random demo data.
from sensor_status import assess_sensor
for pm25, pm10, humidity, temperature in [(15, 30, 30, 20), (15.1, 30.1, 55, 19),
                                        (35.1, 80.1, 60, 27), (75.1, 150.1, 29, 26)]:
    values = dict(source.values, **{'PM2.5': pm25, 'PM10': pm10,
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
window.close()
QTest.qWait(200)
assert not window.sensor_thread.isRunning()
window.sensor_thread.wait()
app.processEvents()
print('PASS: 800x480 bounds, labels, status boundaries, fixed mode, timer, data ranges')
