import sys
import serial
import serial.tools.list_ports # 시리얼 포트 데이터를 가져오기 위해 사용한 모듈
from datetime import datetime

#====================#
#   Sensor Modules   #
#====================#
try:
    # Local/private implementation used with the real sensor module.
    from sensor_protocol import read_sensor_data
    SENSOR_PROTOCOL_CONFIGURED = True
except ModuleNotFoundError as error:
    if error.name != "sensor_protocol":
        raise

    # Public repository fallback.  It lets the GUI start, but deliberately
    # raises a clear error when a real sensor read is attempted.
    from sensor_protocol_template import read_sensor_data
    SENSOR_PROTOCOL_CONFIGURED = False

#====================#
#   Mqtt Modules     #
#====================#
from mqtt_Control import (
    create_client,
    close_client,
    plug_on,
    plug_off,
    get_power_state,
    is_connected
)
#====================#
#   Sqlite Modules   #
#====================#
from dataBase import (
    init_db,
    get_user_config,
    update_serial_config,
    update_interval_sec,
    update_Bio_threshold,
    insert_sensor_data,
    select_by_date,
    get_mqtt_config,
    update_mqtt_config,
    close_db
)
#====================#
#     UI Library     #
#====================#
from PySide6.QtCore import QDate,QTimer, QEvent,Qt
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QLabel,
    QPushButton,
    QComboBox,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QGroupBox,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QHeaderView,
    QMessageBox,
    QDateEdit,
    QTabWidget,
    QDialog,
    QFormLayout,
    QCheckBox
)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Bioaerosol Monitoring")
        self.resize(1200, 700)
        self.test_Mode = False # 테스트 모드로 할경우 True, 실제 센서값을 이용할 경우 False 이부분을 토글로 제어할지 고민
        self.ser = None
        self.MAX_CURRENT_ROWS = 20 # 현재 이력 최대 갯수 (20개가 넘으면 위에서 하나씩 삭제(DB에는 저장됩니다.))
        init_db()
        mqtt_config = get_mqtt_config()
        user_config = get_user_config()
        self.mqtt_client = create_client(
            mqtt_config["broker"],
            mqtt_config["port"],
            mqtt_config["topic"]
        )
        # self.mqtt_power_state = None
        # =========================
        # Central Widget
        # =========================
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)

        # =========================
        # LEFT PANEL
        # =========================
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)

        # =========================
        # Serial Communication
        # =========================
        serial_group = QGroupBox("시리얼 통신 설정")
        serial_layout = QGridLayout()

        # COM Port
        # 시리얼 통신할 포트 콤보박스
        self.combo_port = QComboBox()

        # Baudrate 콤보박스
        self.combo_baud = QComboBox()
        self.combo_baud.addItems([
            "9600",
            "19200",
            "38400",
            "57600",
            "115200",
            "230400",
            "460800",
            "921600"
        ])

        # 통신 baudrate 초기 값
        self.combo_baud.setCurrentText(
            str(user_config["baudrate"])
        )

        # Data Bits
        self.combo_data_bits = QComboBox()
        self.combo_data_bits.addItems([
            "5",
            "6",
            "7",
            "8"
        ])
        self.combo_data_bits.setCurrentText(
            str(user_config["data_bits"])
        )
        # Parity
        self.combo_parity = QComboBox()
        self.combo_parity.addItems([
            "None",
            "Even",
            "Odd",
            "Mark",
            "Space"
        ])
        self.combo_parity.setCurrentText(
            user_config["parity"]
        )

        # Stop Bits
        self.combo_stop_bits = QComboBox()
        self.combo_stop_bits.addItems([
            "1",
            "1.5",
            "2"
        ])
        stop_bits = user_config["stop_bits"]

        if stop_bits == 1.0:
            stop_bits_text = "1"
        elif stop_bits == 1.5:
            stop_bits_text = "1.5"
        else:
            stop_bits_text = "2"

        self.combo_stop_bits.setCurrentText(
            stop_bits_text
        )

        # Buttons
        self.btn_refresh_port = QPushButton("포트 새로고침")
        self.btn_connect = QPushButton("연결")
        self.btn_disconnect = QPushButton("해제")

        self.btn_disconnect.setEnabled(False)

        # =========================
        # Layout
        # =========================
        serial_layout.addWidget(
            QLabel("COM Port"),
            0, 0
        )

        serial_layout.addWidget(
            self.combo_port,
            0, 1
        )

        serial_layout.addWidget(
            QLabel("Baudrate"),
            1, 0
        )

        serial_layout.addWidget(
            self.combo_baud,
            1, 1
        )

        serial_layout.addWidget(
            QLabel("Data Bits"),
            2, 0
        )

        serial_layout.addWidget(
            self.combo_data_bits,
            2, 1
        )

        serial_layout.addWidget(
            QLabel("Parity"),
            3, 0
        )

        serial_layout.addWidget(
            self.combo_parity,
            3, 1
        )

        serial_layout.addWidget(
            QLabel("Stop Bits"),
            4, 0
        )

        serial_layout.addWidget(
            self.combo_stop_bits,
            4, 1
        )

        serial_layout.addWidget(
            self.btn_refresh_port,
            5, 0, 1, 2
        )

        serial_layout.addWidget(
            self.btn_connect,
            6, 0
        )

        serial_layout.addWidget(
            self.btn_disconnect,
            6, 1
        )

        serial_group.setLayout(serial_layout)
        # =========================
        # Communication Interval
        # =========================
        interval_group = QGroupBox("측정 설정")
        interval_layout = QGridLayout()

        self.combo_interval = QComboBox()

        # 1 ~ 10 (취득 주기 설정 초기 (1~10초) 수
        self.combo_interval.addItems(
            [str(i) for i in range(1, 11)]
        )

        # DB에 저장된 유저데이터를 기반으로 이전에 업데이트한 데이터를 가져옴
        self.combo_interval.setCurrentText(
            str(user_config["interval_sec"])
        )

        interval_layout.addWidget(
            QLabel("통신 간격"),
            0, 0
        )

        interval_layout.addWidget(
            self.combo_interval,
            0, 1
        )

        interval_layout.addWidget(
            QLabel("초"),
            0, 2
        )
        self.btn_start_measure = QPushButton("데이터 취득 시작")
        self.btn_stop_measure = QPushButton("데이터 취득 중지")

        self.btn_stop_measure.setEnabled(False)

        interval_layout.addWidget(
            self.btn_start_measure,
            1, 0, 1, 2
        )

        interval_layout.addWidget(
            self.btn_stop_measure,
            1, 2
        )
        interval_group.setLayout(interval_layout)
        # =========================
        # Sensor Values
        # =========================
        sensor_group = QGroupBox("실시간 센서 값")
        sensor_layout = QGridLayout()

        # 출력창 생성
        self.label_pm1_value = QLabel("-")
        self.label_pm25_value = QLabel("-")
        self.label_pm10_value = QLabel("-")
        self.label_bio_value = QLabel("-")

        self.label_temperature_value = QLabel("-")
        self.label_humidity_value = QLabel("-")

        self.label_voc_value = QLabel("-")
        self.label_nox_value = QLabel("-")

        sensor_value_labels = [
            self.label_pm1_value,
            self.label_pm25_value,
            self.label_pm10_value,
            self.label_bio_value,
            self.label_temperature_value,
            self.label_humidity_value,
            self.label_voc_value,
            self.label_nox_value
        ]

        for label in sensor_value_labels:
            label.setStyleSheet("""
                QLabel {
                    border: 1px solid #999;
                    padding: 5px;
                    background-color: white;
                }
            """)
        # =========================
        # 1행
        # PM1.0 | PM2.5
        # =========================
        sensor_layout.addWidget(
            QLabel("PM1.0"),
            0, 0
        )

        sensor_layout.addWidget(
            self.label_pm1_value,
            0, 1
        )

        sensor_layout.addWidget(
            QLabel("PM2.5"),
            0, 2
        )

        sensor_layout.addWidget(
            self.label_pm25_value,
            0, 3
        )

        # =========================
        # 2행
        # PM10 | BioAerosol
        # =========================
        sensor_layout.addWidget(
            QLabel("PM10"),
            1, 0
        )

        sensor_layout.addWidget(
            self.label_pm10_value,
            1, 1
        )

        sensor_layout.addWidget(
            QLabel("BioAerosol"),
            1, 2
        )

        sensor_layout.addWidget(
            self.label_bio_value,
            1, 3
        )

        # =========================
        # 3행
        # 온도 | 습도
        # =========================
        sensor_layout.addWidget(
            QLabel("온도"),
            2, 0
        )

        sensor_layout.addWidget(
            self.label_temperature_value,
            2, 1
        )

        sensor_layout.addWidget(
            QLabel("습도"),
            2, 2
        )

        sensor_layout.addWidget(
            self.label_humidity_value,
            2, 3
        )

        # =========================
        # 4행
        # VOC | NOx
        # =========================
        sensor_layout.addWidget(
            QLabel("VOC"),
            3, 0
        )

        sensor_layout.addWidget(
            self.label_voc_value,
            3, 1
        )

        sensor_layout.addWidget(
            QLabel("NOx"),
            3, 2
        )

        sensor_layout.addWidget(
            self.label_nox_value,
            3, 3
        )

        sensor_group.setLayout(sensor_layout)
        # =========================
        # Smart Plug(가명)
        # =========================
        #mqtt 통신을 통해 스마트플러그로 관련 레이아웃
        plug_group = QGroupBox("스마트플러그")
        plug_layout = QGridLayout()

        self.label_mqtt_status = QLabel(
            "MQTT 통신 상태 : Disconnected"
        )
        self.mqtt_status_timer = QTimer(self)
        self.mqtt_status_timer.timeout.connect(
            self.update_mqtt_status
        )
        self.mqtt_status_timer.start(1000)

        # 이부분은 나중에 파워 관련 데이터 디스플레이가 필요할시
        self.btn_plug_on = QPushButton("ON")
        self.btn_plug_off = QPushButton("OFF")
        self.btn_mqtt_retry = QPushButton("재시도")

        self.mqtt_click_count = 0
        self.btn_plug_on.setEnabled(False)
        self.btn_plug_off.setEnabled(False)

        self.btn_mqtt_retry.setEnabled(True)
        # MQTT 숨은 설정 수정창 클릭 제한용 타이머(5초 이내에 10회이상 클릭)
        self.mqtt_click_timer = QTimer(self)
        self.mqtt_click_timer.setSingleShot(True)

        self.mqtt_click_timer.timeout.connect(
            self.reset_mqtt_click_count
        )

        self.label_mqtt_status.installEventFilter(
            self
        )
        plug_layout.addWidget(
            self.label_mqtt_status,
            0, 0, 1, 2
        )

        plug_layout.addWidget(
            self.btn_plug_on,
            1, 0
        )

        plug_layout.addWidget(
            self.btn_plug_off,
            1, 1
        )
        plug_layout.addWidget(
            self.btn_mqtt_retry,
            2, 0, 1, 2
        )
        plug_group.setLayout(plug_layout)
        # =========================
        # BioAerosol Status
        # =========================
        bio_status_group = QGroupBox("BioAerosol 상태")
        bio_status_layout = QGridLayout()

        self.bio_Threshold = user_config["bio_threshold"]

        self.bio_control_state = None
        self.label_bio_status_led = QLabel()
        self.label_bio_status_led.setFixedSize(24, 24)

        self.label_bio_status_led.setStyleSheet("""
            QLabel {
                background-color: green;
                border-radius: 12px;
                border: 1px solid black;
            }
        """)
        # 임계값 수정용
        self.edit_bio_threshold = QLineEdit(
            str(self.bio_Threshold)
        )

        self.edit_bio_threshold.returnPressed.connect(
            self.update_bio_threshold
        )
        bio_status_layout.addWidget(
            QLabel("현재 상태"),
            0, 0
        )

        bio_status_layout.addWidget(
            self.label_bio_status_led,
            0, 1
        )

        # 현재 적용된 기준값
        bio_status_layout.addWidget(
            QLabel("현재 기준값"),
            1, 0
        )

        self.label_bio_threshold_value = QLabel(
            str(self.bio_Threshold)
        )

        bio_status_layout.addWidget(
            self.label_bio_threshold_value,
            1, 1
        )

        # 임계값 수정
        bio_status_layout.addWidget(
            QLabel("임계값 변경"),
            2, 0
        )
        # 바이오에어로졸 원격제어 임계점 수정 값 입력 칸 길이
        self.edit_bio_threshold.setFixedWidth(80)

        # DB나 이전에 수정한 임계점을 라벨 밑에 추가
        bio_status_layout.addWidget(
            self.edit_bio_threshold,
            2, 1
        )
        bio_status_group.setLayout(
            bio_status_layout
        )

        # =========================
        # Left layout
        # =========================
        left_layout.addWidget(serial_group)
        left_layout.addWidget(interval_group)
        left_layout.addWidget(sensor_group)
        left_layout.addWidget(plug_group)
        left_layout.addWidget(bio_status_group)
        left_layout.addStretch()

        # =========================
        # RIGHT PANEL
        # =========================
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        self.tabs = QTabWidget()

        self.tab_current = QWidget()
        self.tab_history = QWidget()

        self.tabs.addTab(
            self.tab_current,
            "현재"
        )

        self.tabs.addTab(
            self.tab_history,
            "이력 조회"
        )
        # 탭 자체를 오른쪽 패널에 추가
        current_tab_layout = QVBoxLayout(
            self.tab_current
        )

        history_tab_layout = QVBoxLayout(
            self.tab_history
        )
        right_layout.addWidget(
            self.tabs
        )
        history_title = QLabel("측정 이력")
        # =========================
        # Current Table
        # =========================
        #현재 연결해서 업데이트 되고있는 데이터를 누적시킬 테이블
        current_title = QLabel("현재 측정 데이터")
        self.table_current = QTableWidget()
        # 시간, 센서 데이터(8) 이므로 9개의 컬럼 칸을 설정
        self.table_current.setColumnCount(9)
        # 입력 테이블 컬럼 수정 불가 설정
        self.table_current.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.table_current.setHorizontalHeaderLabels([
            "시간",
            "PM1.0\n(㎍/㎥)",
            "PM2.5\n(㎍/㎥)",
            "PM10\n(㎍/㎥)",
            "BioAerosol",
            "온도\n(°C)",
            "습도\n(%)",
            "VOC",
            "NOx"
        ])
        header = self.table_current.horizontalHeader()

        # 시간 컬럼은 내용에 맞게
        header.setSectionResizeMode(
            0,
            QHeaderView.ResizeMode.ResizeToContents
        )

        # 나머지 컬럼은 균등하게
        for column in range(1, 9):
            header.setSectionResizeMode(
                column,
                QHeaderView.ResizeMode.Stretch
            )

        current_tab_layout.addWidget(
            current_title
        )

        current_tab_layout.addWidget(
            self.table_current
        )
        # =========================
        # Date Search
        # =========================
        history_search_layout = QHBoxLayout()

        # 날짜 입력칸
        self.date_start = QDateEdit()
        self.date_end = QDateEdit()

        # 달력 팝업 사용
        self.date_start.setCalendarPopup(True)
        self.date_end.setCalendarPopup(True)

        # 날짜 표시 형식
        self.date_start.setDisplayFormat("yyyy-MM-dd")
        self.date_end.setDisplayFormat("yyyy-MM-dd")

        # 오늘
        today = QDate.currentDate()

        # 시작 날짜 = 오늘 - 7일
        self.date_start.setDate(
            today.addDays(-7)
        )

        # 마지막 날짜 = 오늘
        self.date_end.setDate(
            today
        )

        self.btn_history_search = QPushButton("조회")

        history_search_layout.addWidget(
            QLabel("시작 날짜")
        )

        history_search_layout.addWidget(
            self.date_start
        )

        history_search_layout.addWidget(
            QLabel("마지막 날짜")
        )

        history_search_layout.addWidget(
            self.date_end
        )

        history_search_layout.addWidget(
            self.btn_history_search
        )

        history_search_layout.addStretch()
        # =========================
        # History Table
        # =========================
        # 테이블 정렬 기준 내림차순으로 초기화
        self.history_sort_order = Qt.SortOrder.DescendingOrder
        self.table_history = QTableWidget()
        # 테이블 컬럼 갯수 설정(타임스탬프(날짜), 센서 데이터(8)이므로 9개)
        self.table_history.setColumnCount(9)

        # 입력 컬럼 수정 불가 설정
        self.table_history.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )

        # 이력조회 테이블 컬럼 라벨
        self.table_history.setHorizontalHeaderLabels([
            "시간",
            "PM1.0\n(㎍/㎥)",
            "PM2.5\n(㎍/㎥)",
            "PM10\n(㎍/㎥)",
            "BioAerosol",
            "온도\n(°C)",
            "습도\n(%)",
            "VOC",
            "NOx"
        ])

        header = self.table_history.horizontalHeader()
        # 시간 컬럼을 누르면 정렬순위가 반전
        header.sectionClicked.connect(
            self.on_history_header_clicked
        )
        # 시간 컬럼은 내용에 맞게
        header.setSectionResizeMode(
            0,
            QHeaderView.ResizeMode.ResizeToContents
        )

        # 나머지 컬럼은 균등하게
        for column in range(1, 9):
            header.setSectionResizeMode(
                column,
                QHeaderView.ResizeMode.Stretch
            )
        history_tab_layout.addWidget(
            history_title
        )

        history_tab_layout.addLayout(
            history_search_layout
        )

        history_tab_layout.addWidget(
            self.table_history
        )
        # =========================
        # Main Layout
        # =========================
        main_layout.addWidget(left_panel, 1)
        main_layout.addWidget(right_panel, 2)

        # =========================
        # Button OnClick Event
        # =========================
        self.btn_refresh_port.clicked.connect(
            self.load_serial_ports
        )

        self.btn_connect.clicked.connect(
            self.connect_serial
        )

        self.btn_disconnect.clicked.connect(
            self.disconnect_serial
        )
        # 프로그램 실행 시 포트 자동 검색
        self.load_serial_ports()

        self.sensor_timer = QTimer(self)

        self.sensor_timer.timeout.connect(
            self.read_sensor
        )

        self.btn_start_measure.clicked.connect(
            self.start_measurement
        )

        self.btn_stop_measure.clicked.connect(
            self.stop_measurement
        )
        self.combo_interval.currentTextChanged.connect(
            self.change_interval
        )
        self.btn_plug_on.clicked.connect(
            self.plug_on_event
        )

        self.btn_plug_off.clicked.connect(
            self.plug_off_event
        )
        self.btn_mqtt_retry.clicked.connect(
            self.retry_mqtt_connection
        )
        # 이력조회
        self.btn_history_search.clicked.connect(
            self.search_history
        )

    # ===================================
    # UI 함수
    # ===================================


    # ===================================
    # COM Port 검색
    # ===================================

    # 데스크톱에 연결된 시리얼 포트 탐색 및 포트 콤보박스 업데이트 함수
    def load_serial_ports(self):

        self.combo_port.clear()
        # 시리얼 라이브러리에 있는 데스크톱(혹은 노트북)에 연결된 포트데이터 가져오는 함수
        ports = serial.tools.list_ports.comports()

        for port in ports:

            # 화면에 보여줄 문자열
            # device는 포트 번호, description은 시리얼 포트 이름
            text = (
                f"{port.device} - "
                f"{port.description}"
            )

            # text = 화면 표시
            # port.device = 실제 COM 포트
            self.combo_port.addItem(
                text,
                port.device
            )

        # 아무것도 없으면
        if self.combo_port.count() == 0:

            self.combo_port.addItem(
                "사용 가능한 포트 없음",
                None
            )

    # ===================================
    # Serial 연결
    # ===================================
    def connect_serial(self):
        #콤보박스에 선택된 port 넘버
        port = self.combo_port.currentData()

        baudrate = int(
            self.combo_baud.currentText()
        )

        # COM Port 없음
        if not port:

            QMessageBox.warning(
                self,
                "포트 없음",
                "사용 가능한 COM 포트가 없습니다."
            )

            return

        try:
            data_bits_map = {
                "5": serial.FIVEBITS,
                "6": serial.SIXBITS,
                "7": serial.SEVENBITS,
                "8": serial.EIGHTBITS
            }

            parity_map = {
                "None": serial.PARITY_NONE,
                "Even": serial.PARITY_EVEN,
                "Odd": serial.PARITY_ODD,
                "Mark": serial.PARITY_MARK,
                "Space": serial.PARITY_SPACE
            }

            stop_bits_map = {
                "1": serial.STOPBITS_ONE,
                "1.5": serial.STOPBITS_ONE_POINT_FIVE,
                "2": serial.STOPBITS_TWO
            }

            data_bits = data_bits_map[
                self.combo_data_bits.currentText()
            ]

            parity = parity_map[
                self.combo_parity.currentText()
            ]

            stop_bits = stop_bits_map[
                self.combo_stop_bits.currentText()
            ]
            self.ser = serial.Serial(
                port=port,
                baudrate=baudrate,
                bytesize=data_bits,
                parity=parity,
                stopbits=stop_bits,
                timeout=1
            )
            read_sensor_data(self.ser)
            # 정상 연결시 아래가 진행됨(나머지는 예외처리로 처리함)

            # =========================
            # 측정 중 설정 변경 방지(버튼 활성화 제어)
            # =========================
            self.combo_port.setEnabled(False)
            self.combo_baud.setEnabled(False)
            self.combo_data_bits.setEnabled(False)
            self.combo_parity.setEnabled(False)
            self.combo_stop_bits.setEnabled(False)
            self.btn_refresh_port.setEnabled(False)

            self.btn_connect.setEnabled(False)
            self.btn_disconnect.setEnabled(True)

            QMessageBox.information(
                self,
                "연결 성공",
                f"{port} 연결에 성공했습니다."
            )

            # 여기부터 연결 성공 후 실행( 시리얼 관련 옵션들을 유저DB에 저장)
            # Update를 통해 다음에 프로그램 실행시 연결성공한 옵션들을 그대로 사용
            update_serial_config(
                int(self.combo_baud.currentText()),
                int(self.combo_data_bits.currentText()),
                self.combo_parity.currentText(),
                float(self.combo_stop_bits.currentText())
            )
        except serial.SerialException as e:
            if self.ser is not None:
                try:
                    self.ser.close()
                except Exception:
                    pass
            self.ser = None
            QMessageBox.critical(
                self,
                "연결 오류",
                f"{port}에 연결할 수 없습니다.\n\n"
                f"{e}"
            )

        except Exception as e:
            if self.ser is not None:
                try:
                    self.ser.close()
                except Exception:
                    pass

            self.ser = None

            QMessageBox.critical(
                self,
                "오류",
                f"예상하지 못한 오류가 발생했습니다.\n\n"
                f"{e}"
            )

    # ===================================
    # Serial 연결 해제
    # ===================================
    def disconnect_serial(self):
        # 센서 취득 이벤트가 실행중인 경우 Stop을 함(통신을 안정적으로 종료하기 위해)
        if self.sensor_timer.isActive():
            self.sensor_timer.stop()

        # 시리얼이 비어있지 않거나, 시리얼이 연결되어있으면 종료
        try:
            if self.ser is not None and self.ser.is_open:
                self.ser.close()

        finally:
            # 시리얼 관련 옵션 초기화
            self.ser = None

            ### 시리얼 관련 버튼 접근 가능 상태로
            self.combo_port.setEnabled(True)
            self.combo_baud.setEnabled(True)
            self.combo_data_bits.setEnabled(True)
            self.combo_parity.setEnabled(True)
            self.combo_stop_bits.setEnabled(True)
            self.btn_refresh_port.setEnabled(True)

            self.btn_connect.setEnabled(True)
            self.btn_disconnect.setEnabled(False)

            self.btn_start_measure.setEnabled(True)
            self.btn_stop_measure.setEnabled(False)
    # ===================================
    # 센서 데이터 왼쪽 패널 디스플레이 함수
    # ===================================

    # 센서에서 받은 데이터를 왼쪽 센서 데이터 패널에 디스플레이하기 위한 함수
    def update_sensor_display(self, data):

        self.label_pm1_value.setText(
            f"{data['pm1']:.1f} ㎍/㎥"
        )

        self.label_pm25_value.setText(
            f"{data['pm25']:.1f} ㎍/㎥"
        )

        self.label_pm10_value.setText(
            f"{data['pm10']:.1f} ㎍/㎥"
        )

        self.label_bio_value.setText(
            str(data["bioaerosol"])
        )

        self.label_temperature_value.setText(
            f"{data['temperature']:.1f} °C"
        )

        self.label_humidity_value.setText(
            f"{data['humidity']:.1f} %"
        )

        self.label_voc_value.setText(
            str(data["voc"])
        )

        self.label_nox_value.setText(
            str(data["nox"])
        )

    # ----------------------------
    # 데이터 취득 시작 온클릭 이벤트 함수
    # ----------------------------
    def start_measurement(self):
        if self.ser is None or not self.ser.is_open:
            QMessageBox.warning(
                self,
                "Serial 연결 필요",
                "먼저 시리얼 포트를 연결해주세요."
            )
            return
        self.table_current.setRowCount(0)
        interval_sec = int(
            self.combo_interval.currentText()
        )

        # 첫 행을 채우기 전 정렬을 끄고, 첫 취득 실패 시 시작하지 않는다.
        self.table_current.setSortingEnabled(False)
        if not self.read_sensor():
            return

        # 이후 설정된 주기로 반복
        self.sensor_timer.start(interval_sec * 1000)
        # 데이터 취득시 테이블 정렬 기능 비활성화
        self.table_current.setSortingEnabled(False)
        # 취득 시작 버튼 비활성화 및 취득 종료 버튼 활성화
        self.btn_start_measure.setEnabled(False)
        self.btn_stop_measure.setEnabled(True)
        # 바이오에어로졸 임계점 수정 불가
        self.edit_bio_threshold.setEnabled(False)
        # 수동 mqtt 제어 버튼 비활성화
        self.btn_plug_on.setEnabled(False)
        self.btn_plug_off.setEnabled(False)
        # print(f"데이터 취득 시작: {interval_sec}초 간격")

    # ----------------------------
    # 데이터 취득 정지 클릭 이벤트 함수
    # ----------------------------
    def stop_measurement(self):
        # 센서 취득 이벤트 종료
        self.sensor_timer.stop()

        # 취득이 종료되었으므로 취득 시작 버튼 활성화, 종료 버튼 비활성화
        self.btn_start_measure.setEnabled(True)
        self.btn_stop_measure.setEnabled(False)

        # 데이터가 쌓이지 않으므로 정렬 기능 활성화
        self.table_current.setSortingEnabled(True)
        # 바이오에어로졸 임계점 수정 가능
        self.edit_bio_threshold.setEnabled(True)
        # print("데이터 취득 중지")

    #----------------------------
    # 바이오에어로졸 센서 데이터 취득 함수
    # ----------------------------
    def read_sensor(self):
        try:
            if (
                    self.ser is None
                    or not self.ser.is_open
            ):
                self.stop_measurement()
                return False

            # 이전에 설정한 시리얼 설정을 read_sensor_data 함수에 전달하여 데이터 취득
            data = read_sensor_data(
                self.ser
            )
            # 실시간 값 표시
            self.update_sensor_display(
                data
            )

            # 측정 이력 테이블 추가
            self.add_current_row(
                data
            )
            # Sqlite 데이터 베이스에 현 센서 데이터 삽입
            insert_sensor_data(
                data
            )
            # mqtt 제어 테스트를 위해 바이오에어로졸 데이터 변경(위에서 센서 데이터를 DB에 삽입하기에 실제 데이터엔 영향X)
            if self.test_Mode:
                if self.bio_control_state == "OFF" or self.bio_control_state is None:
                    data["bioaerosol"] = self.bio_Threshold+1
                elif self.bio_control_state == "ON":
                    data["bioaerosol"] = self.bio_Threshold

            # 여기서 취득후 스마트플러그 제어 관련 로직 수행(바이오에어로졸 상태 UI 업데이트 및 조건에 따른 스마트 플러그 제어)
            self.update_bio_status(
                data["bioaerosol"]
            )
            return True
        except Exception as e:
            self.stop_measurement()

            QMessageBox.warning(
                self,
                "센서 통신 오류",
                f"센서 데이터를 취득할 수 없습니다.\n\n{e}"
            )
            return False

    # 데이터 취득 주기 변경 함수
    def change_interval(self):
        # 입력 주기 정수로 변환
        interval_sec = int(
            self.combo_interval.currentText()
        )
        # 취득중이면 현재 진행중인 센서 취득 타이밍을 수정
        if self.sensor_timer.isActive():
            self.sensor_timer.setInterval(
                interval_sec * 1000
            )
        # DB의 유저 데이터 업데이트(데이터 취득 주기)
        update_interval_sec(interval_sec)

    # ======================= #
    #     Mqtt 관련 함수        #
    # ======================= #
    def update_mqtt_status(self):
        if is_connected():
            self.label_mqtt_status.setText(
                "MQTT 통신 상태 : Connected"
            )
            # MQTT 모듈에서 실제 스마트플러그 상태 가져오기 버튼 상태를 정하기 위해 사용하고 버릴거라 지역변수로 사용
            plug_power = get_power_state()
            # 센서 측정 중이 아닐 때만 수동 제어 가능
            if not self.sensor_timer.isActive():
                if plug_power == "ON":
                    self.btn_plug_on.setEnabled(False)
                    self.btn_plug_off.setEnabled(True)
                elif plug_power == "OFF":
                    self.btn_plug_on.setEnabled(True)
                    self.btn_plug_off.setEnabled(False)
                else:  # UNKNOWN
                    self.btn_plug_on.setEnabled(False)
                    self.btn_plug_off.setEnabled(False)
            else:
                # 측정 중에는 수동 제어 금지
                self.btn_plug_on.setEnabled(False)
                self.btn_plug_off.setEnabled(False)

            # 이미 연결됐으므로 재시도 불필요
            self.btn_mqtt_retry.setEnabled(False)

        else:
            self.label_mqtt_status.setText(
                "MQTT 통신 상태 : Disconnected"
            )

            self.btn_plug_on.setEnabled(False)
            self.btn_plug_off.setEnabled(False)

            self.btn_mqtt_retry.setEnabled(True)

    # 수동 스마트플러그 ON 함수
    def plug_on_event(self):
        plug_on(self.mqtt_client)

    # 수동 스마트플러그 OFF 함수
    def plug_off_event(self):
        plug_off(self.mqtt_client)

    # mqtt 재 연결 시도 (버튼 이벤트, mqtt 설정 변경시 사용)
    def retry_mqtt_connection(self):
        # 현재 DB 설정 다시 읽기
        mqtt_config = get_mqtt_config()

        if mqtt_config is None:
            QMessageBox.warning(
                self,
                "MQTT 오류",
                "MQTT 설정을 불러올 수 없습니다."
            )

            return

        # 기존 Client 정리
        close_client(
            self.mqtt_client
        )

        # DB 설정으로 재연결
        self.mqtt_client = create_client(
            mqtt_config["broker"],
            mqtt_config["port"],
            mqtt_config["topic"]
        )

        # 일단 재시도 중에는 버튼 잠금
        self.bio_control_state = None
        self.btn_mqtt_retry.setEnabled(False)

    ## BioAerosol센서 값이 임계값보다 낮을 경우 mqtt를 통해 제품 전원 제어 함수
    def update_bio_status(self, bio_value):
        # 정해진 임계점(0.0)을 초과하면 스마트플러그 작동
        if bio_value > self.bio_Threshold:
            # UI가 나타내는 목표 상태
            # 스마트플러그 ON 및 bioaerosol Status led 색상 Red
            self.label_bio_status_led.setStyleSheet("""
                        QLabel {
                            background-color: red;
                            border-radius: 12px;
                            border: 1px solid black;
                        }
                    """)
            # 목표 상태를 기록하되, 전송 여부는 실제 수신 상태로 판단한다.
            self.bio_control_state = "ON"
            if is_connected() and get_power_state() != "ON":
                # 응답이 없으면 다음 측정 주기에 다시 시도한다.
                plug_on(self.mqtt_client)
        # 정해진 임계점 이하인 경우
        else:
            # 스마트플러그 OFF 및 bioaerosol Status led 색상 Green
            self.label_bio_status_led.setStyleSheet("""
                        QLabel {
                            background-color: green;
                            border-radius: 12px;
                            border: 1px solid black;
                        }
                    """)
            # 목표 상태를 기록하되, 전송 여부는 실제 수신 상태로 판단한다.
            self.bio_control_state = "OFF"
            if is_connected() and get_power_state() != "OFF":
                # 응답이 없으면 다음 측정 주기에 다시 시도한다.
                plug_off(self.mqtt_client)
        # print("체크 후 바이오 제어 상태:", self.bio_control_state)

    # 바이오에어로졸 임계점 DB 업데이트(프로그램 종료 후에 재실행시 기존의 임계점을 가져오기위해)
    def update_bio_threshold(self):
        try:
            # 입력한 임계점을 사용하기 위해 변수에 할당
            new_threshold = int(
                self.edit_bio_threshold.text()
            )
            # if new_threshold < 0:
            #     new_threshold = 0

        except ValueError:

            QMessageBox.warning(
                self,
                "입력 오류",
                "임계값은 숫자로 입력해주세요."
            )

            self.edit_bio_threshold.setText(
                str(self.bio_Threshold)
            )

            return

        # 프로그램 내부 임계점 값 업데이트
        self.bio_Threshold = new_threshold

        # 실제 적용된 값 표시
        self.label_bio_threshold_value.setText(
            str(self.bio_Threshold)
        )
        # print(type(self.bio_Threshold))
        # 새로 업데이트된 임계점을 DB에 업데이트
        update_Bio_threshold(self.bio_Threshold)


    # 프로그램서 mqtt 옵션 확인 및 변경 이벤트(첫 클릭후 5초내에 10번이상 클릭시 발생)
    # 필요시 프로그램에서 mqtt 통신 설정을 변경할수있도록 작성
    def eventFilter(self, obj, event):

        if (
                # mqtt Status 라벨을 클릭 이벤트 대상
                # "MQTT 통신 상태 : Connected" 이렇게 표시된 라벨을 클릭해야함
                obj == self.label_mqtt_status
                and event.type() == QEvent.Type.MouseButtonPress
        ):

            # 첫 클릭이면 3초 타이머 시작
            if self.mqtt_click_count == 0:
                self.mqtt_click_timer.start(5000)

            self.mqtt_click_count += 1
            # print(self.mqtt_click_count)
            # 5초 안에 10번 클릭
            if self.mqtt_click_count >= 10:
                self.mqtt_click_timer.stop()

                # 이벤트 클릭 카운트 초기화(다음에도 사용이 가능하도록)
                self.mqtt_click_count = 0
                # mqtt 세팅 다이얼로그를 띄우면서 세팅을 하도록 함
                self.open_mqtt_setting()

            return True
        return super().eventFilter(
            obj,
            event
        )
    # 클릭 이벤트 실패시 초기화를 위해 작성
    def reset_mqtt_click_count(self):
        self.mqtt_click_count = 0

    # 히든 관리자 설정 다이얼로그 이벤트
    def open_mqtt_setting(self):
        # =========================
        # 현재 MQTT 설정 가져오기(from SQLite)
        # =========================
        config = get_mqtt_config()

        if config is None:
            QMessageBox.warning(
                self,
                "MQTT 설정 오류",
                "MQTT 설정 정보를 불러올 수 없습니다."
            )
            return

        # =========================
        # Dialog 생성
        # =========================
        dialog = QDialog(self)

        dialog.setWindowTitle(
            "관리자 설정"
        )

        dialog.setModal(True)

        layout = QFormLayout(
            dialog
        )

        # =========================
        # 입력창
        # =========================
        edit_broker = QLineEdit()
        edit_port = QLineEdit()
        edit_topic = QLineEdit()

        # 테스트 모드 설정을 위한 체크박스
        chk_test_mode = QCheckBox()
        chk_test_mode.setChecked(self.test_Mode)
        # 센서 데이터 취득 중이면 접근 불가능
        chk_test_mode.setEnabled(
            not self.sensor_timer.isActive()
        )
        # DB에서 가져온 현재값 표시
        edit_broker.setText(
            config["broker"]
        )

        edit_port.setText(
            str(config["port"])
        )

        edit_topic.setText(
            config["topic"]
        )

        layout.addRow(
            "Broker IP",
            edit_broker
        )

        layout.addRow(
            "Port",
            edit_port
        )

        layout.addRow(
            "Topic",
            edit_topic
        )
        # 테스트 모드 기능을 추가하면서 관리자 설정으로 변경
        layout.addRow(
            "테스트 모드",
            chk_test_mode
        )

        # =========================
        # 저장 버튼
        # =========================
        btn_save = QPushButton(
            "저장"
        )

        layout.addRow(
            btn_save
        )

        # =========================
        # 관리자 설정 저장 중첩 함수
        # =========================
        def save_config():
            # broker IP 입력 라인에서 텍스트를 가져오면서 여백을 삭제
            broker = (
                edit_broker
                .text()
                .strip()
            )
            # Topic 입력 라인에서 텍스트를 가져오면서 여백을 삭제
            topic = (
                edit_topic
                .text()
                .strip()
            )

            # -------------------------
            # Port 검사
            # -------------------------
            try:
                port = int(
                    edit_port.text()
                )
            # int 캐스팅을 하면서 입력값이 정수 변환이 안될 경우
            except ValueError:

                QMessageBox.warning(
                    dialog,
                    "입력 오류",
                    "Port는 숫자로 입력해주세요."
                )

                return
            # -------------------------
            # Broker 검사
            # -------------------------
            # broker ip 라인이 비어있을 경우
            if not broker:
                QMessageBox.warning(
                    dialog,
                    "입력 오류",
                    "Broker IP를 입력해주세요."
                )

                return

            # -------------------------
            # Topic 검사
            # -------------------------
            if not topic:
                QMessageBox.warning(
                    dialog,
                    "입력 오류",
                    "Topic을 입력해주세요."
                )

                return

            # -------------------------
            # Port 범위 검사
            # -------------------------
            if not (1 <= port <= 65535):
                QMessageBox.warning(
                    dialog,
                    "입력 오류",
                    "Port 범위는 1 ~ 65535 입니다."
                )

                return

            self.test_Mode = chk_test_mode.isChecked()
            # =========================
            # 설정 변경 여부 확인
            # =========================
            if (
                    broker == config["broker"]
                    and port == config["port"]
                    and topic == config["topic"]
            ):
                dialog.accept()

                return

            # =========================
            # DB Update
            # =========================
            try:
                # 유저 DB에 mqtt 설정 업데이트
                update_mqtt_config(
                    broker,
                    port,
                    topic
                )

            except Exception as e:

                QMessageBox.critical(
                    dialog,
                    "Database 오류",
                    f"MQTT 설정 저장에 실패했습니다.\n\n{e}"
                )

                return

            # =========================
            # 기존 MQTT 종료
            # =========================
            close_client(
                self.mqtt_client
            )

            # =========================
            # 변경 설정으로 재연결
            # =========================
            self.mqtt_client = create_client(
                broker,
                port,
                topic
            )

            # Dialog 종료
            dialog.accept()

        # 저장 버튼 이벤트
        btn_save.clicked.connect(
            save_config
        )

        dialog.exec()
    # =======================
    # SQLite 및 우측 테이블 관련 함수
    # =======================

    # 이 함수는 현재 취득중인 센서데이터를 테이블에 디스플레이하는 함수
    # 센서 데이터를 db에 삽입하는건 read_sensor에서 진행합니다.
    def add_current_row(self, data):
        if self.table_current.rowCount() >= self.MAX_CURRENT_ROWS:
            self.table_current.removeRow(0)

        row = self.table_current.rowCount()
        self.table_current.insertRow(row)
        # 취득 시간을 기준으로 하기 떄문에 datetime함수를 통해 현재 시간을 가져옴
        now = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        values = [
            now,
            f"{data['pm1']:.1f}",
            f"{data['pm25']:.1f}",
            f"{data['pm10']:.1f}",
            str(data["bioaerosol"]),
            f"{data['temperature']:.1f}",
            f"{data['humidity']:.1f}",
            str(data["voc"]),
            str(data["nox"])
        ]

        for column, value in enumerate(values): # enumerate를 통해 리스트의 인덱스(column)와 값(value)을 차례대로 가져옴
            # 반복문을 통해 위에서 센서데이터를 테이블에 입력
            item = QTableWidgetItem(
                value
            )
            # 가운데 정렬
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignCenter
            )
            # 인덱스를 기반으로 데이터(value) 위치를 정함
            self.table_current.setItem(
                row,
                column,
                item
            )

    def update_history_table(self, rows):
        #
        self.table_history.setRowCount(0)

        for row_data in rows:

            row = self.table_history.rowCount()
            self.table_history.insertRow(row)

            for column, value in enumerate(row_data):
                # if column in [4,7,8]:
                #     value = int(value)
                item = QTableWidgetItem(
                    str(value)
                )

                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignCenter
                )

                self.table_history.setItem(
                    row,
                    column,
                    item
                )

    def search_history(self):

        start_date = (
            self.date_start
            .date()
            .toString("yyyy-MM-dd")
        )

        end_date = (
            self.date_end
            .date()
            .toString("yyyy-MM-dd")
        )

        rows = select_by_date(
            start_date,
            end_date
        )

        self.update_history_table(
            rows
        )

    def on_history_header_clicked(self, column):

        if column != 0:
            return

        self.table_history.sortItems(
            0,
            self.history_sort_order
        )

        if self.history_sort_order == Qt.SortOrder.DescendingOrder:
            self.history_sort_order = Qt.SortOrder.AscendingOrder
        else:
            self.history_sort_order = Qt.SortOrder.DescendingOrder

    def closeEvent(self, event):
        if self.sensor_timer.isActive():
            self.sensor_timer.stop()

        if (
                self.ser is not None
                and self.ser.is_open
        ):
            self.ser.close()

        # MQTT 종료
        close_client(
            self.mqtt_client
        )

        # SQLite 종료
        close_db()

        event.accept()




if __name__ == "__main__":

    app = QApplication(sys.argv)

    window = MainWindow()

    window.show()

    sys.exit(app.exec())
