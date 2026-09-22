"""Render the current runtime Qt UI to the two README preview images."""
import os
from pathlib import Path
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from qt_compat import (QApplication, QImage, QPainter, QPainterPath, QColor,
                       QFont, QFontDatabase, QPen, QRectF, Qt)


def render_legacy_concept():
    app = QApplication.instance() or QApplication([])
    family = 'Noto Sans CJK KR'
    if os.name == 'nt':
        QFontDatabase.addApplicationFont(str(Path(os.environ['WINDIR']) / 'Fonts' / 'malgun.ttf'))
        family = 'Malgun Gothic'
    for detail in (False, True):
        img = QImage(800, 480, QImage.Format_ARGB32)
        img.fill(QColor('#F4F7EF'))
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)

        def box(x, y, w, h, color, r=20):
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(color))
            p.drawRoundedRect(QRectF(x, y, w, h), r, r)

        def ellipse(x, y, w, h, color):
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(color))
            p.drawEllipse(QRectF(x, y, w, h))

        def text(x, y, w, h, s, size=20, color='#284D43', bold=False, align=Qt.AlignCenter):
            f = QFont(family)
            f.setPixelSize(size)
            f.setBold(bold)
            p.setFont(f)
            p.setPen(QColor(color))
            p.drawText(QRectF(x, y, w, h), align | Qt.AlignVCenter, s)

        def stroke(points, width=9, color='#CDF9DA'):
            pen = QPen(QColor(color), width)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            path = QPainterPath()
            path.moveTo(*points[0])
            path.cubicTo(*points[1], *points[2], *points[3])
            p.drawPath(path)

        text(28, 19, 200, 30, 'AIR BUDDY', 20, bold=True, align=Qt.AlignLeft)
        text(640, 19, 130, 30, '10:32', 22, align=Qt.AlignRight)
        if not detail:
            text(175, 61, 450, 34, '안녕! 여기 공기는 내가 살펴볼게요.', 23)
            # Calm background halo and floating robot silhouette.
            ellipse(210, 103, 380, 252, '#E5EFDD')
            ellipse(276, 322, 248, 22, '#DCE6D5')
            box(387, 106, 26, 38, '#AACDB7', 12)
            ellipse(384, 99, 32, 27, '#5FB990')
            box(212, 203, 35, 61, '#AACDB7', 15)
            box(553, 203, 35, 61, '#AACDB7', 15)
            box(241, 142, 318, 181, '#C4DAC6', 54)
            box(240, 135, 320, 181, '#FFFFFF', 54)
            box(263, 158, 274, 132, '#284D43', 37)
            stroke([(309, 216), (314, 192), (337, 192), (342, 216)])
            stroke([(458, 216), (463, 192), (486, 192), (491, 216)])
            stroke([(377, 239), (386, 255), (414, 255), (423, 239)], 7)
            ellipse(291, 231, 28, 12, '#74AD96')
            ellipse(481, 231, 28, 12, '#74AD96')
            ellipse(391, 299, 18, 6, '#93C4A7')
            # Deliberate spare decoration: two little glints.
            text(157, 156, 48, 48, '+', 39, '#94BA8F')
            text(602, 253, 32, 32, '+', 26, '#94BA8F')
            text(160, 345, 480, 49, '지금 공기가 좋아요', 32, bold=True)
            text(140, 405, 520, 34, '나를 톡 누르면 주변 공기 수치를 보여줄게요', 20, '#6B8275')
        else:
            text(28, 65, 530, 40, '우리 주변 공기, 조금 더 자세히', 27, bold=True, align=Qt.AlignLeft)
            box(648, 68, 124, 42, '#E1EBDA', 21)
            text(648, 68, 124, 42, '← 돌아가기', 18)
            cards = [('PM1.0', '0.9', 'µg/m³'), ('PM2.5', '1.1', 'µg/m³'),
                     ('PM10', '1.2', 'µg/m³'), ('Bio', '0', '개수'),
                     ('온도', '35.5', '°C'), ('습도', '32.7', '%'),
                     ('VOC', '0', 'a.u.'), ('NOx', '0', 'a.u.')]
            for i, (name, value, unit) in enumerate(cards):
                x, y = 28 + (i % 4) * 190, 127 + (i // 4) * 143
                box(x, y, 174, 131, '#FFFFFF', 22)
                text(x + 14, y + 10, 146, 27, name, 19, '#6B8275')
                text(x + 10, y + 42, 154, 47, value, 35, bold=True)
                text(x + 10, y + 94, 154, 24, unit, 17, '#7C9185')
            text(28, 426, 744, 30, '공기 수치를 살펴본 뒤에는 에어봇이 다시 인사할게요.', 19, '#6B8275')
        p.end()
        name = 'robot_detail_preview.png' if detail else 'robot_home_preview.png'
        assert img.save(str(Path(__file__).with_name(name)))
        print(name)


PREVIEW_VALUES = {
    'PM1.0': 8.0,
    'PM2.5': 12.0,
    'PM10': 18.0,
    'Bio': 16.0,
    'Temperature': 24.5,
    'Humidity': 46.0,
    'VOC': 22.0,
    'NOx': 14.0,
}


def _process_until(app, condition, timeout_sec=3.0):
    """Process Qt events until the preview worker reaches a stable state."""
    import time
    deadline = time.monotonic() + timeout_sec
    while not condition() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()
    if not condition():
        raise RuntimeError('Timed out while preparing the preview window')


def _save_window(window, filename):
    target = Path(__file__).resolve().with_name(filename)
    image = window.grab()
    if image.isNull() or not image.save(str(target)):
        raise RuntimeError('Could not save preview: %s' % target)
    print(filename)


def render():
    """Capture the real runtime widgets used by the application."""
    import time
    import sensor_data
    sensor_data.SOURCE_MODE = 'demo'
    from dashboard import MainWindow
    from robot_led import RobotDisplayState

    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    if os.name == 'nt':
        QFontDatabase.addApplicationFont(str(Path(os.environ['WINDIR']) / 'Fonts' / 'malgun.ttf'))
        app.setFont(QFont('Malgun Gothic'))

    window = MainWindow()
    window.show()
    _process_until(app, lambda: not window._busy)
    window.data_timer.stop()
    window.demo_state_timer.stop()
    window.clock_timer.stop()
    window.clock.setText('10:32:00')

    # Fix the state and animation phase so repeated renders are deterministic.
    window.robot_home_page.show_state(
        RobotDisplayState.MONITORING, '환경 확인 중', '')
    window.robot_home_page.face.animation_started_at = time.monotonic()
    window.pages.setCurrentWidget(window.robot_home_page)
    app.processEvents()
    _save_window(window, 'demo_robot_home.png')

    window.display_values(PREVIEW_VALUES, sensor_data.MAIN_VALUE)
    window.pages.setCurrentWidget(window.dashboard_page)
    window.detail_return_timer.stop()
    app.processEvents()
    _save_window(window, 'demo_preview.png')

    window.close()
    _process_until(app, lambda: not window.sensor_thread.isRunning())
    window.sensor_thread.wait()
    app.processEvents()


if __name__ == '__main__':
    render()
