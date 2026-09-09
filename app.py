import sqlite3
from datetime import datetime, timedelta

from flask import Flask, jsonify, request

from config import STATIONS_5001A, STATIONS_5001B


# ==================================================
# Flask
# ==================================================

app = Flask(__name__)


# ==================================================
# DB 설정
# ==================================================

HISTORICAL_DB_PATH = "data/busflow.db"
REALTIME_DB_PATH = "data/realtime.db"


# ==================================================
# 정류장 이름
# ==================================================

STATION_NAMES = {
    station["id"]: station["name"]
    for station in STATIONS_5001A + STATIONS_5001B
}


# ==================================================
# 과거 혼잡도 DB 노선 ID
# ==================================================

HISTORICAL_ROUTE_IDS = {
    "5001A": "41006433",

    # 5003A 과거 route_id를 확보하면 추가
    # "5003A": "...",
}


# ==================================================
# DB 연결
# ==================================================

def get_historical_db_connection():
    connection = sqlite3.connect(
        HISTORICAL_DB_PATH
    )
    connection.row_factory = sqlite3.Row
    return connection


def get_realtime_db_connection():
    connection = sqlite3.connect(
        REALTIME_DB_PATH
    )
    connection.row_factory = sqlite3.Row
    return connection


# ==================================================
# 날짜 / 요일
# ==================================================

def get_korean_day_name(target_datetime):
    weekday_names = [
        "월",
        "화",
        "수",
        "목",
        "금",
        "토",
        "일",
    ]

    return weekday_names[
        target_datetime.weekday()
    ]


# ==================================================
# 과거 혼잡도 조회
# ==================================================

def get_historical_congestion(
    route_name,
    station_id,
    target_datetime,
):
    route_id = HISTORICAL_ROUTE_IDS.get(
        route_name
    )

    if route_id is None:
        return None

    day_name = get_korean_day_name(
        target_datetime
    )

    time_zone = (
        f"{target_datetime.hour:02d}"
    )

    connection = (
        get_historical_db_connection()
    )

    row = connection.execute(
        """
        SELECT
            ROUND(
                AVG(congestion),
                1
            ) AS avg_congestion,

            COUNT(*) AS data_count

        FROM congestion

        WHERE route_id = ?
          AND station_id = ?
          AND dow_nm = ?
          AND time_zone = ?
        """,
        (
            route_id,
            station_id,
            day_name,
            time_zone,
        ),
    ).fetchone()

    connection.close()

    if (
        row is None
        or row["avg_congestion"] is None
    ):
        return None

    return {
        "avg_congestion":
            row["avg_congestion"],

        "data_count":
            row["data_count"],
    }


# ==================================================
# 최신 실시간 도착 정보
# ==================================================

def get_latest_realtime_arrival(
    route_name
):
    connection = (
        get_realtime_db_connection()
    )

    row = connection.execute(
        """
        SELECT
            collected_at,
            route_name,

            veh_id_1,
            predict_time_sec_1,
            remain_seat_cnt_1,

            veh_id_2,
            predict_time_sec_2,
            remain_seat_cnt_2

        FROM realtime_arrival_a

        WHERE route_name = ?

        ORDER BY collected_at DESC

        LIMIT 1
        """,
        (route_name,),
    ).fetchone()

    connection.close()

    return row


# ==================================================
# 특정 시점 replay 도착 정보
# ==================================================

def get_realtime_snapshot(
    route_name,
    target_datetime,
):
    connection = (
        get_realtime_db_connection()
    )

    row = connection.execute(
        """
        SELECT
            collected_at,
            route_name,

            veh_id_1,
            predict_time_sec_1,
            remain_seat_cnt_1,

            veh_id_2,
            predict_time_sec_2,
            remain_seat_cnt_2

        FROM realtime_arrival_a

        WHERE route_name = ?
          AND collected_at <= ?

        ORDER BY collected_at DESC

        LIMIT 1
        """,
        (
            route_name,
            target_datetime.strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
        ),
    ).fetchone()

    connection.close()

    return row


# ==================================================
# 시간대별 이동시간 조회
# ==================================================

def get_travel_time_stats(
    route_name,
    departure_datetime,
):
    """
    travel_time_stats 테이블에서

    같은 노선 +
    같은 출발 시간대

    이동시간 통계를 조회.

    추천에는 p75를 사용한다.
    """

    departure_hour = (
        departure_datetime.strftime("%H")
    )

    connection = (
        get_realtime_db_connection()
    )

    try:
        row = connection.execute(
            """
            SELECT
                sample_count,
                average_minutes,
                median_minutes,
                p75_minutes,
                min_minutes,
                max_minutes,
                updated_at

            FROM travel_time_stats

            WHERE route_name = ?
              AND departure_hour = ?
            """,
            (
                route_name,
                departure_hour,
            ),
        ).fetchone()

    except sqlite3.OperationalError:
        connection.close()
        return None

    connection.close()

    if row is None:
        return None

    return {
        "sample_count":
            row["sample_count"],

        "average_minutes":
            row["average_minutes"],

        "median_minutes":
            row["median_minutes"],

        "p75_minutes":
            row["p75_minutes"],

        "min_minutes":
            row["min_minutes"],

        "max_minutes":
            row["max_minutes"],

        "updated_at":
            row["updated_at"],
    }


# ==================================================
# 간단 추천 점수
# ==================================================

def calculate_simple_score(
    remain_seats,
    arrival_seconds,
    deadline_met=None,
):
    score = 0

    # 좌석이 많을수록 가점
    if remain_seats is not None:
        score += remain_seats * 2

    # 기다리는 시간이 길수록 감점
    if arrival_seconds is not None:
        score -= arrival_seconds / 60

    # 이동시간 데이터가 있는 경우
    # 희망 도착시간을 못 맞추면 큰 감점
    if deadline_met is False:
        score -= 100

    return round(score, 1)


# ==================================================
# 추천 후보 생성
# ==================================================

def create_recommendation_candidate(
    route_name,
    bus_number,
    row,
    target_datetime,
    desired_arrival,
    start_station_id,
):
    if bus_number == 1:
        vehicle_id = row["veh_id_1"]

        arrival_seconds = (
            row["predict_time_sec_1"]
        )

        remain_seats = (
            row["remain_seat_cnt_1"]
        )

    else:
        vehicle_id = row["veh_id_2"]

        arrival_seconds = (
            row["predict_time_sec_2"]
        )

        remain_seats = (
            row["remain_seat_cnt_2"]
        )

    if arrival_seconds is None:
        return None

    # ----------------------------------------------
    # snapshot 실제 수집 시각
    # ----------------------------------------------

    snapshot_datetime = datetime.strptime(
        row["collected_at"],
        "%Y-%m-%d %H:%M:%S",
    )

    # ----------------------------------------------
    # 기흥역 버스 도착 예상 시각
    # ----------------------------------------------

    bus_departure_time = (
        snapshot_datetime
        + timedelta(
            seconds=arrival_seconds
        )
    )

    # 사용자가 출발 가능한 시간보다
    # 먼저 도착하는 버스는 제외
    if bus_departure_time < target_datetime:
        return None

    # ----------------------------------------------
    # 이동시간 통계
    # ----------------------------------------------

    travel_stats = get_travel_time_stats(
        route_name,
        bus_departure_time,
    )

    estimated_arrival = None
    deadline_met = None
    travel_minutes = None

    if travel_stats is not None:
        travel_minutes = (
            travel_stats["p75_minutes"]
        )

        estimated_arrival = (
            bus_departure_time
            + timedelta(
                minutes=travel_minutes
            )
        )

        deadline_met = (
            estimated_arrival
            <= desired_arrival
        )

    # ----------------------------------------------
    # 과거 혼잡도
    # ----------------------------------------------

    historical = (
        get_historical_congestion(
            route_name,
            start_station_id,
            bus_departure_time,
        )
    )

    # ----------------------------------------------
    # 점수
    # ----------------------------------------------

    score = calculate_simple_score(
        remain_seats,
        arrival_seconds,
        deadline_met,
    )

    return {
        "route":
            route_name,

        "bus_number":
            bus_number,

        "vehicle_id":
            vehicle_id,

        "snapshot_time":
            row["collected_at"],

        "departure_time":
            bus_departure_time.strftime(
                "%H:%M"
            ),

        "arrival_seconds":
            arrival_seconds,

        "remain_seats":
            remain_seats,

        "travel_time_minutes":
            (
                round(
                    travel_minutes,
                    1,
                )
                if travel_minutes
                is not None
                else None
            ),

        "travel_time_method":
            (
                "p75"
                if travel_stats
                is not None
                else None
            ),

        "travel_time_sample_count":
            (
                travel_stats[
                    "sample_count"
                ]
                if travel_stats
                is not None
                else 0
            ),

        "estimated_arrival_time":
            (
                estimated_arrival.strftime(
                    "%H:%M"
                )
                if estimated_arrival
                is not None
                else None
            ),

        "deadline_met":
            deadline_met,

        "historical_congestion":
            historical,

        "score":
            score,
    }


# ==================================================
# Home
# ==================================================

@app.route("/")
def home():
    connection = (
        get_historical_db_connection()
    )

    count = connection.execute(
        """
        SELECT COUNT(*)
        FROM congestion
        """
    ).fetchone()[0]

    connection.close()

    return (
        "BusFlow API 실행 중<br>"
        f"과거 혼잡도 데이터: {count}개"
    )


# ==================================================
# 노선 목록
# ==================================================

@app.route("/api/routes")
def get_routes():
    connection = (
        get_historical_db_connection()
    )

    rows = connection.execute(
        """
        SELECT
            route_id,
            COUNT(*) AS data_count

        FROM congestion

        GROUP BY route_id

        ORDER BY route_id
        """
    ).fetchall()

    connection.close()

    routes = [
        {
            "route_id":
                row["route_id"],

            "data_count":
                row["data_count"],
        }
        for row in rows
    ]

    return jsonify(routes)


# ==================================================
# 정류장 목록
# ==================================================

@app.route(
    "/api/stations/<route_id>"
)
def get_stations(route_id):
    connection = (
        get_historical_db_connection()
    )

    rows = connection.execute(
        """
        SELECT DISTINCT
            station_id,
            station_seq

        FROM congestion

        WHERE route_id = ?

        ORDER BY station_seq
        """,
        (route_id,),
    ).fetchall()

    connection.close()

    stations = [
        {
            "station_id":
                row["station_id"],

            "station_name":
                STATION_NAMES.get(
                    row["station_id"],
                    "알 수 없는 정류장",
                ),

            "station_seq":
                row["station_seq"],
        }
        for row in rows
    ]

    return jsonify(stations)


# ==================================================
# 시간대별 혼잡도
# ==================================================

@app.route(
    "/api/congestion/"
    "<route_id>/<station_id>"
)
def get_congestion(
    route_id,
    station_id,
):
    connection = (
        get_historical_db_connection()
    )

    rows = connection.execute(
        """
        SELECT
            time_zone,

            ROUND(
                AVG(congestion),
                1
            ) AS avg_congestion,

            COUNT(*) AS data_count

        FROM congestion

        WHERE route_id = ?
          AND station_id = ?

        GROUP BY time_zone

        ORDER BY time_zone
        """,
        (
            route_id,
            station_id,
        ),
    ).fetchall()

    connection.close()

    congestion_data = [
        {
            "time_zone":
                row["time_zone"],

            "avg_congestion":
                row["avg_congestion"],

            "data_count":
                row["data_count"],
        }
        for row in rows
    ]

    return jsonify(
        congestion_data
    )


# ==================================================
# 요일 + 시간별 혼잡도
# ==================================================

@app.route(
    "/api/congestion/"
    "<route_id>/<station_id>/by-day"
)
def get_congestion_by_day(
    route_id,
    station_id,
):
    connection = (
        get_historical_db_connection()
    )

    rows = connection.execute(
        """
        SELECT
            dow_nm,
            time_zone,

            ROUND(
                AVG(congestion),
                1
            ) AS avg_congestion,

            COUNT(*) AS data_count

        FROM congestion

        WHERE route_id = ?
          AND station_id = ?

        GROUP BY
            dow_nm,
            time_zone

        ORDER BY
            dow_nm,
            time_zone
        """,
        (
            route_id,
            station_id,
        ),
    ).fetchall()

    connection.close()

    congestion_data = [
        {
            "day":
                row["dow_nm"],

            "time_zone":
                row["time_zone"],

            "avg_congestion":
                row["avg_congestion"],

            "data_count":
                row["data_count"],
        }
        for row in rows
    ]

    return jsonify(
        congestion_data
    )


# ==================================================
# 최신 실시간 조회
# ==================================================

@app.route(
    "/api/realtime/<route_name>"
)
def get_realtime(route_name):
    if route_name not in [
        "5001A",
        "5003A",
    ]:
        return jsonify(
            {
                "error":
                    "지원하지 않는 노선입니다."
            }
        ), 400

    row = get_latest_realtime_arrival(
        route_name
    )

    if row is None:
        return jsonify(
            {
                "error":
                    "실시간 데이터가 없습니다."
            }
        ), 404

    return jsonify(
        {
            "route_name":
                row["route_name"],

            "collected_at":
                row["collected_at"],

            "first_bus": {
                "vehicle_id":
                    row["veh_id_1"],

                "arrival_seconds":
                    row[
                        "predict_time_sec_1"
                    ],

                "remain_seats":
                    row[
                        "remain_seat_cnt_1"
                    ],
            },

            "second_bus": {
                "vehicle_id":
                    row["veh_id_2"],

                "arrival_seconds":
                    row[
                        "predict_time_sec_2"
                    ],

                "remain_seats":
                    row[
                        "remain_seat_cnt_2"
                    ],
            },
        }
    )


# ==================================================
# 추천 API
# ==================================================

@app.route(
    "/api/recommend",
    methods=["POST"],
)
def recommend():
    data = request.get_json(
        silent=True
    )

    if not data:
        return jsonify(
            {
                "error":
                    "JSON 데이터가 필요합니다."
            }
        ), 400

    required_fields = [
        "date",
        "start_station",
        "departure_time",
        "arrival_time",
        "destination",
    ]

    for field in required_fields:
        if field not in data:
            return jsonify(
                {
                    "error":
                        f"{field} 값이 필요합니다."
                }
            ), 400

    date_string = data["date"]

    start_station = (
        data["start_station"]
    )

    departure_time_string = (
        data["departure_time"]
    )

    arrival_time_string = (
        data["arrival_time"]
    )

    destination = (
        data["destination"]
    )

    # ----------------------------------------------
    # MVP 출발지
    # ----------------------------------------------

    if start_station != "기흥역":
        return jsonify(
            {
                "error":
                    "현재는 기흥역 출발만 "
                    "지원합니다."
            }
        ), 400

    # 과거 혼잡 DB 기준 기흥역
    start_station_id = "4111657"

    # ----------------------------------------------
    # 시간 파싱
    # ----------------------------------------------

    try:
        target_datetime = datetime.strptime(
            (
                f"{date_string} "
                f"{departure_time_string}"
            ),
            "%Y-%m-%d %H:%M",
        )

        desired_arrival = datetime.strptime(
            (
                f"{date_string} "
                f"{arrival_time_string}"
            ),
            "%Y-%m-%d %H:%M",
        )

    except ValueError:
        return jsonify(
            {
                "error":
                    "날짜는 YYYY-MM-DD, "
                    "시간은 HH:MM 형식이어야 합니다."
            }
        ), 400

    if desired_arrival <= target_datetime:
        return jsonify(
            {
                "error":
                    "도착시간은 출발시간보다 "
                    "늦어야 합니다."
            }
        ), 400

    # ----------------------------------------------
    # 후보 생성
    # ----------------------------------------------

    candidates = []

    for route_name in [
        "5001A",
        "5003A",
    ]:
        row = get_realtime_snapshot(
            route_name,
            target_datetime,
        )

        if row is None:
            continue

        for bus_number in [1, 2]:
            candidate = (
                create_recommendation_candidate(
                    route_name=
                        route_name,

                    bus_number=
                        bus_number,

                    row=
                        row,

                    target_datetime=
                        target_datetime,

                    desired_arrival=
                        desired_arrival,

                    start_station_id=
                        start_station_id,
                )
            )

            if candidate is not None:
                candidates.append(
                    candidate
                )

    if not candidates:
        return jsonify(
            {
                "error":
                    "해당 시점의 수집 데이터가 "
                    "없습니다."
            }
        ), 404

    # ----------------------------------------------
    # 정렬
    # ----------------------------------------------
    #
    # deadline_met:
    #
    # True  → 시간 내 도착
    # None  → 이동시간 데이터 없음
    # False → 시간 초과
    #
    # True를 최우선으로 두고,
    # 그 다음 아직 판단 불가능한 None,
    # 마지막이 False
    #
    # 같은 그룹에서는 점수 높은 순
    # ----------------------------------------------

    def candidate_sort_key(
        candidate
    ):
        deadline = candidate[
            "deadline_met"
        ]

        if deadline is True:
            deadline_priority = 2

        elif deadline is None:
            deadline_priority = 1

        else:
            deadline_priority = 0

        return (
            deadline_priority,
            candidate["score"],
        )

    candidates.sort(
        key=candidate_sort_key,
        reverse=True,
    )

    recommended = candidates[0]

    # ----------------------------------------------
    # 추천 이유
    # ----------------------------------------------

    reasons = []

    seats = recommended[
        "remain_seats"
    ]

    if seats is not None:
        if seats >= 20:
            reasons.append(
                "현재 잔여좌석이 "
                "비교적 여유롭습니다."
            )

        elif seats >= 5:
            reasons.append(
                "현재 탑승 가능한 "
                "좌석이 남아 있습니다."
            )

        else:
            reasons.append(
                "현재 잔여좌석이 "
                "많지 않습니다."
            )

    deadline = recommended[
        "deadline_met"
    ]

    if deadline is True:
        reasons.append(
            "실제 수집 이동시간의 "
            "75퍼센타일 기준으로도 "
            "희망 도착시간 이전 도착이 "
            "예상됩니다."
        )

    elif deadline is False:
        reasons.append(
            "현재 이동시간 추정으로는 "
            "희망 도착시간을 넘길 "
            "가능성이 있습니다."
        )

    else:
        reasons.append(
            "아직 해당 시간대의 "
            "이동시간 표본이 없어 "
            "도착시간은 추천 점수에 "
            "반영되지 않았습니다."
        )

    historical = recommended[
        "historical_congestion"
    ]

    if historical is not None:
        reasons.append(
            "과거 동일 요일·시간대 "
            f"평균 혼잡도는 "
            f"{historical['avg_congestion']}입니다."
        )

    # ----------------------------------------------
    # 결과
    # ----------------------------------------------

    return jsonify(
        {
            "request": {
                "date":
                    date_string,

                "start_station":
                    start_station,

                "departure_time":
                    departure_time_string,

                "arrival_time":
                    arrival_time_string,

                "destination":
                    destination,
            },

            "recommended":
                recommended,

            "reasons":
                reasons,

            "alternatives":
                candidates[1:],

            "generated_at":
                datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
        }
    )


# ==================================================
# 실행
# ==================================================

if __name__ == "__main__":
    app.run(
        debug=True,
        port=5001,
    )