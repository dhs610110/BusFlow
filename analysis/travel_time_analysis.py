import sqlite3
from pathlib import Path
from statistics import median


# ============================================================
# 경로 설정
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "realtime.db"

TRAVEL_TIME_TABLE = "travel_time_stats"

# ============================================================
# 정류장 설정
# ============================================================

# 기흥역은 이미 확인 완료
GIHEUNG_STATION_ID = "228000682"

# A 방향 신논현역 실시간 station_id
#
# 아직 정확한 ID를 확인하지 못했으므로 None으로 둔다.
# 찾은 뒤 아래처럼 넣으면 됨.
#
# 예:
# "5001A": "xxxxxxxxx",
# "5003A": "xxxxxxxxx",
#
SINNONHYEON_STATION_IDS = {
    "5001A": "228001278",
    "5003A": "228001278",
}

TARGET_ROUTES = [
    "5001A",
    "5003A",
]


# ============================================================
# DB 연결
# ============================================================

def get_connection():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row

    return connection


# ============================================================
# 노선 기본 정보 출력
# ============================================================

def print_route_info():
    connection = get_connection()

    print()
    print("=" * 70)
    print("노선별 실시간 위치 데이터")
    print("=" * 70)

    for route_name in TARGET_ROUTES:
        row = connection.execute(
            """
            SELECT
                COUNT(*) AS data_count,
                COUNT(DISTINCT veh_id) AS vehicle_count,
                MIN(station_seq) AS min_seq,
                MAX(station_seq) AS max_seq,
                MIN(collected_at) AS first_time,
                MAX(collected_at) AS last_time
            FROM realtime_location
            WHERE route_name = ?
            """,
            (route_name,),
        ).fetchone()

        print()
        print(f"[{route_name}]")
        print("데이터 개수 :", row["data_count"])
        print("차량 수     :", row["vehicle_count"])
        print(
            "station_seq :",
            row["min_seq"],
            "~",
            row["max_seq"],
        )
        print("최초 수집   :", row["first_time"])
        print("마지막 수집 :", row["last_time"])

    connection.close()


# ============================================================
# 기흥역 seq 확인
# ============================================================

def print_giheung_info():
    connection = get_connection()

    print()
    print("=" * 70)
    print("기흥역 정보")
    print("=" * 70)

    rows = connection.execute(
        """
        SELECT DISTINCT
            route_name,
            station_id,
            station_seq
        FROM realtime_location
        WHERE station_id = ?
          AND route_name IN ('5001A', '5003A')
        ORDER BY route_name
        """,
        (GIHEUNG_STATION_ID,),
    ).fetchall()

    for row in rows:
        print(
            row["route_name"],
            "| station_id:",
            row["station_id"],
            "| seq:",
            row["station_seq"],
        )

    connection.close()


# ============================================================
# 신논현 후보 찾기
# ============================================================

def print_destination_candidates():
    """
    신논현역 실시간 station_id를 아직 모를 때
    노선 뒤쪽의 정류장들을 출력한다.

    두 노선에서 공통으로 등장하는 ID도 표시한다.
    """

    connection = get_connection()

    print()
    print("=" * 70)
    print("서울 방향 후반부 정류장 후보")
    print("=" * 70)

    route_stations = {}

    for route_name in TARGET_ROUTES:

        max_seq_row = connection.execute(
            """
            SELECT MAX(station_seq) AS max_seq
            FROM realtime_location
            WHERE route_name = ?
            """,
            (route_name,),
        ).fetchone()

        max_seq = max_seq_row["max_seq"]

        if max_seq is None:
            continue

        # 마지막 15개 seq 정도 확인
        start_seq = max_seq - 15

        rows = connection.execute(
            """
            SELECT DISTINCT
                station_seq,
                station_id
            FROM realtime_location
            WHERE route_name = ?
              AND station_seq >= ?
            ORDER BY station_seq
            """,
            (
                route_name,
                start_seq,
            ),
        ).fetchall()

        route_stations[route_name] = {
            row["station_id"]: row["station_seq"]
            for row in rows
        }

        print()
        print(f"[{route_name}]")

        for row in rows:
            print(
                f'{row["station_seq"]:>3}',
                "|",
                row["station_id"],
            )

    # 두 노선 공통 station_id 출력
    if (
        "5001A" in route_stations
        and "5003A" in route_stations
    ):
        common_ids = (
            set(route_stations["5001A"].keys())
            & set(route_stations["5003A"].keys())
        )

        print()
        print("=" * 70)
        print("5001A / 5003A 공통 후반부 정류장")
        print("=" * 70)

        for station_id in common_ids:
            print(
                station_id,
                "| 5001A seq:",
                route_stations["5001A"][station_id],
                "| 5003A seq:",
                route_stations["5003A"][station_id],
            )

    connection.close()


# ============================================================
# 차량의 특정 정류장 통과시간 찾기
# ============================================================

def get_vehicle_station_time(
    connection,
    route_name,
    veh_id,
    station_id,
    mode,
):
    """
    같은 차량이 특정 정류장에 여러 번 기록될 수 있음.

    기흥역:
        MAX(collected_at)
        → 정류장을 떠나기 직전 기록에 가깝게 사용

    신논현역:
        MIN(collected_at)
        → 정류장에 처음 도착한 기록에 가깝게 사용
    """

    if mode == "last":
        sql_function = "MAX"

    elif mode == "first":
        sql_function = "MIN"

    else:
        raise ValueError(
            "mode는 first 또는 last여야 합니다."
        )

    query = f"""
        SELECT
            {sql_function}(collected_at) AS station_time
        FROM realtime_location
        WHERE route_name = ?
          AND veh_id = ?
          AND station_id = ?
    """

    row = connection.execute(
        query,
        (
            route_name,
            veh_id,
            station_id,
        ),
    ).fetchone()

    if row is None:
        return None

    return row["station_time"]


# ============================================================
# 차량별 실제 이동시간 계산
# ============================================================

def calculate_vehicle_travel_times(
    route_name,
    destination_station_id,
):
    connection = get_connection()

    # 기흥역에 실제로 관측된 차량 목록
    vehicles = connection.execute(
        """
        SELECT DISTINCT
            veh_id
        FROM realtime_location
        WHERE route_name = ?
          AND station_id = ?
          AND veh_id IS NOT NULL
        """,
        (
            route_name,
            GIHEUNG_STATION_ID,
        ),
    ).fetchall()

    results = []

    for vehicle in vehicles:

        veh_id = vehicle["veh_id"]

        # 기흥역 마지막 관측시각
        giheung_time = get_vehicle_station_time(
            connection,
            route_name,
            veh_id,
            GIHEUNG_STATION_ID,
            "last",
        )

        # 신논현 첫 관측시각
        sinnonghyeon_time = get_vehicle_station_time(
            connection,
            route_name,
            veh_id,
            destination_station_id,
            "first",
        )

        # 둘 중 하나라도 없으면 계산 불가
        if (
            giheung_time is None
            or sinnonghyeon_time is None
        ):
            continue

        row = connection.execute(
            """
            SELECT
                (
                    julianday(?)
                    - julianday(?)
                ) * 24 * 60
                AS travel_minutes
            """,
            (
                sinnonghyeon_time,
                giheung_time,
            ),
        ).fetchone()

        travel_minutes = row["travel_minutes"]

        if travel_minutes is None:
            continue

        # 이상치 제거
        #
        # 음수 → 잘못 매칭
        # 2시간 이상 → 다른 운행 회차 등이 섞였을 가능성
        if (
            travel_minutes <= 0
            or travel_minutes > 120
        ):
            continue

        departure_date = giheung_time[:10]
        departure_hour = giheung_time[11:13]

        results.append({
            "route_name": route_name,
            "veh_id": veh_id,
            "date": departure_date,
            "departure_hour": departure_hour,
            "giheung_time": giheung_time,
            "sinnonghyeon_time": sinnonghyeon_time,
            "travel_minutes": round(
                travel_minutes,
                1,
            ),
        })

    connection.close()

    results.sort(
        key=lambda row: row["giheung_time"]
    )

    return results


# ============================================================
# 차량별 결과 출력
# ============================================================

def print_vehicle_results(results):
    if not results:
        print("계산 가능한 차량이 없습니다.")
        return

    print()
    print("=" * 100)
    print("차량별 기흥역 → 신논현역 실제 이동시간")
    print("=" * 100)

    print(
        f'{"노선":<8}'
        f'{"차량":<15}'
        f'{"날짜":<13}'
        f'{"기흥":<22}'
        f'{"신논현":<22}'
        f'{"소요시간":>10}'
    )

    print("-" * 100)

    for row in results:
        print(
            f'{row["route_name"]:<8}'
            f'{row["veh_id"]:<15}'
            f'{row["date"]:<13}'
            f'{row["giheung_time"]:<22}'
            f'{row["sinnonghyeon_time"]:<22}'
            f'{row["travel_minutes"]:>8.1f}분'
        )


# ============================================================
# 시간대별 통계
# ============================================================

def calculate_hourly_statistics(results):
    grouped = {}

    for row in results:

        key = (
            row["route_name"],
            row["departure_hour"],
        )

        if key not in grouped:
            grouped[key] = []

        grouped[key].append(
            row["travel_minutes"]
        )

    statistics = []

    for key, values in grouped.items():

        route_name, hour = key

        values_sorted = sorted(values)

        average = sum(values) / len(values)

        median_value = median(values)

        # 75 percentile
        index_75 = int(
            (len(values_sorted) - 1) * 0.75
        )

        percentile_75 = values_sorted[index_75]

        statistics.append({
            "route_name": route_name,
            "hour": hour,
            "count": len(values),
            "average": round(
                average,
                1,
            ),
            "median": round(
                median_value,
                1,
            ),
            "p75": round(
                percentile_75,
                1,
            ),
            "minimum": round(
                min(values),
                1,
            ),
            "maximum": round(
                max(values),
                1,
            ),
        })

    statistics.sort(
        key=lambda row: (
            row["route_name"],
            row["hour"],
        )
    )

    return statistics


# ============================================================
# 시간대별 통계 출력
# ============================================================

def print_hourly_statistics(statistics):
    print()
    print("=" * 80)
    print("시간대별 이동시간 통계")
    print("=" * 80)

    if not statistics:
        print("통계 데이터가 없습니다.")
        return

    print(
        f'{"노선":<8}'
        f'{"시간":<8}'
        f'{"차량수":>8}'
        f'{"평균":>10}'
        f'{"중앙값":>10}'
        f'{"75%":>10}'
        f'{"최소":>10}'
        f'{"최대":>10}'
    )

    print("-" * 80)

    for row in statistics:

        print(
            f'{row["route_name"]:<8}'
            f'{row["hour"] + "시":<8}'
            f'{row["count"]:>8}'
            f'{row["average"]:>9.1f}분'
            f'{row["median"]:>9.1f}분'
            f'{row["p75"]:>9.1f}분'
            f'{row["minimum"]:>9.1f}분'
            f'{row["maximum"]:>9.1f}분'
        )

def create_travel_time_table():
    connection = get_connection()

    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TRAVEL_TIME_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            route_name TEXT NOT NULL,
            departure_hour TEXT NOT NULL,

            sample_count INTEGER NOT NULL,

            average_minutes REAL NOT NULL,
            median_minutes REAL NOT NULL,
            p75_minutes REAL NOT NULL,

            min_minutes REAL NOT NULL,
            max_minutes REAL NOT NULL,

            updated_at TEXT NOT NULL,

            UNIQUE(route_name, departure_hour)
        )
        """
    )

    connection.commit()
    connection.close()


def save_hourly_statistics(statistics):
    if not statistics:
        print()
        print("저장할 이동시간 통계가 없습니다.")
        return

    connection = get_connection()

    for row in statistics:
        connection.execute(
            f"""
            INSERT INTO {TRAVEL_TIME_TABLE} (
                route_name,
                departure_hour,
                sample_count,
                average_minutes,
                median_minutes,
                p75_minutes,
                min_minutes,
                max_minutes,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))

            ON CONFLICT(route_name, departure_hour)
            DO UPDATE SET
                sample_count = excluded.sample_count,
                average_minutes = excluded.average_minutes,
                median_minutes = excluded.median_minutes,
                p75_minutes = excluded.p75_minutes,
                min_minutes = excluded.min_minutes,
                max_minutes = excluded.max_minutes,
                updated_at = excluded.updated_at
            """,
            (
                row["route_name"],
                row["hour"],
                row["count"],
                row["average"],
                row["median"],
                row["p75"],
                row["minimum"],
                row["maximum"],
            ),
        )

    connection.commit()
    connection.close()

    print()
    print(
        f"{len(statistics)}개 시간대 통계를 "
        f"{TRAVEL_TIME_TABLE} 테이블에 저장했습니다."
    )
    
# ============================================================
# 메인
# ============================================================

def main():
    print()
    print("BusFlow 이동시간 분석")
    print("DB:", DB_PATH)

    #이동시간 통계 테이블 항상 생성
    create_travel_time_table()

    # DB 기본 상태 확인
    print_route_info()
    print_giheung_info()

    # 신논현 ID가 아직 하나라도 없으면
    # 후반부 후보 정류장 출력 후 종료
    missing_routes = [
        route_name
        for route_name in TARGET_ROUTES
        if SINNONHYEON_STATION_IDS[
            route_name
        ] is None
    ]

    if missing_routes:
        print()
        print(
            "아직 신논현역 실시간 station_id가 "
            "설정되지 않았습니다."
        )

        print(
            "미설정 노선:",
            ", ".join(missing_routes),
        )

        print_destination_candidates()

        print()
        print("=" * 70)
        print("다음 단계")
        print("=" * 70)

        print(
            "A방향 신논현역 station_id를 확인한 뒤 "
            "SINNONHYEON_STATION_IDS에 입력하세요."
        )

        return

    # --------------------------------------------------------
    # 실제 이동시간 계산
    # --------------------------------------------------------

    all_results = []

    for route_name in TARGET_ROUTES:

        destination_station_id = (
            SINNONHYEON_STATION_IDS[
                route_name
            ]
        )

        route_results = (
            calculate_vehicle_travel_times(
                route_name,
                destination_station_id,
            )
        )

        all_results.extend(route_results)

    # 차량별 출력
    print_vehicle_results(all_results)

    # 시간대 통계
    statistics = calculate_hourly_statistics(
    all_results
)

    print_hourly_statistics(statistics)

    save_hourly_statistics(statistics)


if __name__ == "__main__":
    main()