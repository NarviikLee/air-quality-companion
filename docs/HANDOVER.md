# 인수인계 안내

정리 기준: 2026-10-07. 현재 작업 트리의 코드를 기준으로 작성했습니다. 문서 작성일과 장비 시험일은 다릅니다.

## 먼저 알아둘 사항

이 프로젝트는 800×480 Qt 공기질 표시 프로그램입니다. 로봇 홈 화면과 8개 센서 카드 화면을 표시하며, 실제 이동·정화 장비를 제어하지 않습니다. 음성 대화 기능은 없습니다.

현재 사용자 결정은 **PM1.0·PM2.5·PM10과 온도·습도를 함께 판단하고 기존 표정 디자인을 유지**하는 것입니다. PM만 판단하는 토글은 논의했지만 구현하지 않았습니다. 다른 디자인 실험은 별도 워크스페이스에서 진행할 예정입니다.

공개 저장소만으로 센서 없는 데모를 실행할 수 있습니다. 실제 장비 실행에는 별도로 인계받는 `sensor_protocol.py`와 `sensor_connection_local.py`가 필요합니다. 공개 템플릿은 작동하는 장비 프로토콜이 아닙니다.

## 읽는 순서

| 문서 | 목적 |
|---|---|
| [이 안내](HANDOVER.md) | 실행, 설정, 운영, 검증 범위, AI 작업 시 주의사항 |
| [구조 안내](ARCHITECTURE.md) | 데이터 흐름과 수정할 파일 찾기 |
| [README](../README.md) | 기능, 데모, 변경 이력, 시험 결과 상세 |
| [판정 기준](../SENSOR_CRITERIA.md) | 카드 등급·종합 표정 기준과 근거 |

로컬 `HANDOFF.md`, `RASPBERRY_PI.md`, `V1_*.md`, `UI_V1_NATIVE.md` 등은 Git에서 제외된 내부 자료입니다. 과거 설치·작업 기록이 섞여 있으므로 현재 코드와 이 안내를 우선하고, 과거의 “미구현”, “미검증”, “PNG 필수” 문구를 현재 사실로 해석하지 않습니다.

## 처음 실행하기

명령은 프로젝트 루트에서 실행합니다. Windows 개발 환경에서는 프로젝트에 설정된 인터프리터를 사용합니다. 기존 환경이 없다면:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py --demo --windowed
```

| 옵션 | 용도 |
|---|---|
| `--demo` | 센서 없이 더미 데이터로 실행 |
| `--demo-states` | 표정 7종을 순서대로 표시 |
| `--demo-partial` | 일부 센서 무효값 처리 확인 |
| `--demo-pm-rise` | PM 급상승 반영 확인 |
| `--demo-tour` | 정상·오류·재연결 통합 시나리오 |
| `--windowed` | 개발용 창 모드; 생략하면 기본 전체화면 |

기존 Pi는 Python 3.7.3 / PySide2 / Qt 5.11.3 환경입니다. Windows는 PySide6를 사용합니다. `qt_compat.py`가 바인딩을 선택하며 `QT_API=pyside2` 또는 `pyside6`으로 지정할 수 있습니다. Pi에서 Windows `.venv`를 복사하거나 같은 Qt 버전이라고 가정하지 않습니다. 기존 Buster 의존성 설치 안내는 [requirements.txt](../requirements.txt)에 있습니다.

```bash
QT_API=pyside2 /usr/bin/python3 main.py --demo --windowed
```

실제 실행은 로컬 파일 인계·검토 후 데스크톱 세션에서 `main.py --fullscreen`을 사용합니다. 데모와 실제 서비스를 동시에 실행하면 사용자 단위 중복 실행 잠금으로 두 번째 실행이 종료될 수 있습니다.

## 설정과 시간 기준

| 설정 | 현재 값 | 의미 |
|---|---|---|
| `app_config.ini`: `sensor_detail_timeout_sec` | 30초 | 상세 화면에 진입한 뒤 홈으로 자동 복귀 |
| `SENSOR_STALE_TIMEOUT_SEC` | 5초 | 전체 정상 데이터 수신 공백 감지 |
| `CHANNEL_STALE_TIMEOUT_SEC` | 5초 | 개별 분석 항목의 무효 데이터 공백 감지 |
| `DISCONNECT_FACE_HOLD_SEC` | 30초 | 마지막 정상 수신부터 이전 확정 표정을 유지하는 유예 |
| `MOVING_AVERAGE_WINDOW_SEC` / `MIN_SAMPLES_IN_WINDOW` | 30초 / 24개 | 최초·일반 분석 수집 기준 |
| `STATE_CONFIRM_DURATION_SEC` | 10초 | 일반 후보 상태 확인 |
| `RECONNECT_WINDOW_SEC` / `RECONNECT_MIN_SAMPLES` | 10초 / 8개 | 재연결 후 새 표본 수집 |
| `RECONNECT_CONFIRM_SEC` | 5초 | 재연결 후보 상태 확인 |
| `RETRY_INTERVAL_SECONDS` | 3초 | 실패 후 재시도 간격 |

INI를 제외한 위 상수는 [sensor_data.py](../sensor_data.py)에 있습니다. 설정은 시작 시 읽으므로 변경 적용에는 재실행이 필요합니다. 잘못된 상세 복귀 설정은 5초 기본값으로 복구됩니다. 시험 중 적용을 위해 임의로 재시작하지 말고 시험 종료 후 적용합니다.

**상세 화면 복귀 30초, 단절 표정 유지 30초, 최초 분석 30초는 서로 다른 타이머입니다.** 단절 시 카드는 마지막 숫자를 지우지 않고 지연 상태를 표시합니다. 마지막 정상 수신 후 30초 이상이면 홈으로 강제 복귀하며 기존 표정 유지도 만료됩니다. 재연결만으로 상세 화면을 다시 열지 않습니다.

처음 실행한 경우 정상 데이터 수신부터 일반적으로 약 40초(30초 수집+10초 확인), 재연결은 약 15초(10초+5초)가 기준입니다. 포트 탐색 시간, 표본 부족, 무효값, 후보 변경·PM 급상승 경로에 따라 달라지므로 고정 완료 시간을 보장하지 않습니다. 오래 분리했어도 프로그램이 계속 실행 중이었다면 재연결 경로입니다. 프로그램 자체를 재시작하면 최초 실행 경로입니다.

## 실제 장비 인계와 운영

인수자는 다음을 별도 확인합니다.

- 승인된 로컬 프로토콜·연결 설정과 장비의 실제 배포 버전
- 데스크톱 세션, 시리얼 접근 권한, 사용자 systemd 서비스 설치 상태
- 로컬 `deploy/` 파일의 경로와 계정 설정; 공개 Git clone에는 이 파일이 없음
- 운영 UI 설정을 유지할지 여부; `app_config.ini`를 무조건 덮어쓰지 않음

런타임 루트 `.py` 파일은 같은 버전으로 맞추되 두 비공개 파일은 보존합니다. `previews/`, `designs/`, `logs/`, `tests/`, 백업과 Windows 가상환경은 현재 운영 화면 실행에 필요하지 않습니다. 얼굴은 QPainter로 그리므로 미리보기 PNG를 Pi에 복사할 필요가 없습니다.

현재 서비스 상태 확인은 재시작 없이 수행합니다.

```bash
systemctl --user status air-quality-display.service --no-pager -l
systemctl --user show air-quality-display.service \
  -p ActiveState -p SubState -p MainPID -p NRestarts
sudo journalctl --user-unit=air-quality-display.service \
  --since "2 hours ago" -o short-precise --no-pager
```

`--user` systemctl은 실제 서비스를 실행하는 사용자 세션에서 사용합니다. 서비스는 `Restart=on-failure`, `RestartSec=5`, `WatchdogSec=30`으로 구성된 로컬 배포 설정을 사용합니다. 포트 없음이나 처리된 수신 실패는 재시도 대상이며, 그 자체로 서비스를 계속 재시작하는 정책이 아닙니다. 정상 종료와 `systemctl stop`은 장애 복구 시험이 아닙니다.

`No journal files were found` 또는 `No entries`는 “오류가 없었다”는 증거가 아닙니다. 조회 범위·사용자·저널 보관 상태를 확인하고, 필요하면 해당 PID로 `sudo journalctl _PID=<PID>`를 조회합니다. `status`의 로그는 최근 일부이므로 전체 시험 로그와 구분합니다.

## 검증과 남은 범위

공개 자료: [logs/](../logs/). 장비 이름·사용자 경로를 익명화했으며 날짜·PID·측정값은 유지했습니다. 날짜는 장비 시계 기준입니다.

| 시험 | 확인된 결과 | 한계 |
|---|---|---|
| 이전 약 3시간 및 별도 약 2시간 운전 | 기록상 서비스 또는 PID 유지 | 서로 다른 실행; 하나의 연속 시험으로 합산하지 않음 |
| 2026-09-23 오전 약 3시간·오후 약 2시간 | PID 1111, 재시작 0회; 프로그램 메모리 78.4→78.9MB 후 유지 | 두 TSV 사이에 기록 공백; CPU는 수집 방식에 따른 기록값 |
| 오후 분리·재연결 5회 | 모두 수신 복구; 짧은 단절 표정 유지 정책 일치 | 최종 표정 복구 시각은 로그에 없음 |
| 사용자 SIGKILL 시험 1회 | PID 31517, 재시작 횟수 1, 서비스·포트 확인 복구 | 터미널 출력 근거; 종료 시각·전체 화면 복구 시간 미기록 |

공유 코드의 2026-10-01 변경일과 시험 자료의 2026-09-23 장비 날짜가 다릅니다. 시험한 정확한 커밋을 확정하지 못하므로 특정 최신 커밋의 모든 기능이 실장비 검증됐다고 주장하지 않습니다. 수일 연속 운전과 센서 측정 정확도는 이 기록으로 검증되지 않았습니다. watchdog 설정·활성화 및 SIGKILL 복구는 확인되지만, 공개 로그만으로 heartbeat 중단 시험 성공까지 확정하지 않습니다.

코드 변경 후에는 변경에 관련된 테스트를 실행합니다. 아래는 전체 검사 명령이며 문서만 바꿀 때마다 재실행할 필요는 없습니다.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
.\.venv\Scripts\python.exe tests\check_demo.py
.\.venv\Scripts\python.exe previews\preview_robot.py
.\.venv\Scripts\python.exe previews\render_preview_compare.py
```

`tests/check_demo.py`는 이미지도 생성합니다. README용 고정 이미지는 이후 `previews/preview_robot.py`로 생성합니다. 공개본의 비공개 프로토콜 관련 검사는 건너뛸 수 있으며, 현재 전체 테스트 수는 실행 결과로 확인합니다. 과거 README의 테스트 개수를 현재 결과로 재사용하지 않습니다.

## AI 도구에 전달할 작업 맥락

새 세션에는 이 안내와 [구조 안내](ARCHITECTURE.md)를 먼저 읽게 하고 다음을 전달합니다.

> 이 프로젝트의 현재 동작과 표정 디자인을 보존하면서 요청한 변경만 수행한다. 실제 프로토콜·연결 설정은 로컬 비공개 파일이며 공개 템플릿을 운영 파일에 덮어쓰지 않는다. 표정은 PM 3종+온습도로 판단하고 VOC/NOx/Bio는 표시 전용이다. 화면 그리기와 판단 로직을 구분한다. Qt5/Python3.7 운영 호환성을 고려하고 실제 실행할 인터프리터를 먼저 확인한다. 장비 시험 중에는 임의 재시작하지 않는다. `.gitignore`의 개별 공개 허용 규칙을 유지하고, 새 파일이나 로그를 공개하기 전 내용과 추적 대상을 검토한다. 현재 코드·설정을 근거로 판단하며 과거 문서의 미구현 상태를 현재 사실로 사용하지 않는다.

이 문서는 실행 지침이며 자동 배포·메시지 전송·공개 승인을 부여하지 않습니다. 인수인계 시 실제 변경 커밋, 장비 배포 버전, 로컬 파일 전달 여부를 함께 기록하면 다음 작업자가 검증 범위를 구분할 수 있습니다.
