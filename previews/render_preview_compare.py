"""Render every runtime robot expression with and without its corner frame."""
import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from qt_compat import (QApplication, QColor, QFont, QFontDatabase, QImage,
                       QPainter, QPoint, QRectF, Qt)
from robot_ui import RobotFaceWidget


EXPRESSIONS = (
    ('waiting', '센서 확인 / WAITING'),
    ('monitoring', '환경 확인 / MONITORING'),
    ('normal', '보통 / NORMAL'),
    ('detected', '개선 필요 / DETECTED'),
    ('comfortable', '쾌적 / COMFORTABLE'),
    ('moving', '이동 / MOVING'),
    ('purifying', '공기 정화 / PURIFYING'),
)

FACE_SIZE = (752, 304)
PREVIEW_SIZE = (564, 228)
LABEL_WIDTH = 280
GAP = 28
TOP = 100
ROW_HEIGHT = 286
CANVAS_WIDTH = LABEL_WIDTH + PREVIEW_SIZE[0] * 2 + GAP * 3
CANVAS_HEIGHT = TOP + ROW_HEIGHT * len(EXPRESSIONS) + 24


def _font(family, size, bold=False):
    font = QFont(family)
    font.setPixelSize(size)
    font.setBold(bold)
    return font


def _render_face(expression, show_corner_frame):
    widget = RobotFaceWidget()
    widget.resize(*FACE_SIZE)
    widget.show_corner_frame = show_corner_frame
    widget.set_expression(expression)
    widget.animation_timer.stop()

    image = QImage(*FACE_SIZE, QImage.Format_ARGB32)
    image.fill(QColor('#080F16'))
    painter = QPainter(image)
    widget.render(painter, QPoint())
    painter.end()
    widget.close()
    return image


def render():
    app = QApplication.instance() or QApplication([])
    family = 'Noto Sans CJK KR'
    if os.name == 'nt':
        QFontDatabase.addApplicationFont(
            str(Path(os.environ['WINDIR']) / 'Fonts' / 'malgun.ttf'))
        family = 'Malgun Gothic'

    sheet = QImage(CANVAS_WIDTH, CANVAS_HEIGHT, QImage.Format_ARGB32)
    sheet.fill(QColor('#080F16'))
    painter = QPainter(sheet)
    painter.setRenderHint(QPainter.Antialiasing)

    painter.setFont(_font(family, 24, True))
    painter.setPen(QColor('#D6EBED'))
    left_x = LABEL_WIDTH + GAP
    right_x = left_x + PREVIEW_SIZE[0] + GAP
    painter.drawText(QRectF(left_x, 24, PREVIEW_SIZE[0], 48),
                     Qt.AlignCenter, '현재 버전 · 테두리 있음')
    painter.drawText(QRectF(right_x, 24, PREVIEW_SIZE[0], 48),
                     Qt.AlignCenter, '비교 버전 · 테두리 없음')

    # A fixed time exposes each state's distinguishing animated symbol.
    with patch('robot_ui.time.monotonic', return_value=100.5):
        for index, (expression, label) in enumerate(EXPRESSIONS):
            y = TOP + index * ROW_HEIGHT
            painter.setFont(_font(family, 17, True))
            painter.setPen(QColor('#B7C2D8'))
            painter.drawText(QRectF(GAP, y, LABEL_WIDTH - GAP * 2, PREVIEW_SIZE[1]),
                             Qt.AlignCenter, label)

            for x, framed in ((left_x, True), (right_x, False)):
                face = _render_face(expression, framed)
                painter.drawImage(QRectF(x, y, *PREVIEW_SIZE), face)

            painter.setPen(QColor('#20343D'))
            painter.drawLine(GAP, y + PREVIEW_SIZE[1] + 28,
                             CANVAS_WIDTH - GAP, y + PREVIEW_SIZE[1] + 28)

    painter.end()
    target = Path(__file__).resolve().parent / 'images' / 'preview_compare.png'
    target.parent.mkdir(exist_ok=True)
    if not sheet.save(str(target)):
        raise RuntimeError('Could not save comparison preview: %s' % target)
    print(target)
    app.processEvents()


if __name__ == '__main__':
    render()
