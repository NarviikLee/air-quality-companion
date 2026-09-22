# Air Quality Robot Display — V2 UI Animation / WIP

800×480 Qt 화면에서 주변 환경을 로봇 표정과 8개 센서 카드로 표시하는 Python 프로젝트입니다. 실제 로봇 이동이나 공기청정 장비를 제어하지 않습니다.

## 주요 기능

- QPainter 로봇 얼굴과 Qt 센서 카드, 홈/상세 화면 전환
- PM1.0, PM2.5, PM10, VOC, NOx, Bioaerosol, 온도, 습도 표시
- PM 3종과 온습도의 최근 30초 이동평균, 최소 24개 sample, 후보 상태 10초 확인
- 짧은 수신 오류 허용, stale 표시, worker 취소와 재연결
- VOC/NOx/Bio는 표시 전용이며 종합 표정에서 제외
- 데모 모드, 종료 처리, 중복 실행 방지, systemd watchdog 지원

상세 카드는 최신 수신값, 얼굴은 평균과 확정 결과를 표시합니다. 수신이 지연되면 카드 숫자는 마지막 정상값을 유지하되 카드 상태 문구와 색상이 `수신 지연`으로 바뀌며, 새 정상값이 들어오면 자동으로 복구됩니다. 센서 대기 중 상세 진입은 차단됩니다. `MONITORING` 이후에는 로봇 홈 영역을 터치해 상세 화면으로 이동할 수 있습니다. 상세 화면은 읽기 전용이며 화면을 다시 터치하거나 설정 시간이 지나면 얼굴 화면으로 복귀합니다. 로봇 홈에는 확정 상태 제목만 표시하며 후보 확인·수신 지연·원인 정보는 내부 분석 상태로만 유지합니다. 공식 AQI나 건강 안전 판정이 아닙니다. 판정 근거는 [SENSOR_CRITERIA.md](SENSOR_CRITERIA.md)를 참고하세요.

## 기술 스택

Python, PySide6(Windows 개발), PySide2/Qt 5(기존 Raspberry Pi 환경), QPainter, pySerial, unittest.

### V1 화면 호환성 보완

Pi의 Qt 5와 Windows Qt 6에서 헤더·상세·홈·종료 화면 및 바깥 여백을 어두운 배경으로 명시합니다. 각 컨테이너에 `WA_StyledBackground`를 적용했습니다. 헤더의 DEMO/연결 알림은 숨겼습니다. 로봇 홈은 얼굴 아래 상태 제목만 표시하고, 상세 화면은 별도 제목·갱신 경과시간·수신 지연·안내 문구 없이 8개 센서 카드만 표시합니다. 터치 후 얼굴에 남던 버튼 포커스 테두리도 제거했습니다. 분석 및 통신 기준은 변경하지 않았습니다. 배포 시 `dashboard.py`, `robot_ui.py`, `robot_led.py`, `sensor_data.py`, `app_config.ini`를 함께 복사하세요. 실제 Pi 렌더링은 재확인이 필요합니다.

### UI 설정

센서 상세 화면의 자동 복귀 시간은 `app_config.ini`에서 초 단위로 변경합니다. 설정은 프로그램을 다시 시작할 때 적용됩니다. 파일이 없거나, INI 문법이 잘못됐거나, 값을 읽을 수 없거나, 값이 0 이하이면 5초를 사용합니다.

```ini
[ui]
sensor_detail_timeout_sec = 5
```

### V2 얼굴 애니메이션

V1의 센서 통신과 환경 판정은 유지하면서 QPainter 얼굴에 상태별 움직임을 추가했습니다. `robot_animation.py`는 경과시간에 따른 눈 위치, 눈 개방 정도, 입 파형과 상태 기호만 계산하고, `robot_ui.py`가 하나의 75ms Qt 타이머로 화면을 다시 그립니다. 얼굴 화면이 숨겨지면 해당 타이머도 정지합니다.

- `waiting`: 입 파형이 오른쪽으로 흐름
- `monitoring`: 눈이 좌우로 주변을 탐색
- `normal`: 일정 간격으로 눈을 깜빡임
- `detected`: 느낌표가 점멸
- `comfortable`: 눈이 위아래로 미세하게 이동
- `moving`: 방향 화살표와 시선이 좌우로 전환
- `purifying`: 좌우 가장자리의 가로 공기 물결이 얼굴 쪽으로 번갈아 흐르고 입 파형이 움직임

`moving`과 `purifying`은 표시 상태일 뿐 실제 이동이나 공기청정 장비를 제어하지 않습니다. `PURIFYING`은 향후 외부 상태 입력을 받을 수 있도록 표시용 API만 제공하며 현재 통신 프로토콜은 구현하지 않았습니다.

각 애니메이션 프레임은 얼굴 영역을 먼저 초기화한 뒤 다시 그립니다. `detected`의 눈과 glow는 모두 원형으로 렌더링해 `normal`에서 전환할 때 사각 눈 모양이 잔상처럼 보이지 않도록 했습니다.

## 데모 실행

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py --demo --windowed
```

센서 판정 대기 없이 7개 얼굴 상태와 애니메이션을 4초마다 순서대로 확인하려면 다음 명령을 사용합니다. `NORMAL` 다음에 `DETECTED`가 나오므로 상태 전환 잔상도 확인할 수 있습니다.

```powershell
.\.venv\Scripts\python.exe main.py --demo-states --windowed
```

Raspberry Pi/Linux에서는 같은 옵션을 `python3 main.py --demo-states --windowed` 형식으로 실행합니다. 전체화면 확인 시 `--windowed`를 생략합니다.

공개본에는 실제 센서 프로토콜과 통신 값이 없습니다. 먼저 `--demo`로 실행하세요. 전체화면은 `--windowed`를 생략합니다. Linux에서는 해당 환경의 PySide2 또는 PySide6와 pySerial을 별도로 준비하세요. 기존 Raspberry Pi의 Python 3.7/PySide2 호환을 고려하지만 장비에서 직접 검증해야 합니다.

## 로컬 전용 센서 설정

없는 파일만 생성하고 기존 장비 설정은 덮어쓰지 않습니다.

```powershell
if (!(Test-Path sensor_protocol.py)) { Copy-Item sensor_protocol_template.py sensor_protocol.py }
if (!(Test-Path sensor_connection_local.py)) { Copy-Item sensor_connection_example.py sensor_connection_local.py }
```

- `sensor_protocol.py`: 실제 장비에 대해 승인된 로컬 구현을 넣습니다. 공개 예제는 함수/예외 인터페이스만 제공하며 패킷을 생성하거나 전송하지 않습니다. placeholder 값만 채워도 완성되는 구현이 아닙니다.
- `sensor_connection_local.py`: 실제 baudrate, 데이터 비트, 패리티, 정지 비트 등 장비 설정을 로컬에서 입력합니다.
- 실제 register address, slave/device ID, 요청/응답과 매핑 정보는 공개 저장소에 포함되지 않습니다.
- 기존 장비의 두 로컬 파일은 유지하세요. 배포 시 공유 코드와 로컬 설정이 함께 필요합니다. Git clone/pull만으로 비공개 파일이 복원되지는 않습니다.
- `read_sensor_data(ser, cancel_event=None)`는 정상 프레임 전체 검증 후 센서 key의 dict를 반환해야 합니다. CRC/프레임 오류를 부분 성공으로 처리하지 않습니다.

## 검사

위 예제 복사 후 센서 없이 실행할 수 있습니다.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -p "test_*.py"
.\.venv\Scripts\python.exe check_demo.py
```

테스트는 가짜 포트/데이터와 offscreen Qt를 사용합니다. 실제 장비 전용 패킷 테스트는 공개하지 않습니다. `check_demo.py`는 미리보기 PNG를 생성합니다.

README에 사용하는 현재 런타임 UI 이미지는 다음 명령으로 다시 생성합니다. `preview_robot.py`는 별도의 목업을 그리지 않고 실제 `MainWindow`, 로봇 홈 위젯, 센서 카드 위젯을 캡처합니다. 홈 이미지는 `MONITORING / 환경 확인 중` 상태로 고정됩니다.

```powershell
.\.venv\Scripts\python.exe preview_robot.py
```

- `demo_robot_home.png`: MONITORING 로봇 홈 화면
- `demo_preview.png`: 고정 예시값을 표시한 8개 센서 카드 화면

## 유지보수 이력

### 2026-09-17 · V1 공개 저장소 구성

- 800×480 Qt 센서 디스플레이, 8개 센서 카드와 V1 공기질 분석 로직을 공개 저장소로 정리했습니다.
- 실제 센서 프로토콜, register 주소, 장치 ID와 시리얼 설정은 로컬 전용 파일로 분리하고 Git 추적에서 제외했습니다.
- `sensor_protocol_template.py`와 `sensor_connection_example.py`를 추가해 공개 코드와 로컬 장비 설정의 인터페이스를 맞췄습니다.
- CRC·프레임 오류는 전체 응답 실패로 유지하고, 정상 프레임 내부의 개별 센서 무효값만 분리 처리하도록 검증했습니다.

### 2026-09-18 · Raspberry Pi 화면 보완과 V2 애니메이션

- Raspberry Pi의 PySide2/Qt 5에서 보이던 헤더와 하단의 흰 여백을 어두운 배경으로 명시했습니다.
- 페이지 높이와 컨테이너 배경을 조정해 Windows PySide6와 Raspberry Pi에서 같은 800×480 구성을 사용하도록 보완했습니다.
- `robot_animation.py`를 추가하고 waiting, monitoring, normal, detected, comfortable, moving, purifying의 7개 애니메이션 상태를 구현했습니다.
- 상태 전환 시 이전 눈 모양이 남던 잔상 문제를 해결하기 위해 매 프레임 얼굴 영역 전체를 먼저 지우고 다시 그리도록 수정했습니다.
- `--demo-states`를 추가해 실제 센서 대기 없이 모든 상태와 상태 전환을 순서대로 확인할 수 있게 했습니다.

### 2026-09-21 · 터치 동작과 상세 화면 정리

- 로봇 홈에서 센서 상세 화면으로 이동하고, 상세 화면을 다시 터치하거나 설정 시간이 지나면 자동으로 복귀하도록 구성했습니다.
- 상세 화면의 별도 복귀 버튼을 제거하고 페이지 전체 터치를 하나의 복귀 이벤트로 통합했습니다.
- 센서 수신 중에도 사용자가 보고 있는 상세 페이지를 유지하도록 페이지 상태와 수신 상태를 분리했습니다.
- 로봇 홈 전체 영역을 터치 대상으로 확장하고 SENSOR_CHECK/WAITING 중에는 상세 진입을 계속 차단했습니다.
- 로봇 홈은 상태 제목만, 상세 화면은 8개 센서 카드만 표시하도록 안내·원인·갱신 라벨을 정리했습니다.
- 상세 화면 자동 복귀 시간을 `app_config.ini`의 `sensor_detail_timeout_sec`로 분리했습니다.

### 2026-09-22 · 설정 복구, 상태 가시성 및 미리보기 안정화

- 얼굴 버튼을 터치한 뒤 남던 Qt 포커스 테두리를 제거했습니다.
- `preview_robot.py`가 별도 목업 대신 실제 런타임 Qt 위젯으로 README 이미지를 생성하도록 변경했습니다.
- 홈 미리보기 상태를 `MONITORING / 환경 확인 중`으로 맞추고 애니메이션 시각을 고정해 반복 생성한 PNG가 동일하도록 보완했습니다.
- 잘못된 `app_config.ini` 문법, 인코딩, 읽기 실패, 숫자가 아닌 값과 0 이하 값에서 프로그램이 중단되지 않고 5초 기본값으로 복구되도록 수정했습니다.
- 별도 하단 라벨 없이 카드 내부 상태 영역에 `수신 지연`을 표시하고, 정상 수신 시 기존 센서 판정으로 자동 복귀하도록 보완했습니다.
- 터치스크린에서 갑자기 나타나던 센서 카드 hover 설명을 제거하고, 화면에 보이지 않는 접근성 이름은 유지했습니다.
- Raspberry Pi에서 확인한 동작에 맞춰 얼굴 애니메이션 갱신 주기를 75ms로 통일했습니다.
- 전체 단위·통합 테스트 90개와 offscreen 데모 검사를 통과했습니다. 실제 센서 장시간 운용과 Raspberry Pi 성능은 계속 현장에서 확인합니다.

## 공개 범위와 현재 상태

`.gitignore`는 검토한 파일만 공개하는 allowlist입니다. 새 파일을 추가할 때 공개 여부를 검토해야 합니다. 실제 protocol/config, .env, IDE/캐시, 백업 ZIP, 장비 로그, 대화/인계 문서와 이전 제어 프로그램은 제외됩니다. `git add -f`로 제외 파일을 추가하지 마세요.

**V2 UI Animation / WIP.** 센서 분석과 통신은 V1 기준을 유지합니다. 실제 센서의 단위·음수 온도 인코딩·무효값, Pi의 응답 주기/timeout/터치/폰트·애니메이션 성능과 복구 동작은 장비에서 추가 확인해야 합니다. 외부 이동/정화 통신 규격과 장비 제어는 구현하지 않았습니다.

![Robot home](demo_robot_home.png)
![Sensor detail](demo_preview.png)
