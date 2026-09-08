import os
import sqlite3
import time
from datetime import datetime

import requests
from dotenv import load_dotenv


load_dotenv()

API_KEY = os.getenv("DATA_API_KEY")

URL = (
    "https://apis.data.go.kr/6410000/"
    "busarrivalservice/v2/getBusArrivalListv2"
)

DB_PATH = "data/realtime.db"

# 실시간 API 기준 기흥역 ID
STATION_ID = "228000682"
STATION_NAME = "기흥역"

# 실시간 API 기준 노선 ID
TARGET_ROUTES = {
    "228000429": "5001A",
    "228000431": "5003A",
}

# API 호출 간격
COLLECT_INTERVAL = 60


# --------------------------------------------------
# DB 생성
# --------------------------------------------------

def create_database():

    connection = sqlite3.connect(DB_PATH)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS realtime_arrival (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            collected_at TEXT NOT NULL,

            route_name TEXT NOT NULL,
            route_id TEXT NOT NULL,

            station_id TEXT NOT NULL,
            station_name TEXT,

            sta_order INTEGER,

            veh_id_1 TEXT,
            plate_no_1 TEXT,
            predict_time_sec_1 INTEGER,
            location_no_1 INTEGER,
            vehicle_station_name_1 TEXT,
            remain_seat_cnt_1 INTEGER,
            crowded_1 INTEGER,

            veh_id_2 TEXT,
            plate_no_2 TEXT,
            predict_time_sec_2 INTEGER,
            location_no_2 INTEGER,
            vehicle_station_name_2 TEXT,
            remain_seat_cnt_2 INTEGER,
            crowded_2 INTEGER
        )
    """)

    connection.commit()
    connection.close()


# --------------------------------------------------
# API 호출
# --------------------------------------------------

def get_arrival_data():

    params = {
        "serviceKey": API_KEY,
        "stationId": STATION_ID,
        "format": "json",
    }

    try:

        response = requests.get(
            URL,
            params=params,
            timeout=30
        )

        response.raise_for_status()

        data = response.json()

        header = data["response"]["msgHeader"]

        if header["resultCode"] != 0:

            print(
                "API 응답 오류:",
                header["resultMessage"]
            )

            return []

        body = data["response"].get(
            "msgBody",
            {}
        )

        arrivals = body.get(
            "busArrivalList",
            []
        )

        return arrivals

    except requests.exceptions.Timeout:

        print("API TIMEOUT")

    except requests.exceptions.RequestException as e:

        print("API 요청 오류:", e)

    except (KeyError, ValueError) as e:

        print("응답 파싱 오류:", e)

    return []


# --------------------------------------------------
# 우리가 원하는 노선만 추출
# --------------------------------------------------

def filter_target_routes(arrivals):

    results = []

    for bus in arrivals:

        route_id = str(bus.get("routeId", ""))

        if route_id not in TARGET_ROUTES:
            continue

        results.append(bus)

    return results


# --------------------------------------------------
# 빈 문자열 → None
# --------------------------------------------------

def clean_value(value):

    if value == "":
        return None

    return value


# --------------------------------------------------
# DB 저장
# --------------------------------------------------

def save_arrival(bus):

    route_id = str(bus.get("routeId"))
    route_name = TARGET_ROUTES[route_id]

    collected_at = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    values = (
        collected_at,

        route_name,
        route_id,

        STATION_ID,
        STATION_NAME,

        clean_value(bus.get("staOrder")),

        clean_value(bus.get("vehId1")),
        clean_value(bus.get("plateNo1")),
        clean_value(bus.get("predictTimeSec1")),
        clean_value(bus.get("locationNo1")),
        clean_value(bus.get("stationNm1")),
        clean_value(bus.get("remainSeatCnt1")),
        clean_value(bus.get("crowded1")),

        clean_value(bus.get("vehId2")),
        clean_value(bus.get("plateNo2")),
        clean_value(bus.get("predictTimeSec2")),
        clean_value(bus.get("locationNo2")),
        clean_value(bus.get("stationNm2")),
        clean_value(bus.get("remainSeatCnt2")),
        clean_value(bus.get("crowded2")),
    )

    connection = sqlite3.connect(DB_PATH)

    connection.execute("""
        INSERT INTO realtime_arrival (

            collected_at,

            route_name,
            route_id,

            station_id,
            station_name,

            sta_order,

            veh_id_1,
            plate_no_1,
            predict_time_sec_1,
            location_no_1,
            vehicle_station_name_1,
            remain_seat_cnt_1,
            crowded_1,

            veh_id_2,
            plate_no_2,
            predict_time_sec_2,
            location_no_2,
            vehicle_station_name_2,
            remain_seat_cnt_2,
            crowded_2

        )

        VALUES (
            ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?
        )
    """, values)

    connection.commit()
    connection.close()

    print(
        f"{collected_at} | "
        f"{route_name} | "
        f"1번 {bus.get('predictTimeSec1')}초 "
        f"{bus.get('remainSeatCnt1')}석 | "
        f"2번 {bus.get('predictTimeSec2')}초 "
        f"{bus.get('remainSeatCnt2')}석"
    )


# --------------------------------------------------
# 한 번 수집
# --------------------------------------------------

def collect_once():

    arrivals = get_arrival_data()

    target_buses = filter_target_routes(
        arrivals
    )

    if not target_buses:

        print("대상 노선 데이터 없음")
        return

    for bus in target_buses:

        save_arrival(bus)


# --------------------------------------------------
# 반복 수집
# --------------------------------------------------

def run_collector():

    print("실시간 수집 시작")
    print("정류장:", STATION_NAME)
    print("수집 간격:", COLLECT_INTERVAL, "초")
    print("CTRL + C 로 종료")
    print()

    while True:

        try:

            collect_once()

            time.sleep(
                COLLECT_INTERVAL
            )

        except KeyboardInterrupt:

            print()
            print("수집 종료")
            break


# --------------------------------------------------
# 실행
# --------------------------------------------------

if __name__ == "__main__":

    if not API_KEY:
        print("DATA_API_KEY가 없습니다.")
        raise SystemExit

    create_database()

    run_collector()