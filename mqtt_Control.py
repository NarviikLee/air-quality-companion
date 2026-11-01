import paho.mqtt.client as mqtt

mqtt_connected = False
power_state = "UNKNOWN"

TOPIC_CMD = None
TOPIC_STAT = None

def on_connect(
    client,
    userdata,
    flags,
    reason_code,
    properties
):

    global mqtt_connected

    if reason_code == 0:

        mqtt_connected = True

        client.subscribe(
            TOPIC_STAT
        )

        # 연결 직후 현재 상태 조회
        client.publish(
            TOPIC_CMD,
            ""
        )

    else:
        mqtt_connected = False


def on_disconnect(
    client,
    userdata,
    disconnect_flags,
    reason_code,
    properties
):
    global mqtt_connected, power_state
    mqtt_connected = False
    # 재연결 후 이전 상태를 실제 장치 상태로 오인하지 않는다.
    power_state = "UNKNOWN"



def on_message(
    client,
    userdata,
    msg
):
    global power_state
    if msg.topic == TOPIC_STAT:
        power_state = (
            msg.payload
            .decode()
        )


def create_client(
    broker,
    port,
    topic
):
    global TOPIC_CMD
    global TOPIC_STAT
    global mqtt_connected
    global power_state


    TOPIC_CMD = (
        f"cmnd/{topic}/POWER"
    )

    TOPIC_STAT = (
        f"stat/{topic}/POWER"
    )

    # 새로운 연결 시도 전 초기화
    mqtt_connected = False
    power_state = "UNKNOWN"

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2
    )

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message

    try:

        client.connect(
            broker,
            port,
            60
        )

        client.loop_start()

    except Exception as e:

        print(
            "MQTT 연결 실패:",
            e
        )

    return client

def plug_on(client):
    global power_state
    if (client is not None
        and mqtt_connected and TOPIC_CMD is not None and power_state != "ON"):

        client.publish(
            TOPIC_CMD,
            "ON"
        )
        print("Plug ON 명령 전송")



def plug_off(client):
    global power_state
    if (client is not None
        and mqtt_connected and TOPIC_CMD is not None and power_state != "OFF"):
        client.publish(
            TOPIC_CMD,
            "OFF"
        )
        print("Plug OFF 명령 전송")


def get_power_state():
    return power_state


def is_connected():
    return mqtt_connected

def close_client(client):

    global mqtt_connected
    global power_state
    if client is None:
        return

    try:
        client.disconnect()
        client.loop_stop()

    except Exception as e:
        print(
            "MQTT 종료 오류:",
            e
        )

    mqtt_connected = False
    power_state = "UNKNOWN"

