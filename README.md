# BioAerosol Control

BioAerosol Control은 바이오에어로졸 센서 데이터를 수집하고 화면에 표시하는 Windows용 PySide6 애플리케이션입니다. 센서 측정 이력을 SQLite에 저장하며, MQTT를 통해 외부 스마트 플러그의 상태를 확인하고 제어할 수 있습니다.

## 주요 기능

- 시리얼 포트 검색 및 통신 설정
- 센서 측정 시작·중지와 실시간 데이터 표시
- PM1.0, PM2.5, PM10, BioAerosol, 온도, 습도, VOC, NOx 표시
- 측정 주기와 BioAerosol 임계값 설정
- 날짜별 측정 이력 조회
- MQTT 연결 상태 확인 및 스마트 플러그 제어
- PyInstaller를 이용한 Windows 실행 파일 생성

## 동작 구조

```text
센서 모듈
   │ 시리얼 통신
   ▼
sensor_protocol.py
   │ 측정값 딕셔너리
   ▼
bioaerosol_QT_control.py
   ├─ 화면과 현재 측정 테이블 갱신
   ├─ dataBase.py → SQLite 측정 이력 저장
   └─ 임계값 판정 → mqtt_Control.py → 스마트 플러그 제어
```

시리얼 통신, 화면 표시, 데이터 저장과 MQTT 제어를 모듈별로 분리했습니다. 센서 측정에 실패하면 해당 주기의 저장과 자동 제어를 중단하며, 정상 데이터를 수신한 경우에만 이력 저장과 임계값 판정을 수행합니다.

## 파일 구성

| 파일 | 역할 |
| --- | --- |
| `bioaerosol_QT_control.py` | PySide6 화면과 프로그램 동작을 관리하는 메인 모듈 |
| `dataBase.py` | SQLite 데이터베이스 생성, 설정 저장, 측정 이력 관리 |
| `mqtt_Control.py` | MQTT 연결과 스마트 플러그 상태·전원 제어 |
| `sensor_protocol_template.py` | 비공개 센서 프로토콜 구현을 위한 공개 인터페이스 템플릿 |
| `bioaerosol_QT_control.spec` | PyInstaller 빌드 설정 |

센서 통신 프로토콜 구현과 장비 시험 코드는 장비별 비공개 정보가 포함되어 이 저장소에서 제외됩니다. 프로그램을 실제 센서와 연결하려면 프로젝트와 호환되는 `sensor_protocol.py`를 별도로 준비해야 합니다.

## 센서 프로토콜 연결

저장소에는 실제 프로토콜 대신 `sensor_protocol_template.py`가 포함됩니다. 실제 장비를 연결하는 개발 환경에서는 다음 순서로 준비합니다.

1. `sensor_protocol_template.py`를 `sensor_protocol.py`로 복사합니다.
2. 제조사 문서에 따라 요청 생성, 응답 검증, 데이터 해석 함수를 구현합니다.
3. 각 측정값의 주소, 자료형, 부호, 배율, 단위와 무효값을 확인합니다.
4. 알려진 요청·응답 자료로 단위 테스트한 뒤 실제 장비에서 검증합니다.

`sensor_protocol.py`는 `.gitignore`에 등록되어 있어 로컬 구현이 Git에 추가되지 않습니다. 프로그램은 실제 파일이 없으면 자동으로 템플릿을 불러오므로 GUI, 데이터베이스 화면과 MQTT 기능은 확인할 수 있습니다. 이 상태에서 센서 연결을 시도하면 템플릿이 명확한 `SensorProtocolNotConfiguredError`를 발생시키므로, 실제 통신이 준비되지 않은 상태를 정상 측정값으로 오인하지 않습니다.

## 실행 환경

- Python 3
- PySide6
- pyserial
- paho-mqtt

`mqtt_Control.py`는 paho-mqtt 2.x의 Callback API를 사용합니다. 정확한 설치 범위는 `requirements.txt`에 명시되어 있습니다.

필요한 패키지를 설치한 뒤 다음 명령으로 실행합니다.

```bash
pip install -r requirements.txt
python bioaerosol_QT_control.py
```

첫 실행 시 프로그램 폴더에 `BioAerosol_Control.db`가 생성됩니다. 이 파일에는 측정 이력과 로컬 설정이 저장되므로 Git에 포함하지 않습니다.

## 실행 파일 빌드

PyInstaller가 설치된 환경에서 다음 명령을 실행합니다.

```bash
pyinstaller bioaerosol_QT_control.spec
```

생성되는 `build/`와 `dist/`는 빌드 결과물이므로 저장소에서 제외합니다.

## 공개 범위

이 저장소는 GUI, 데이터 저장, MQTT 제어 코드와 센서 프로토콜 인터페이스 템플릿을 공유합니다. 센서 레지스터, 패킷 구조, 체크섬 매개변수, 통신 시험 프레임 등 장비 프로토콜의 세부 구현은 포함하지 않습니다.

현재 공개본으로 확인할 수 있는 범위는 화면 구성, SQLite 이력 관리, MQTT 제어 흐름과 프로토콜 모듈의 연결 구조입니다. 실제 센서 측정 정확도와 장비 통신 성공 여부는 비공개 프로토콜 구현과 실물 센서 환경에서 별도로 검증해야 합니다.
