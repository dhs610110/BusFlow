import os
import sqlite3
from datetime import datetime

import requests
from dotenv import load_dotenv

from config import (
    REALTIME_ROUTES,
    REALTIME_STATIONS_B,
)


# ==================================================
# 기본 설정
# ==================================================

load_dotenv()

API_KEY = os.getenv("DATA_API_KEY")

PROJECT_ROOT = os.path.dirname(
    os.path.abspath(__file__)
)

DB_PATH = os.path.join(
    PROJECT_ROOT,
    "data",
    "realtime.db",
)

ARRIVAL_URL = (
    "https://apis.data.go.kr/6410000/"
    "busarrivalservice/v2/getBusArrivalListv2"
)

# 최근 이 시간 안의 DB 데이터면 API를 다시 호출하지 않음
MAX_CACHE_AGE_SECONDS = 90

# 현재는 B 방향부터 LIVE 연결
ROUTE_NAME_TO_ID = {
    "5001B": str(REALTIME_ROUTES["5001B"]),
    "5003B": str(REALTIME_ROUTES["5003B"]),
}


# ==================================================
# 정류장 이름 처리
# ==================================================

def normalize_station_name(name: str) -> str:
    if not name:
        return ""

    name = name.strip()

    aliases = {
        "신논현": "신논현역",
        "강남": "강남역",
        "양재": "양재역",
    }

    return aliases.get(name, name)


def find_station_id(station_name: str) -> str | None:
    target = normalize_station_name(station_name)

    for station in REALTIME_STATIONS_B:
        current = normalize_station_name(
            station["name"]
        )

        if current == target:
            return str(station["id"])

        # 긴 정류장명 대응
        if target in current or current in target:
            return str(station["id"])

    return None


# ==================================================
# 값 정리
# ==================================================

def _clean_int(value):
    if value in (None, ""):
        return None

    try:
        value = int(value)
    except (TypeError, ValueError):
        return None

    # -1은 미제공/알 수 없음으로 처리
    return None if value < 0 else value


def _parse_datetime(value: str) -> datetime | None:
    try:
        return datetime.strptime(
            value,
            "%Y-%m-%d %H:%M:%S",
        )
    except (TypeError, ValueError):
        return None


def _age_seconds(collected_at: str) -> int | None:
    dt = _parse_datetime(collected_at)

    if dt is None:
        return None

    return max(
        0,
        int(
            (
                datetime.now() - dt
            ).total_seconds()
        ),
    )


def _countdown_value(
    seconds,
    age_seconds,
):
    """
    최근 DB 캐시를 LIVE처럼 보여주기 위해
    수집 후 경과시간만큼 ETA를 감소시킨다.

    오래된 fallback 데이터에는 사용하지 않는다.
    """

    seconds = _clean_int(seconds)

    if seconds is None:
        return None

    if age_seconds is None:
        return seconds

    return max(
        0,
        seconds - age_seconds,
    )


# ==================================================
# DB 캐시 조회
# ==================================================

def _get_cached_arrival(
    route_name: str,
    station_id: str,
) -> dict | None:

    if not os.path.exists(DB_PATH):
        return None

    connection = sqlite3.connect(
        DB_PATH
    )

    connection.row_factory = sqlite3.Row

    try:
        row = connection.execute(
            """
            SELECT
                collected_at,

                route_name,
                route_id,

                station_id,
                station_name,

                veh_id_1,
                plate_no_1,
                predict_time_sec_1,
                remain_seat_cnt_1,
                location_no_1,
                vehicle_station_name_1,

                veh_id_2,
                plate_no_2,
                predict_time_sec_2,
                remain_seat_cnt_2,
                location_no_2,
                vehicle_station_name_2

            FROM realtime_arrival_b

            WHERE route_name = ?
              AND station_id = ?

            ORDER BY collected_at DESC

            LIMIT 1
            """,
            (
                route_name,
                station_id,
            ),
        ).fetchone()

    finally:
        connection.close()

    if row is None:
        return None

    age = _age_seconds(
        row["collected_at"]
    )

    return {
        "route_name": row["route_name"],
        "station_name": row["station_name"],
        "station_id": row["station_id"],
        "collected_at": row["collected_at"],
        "age_seconds": age,

        "first_bus": {
            "vehicle_id": row["veh_id_1"],
            "plate_no": row["plate_no_1"],
            "arrival_seconds_raw": _clean_int(
                row["predict_time_sec_1"]
            ),
            "remain_seats": _clean_int(
                row["remain_seat_cnt_1"]
            ),
            "location_no": _clean_int(
                row["location_no_1"]
            ),
            "vehicle_station_name": (
                row["vehicle_station_name_1"]
            ),
        },

        "second_bus": {
            "vehicle_id": row["veh_id_2"],
            "plate_no": row["plate_no_2"],
            "arrival_seconds_raw": _clean_int(
                row["predict_time_sec_2"]
            ),
            "remain_seats": _clean_int(
                row["remain_seat_cnt_2"]
            ),
            "location_no": _clean_int(
                row["location_no_2"]
            ),
            "vehicle_station_name": (
                row["vehicle_station_name_2"]
            ),
        },
    }


def _make_cache_response(
    cached: dict,
    *,
    stale: bool,
    reason: str,
) -> dict:

    age = cached.get(
        "age_seconds"
    )

    first = cached["first_bus"].copy()
    second = cached["second_bus"].copy()

    # 최근 캐시만 ETA를 현재 시각 기준으로 보정
    if not stale:
        first["arrival_seconds"] = (
            _countdown_value(
                first.get(
                    "arrival_seconds_raw"
                ),
                age,
            )
        )

        second["arrival_seconds"] = (
            _countdown_value(
                second.get(
                    "arrival_seconds_raw"
                ),
                age,
            )
        )

    else:
        # 오래된 데이터는 과거 스냅샷임을 명확히 하기 위해
        # 원래 수집 당시 ETA를 그대로 제공
        first["arrival_seconds"] = (
            first.get(
                "arrival_seconds_raw"
            )
        )

        second["arrival_seconds"] = (
            second.get(
                "arrival_seconds_raw"
            )
        )

    first.pop(
        "arrival_seconds_raw",
        None,
    )

    second.pop(
        "arrival_seconds_raw",
        None,
    )

    return {
        "route_name": cached[
            "route_name"
        ],
        "station_name": cached[
            "station_name"
        ],
        "station_id": cached[
            "station_id"
        ],
        "collected_at": cached[
            "collected_at"
        ],

        "data_source": (
            "stale_cache"
            if stale
            else "cache"
        ),

        "stale": stale,
        "age_seconds": age,
        "cache_reason": reason,

        "first_bus": first,
        "second_bus": second,
    }


# ==================================================
# 공공데이터 API 직접 호출
# ==================================================

def _call_arrival_api(
    station_id: str,
) -> list[dict]:

    if not API_KEY:
        raise RuntimeError(
            "DATA_API_KEY가 없습니다."
        )

    response = requests.get(
        ARRIVAL_URL,
        params={
            "serviceKey": API_KEY,
            "stationId": station_id,
            "format": "json",
        },
        timeout=15,
    )

    response.raise_for_status()

    data = response.json()

    header = data[
        "response"
    ][
        "msgHeader"
    ]

    if str(
        header.get(
            "resultCode"
        )
    ) != "0":

        raise RuntimeError(
            header.get(
                "resultMessage"
            )
            or "경기도 버스 API 응답 오류"
        )

    body = (
        data["response"].get(
            "msgBody",
            {}
        )
    )

    arrivals = body.get(
        "busArrivalList",
        []
    )

    if isinstance(
        arrivals,
        dict,
    ):
        arrivals = [
            arrivals
        ]

    return arrivals


# ==================================================
# LIVE 조회 메인 함수
# ==================================================

def get_live_arrival(
    route_name: str,
    station_name: str,
) -> dict:
    """
    1) 최근 90초 이내 DB 캐시가 있으면 즉시 반환
    2) 없거나 오래됐으면 공공데이터 API 직접 호출
    3) API가 429/오류일 경우 마지막 DB 데이터 fallback
    """

    route_name = (
        route_name
        .upper()
        .strip()
    )

    if (
        route_name
        not in ROUTE_NAME_TO_ID
    ):
        raise ValueError(
            "현재 LIVE API는 "
            "5001B/5003B만 지원합니다: "
            f"{route_name}"
        )

    station_id = find_station_id(
        station_name
    )

    if station_id is None:
        raise ValueError(
            "B 방향 정류장에서 "
            "찾을 수 없습니다: "
            f"{station_name}"
        )

    # ----------------------------------------------
    # 1. DB 최근 데이터 확인
    # ----------------------------------------------

    cached = _get_cached_arrival(
        route_name,
        station_id,
    )

    if cached is not None:

        age = cached.get(
            "age_seconds"
        )

        if (
            age is not None
            and
            age <= MAX_CACHE_AGE_SECONDS
        ):

            return _make_cache_response(
                cached,
                stale=False,
                reason=(
                    f"최근 {age}초 전 "
                    "수집 데이터를 사용했습니다."
                ),
            )

    # ----------------------------------------------
    # 2. 캐시가 오래됐으면 실제 API 호출
    # ----------------------------------------------

    route_id = (
        ROUTE_NAME_TO_ID[
            route_name
        ]
    )

    try:

        arrivals = _call_arrival_api(
            station_id
        )

        target = None

        for bus in arrivals:

            if str(
                bus.get(
                    "routeId",
                    "",
                )
            ) == route_id:

                target = bus
                break

        if target is None:

            return {
                "route_name": route_name,
                "station_name": (
                    station_name
                ),
                "station_id": (
                    station_id
                ),
                "collected_at": (
                    datetime.now()
                    .strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                ),

                "data_source": "api",
                "stale": False,
                "age_seconds": 0,

                "first_bus": None,
                "second_bus": None,

                "message": (
                    "현재 이 정류장에 "
                    "해당 노선 도착정보가 없습니다."
                ),
            }

        return {
            "route_name": route_name,
            "station_name": (
                station_name
            ),
            "station_id": station_id,
            "collected_at": (
                datetime.now()
                .strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            ),

            "data_source": "api",
            "stale": False,
            "age_seconds": 0,

            "first_bus": {
                "vehicle_id": (
                    target.get(
                        "vehId1"
                    )
                ),
                "plate_no": (
                    target.get(
                        "plateNo1"
                    )
                ),
                "arrival_seconds": (
                    _clean_int(
                        target.get(
                            "predictTimeSec1"
                        )
                    )
                ),
                "remain_seats": (
                    _clean_int(
                        target.get(
                            "remainSeatCnt1"
                        )
                    )
                ),
                "location_no": (
                    _clean_int(
                        target.get(
                            "locationNo1"
                        )
                    )
                ),
                "vehicle_station_name": (
                    target.get(
                        "stationNm1"
                    )
                ),
            },

            "second_bus": {
                "vehicle_id": (
                    target.get(
                        "vehId2"
                    )
                ),
                "plate_no": (
                    target.get(
                        "plateNo2"
                    )
                ),
                "arrival_seconds": (
                    _clean_int(
                        target.get(
                            "predictTimeSec2"
                        )
                    )
                ),
                "remain_seats": (
                    _clean_int(
                        target.get(
                            "remainSeatCnt2"
                        )
                    )
                ),
                "location_no": (
                    _clean_int(
                        target.get(
                            "locationNo2"
                        )
                    )
                ),
                "vehicle_station_name": (
                    target.get(
                        "stationNm2"
                    )
                ),
            },
        }

    # ----------------------------------------------
    # 3. 429 등 API 오류 → 마지막 DB 데이터 사용
    # ----------------------------------------------

    except requests.exceptions.HTTPError as e:

        if cached is not None:

            status_code = (
                e.response.status_code
                if e.response is not None
                else None
            )

            return _make_cache_response(
                cached,
                stale=True,
                reason=(
                    "공공데이터 API 호출 실패"
                    f" (HTTP {status_code}). "
                    "마지막 저장 데이터를 표시합니다."
                ),
            )

        raise

    except requests.exceptions.RequestException:

        if cached is not None:

            return _make_cache_response(
                cached,
                stale=True,
                reason=(
                    "공공데이터 API 네트워크 오류로 "
                    "마지막 저장 데이터를 표시합니다."
                ),
            )

        raise

    except Exception:

        if cached is not None:

            return _make_cache_response(
                cached,
                stale=True,
                reason=(
                    "실시간 API 처리 실패로 "
                    "마지막 저장 데이터를 표시합니다."
                ),
            )

        raise
