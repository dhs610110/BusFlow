import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from flask import (
    Flask,
    jsonify,
    request,
    send_from_directory,
)

from live_bus_service import get_live_arrival
from services.highway_predictor import predict_highway_time


# ==================================================
# Flask
# ==================================================

app = Flask(__name__)


# ==================================================
# 프로젝트 / DB 경로
# ==================================================

PROJECT_ROOT = Path(__file__).resolve().parent

HISTORICAL_DB_PATHS = {
    "5001A": PROJECT_ROOT / "data" / "busflow.db",
    "5001B": PROJECT_ROOT / "data" / "busflow.db",
    "5003A": PROJECT_ROOT / "data" / "busflow_5003.db",
    "5003B": PROJECT_ROOT / "data" / "busflow_5003.db",
}

REALTIME_DB_PATH = (
    PROJECT_ROOT / "data" / "realtime.db"
)


# ==================================================
# 과거 혼잡도 노선 ID
# ==================================================

HISTORICAL_ROUTE_IDS = {
    "5001A": "41006433",
    "5001B": "41006248",
    "5003A": "41006409",
    "5003B": "41006064",
}


# ==================================================
# 과거 혼잡도 정류장 ID
# ==================================================

HISTORICAL_STATION_IDS = {
    "기흥역": "4111657",

    # 서울 B 방향
    "양재역": "4151629",
    "강남역": "4151638",
    "신논현역": "4105915",

    # A 방향 대안
    "강남대역.강남대입구": "4111660",
}


# ==================================================
# 앞 정류장 이동 시간
#
# MVP 임시값.
# 실제 도보/지하철 이동시간 연동 시 교체.
# ==================================================

MOVE_TIME_MINUTES = {
    ("신논현역", "강남역"): 5,
    ("신논현역", "양재역"): 12,

    ("기흥역", "강남대역.강남대입구"): 7,
}


# ==================================================
# 최근 realtime_location 분석 기반
# 기대 좌석 이득
#
# B 방향:
# 강남 → 신논현 실제 좌석 감소 평균
# 양재 → 신논현은 같은 차량의 누적 감소 평균
#
# 표본이 적으므로 MVP 휴리스틱으로만 사용.
# ==================================================

EXPECTED_SEAT_GAIN_BY_HOUR = {

    # ------------------------------
    # 5001B 강남 → 신논현
    # ------------------------------
    ("5001B", "강남역", "신논현역"): {
        17: 6.0,
        18: 6.4,
        19: 15.2,
        20: 21.4,
        21: 20.6,
        22: 21.4,
        23: 9.6,
    },

    # ------------------------------
    # 5003B 강남 → 신논현
    # ------------------------------
    ("5003B", "강남역", "신논현역"): {
        17: 25.8,
        18: 21.5,
        19: 19.0,
        20: 12.9,
        21: 25.0,
        22: 23.2,
        23: 9.2,
    },

    # ------------------------------
    # 5001B 양재 → 신논현
    # ------------------------------
    ("5001B", "양재역", "신논현역"): {
        17: 23.8,
        18: 32.0,
        19: 32.8,
        20: 30.9,
        21: 31.4,
        22: 25.0,
        23: 11.0,
    },

    # ------------------------------
    # 5003B 양재 → 신논현
    # ------------------------------
    ("5003B", "양재역", "신논현역"): {
        17: 45.5,
        18: 41.9,
        19: 29.5,
        20: 22.3,
        21: 32.2,
        22: 31.0,
        23: 13.0,
    },
}


# ==================================================
# A 방향 MVP 대안
# ==================================================

A_UPSTREAM_ALTERNATIVES = {
    "5001A": {
        "기흥역": {
            "station": "강남대역.강남대입구",
            "expected_seat_gain": 8,
        }
    },
    "5003A": {
        "기흥역": {
            "station": "강남대역.강남대입구",
            "expected_seat_gain": 8,
        }
    },
}


# ==================================================
# DB 연결
# ==================================================

def get_historical_db_connection(
    route_name
):
    db_path = HISTORICAL_DB_PATHS.get(
        route_name
    )

    if db_path is None:
        raise ValueError(
            f"지원하지 않는 노선: {route_name}"
        )

    connection = sqlite3.connect(
        db_path
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

def get_korean_day_name(
    target_datetime
):
    weekday_names = [
        "월요일",
        "화요일",
        "수요일",
        "목요일",
        "금요일",
        "토요일",
        "일요일",
    ]

    return weekday_names[
        target_datetime.weekday()
    ]


# ==================================================
# 과거 혼잡도
# ==================================================

def get_historical_congestion(
    route_name,
    station_name,
    target_datetime,
):
    route_id = (
        HISTORICAL_ROUTE_IDS.get(
            route_name
        )
    )

    station_id = (
        HISTORICAL_STATION_IDS.get(
            station_name
        )
    )

    if (
        route_id is None
        or station_id is None
    ):
        return None

    day_name = get_korean_day_name(
        target_datetime
    )

    time_zone = (
        f"{target_datetime.hour:02d}"
    )

    connection = (
        get_historical_db_connection(
            route_name
        )
    )

    try:
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

    finally:
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
# 실시간 테이블
# ==================================================

def get_realtime_table_name(
    route_name
):
    if route_name.endswith("A"):
        return "realtime_arrival_a"

    if route_name.endswith("B"):
        return "realtime_arrival_b"

    return None


# ==================================================
# 특정 시점 replay 실시간 데이터
# ==================================================

def get_realtime_snapshot(
    route_name,
    station_name,
    target_datetime,
):
    table_name = (
        get_realtime_table_name(
            route_name
        )
    )

    if table_name is None:
        return None

    connection = (
        get_realtime_db_connection()
    )

    query = f"""
        SELECT
            collected_at,
            route_name,
            station_name,

            veh_id_1,
            predict_time_sec_1,
            remain_seat_cnt_1,

            veh_id_2,
            predict_time_sec_2,
            remain_seat_cnt_2

        FROM {table_name}

        WHERE route_name = ?
          AND station_name = ?
          AND collected_at <= ?

        ORDER BY collected_at DESC

        LIMIT 1
    """

    try:
        row = connection.execute(
            query,
            (
                route_name,
                station_name,
                target_datetime.strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
            ),
        ).fetchone()

    finally:
        connection.close()

    return row


# ==================================================
# 이동시간 통계
# ==================================================

def get_travel_time_stats(
    route_name,
    departure_datetime,
):
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
        return None

    finally:
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
# 후보 점수
# ==================================================

def calculate_simple_score(
    remain_seats,
    arrival_seconds,
    deadline_met=None,
):
    score = 0

    if remain_seats is not None:

        if remain_seats >= 20:
            score += 30

        elif remain_seats >= 10:
            score += 25

        elif remain_seats >= 5:
            score += 12

        elif remain_seats > 0:
            score += 3

        else:
            score -= 20

    if arrival_seconds is not None:
        wait_minutes = (
            arrival_seconds / 60
        )

        score -= (
            wait_minutes * 2
        )

    if deadline_met is False:
        score -= 100

    return round(
        score,
        1
    )


# ==================================================
# 앞 정류장 점수
# ==================================================

def calc_station_alternative_score(
    expected_seat_gain,
    congestion_improvement,
    first_bus_seats,
    second_bus_seats,
    second_bus_gap_min,
    move_time_min,
):
    score = 0

    if expected_seat_gain >= 15:
        score += 35

    elif expected_seat_gain >= 10:
        score += 25

    elif expected_seat_gain >= 5:
        score += 15

    elif expected_seat_gain > 0:
        score += 5

    if congestion_improvement >= 20:
        score += 25

    elif congestion_improvement >= 10:
        score += 15

    elif congestion_improvement >= 5:
        score += 8

    if first_bus_seats is not None:

        if first_bus_seats <= 5:
            score += 15

        elif first_bus_seats <= 10:
            score += 7

    if second_bus_seats is not None:

        if second_bus_seats <= 5:
            score += 15

        elif second_bus_seats <= 10:
            score += 7

    if (
        first_bus_seats is not None
        and second_bus_seats is not None
        and second_bus_gap_min is not None
        and first_bus_seats <= 5
        and second_bus_seats >= 10
        and second_bus_gap_min <= 7
    ):
        score -= 30

    if move_time_min is not None:
        score -= (
            move_time_min * 3
        )

    return round(
        score,
        1
    )


def classify_alternative(
    score
):
    if score >= 45:
        return "strong"

    if score >= 25:
        return "recommend"

    if score >= 10:
        return "consider"

    return "stay"


# ==================================================
# 배차간격
# ==================================================

def get_second_bus_gap_min(
    row
):
    if row is None:
        return None

    first = row[
        "predict_time_sec_1"
    ]

    second = row[
        "predict_time_sec_2"
    ]

    if (
        first is None
        or second is None
    ):
        return None

    gap = (
        second - first
    ) / 60

    if gap < 0:
        return None

    return gap


# ==================================================
# B 방향 앞 정류장 후보
# ==================================================

def get_b_upstream_options(
    route_name,
    current_station,
    target_datetime,
):
    if current_station != "신논현역":
        return []

    hour = target_datetime.hour

    options = []

    for upstream_station in [
        "강남역",
        "양재역",
    ]:
        gain_map = (
            EXPECTED_SEAT_GAIN_BY_HOUR.get(
                (
                    route_name,
                    upstream_station,
                    current_station,
                ),
                {},
            )
        )

        expected_gain = (
            gain_map.get(
                hour,
                0,
            )
        )

        move_time = (
            MOVE_TIME_MINUTES.get(
                (
                    current_station,
                    upstream_station,
                ),
                0,
            )
        )

        options.append(
            {
                "station":
                    upstream_station,

                "expected_seat_gain":
                    expected_gain,

                "move_time_min":
                    move_time,
            }
        )

    return options


# ==================================================
# A 방향 탑승 전략
# ==================================================

def build_a_boarding_strategy(
    route_name,
    current_station,
    row,
    target_datetime,
):
    if row is None:
        return None

    first_seats = (
        row["remain_seat_cnt_1"]
    )

    second_seats = (
        row["remain_seat_cnt_2"]
    )

    first_eta = (
        row["predict_time_sec_1"]
    )

    second_eta = (
        row["predict_time_sec_2"]
    )

    first_eta_min = (
        first_eta / 60
        if first_eta is not None
        else None
    )

    second_eta_min = (
        second_eta / 60
        if second_eta is not None
        else None
    )

    gap = get_second_bus_gap_min(
        row
    )

    # 첫차 충분
    if (
        first_seats is not None
        and first_seats >= 10
    ):
        return {
            "route":
                route_name,

            "strategy":
                "take_first_bus",

            "grade":
                "안전",

            "station":
                current_station,

            "title":
                f"{route_name} 첫 차량 추천",

            "message":
                (
                    f"첫 차량이 약 {first_eta_min:.1f}분 후 도착하고 "
                    f"잔여좌석은 {first_seats}석입니다."
                ),
        }

    # 뒤차 회복
    if (
        first_seats is not None
        and second_seats is not None
        and gap is not None
        and first_seats <= 5
        and second_seats >= 10
        and gap <= 7
    ):
        return {
            "route":
                route_name,

            "strategy":
                "wait_second_bus",

            "grade":
                "안전",

            "station":
                current_station,

            "title":
                f"{route_name} 다음 차량 추천",

            "message":
                (
                    f"첫 차량은 {first_seats}석이지만 "
                    f"약 {gap:.1f}분 뒤 차량은 "
                    f"{second_seats}석입니다."
                ),
        }

    # A방향 대안
    config = (
        A_UPSTREAM_ALTERNATIVES
        .get(
            route_name,
            {}
        )
        .get(
            current_station
        )
    )

    if config:
        upstream = (
            config["station"]
        )

        move_time = (
            MOVE_TIME_MINUTES.get(
                (
                    current_station,
                    upstream,
                ),
                7,
            )
        )

        current_hist = (
            get_historical_congestion(
                route_name,
                current_station,
                target_datetime,
            )
        )

        upstream_hist = (
            get_historical_congestion(
                route_name,
                upstream,
                target_datetime,
            )
        )

        current_congestion = (
            current_hist["avg_congestion"]
            if current_hist
            else None
        )

        upstream_congestion = (
            upstream_hist["avg_congestion"]
            if upstream_hist
            else None
        )

        congestion_improvement = 0

        if (
            current_congestion is not None
            and upstream_congestion is not None
        ):
            congestion_improvement = (
                current_congestion
                -
                upstream_congestion
            )

        score = (
            calc_station_alternative_score(
                expected_seat_gain=
                    config[
                        "expected_seat_gain"
                    ],

                congestion_improvement=
                    congestion_improvement,

                first_bus_seats=
                    first_seats,

                second_bus_seats=
                    second_seats,

                second_bus_gap_min=
                    gap,

                move_time_min=
                    move_time,
            )
        )

        if score >= 25:
            return {
                "route":
                    route_name,

                "strategy":
                    "consider_upstream",

                "grade":
                    "보통",

                "station":
                    upstream,

                "alternative_score":
                    score,

                "title":
                    f"{upstream} 선탑승 고려",

                "message":
                    (
                        f"현재 좌석 상황이 불안정해 "
                        f"{upstream} 선탑승을 고려할 수 있습니다."
                    ),
            }

    return {
        "route":
            route_name,

        "strategy":
            "high_risk",

        "grade":
            "주의",

        "station":
            current_station,

        "title":
            "좌석 상황 주의",

        "message":
            "첫 차량과 다음 차량 좌석 상황을 함께 확인하세요.",
    }


# ==================================================
# B 방향 탑승 전략
# ==================================================

def build_b_boarding_strategy(
    route_name,
    current_station,
    row,
    target_datetime,
):
    if row is None:
        return None

    first_seats = row["remain_seat_cnt_1"]
    second_seats = row["remain_seat_cnt_2"]

    if first_seats is not None and first_seats < 0:
        first_seats = None

    if second_seats is not None and second_seats < 0:
        second_seats = None

    first_eta_sec = row["predict_time_sec_1"]
    second_eta_sec = row["predict_time_sec_2"]

    first_eta_min = (
        first_eta_sec / 60
        if first_eta_sec is not None
        else None
    )

    gap = None

    if (
        first_eta_sec is not None
        and second_eta_sec is not None
    ):
        raw_gap = (
            second_eta_sec - first_eta_sec
        ) / 60

        if raw_gap > 0.5:
            gap = raw_gap

    if (
        first_seats is not None
        and first_seats >= 10
    ):
        return {
            "route": route_name,
            "strategy": "take_first_bus",
            "grade": "안전",
            "station": current_station,
            "title": f"{route_name} 첫 차량 추천",
            "message": (
                f"첫 차량은 약 {first_eta_min:.1f}분 후 도착하며 "
                f"잔여좌석은 {first_seats}석입니다. "
                f"현재 정류장에서 바로 탑승하는 것이 좋습니다."
            ),
            "first_bus_seats": first_seats,
            "second_bus_seats": second_seats,
            "second_bus_gap_min": gap,
        }

    if (
        first_seats is not None
        and first_seats <= 5
        and second_seats is not None
        and second_seats >= 10
        and gap is not None
        and gap <= 7
    ):
        return {
            "route": route_name,
            "strategy": "wait_second_bus",
            "grade": "안전",
            "station": current_station,
            "title": f"{route_name} 다음 차량 추천",
            "message": (
                f"첫 차량은 {first_seats}석이지만 "
                f"약 {gap:.1f}분 뒤 차량은 {second_seats}석이 남아 있습니다. "
                f"현재 정류장에서 다음 차량을 기다리는 편이 좋습니다."
            ),
            "first_bus_seats": first_seats,
            "second_bus_seats": second_seats,
            "second_bus_gap_min": gap,
        }

    current_hist = get_historical_congestion(
        route_name,
        current_station,
        target_datetime,
    )

    current_congestion = (
        current_hist["avg_congestion"]
        if current_hist
        else None
    )

    scored_options = []

    for option in get_b_upstream_options(
        route_name,
        current_station,
        target_datetime,
    ):
        upstream_station = option["station"]

        upstream_hist = get_historical_congestion(
            route_name,
            upstream_station,
            target_datetime,
        )

        upstream_congestion = (
            upstream_hist["avg_congestion"]
            if upstream_hist
            else None
        )

        congestion_improvement = 0

        if (
            current_congestion is not None
            and upstream_congestion is not None
        ):
            congestion_improvement = (
                current_congestion
                - upstream_congestion
            )

        score = calc_station_alternative_score(
            expected_seat_gain=option["expected_seat_gain"],
            congestion_improvement=congestion_improvement,
            first_bus_seats=first_seats,
            second_bus_seats=second_seats,
            second_bus_gap_min=gap,
            move_time_min=option["move_time_min"],
        )

        scored_options.append(
            {
                **option,
                "score": score,
                "congestion_improvement": round(
                    congestion_improvement,
                    1,
                ),
            }
        )

    scored_options.sort(
        key=lambda item: item["score"],
        reverse=True,
    )

    best = (
        scored_options[0]
        if scored_options
        else None
    )

    if best is not None:
        alternative_class = classify_alternative(
            best["score"]
        )

        if alternative_class in [
            "strong",
            "recommend",
        ]:
            return {
                "route": route_name,
                "strategy": "move_upstream",
                "grade": (
                    "매우 안전"
                    if alternative_class == "strong"
                    else "보통"
                ),
                "station": best["station"],
                "title": f"{best['station']} 선탑승 추천",
                "message": (
                    f"현재 {current_station}의 좌석 상황이 불안정합니다. "
                    f"최근 데이터에서 {best['station']}부터 "
                    f"{current_station}까지 평균 약 "
                    f"{best['expected_seat_gain']:.1f}석이 감소했습니다. "
                    f"추가 이동시간은 약 {best['move_time_min']}분으로 가정했습니다."
                ),
                "alternative_score": best["score"],
                "expected_seat_gain": best["expected_seat_gain"],
                "move_time_min": best["move_time_min"],
                "second_bus_gap_min": gap,
                "alternative_options": scored_options,
            }

    if (
        second_seats is not None
        and (
            first_seats is None
            or second_seats > first_seats
        )
    ):
        return {
            "route": route_name,
            "strategy": "wait_second_bus",
            "grade": "주의",
            "station": current_station,
            "title": "다음 차량 확인 추천",
            "message": (
                "현재 첫 차량보다 다음 차량의 좌석 상황이 더 좋습니다. "
                "다만 정확한 배차간격이 불명확할 수 있으므로 "
                "도착정보를 한 번 더 확인하는 편이 좋습니다."
            ),
            "first_bus_seats": first_seats,
            "second_bus_seats": second_seats,
            "second_bus_gap_min": gap,
            "alternative_options": scored_options,
        }

    return {
        "route": route_name,
        "strategy": "high_risk",
        "grade": "위험",
        "station": current_station,
        "title": "탑승 위험",
        "message": (
            "현재 차량과 다음 차량 모두 좌석 확보가 불안정합니다. "
            "더 이른 출발 또는 앞 정류장 선탑승을 고려하세요."
        ),
        "first_bus_seats": first_seats,
        "second_bus_seats": second_seats,
        "second_bus_gap_min": gap,
        "alternative_options": scored_options,
    }


# ==================================================
# 추천 후보 생성
# ==================================================

def create_candidate(
    route_name,
    bus_number,
    row,
    target_datetime,
    desired_arrival,
    start_station,
):
    if bus_number == 1:
        vehicle_id = (
            row["veh_id_1"]
        )

        arrival_seconds = (
            row["predict_time_sec_1"]
        )

        remain_seats = (
            row["remain_seat_cnt_1"]
        )

    else:
        vehicle_id = (
            row["veh_id_2"]
        )

        arrival_seconds = (
            row["predict_time_sec_2"]
        )

        remain_seats = (
            row["remain_seat_cnt_2"]
        )

    if (
        remain_seats is not None
        and remain_seats < 0
    ):
        remain_seats = None

    if arrival_seconds is None:
        return None

    snapshot_datetime = datetime.strptime(
        row["collected_at"],
        "%Y-%m-%d %H:%M:%S",
    )

    bus_departure_time = (
        snapshot_datetime
        +
        timedelta(
            seconds=arrival_seconds
        )
    )

    if (
        bus_departure_time
        <
        target_datetime
    ):
        return None

    travel_stats = (
        get_travel_time_stats(
            route_name,
            bus_departure_time,
        )
    )

    travel_minutes = None
    estimated_arrival = None
    deadline_met = None

    if travel_stats is not None:
        travel_minutes = (
            travel_stats[
                "p75_minutes"
            ]
        )

        if travel_minutes is not None:
            estimated_arrival = (
                bus_departure_time
                +
                timedelta(
                    minutes=
                        travel_minutes
                )
            )

            deadline_met = (
                estimated_arrival
                <=
                desired_arrival
            )

    historical = (
        get_historical_congestion(
            route_name,
            start_station,
            bus_departure_time,
        )
    )

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

        "historical_congestion":
            historical,

        "travel_time_minutes":
            travel_minutes,

        "estimated_arrival_time":
            (
                estimated_arrival.strftime(
                    "%H:%M"
                )
                if estimated_arrival
                else None
            ),

        "deadline_met":
            deadline_met,

        "score":
            score,
    }


# ==================================================
# 탑승전략을 후보 점수에 반영
# ==================================================

def apply_strategy_to_candidates(
    candidates,
    strategies,
):
    strategy_map = {
        strategy["route"]: strategy
        for strategy in strategies
    }

    adjusted_candidates = []

    for candidate in candidates:
        candidate = candidate.copy()

        strategy = strategy_map.get(
            candidate["route"]
        )

        base_score = candidate["score"]
        adjustment = 0

        if strategy is not None:
            strategy_type = strategy["strategy"]

            if strategy_type == "take_first_bus":
                if candidate["bus_number"] == 1:
                    adjustment += 25
                else:
                    adjustment -= 10

            elif strategy_type == "wait_second_bus":
                if candidate["bus_number"] == 2:
                    adjustment += 25
                else:
                    adjustment -= 25

            elif strategy_type == "move_upstream":
                adjustment -= 100

            elif strategy_type == "high_risk":
                adjustment -= 50

        candidate["base_score"] = base_score
        candidate["strategy_adjustment"] = adjustment

        candidate["final_score"] = round(
            base_score + adjustment,
            1,
        )

        candidate["boarding_strategy"] = (
            strategy["strategy"]
            if strategy
            else None
        )

        adjusted_candidates.append(
            candidate
        )

    return adjusted_candidates


# ==================================================
# Home
# ==================================================

@app.route("/")
@app.route("/timekeeper")
def timekeeper():
    return send_from_directory(
        PROJECT_ROOT,
        "Time_Keeper_mid_prototype.html"
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
        return jsonify({
            "error":
                "JSON 데이터가 필요합니다."
        }), 400

    required_fields = [
        "date",
        "start_station",
        "departure_time",
        "arrival_time",
        "destination",
    ]

    for field in required_fields:
        if field not in data:
            return jsonify({
                "error":
                    f"{field} 값이 필요합니다."
            }), 400

    date_string = data["date"]

    start_station = data[
        "start_station"
    ]

    departure_time_string = data[
        "departure_time"
    ]

    arrival_time_string = data[
        "arrival_time"
    ]

    destination = data[
        "destination"
    ]

    # ==================================================
    # 날씨 입력
    #
    # 현재:
    # 프론트/API 요청에서 받은 값을 사용
    #
    # 추후:
    # 실시간 날씨 API 결과로 교체 가능
    # ==================================================

    weather = data.get(
        "weather",
        {}
    )

    temperature = weather.get(
        "temperature"
    )

    humidity = weather.get(
        "humidity"
    )

    wind_speed = weather.get(
        "wind_speed"
    )

    rainfall = weather.get(
        "rainfall",
        0.0,
    )

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
        return jsonify({
            "error":
                "날짜는 YYYY-MM-DD, "
                "시간은 HH:MM 형식이어야 합니다."
        }), 400

    if desired_arrival <= target_datetime:
        return jsonify({
            "error":
                "도착시간은 출발시간보다 늦어야 합니다."
        }), 400


    # ==================================================
    # 고속도로 RF 예측
    #
    # 현재 weather가 들어온 경우에만 실행.
    #
    # 모델 예측 실패 시에도
    # 버스 추천 API 자체는 계속 동작하도록 한다.
    # ==================================================

    highway_prediction = None

    if (
        temperature is not None
        and humidity is not None
        and wind_speed is not None
    ):
        try:
            highway_prediction = (
                predict_highway_time(
                    hour=
                        target_datetime.hour,

                    day_of_week=
                        target_datetime.weekday(),

                    temperature=
                        float(temperature),

                    humidity=
                        float(humidity),

                    wind_speed=
                        float(wind_speed),

                    rainfall=
                        float(rainfall),
                )
            )

        except Exception as e:
            print(
                "[HIGHWAY MODEL ERROR]",
                e,
            )


    # ==================================================
    # 방향 결정
    # ==================================================

    if start_station == "기흥역":

        route_names = [
            "5001A",
            "5003A",
        ]

        direction = "A"

    elif start_station == "신논현역":

        route_names = [
            "5001B",
            "5003B",
        ]

        direction = "B"

    else:
        return jsonify({
            "error":
                "현재 MVP는 기흥역 또는 "
                "신논현역 출발을 지원합니다."
        }), 400


    # ==================================================
    # 후보 / 전략 생성
    # ==================================================

    candidates = []
    strategies = []

    for route_name in route_names:

        row = get_realtime_snapshot(
            route_name,
            start_station,
            target_datetime,
        )

        if row is None:
            continue

        if direction == "A":

            strategy = (
                build_a_boarding_strategy(
                    route_name,
                    start_station,
                    row,
                    target_datetime,
                )
            )

        else:

            strategy = (
                build_b_boarding_strategy(
                    route_name,
                    start_station,
                    row,
                    target_datetime,
                )
            )

        if strategy is not None:
            strategies.append(
                strategy
            )

        for bus_number in [1, 2]:

            candidate = create_candidate(
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

                start_station=
                    start_station,
            )

            if candidate is not None:
                candidates.append(
                    candidate
                )


    # ==================================================
    # 후보 없음
    # ==================================================

    if not candidates:
        return jsonify({
            "error":
                "해당 시점 이후 탑승 가능한 "
                "수집 버스 데이터가 없습니다.",

            "highway_prediction":
                highway_prediction,
        }), 404


    # ==================================================
    # 탑승 전략 점수 반영
    # ==================================================

    candidates = (
        apply_strategy_to_candidates(
            candidates,
            strategies,
        )
    )


    # ==================================================
    # 후보 정렬
    # ==================================================

    def final_sort_key(
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
            candidate[
                "final_score"
            ],
        )


    candidates.sort(
        key=
            final_sort_key,

        reverse=
            True,
    )


    # ==================================================
    # 정상 추천 후보
    # ==================================================

    valid_candidates = [
        candidate

        for candidate
        in candidates

        if (
            candidate[
                "final_score"
            ] >= 0

            and

            candidate[
                "boarding_strategy"
            ]

            not in [
                "move_upstream",
                "high_risk",
            ]
        )
    ]


    recommended = (
        valid_candidates[0]
        if valid_candidates
        else None
    )


    # ==================================================
    # 정상 후보가 없을 경우
    # 앞 정류장 / 위험 전략 선택
    # ==================================================

    recommended_strategy = None

    if recommended is None:

        move_strategies = [
            strategy

            for strategy
            in strategies

            if strategy[
                "strategy"
            ] == "move_upstream"
        ]

        if move_strategies:

            move_strategies.sort(
                key=lambda strategy:
                    strategy.get(
                        "alternative_score",
                        0,
                    ),

                reverse=True,
            )

            recommended_strategy = (
                move_strategies[0]
            )

        else:

            risk_strategies = [
                strategy

                for strategy
                in strategies

                if strategy[
                    "strategy"
                ] == "high_risk"
            ]

            if risk_strategies:
                recommended_strategy = (
                    risk_strategies[0]
                )


    # ==================================================
    # 추천 이유
    # ==================================================

    reasons = []

    if recommended is not None:

        seats = recommended[
            "remain_seats"
        ]

        if seats is not None:

            if seats >= 20:
                reasons.append(
                    "현재 잔여좌석이 "
                    "비교적 여유롭습니다."
                )

            elif seats >= 10:
                reasons.append(
                    "현재 좌석 여유가 있습니다."
                )

            elif seats >= 5:
                reasons.append(
                    "탑승 가능한 좌석은 "
                    "남아 있지만 여유가 크지 않습니다."
                )

            else:
                reasons.append(
                    "현재 잔여좌석이 매우 적습니다."
                )

        historical = recommended[
            "historical_congestion"
        ]

        if historical:

            reasons.append(
                "과거 동일 요일·시간대 "
                f"평균 혼잡도는 "
                f"{historical['avg_congestion']}입니다."
            )

        if (
            recommended[
                "deadline_met"
            ] is None
        ):
            reasons.append(
                "현재 이동시간 표본 부족으로 "
                "마감시간 판정은 아직 "
                "반영하지 않았습니다."
            )

    else:

        reasons.append(
            "현재 정류장에서 바로 탑승하는 것보다 "
            "앞 정류장 선탑승이 더 유리합니다."
        )

        if (
            recommended_strategy
            is not None
        ):
            reasons.append(
                recommended_strategy[
                    "message"
                ]
            )


    # ==================================================
    # 고속도로 ML 설명 추가
    # ==================================================

    if highway_prediction is not None:

        if highway_prediction[
            "rain_adjusted"
        ]:
            reasons.append(
                "강수 상황을 반영해 "
                "고속도로 예상 속도를 보정했습니다."
            )

        reasons.append(
            "고속도로 약 "
            f"{highway_prediction['distance_km']}km "
            "구간의 예상 주행시간은 약 "
            f"{highway_prediction['highway_minutes']}분입니다."
        )


    # ==================================================
    # 최종 응답
    # ==================================================

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

                "direction":
                    direction,

                "weather":
                    weather,
            },

            "highway_prediction":
                highway_prediction,

            "recommended":
                recommended,

            "recommended_strategy":
                recommended_strategy,

            "boarding_strategies":
                strategies,

            "reasons":
                reasons,

            "alternatives":
                candidates,

            "generated_at":
                datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
        }
    )


# ==================================================
# 실시간 버스 API
# ==================================================

@app.get(
    "/api/realtime/<route_name>"
)
def realtime_api(
    route_name
):
    station_name = (
        request.args.get(
            "station"
        )
    )

    if not station_name:
        return jsonify({
            "error":
                "station_required"
        }), 400

    try:
        result = get_live_arrival(
            route_name=
                route_name,

            station_name=
                station_name,
        )

        return jsonify(
            result
        )

    except ValueError as e:

        return jsonify({
            "error":
                str(e)
        }), 400

    except Exception as e:

        return jsonify({
            "error":
                "live_api_failed",

            "message":
                str(e),
        }), 500


# ==================================================
# 실행
# ==================================================

if __name__ == "__main__":
    app.run(
        debug=True,
        port=5001,
    )