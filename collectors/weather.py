import sqlite3
import time
from datetime import datetime, timedelta

import requests

from config import (
    KMA_API_KEY,
    ROUTES,
    STATIONS_5001A,
    STATIONS_5001B,
    WEATHER_STATIONS_BY_SGG,
)

from database.db import save_weather


URL = (
    "https://apis.data.go.kr/"
    "1360000/AsosHourlyInfoService/"
    "getWthrDataList"
)

DB_PATH = "data/busflow.db"

START_HOUR = 6
END_HOUR = 22


ROUTE_STATIONS = {
    "5001A": STATIONS_5001A,
    "5001B": STATIONS_5001B,
}


def to_float(value):

    if value is None:
        return None

    value = str(value).strip()

    if value == "":
        return None

    try:
        return float(value)

    except ValueError:
        return None


def already_collected(
    date,
    route_id,
    station_id
):

    conn = sqlite3.connect(DB_PATH)

    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM weather
        WHERE opr_ymd = ?
        AND route_id = ?
        AND station_id = ?
        """,
        (
            date,
            route_id,
            station_id
        )
    )

    count = cursor.fetchone()[0]

    conn.close()

    # 06~07부터 22~23까지 총 17개
    expected_count = (
        END_HOUR
        - START_HOUR
        + 1
    )

    return count >= expected_count


def get_required_weather_stations():

    required_stations = {}

    for stations in ROUTE_STATIONS.values():

        for station in stations:

            sgg_cd = station["sgg_cd"]

            weather_station = (
                WEATHER_STATIONS_BY_SGG.get(
                    sgg_cd
                )
            )

            if weather_station is None:

                print(
                    "날씨 관측소 매핑 없음:",
                    station["name"],
                    sgg_cd
                )

                continue

            weather_station_id = (
                weather_station[
                    "station_id"
                ]
            )

            required_stations[
                weather_station_id
            ] = weather_station

    return required_stations


def get_weather(
    date,
    weather_station_id
):

    params = {
        "ServiceKey": KMA_API_KEY,

        "pageNo": 1,
        "numOfRows": 100,
        "dataType": "JSON",

        "dataCd": "ASOS",
        "dateCd": "HR",

        "startDt": date,
        "startHh": "06",

        "endDt": date,
        "endHh": "22",

        "stnIds": weather_station_id,
    }

    try:

        response = requests.get(
            URL,
            params=params,
            timeout=20
        )

    except requests.RequestException as error:

        print()
        print("네트워크 오류:", error)

        return "STOP"


    if response.status_code == 429:

        print()
        print("기상청 API 호출 한도 초과 (429)")
        print("수집을 중단합니다.")

        return "STOP"


    if response.status_code != 200:

        print()
        print(
            "기상청 API 요청 실패:",
            response.status_code
        )

        return "STOP"


    try:

        data = response.json()

    except ValueError:

        print()
        print("기상청 JSON 변환 실패")

        return "STOP"


    if "response" not in data:

        print()
        print(
            "기상청 비정상 응답:",
            data
        )

        return "STOP"


    header = data["response"]["header"]

    if header["resultCode"] != "00":

        print()
        print(
            "기상청 API 오류:",
            header["resultCode"],
            header["resultMsg"]
        )

        return "STOP"


    body = data["response"]["body"]

    if int(body["totalCount"]) == 0:
        return []


    items = body["items"]["item"]

    if isinstance(items, dict):
        items = [items]


    result = []

    for item in items:

        tm = item.get("tm")

        if not tm:
            continue

        try:
            hour = int(
                tm.split(" ")[1]
            )

        except (
            IndexError,
            ValueError
        ):
            continue

        if START_HOUR <= hour <= END_HOUR:
            result.append(item)


    result.sort(
        key=lambda item: item["tm"]
    )

    return result


def normalize_weather(
    weather,
    date,
    route_id,
    station
):

    tm = weather["tm"]

    hour = int(
        tm.split(" ")[1]
    )

    return {
        # -------------------------------------------------
        # 친구 congestion 데이터와 JOIN할 키
        # -------------------------------------------------

        "opr_ymd": date,

        "route_id": route_id,

        "station_id": station["id"],

        "station_seq": station["seq"],

        # 친구 데이터와 동일하게:
        # 06~07, 07~08, ..., 22~23
        "time_zone":
            f"{hour:02d}~{hour + 1:02d}",


        # -------------------------------------------------
        # 어떤 관측소의 날씨인지
        # -------------------------------------------------

        "weather_station_id":
            str(
                weather.get(
                    "stnId",
                    ""
                )
            ),

        "weather_station_name":
            weather.get("stnNm"),


        # -------------------------------------------------
        # 실제로 저장할 5개 날씨 변수
        # -------------------------------------------------

        # 기온 (℃)
        "temperature":
            to_float(
                weather.get("ta")
            ),

        # 시간 강수량 (mm)
        "rainfall":
            to_float(
                weather.get("rn")
            ),

        # 상대습도 (%)
        "humidity":
            to_float(
                weather.get("hm")
            ),

        # 풍속 (m/s)
        "wind_speed":
            to_float(
                weather.get("ws")
            ),

        # 적설량 (cm)
        "snow_depth":
            to_float(
                weather.get("dsnw")
            ),
    }


def collect_date(date):

    print()
    print("============================")
    print("날짜:", date)
    print("============================")


    # -----------------------------------------------------
    # 1. 날짜별 지역 날씨를 한 번씩만 호출
    # -----------------------------------------------------

    required_weather_stations = (
        get_required_weather_stations()
    )

    weather_cache = {}


    for (
        weather_station_id,
        weather_station
    ) in required_weather_stations.items():

        print(
            weather_station["station_name"],
            "날씨 API 요청",
            end=" "
        )

        items = get_weather(
            date=date,
            weather_station_id=
                weather_station_id
        )

        if items == "STOP":
            return False

        weather_cache[
            weather_station_id
        ] = items

        print(
            "→",
            len(items),
            "개"
        )

        time.sleep(0.5)


    # -----------------------------------------------------
    # 2. 같은 지역의 정류장들에 동일 날씨 복제 후 DB 저장
    # -----------------------------------------------------

    for route_name, stations in (
        ROUTE_STATIONS.items()
    ):

        route_id = ROUTES[
            route_name
        ]

        print()
        print(
            "########",
            route_name,
            "########"
        )


        for station in stations:

            if already_collected(
                date,
                route_id,
                station["id"]
            ):

                print(
                    station["seq"],
                    station["name"],
                    "→ 이미 저장됨 (SKIP)"
                )

                continue


            weather_station = (
                WEATHER_STATIONS_BY_SGG[
                    station["sgg_cd"]
                ]
            )

            weather_station_id = (
                weather_station[
                    "station_id"
                ]
            )

            items = weather_cache.get(
                weather_station_id,
                []
            )


            rows = []

            for weather in items:

                row = normalize_weather(
                    weather=weather,
                    date=date,
                    route_id=route_id,
                    station=station
                )

                rows.append(row)


            if rows:

                save_weather(rows)

                print(
                    station["seq"],
                    station["name"],
                    "→",
                    len(rows),
                    "개 저장"
                )

            else:

                print(
                    station["seq"],
                    station["name"],
                    "→ 날씨 데이터 없음"
                )


    return True


def collect_weather_range(
    start_date,
    end_date
):

    current_date = datetime.strptime(
        start_date,
        "%Y%m%d"
    )

    last_date = datetime.strptime(
        end_date,
        "%Y%m%d"
    )


    while current_date <= last_date:

        date_str = current_date.strftime(
            "%Y%m%d"
        )

        success = collect_date(
            date_str
        )

        if not success:

            print()
            print("날씨 수집 중단")
            print("나중에 다시 실행해주세요.")

            return False


        current_date += timedelta(
            days=1
        )


    return True


if __name__ == "__main__":

    if not KMA_API_KEY:

        print()
        print("============================")
        print("KMA_API_KEY가 없습니다.")
        print(
            ".env 또는 Codespaces 환경변수에 "
            "KMA_API_KEY를 추가해주세요."
        )
        print("============================")

        raise SystemExit


    print()
    print("############################")
    print("날씨 수집 시작")
    print("############################")


    success = collect_weather_range(
        start_date="20260201",
        end_date="20260807",
    )


    if not success:
        raise SystemExit


    print()
    print("############################")
    print("전체 날씨 수집 완료")
    print("############################")
