import os
import sys
import sqlite3
import time
from datetime import datetime

import requests
from dotenv import load_dotenv


PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)

sys.path.append(PROJECT_ROOT)


from config import (
    REALTIME_ROUTES,
    REALTIME_STATIONS_5001A,
    REALTIME_STATIONS_5003A,
)


# ==================================================
# 기본 설정
# ==================================================

load_dotenv()

API_KEY = os.getenv("DATA_API_KEY")

URL = (
    "https://apis.data.go.kr/6410000/"
    "busarrivalservice/v2/getBusArrivalListv2"
)

DB_PATH = "data/realtime.db"

COLLECT_INTERVAL = 60


# ==================================================
# 수집 대상 정류장 자르기
# ==================================================

def stations_from(stations, start_station_name):

    start_index = next(
        i
        for i, station in enumerate(stations)
        if station["name"] == start_station_name
    )

    return stations[start_index:]


STATIONS_5001A = stations_from(
    REALTIME_STATIONS_5001A,
    "삼가역.두산위브"
)

STATIONS_5003A = stations_from(
    REALTIME_STATIONS_5003A,
    "동백이마트"
)


# ==================================================
# 실행 전 검증
# ==================================================

if len(STATIONS_5001A) <= 1:
    raise RuntimeError(
        "5001A 다정류장 설정 오류"
    )

if len(STATIONS_5003A) <= 1:
    raise RuntimeError(
        "5003A 다정류장 설정 오류"
    )


# ==================================================
# DB 생성
# ==================================================

def create_database():

    os.makedirs(
        os.path.dirname(DB_PATH),
        exist_ok=True
    )

    connection = sqlite3.connect(
        DB_PATH
    )

    connection.execute("""
        CREATE TABLE IF NOT EXISTS realtime_arrival_a (
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

    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_arrival_a_time
        ON realtime_arrival_a (
            route_id,
            station_id,
            collected_at
        )
    """)

    connection.commit()
    connection.close()


# ==================================================
# API 호출
# ==================================================

def get_arrival_data(station_id):

    params = {
        "serviceKey": API_KEY,
        "stationId": station_id,
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

        result_code = header.get("resultCode")
        result_message = header.get(
            "resultMessage"
        )

        if str(result_code) != "0":

            print(
                "API 응답 오류:",
                result_message
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

        if isinstance(arrivals, dict):
            arrivals = [arrivals]

        return arrivals

    except requests.exceptions.Timeout:

        print(
            f"API TIMEOUT | station={station_id}"
        )

    except requests.exceptions.RequestException as e:

        print(
            f"API 요청 오류 | "
            f"station={station_id} | {e}"
        )

    except (KeyError, ValueError) as e:

        print(
            f"응답 파싱 오류 | "
            f"station={station_id} | {e}"
        )

    return []


# ==================================================
# 빈 문자열 처리
# ==================================================

def clean_value(value):

    if value == "":
        return None

    return value


# ==================================================
# DB 저장
# ==================================================

def save_arrival(
    connection,
    bus,
    route_name,
    station_id,
    station_name,
    collected_at
):

    route_id = str(
        bus.get("routeId")
    )

    values = (
        collected_at,

        route_name,
        route_id,

        station_id,
        station_name,

        clean_value(
            bus.get("staOrder")
        ),

        clean_value(
            bus.get("vehId1")
        ),
        clean_value(
            bus.get("plateNo1")
        ),
        clean_value(
            bus.get("predictTimeSec1")
        ),
        clean_value(
            bus.get("locationNo1")
        ),
        clean_value(
            bus.get("stationNm1")
        ),
        clean_value(
            bus.get("remainSeatCnt1")
        ),
        clean_value(
            bus.get("crowded1")
        ),

        clean_value(
            bus.get("vehId2")
        ),
        clean_value(
            bus.get("plateNo2")
        ),
        clean_value(
            bus.get("predictTimeSec2")
        ),
        clean_value(
            bus.get("locationNo2")
        ),
        clean_value(
            bus.get("stationNm2")
        ),
        clean_value(
            bus.get("remainSeatCnt2")
        ),
        clean_value(
            bus.get("crowded2")
        ),
    )

    connection.execute("""
        INSERT INTO realtime_arrival_a (
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


# ==================================================
# 정류장 하나 수집
# ==================================================

def collect_station(
    connection,
    route_name,
    station
):

    station_id = station["id"]
    station_name = station["name"]

    arrivals = get_arrival_data(
        station_id
    )

    target_route_id = REALTIME_ROUTES[
        route_name
    ]

    target_bus = None

    for bus in arrivals:

        route_id = str(
            bus.get("routeId", "")
        )

        if route_id == target_route_id:
            target_bus = bus
            break

    if target_bus is None:

        print(
            f"{route_name} | "
            f"{station_name} | "
            f"데이터 없음"
        )

        return False

    collected_at = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    save_arrival(
        connection,
        target_bus,
        route_name,
        station_id,
        station_name,
        collected_at
    )

    print(
        f"{collected_at} | "
        f"{route_name} | "
        f"{station_name} | "
        f"1번: "
        f"{target_bus.get('predictTimeSec1')}초 / "
        f"{target_bus.get('remainSeatCnt1')}석 | "
        f"2번: "
        f"{target_bus.get('predictTimeSec2')}초 / "
        f"{target_bus.get('remainSeatCnt2')}석"
    )

    return True


# ==================================================
# 한 번 수집
# ==================================================

def collect_once():

    connection = sqlite3.connect(
        DB_PATH
    )

    saved_count = 0

    try:

        print()
        print("=" * 90)
        print(
            "수집 시작:",
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        )
        print("=" * 90)

        print()
        print("[5001A]")
        print("-" * 90)

        for station in STATIONS_5001A:

            if collect_station(
                connection,
                "5001A",
                station
            ):
                saved_count += 1

        print()
        print("[5003A]")
        print("-" * 90)

        for station in STATIONS_5003A:

            if collect_station(
                connection,
                "5003A",
                station
            ):
                saved_count += 1

        connection.commit()

    finally:

        connection.close()

    print()
    print(
        f"이번 사이클 저장: "
        f"{saved_count}개"
    )


# ==================================================
# 반복 실행
# ==================================================

def run_collector():

    print()
    print("BusFlow A 방향 다정류장 수집기")
    print("=" * 90)

    print()
    print(
        f"5001A 정류장 수: "
        f"{len(STATIONS_5001A)}"
    )

    for station in STATIONS_5001A:
        print(
            " -",
            station["name"],
            station["id"]
        )

    print()
    print(
        f"5003A 정류장 수: "
        f"{len(STATIONS_5003A)}"
    )

    for station in STATIONS_5003A:
        print(
            " -",
            station["name"],
            station["id"]
        )

    print()
    print(
        "수집 간격:",
        COLLECT_INTERVAL,
        "초"
    )

    print()
    print("CTRL + C 로 종료")
    print()

    while True:

        try:

            cycle_start = time.time()

            collect_once()

            elapsed = (
                time.time()
                - cycle_start
            )

            sleep_time = max(
                0,
                COLLECT_INTERVAL - elapsed
            )

            print(
                f"다음 사이클까지 "
                f"{sleep_time:.1f}초"
            )

            time.sleep(
                sleep_time
            )

        except KeyboardInterrupt:

            print()
            print(
                "다정류장 수집 종료"
            )

            break


# ==================================================
# 실행
# ==================================================

if __name__ == "__main__":

    if not API_KEY:

        print(
            "DATA_API_KEY가 없습니다."
        )

        raise SystemExit

    create_database()

    run_collector()