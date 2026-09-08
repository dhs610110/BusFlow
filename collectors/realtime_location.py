import os
import sqlite3
import time
from datetime import datetime

import requests
from dotenv import load_dotenv


# ==================================================
# 기본 설정
# ==================================================

load_dotenv()

API_KEY = os.getenv("DATA_API_KEY")

URL = (
    "https://apis.data.go.kr/6410000/"
    "buslocationservice/v2/getBusLocationListv2"
)

DB_PATH = "data/realtime.db"

# 실시간 BMS 기준 routeId
ROUTES = {
    "5001A": "228000429",
    "5003A": "228000431",

    # B 노선은 저녁에 정상 응답 확인 후 추가
    # "5001B": "228000176",
    # "5003B": "228000182",
}

# 60초마다 수집
COLLECT_INTERVAL = 60


# ==================================================
# DB 생성
# ==================================================

def create_database():

    connection = sqlite3.connect(DB_PATH)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS realtime_location (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            collected_at TEXT NOT NULL,
            query_time TEXT,

            route_name TEXT NOT NULL,
            route_id TEXT NOT NULL,

            veh_id TEXT NOT NULL,
            plate_no TEXT,

            station_id TEXT,
            station_seq INTEGER,

            remain_seat_cnt INTEGER,
            crowded INTEGER,
            state_cd INTEGER
        )
    """)

    # 나중에 차량 추적할 때 검색 속도를 높이기 위한 인덱스
    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_realtime_vehicle
        ON realtime_location (
            route_id,
            veh_id,
            collected_at
        )
    """)

    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_realtime_station
        ON realtime_location (
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

def get_bus_locations(route_name, route_id):

    params = {
        "serviceKey": API_KEY,
        "routeId": route_id,
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
        result_message = header.get("resultMessage")
        query_time = header.get("queryTime")

        # 정상 응답이 아닌 경우
        if result_code != 0:

            print(
                f"{route_name} | "
                f"API 응답: {result_message}"
            )

            return query_time, []

        body = data["response"].get(
            "msgBody",
            {}
        )

        buses = body.get(
            "busLocationList",
            []
        )

        return query_time, buses

    except requests.exceptions.Timeout:

        print(
            f"{route_name} | API TIMEOUT"
        )

    except requests.exceptions.RequestException as e:

        print(
            f"{route_name} | API 요청 오류:",
            e
        )

    except (KeyError, ValueError) as e:

        print(
            f"{route_name} | 응답 파싱 오류:",
            e
        )

    return None, []


# ==================================================
# 값 정리
# ==================================================

def clean_value(value):

    if value == "":
        return None

    return value


# ==================================================
# DB 저장
# ==================================================

def save_bus_locations(
    route_name,
    route_id,
    query_time,
    buses
):

    if not buses:
        return 0

    collected_at = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    rows = []

    for bus in buses:

        veh_id = clean_value(
            bus.get("vehId")
        )

        # vehId 없는 데이터는 저장하지 않음
        if veh_id is None:
            continue

        row = (
            collected_at,
            query_time,

            route_name,
            route_id,

            veh_id,
            clean_value(
                bus.get("plateNo")
            ),

            clean_value(
                bus.get("stationId")
            ),
            clean_value(
                bus.get("stationSeq")
            ),

            clean_value(
                bus.get("remainSeatCnt")
            ),
            clean_value(
                bus.get("crowded")
            ),
            clean_value(
                bus.get("stateCd")
            ),
        )

        rows.append(row)

    if not rows:
        return 0

    connection = sqlite3.connect(
        DB_PATH
    )

    connection.executemany("""
        INSERT INTO realtime_location (
            collected_at,
            query_time,

            route_name,
            route_id,

            veh_id,
            plate_no,

            station_id,
            station_seq,

            remain_seat_cnt,
            crowded,
            state_cd
        )

        VALUES (
            ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?
        )
    """, rows)

    connection.commit()
    connection.close()

    return len(rows)


# ==================================================
# 한 번 수집
# ==================================================

def collect_once():

    collected_at = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    print()
    print("=" * 70)
    print("수집 시간:", collected_at)
    print("=" * 70)

    total_saved = 0

    for route_name, route_id in ROUTES.items():

        query_time, buses = get_bus_locations(
            route_name,
            route_id
        )

        if not buses:

            print(
                f"{route_name} | "
                f"운행 차량 없음"
            )

            continue

        saved_count = save_bus_locations(
            route_name,
            route_id,
            query_time,
            buses
        )

        total_saved += saved_count

        print(
            f"{route_name} | "
            f"운행 {len(buses)}대 | "
            f"저장 {saved_count}개"
        )

        # 확인용으로 현재 차량 상태 출력
        for bus in buses:

            print(
                f"  "
                f"veh={bus.get('vehId')} | "
                f"seq={bus.get('stationSeq')} | "
                f"station={bus.get('stationId')} | "
                f"seat={bus.get('remainSeatCnt')}"
            )

    print(
        f"이번 수집 총 {total_saved}개 저장"
    )


# ==================================================
# 반복 수집
# ==================================================

def run_collector():

    print()
    print("BusFlow 실시간 위치 수집 시작")
    print(
        "수집 노선:",
        ", ".join(ROUTES.keys())
    )
    print(
        "수집 간격:",
        COLLECT_INTERVAL,
        "초"
    )
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
            print("실시간 위치 수집 종료")
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