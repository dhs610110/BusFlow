import os
import sys
import sqlite3
import time
from datetime import datetime

import requests
from dotenv import load_dotenv


# ==================================================
# 프로젝트 루트 추가
# ==================================================

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

sys.path.append(PROJECT_ROOT)


from config import (
    REALTIME_ROUTES,
    REALTIME_STATIONS_B,
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

DB_PATH = os.path.join(
    PROJECT_ROOT,
    "data",
    "realtime.db"
)

COLLECT_INTERVAL = 60


# ==================================================
# 수집 대상 노선
# ==================================================

TARGET_ROUTES = {
    REALTIME_ROUTES["5001B"]: "5001B",
    REALTIME_ROUTES["5003B"]: "5003B",
}


# ==================================================
# 수집 대상 정류장
# ==================================================

TARGET_STATIONS = REALTIME_STATIONS_B


# ==================================================
# 실행 전 검증
# ==================================================

if len(TARGET_STATIONS) <= 1:
    raise RuntimeError(
        "B 방향 다정류장 설정 오류"
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
        CREATE TABLE IF NOT EXISTS realtime_arrival_b (
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
        CREATE INDEX IF NOT EXISTS idx_arrival_b_time
        ON realtime_arrival_b (
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

        result_code = header.get(
            "resultCode"
        )

        result_message = header.get(
            "resultMessage"
        )

        if str(result_code) != "0":

            print(
                f"API 응답 오류 | "
                f"station={station_id} | "
                f"{result_message}"
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
            f"API TIMEOUT | "
            f"station={station_id}"
        )

    except requests.exceptions.RequestException as e:

        print(
            f"API 요청 오류 | "
            f"station={station_id} | "
            f"{e}"
        )

    except (KeyError, ValueError) as e:

        print(
            f"응답 파싱 오류 | "
            f"station={station_id} | "
            f"{e}"
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
    station_id,
    station_name,
    collected_at
):

    route_id = str(
        bus.get("routeId")
    )

    route_name = TARGET_ROUTES[
        route_id
    ]

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
        INSERT INTO realtime_arrival_b (
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

    return route_name


# ==================================================
# 특정 정류장 수집
# ==================================================

def collect_station(
    connection,
    station
):

    station_id = station["id"]
    station_name = station["name"]

    arrivals = get_arrival_data(
        station_id
    )

    if not arrivals:

        print(
            f"{station_name:20} | "
            f"도착정보 없음"
        )

        return 0

    saved_count = 0

    for bus in arrivals:

        route_id = str(
            bus.get("routeId", "")
        )

        if route_id not in TARGET_ROUTES:
            continue

        collected_at = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        route_name = save_arrival(
            connection,
            bus,
            station_id,
            station_name,
            collected_at
        )

        print(
            f"{collected_at} | "
            f"{route_name:5} | "
            f"{station_name:20} | "
            f"1번 "
            f"{bus.get('predictTimeSec1')}초 / "
            f"{bus.get('remainSeatCnt1')}석 | "
            f"2번 "
            f"{bus.get('predictTimeSec2')}초 / "
            f"{bus.get('remainSeatCnt2')}석"
        )

        saved_count += 1

    if saved_count == 0:

        print(
            f"{station_name:20} | "
            f"5001B / 5003B 데이터 없음"
        )

    return saved_count


# ==================================================
# 한 사이클 수집
# ==================================================

def collect_once():

    cycle_start = datetime.now()

    print()
    print("=" * 100)
    print(
        "B 방향 수집 시작:",
        cycle_start.strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    )
    print("=" * 100)

    connection = sqlite3.connect(
        DB_PATH
    )

    saved_count = 0

    try:

        for station in TARGET_STATIONS:

            count = collect_station(
                connection,
                station
            )

            saved_count += count

        connection.commit()

    finally:

        connection.close()

    elapsed = (
        datetime.now()
        - cycle_start
    ).total_seconds()

    print()
    print(
        f"이번 사이클 저장: "
        f"{saved_count}개 | "
        f"소요시간: {elapsed:.1f}초"
    )


# ==================================================
# 반복 수집
# ==================================================

def run_collector():

    print()
    print("=" * 100)
    print(
        "BusFlow B 방향 다정류장 수집기"
    )
    print("=" * 100)

    print()
    print(
        "수집 노선:",
        ", ".join(
            TARGET_ROUTES.values()
        )
    )

    print()
    print(
        f"수집 정류장 수: "
        f"{len(TARGET_STATIONS)}"
    )

    for station in TARGET_STATIONS:

        print(
            f" - "
            f"{station['name']} | "
            f"{station['id']}"
        )

    print()
    print(
        "수집 간격:",
        COLLECT_INTERVAL,
        "초"
    )

    print()
    print(
        "CTRL + C 로 종료"
    )
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
                "B 방향 다정류장 수집 종료"
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