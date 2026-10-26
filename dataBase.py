import sqlite3
import os
import sys
from datetime import datetime, timedelta


DB_NAME = "BioAerosol_Control.db"

conn = None


# ===================================
# 실행 파일 기준으로 db파일 체크 및 생성
# ===================================
def get_db_path():

    # PyInstaller exe 실행
    if getattr(sys, "frozen", False):
        base_path = os.path.dirname(sys.executable)

    # Python 직접 실행
    else:
        base_path = os.path.dirname(
            os.path.abspath(__file__)
        )

    return os.path.join(
        base_path,
        DB_NAME
    )


# ===================================
# 1. DB 연결 / 생성
# ===================================

# 여기서 초기화해둔 mqtt설정 그리고 데이터베이스 확인 및 생성을 진행함
def init_db():

    global conn

    if conn is not None:
        return

    db_path = get_db_path()

    conn = sqlite3.connect(
        db_path
    )

    cursor = conn.cursor()

    # 센서 데이터
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sensor_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            pm1 REAL,
            pm25 REAL,
            pm10 REAL,
            bioaerosol INTEGER,
            temperature REAL,
            humidity REAL,
            voc INTEGER,
            nox INTEGER
        )
    """)

    # MQTT 설정
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mqtt_config (
            id INTEGER PRIMARY KEY,
            broker TEXT NOT NULL,
            port INTEGER NOT NULL,
            topic TEXT NOT NULL
        )
    """)

    # 최초 실행 시 기본값 생성
    cursor.execute("""
        INSERT OR IGNORE INTO mqtt_config (
            id,
            broker,
            port,
            topic
        )
        VALUES (
            1,
            ?,
            ?,
            ?
        )
    """, (
        "192.168.77.100",
        1883,
        "Smartplug1"
    ))
    cursor.execute("""
                   CREATE TABLE IF NOT EXISTS user_config
                   (
                       id
                       INTEGER
                       PRIMARY
                       KEY,
                       interval_sec
                       INTEGER
                       NOT
                       NULL,
                       bio_threshold
                       INTEGER
                       NOT
                       NULL,
                       baudrate
                       INTEGER
                       NOT
                       NULL,
                       data_bits
                       INTEGER
                       NOT
                       NULL,
                       parity
                       TEXT
                       NOT
                       NULL,
                       stop_bits
                       REAL
                       NOT
                       NULL
                   )
                   """)

    cursor.execute("""
                   INSERT
                   OR IGNORE INTO user_config (
        id,
        interval_sec,
        bio_threshold,
        baudrate,
        data_bits,
        parity,
        stop_bits
    )
    VALUES (
        1,
        4,
        0,
        115200,
        8,
        'None',
        1
    )
                   """)
    conn.commit()


# ===================================
# 2. Sensor Data INSERT
# ===================================
def insert_sensor_data(data):

    if conn is None:
        init_db()

    timestamp = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    # print(data)
    conn.execute("""
        INSERT INTO sensor_history (
            timestamp,
            pm1,
            pm25,
            pm10,
            bioaerosol,
            temperature,
            humidity,
            voc,
            nox
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        timestamp,
        data["pm1"],
        data["pm25"],
        data["pm10"],
        data["bioaerosol"],
        data["temperature"],
        data["humidity"],
        data["voc"],
        data["nox"]
    ))

    conn.commit()


# ===================================
# 3. 전체 데이터 SELECT
# ===================================
def select_all():

    if conn is None:
        init_db()

    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            timestamp,
            pm1,
            pm25,
            pm10,
            bioaerosol,
            temperature,
            humidity,
            voc,
            nox
        FROM sensor_history

        ORDER BY timestamp DESC
    """)

    return cursor.fetchall()

# ===================================
# 3. Mqtt 설정 값 SELECT
# ===================================
def get_mqtt_config():

    if conn is None:
        init_db()

    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            broker,
            port,
            topic
        FROM mqtt_config
        WHERE id = 1
    """)

    row = cursor.fetchone()

    if row is None:
        return None

    return {
        "broker": row[0],
        "port": row[1],
        "topic": row[2]
    }
# ===================================
# 4. Mqtt 설정 변경 Update
# ===================================
def update_mqtt_config(
    broker,
    port,
    topic
):

    if conn is None:
        init_db()

    conn.execute("""
        UPDATE mqtt_config

        SET
            broker = ?,
            port = ?,
            topic = ?

        WHERE id = 1
    """, (
        broker,
        port,
        topic
    ))

    conn.commit()
# ===================================
# 5. 날짜 범위 SELECT
# ===================================
def select_by_date(
    start_date,
    end_date
):

    if conn is None:
        init_db()

    # 예:
    # start_date = "2026-08-01"
    # end_date   = "2026-08-13"

    start_datetime = (
        f"{start_date} 00:00:00"
    )

    # 종료 날짜 다음날 00:00:00
    end_next_day = (
        datetime.strptime(
            end_date,
            "%Y-%m-%d"
        )
        + timedelta(days=1)
    ).strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            timestamp,
            pm1,
            pm25,
            pm10,
            bioaerosol,
            temperature,
            humidity,
            voc,
            nox
        FROM sensor_history

        WHERE timestamp >= ?
          AND timestamp < ?

        ORDER BY timestamp DESC
    """, (
        start_datetime,
        end_next_day
    ))
    return cursor.fetchall()

# ===================================
# 6. 사용자 최근 옵션 취득 함수
# ===================================
def get_user_config():
    if conn is None:
        init_db()

    cursor = conn.cursor()

    cursor.execute("""
                   SELECT interval_sec,
                          bio_threshold,
                          baudrate,
                          data_bits,
                          parity,
                          stop_bits

                   FROM user_config
                   """, )
    row = cursor.fetchone()
    if row is None:
        return None

    return {
        "interval_sec": row[0],
        "bio_threshold": row[1],
        "baudrate": row[2],
        "data_bits": row[3],
        "parity": row[4],
        "stop_bits": row[5]
    }

# ===================================
# 7. 시리얼 데이터 업데이트 함수
# ===================================
def update_serial_config(
    baudrate,
    data_bits,
    parity,
    stop_bits
):
    if conn is None:
        init_db()

    cursor = conn.cursor()

    cursor.execute("""
        UPDATE user_config
        SET
            baudrate = ?,
            data_bits = ?,
            parity = ?,
            stop_bits = ?
        WHERE id = 1
    """, (
        baudrate,
        data_bits,
        parity,
        stop_bits
    ))

    conn.commit()

# ===================================
# 8. 측정간격 업데이트 함수
# ===================================
def update_interval_sec(interval_sec):
    if conn is None:
        init_db()

    cursor = conn.cursor()

    cursor.execute("""
        UPDATE user_config
        SET
            interval_sec = ?
        WHERE id = 1
    """, (
        interval_sec,
    ))

    conn.commit()
# ===================================
# 9. 바이오 임계점 업데이트 함수
# ===================================
def update_Bio_threshold(bio_threshold):
    if conn is None:
        init_db()

    cursor = conn.cursor()
    cursor.execute("""
        UPDATE user_config
        SET
            bio_threshold = ?
        WHERE id = 1
    """, (
        bio_threshold,
    ))

    conn.commit()
# ===================================
# 10. DB 연결 종료
# ===================================
def close_db():

    global conn

    if conn is not None:

        conn.close()
        conn = None

        # print("Database 연결 종료")
