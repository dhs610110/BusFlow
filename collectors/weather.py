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


# =========================================================
# 현재 노선별 정류장 목록
# =========================================================

ROUTE_STATIONS = {
    "5001A": STATIONS_5001A,
    "5001B": STATIONS_5001B,
}


# =========================================================
# 값 변환
# =========================================================

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


# =========================================================
# 이미 DB에 저장되어 있는지 확인
# =========================================================

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

    # 06시 ~ 22시 = 17개
    expected_count = (
        END_HOUR
        - START_HOUR
        + 1
    )

    return count >= expected_count


# =========================================================
# 필요한 기상관측소 추출
# =========================================================

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


# =========================================================
# 기상청 ASOS 시간자료 요청
# =========================================================

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
        print("수집을 중단합니다.")

        return "STOP"


    # -----------------------------------------------------
    # API 호출 제한
    # -----------------------------------------------------

    if response.status_code == 429:

        print()
        print("================================")
        print("기상청 API 호출 한도 초과 (429)")
        print("수집을 중단합니다.")
        print("나중에 다시 실행하면 이어서 수집됩니다.")
        print("================================")
        print()

        return "STOP"


    # -----------------------------------------------------
    # 기타 HTTP 오류
    # -----------------------------------------------------

    if response.status_code != 200:

        print()
        print(
            "기상청 API 요청 실패:",
            response.status_code
        )

        return "STOP"


    # -----------------------------------------------------
    # JSON 변환
    # -----------------------------------------------------

    try:

        data = response.json()

    except ValueError:

        print()
        print("기상청 JSON 변환 실패")
        print("수집을 중단합니다.")

        return "STOP"


    # -----------------------------------------------------
    # API 자체 오류
    # -----------------------------------------------------

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


    # -----------------------------------------------------
    # 정상 응답
    # -----------------------------------------------------

    body = data["response"]["body"]

    if int(body["totalCount"]) == 0:
        return []


    items = body["items"]["item"]

    if isinstance(items, dict):
        items = [items]


    # 혹시 모를 범위 밖 데이터 제거
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


# =========================================================
# 기상청 원본 -> DB 저장용 형식
# =========================================================

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

        # 친구의 congestion 테이블과
        # 최대한 동일한 JOIN 키 사용
        "opr_ymd": date,

        "route_id": route_id,

        "station_id": station["id"],

        "station_seq": station["seq"],

        # 시간대 비교가 쉽게 06, 07 ... 22로 저장
        "time_zone": f"{hour:02d}",


        # 어떤 기상관측소 값인지 기록
        "weather_station_id":
            str(weather.get("stnId", "")),

        "weather_station_name":
            weather.get("stnNm"),


        # -------------------------
        # 핵심 날씨 변수
        # -------------------------

        "temperature":
            to_float(
                weather.get("ta")
            ),

        "rainfall":
            to_float(
                weather.get("rn")
            ),

        "humidity":
            to_float(
                weather.get("hm")
            ),


        # -------------------------
        # 바람
        # -------------------------

        "wind_speed":
            to_float(
                weather.get("ws")
            ),

        "wind_direction":
            to_float(
                weather.get("wd")
            ),


        # -------------------------
        # 기압 / 수증기
        # -------------------------

        "local_pressure":
            to_float(
                weather.get("pa")
            ),

        "sea_pressure":
            to_float(
                weather.get("ps")
            ),

        "dew_point":
            to_float(
                weather.get("td")
            ),

        "vapor_pressure":
            to_float(
                weather.get("pv")
            ),


        # -------------------------
        # 일조 / 일사
        # -------------------------

        "sunshine":
            to_float(
                weather.get("ss")
            ),

        "solar_radiation":
            to_float(
                weather.get("icsr")
            ),


        # -------------------------
        # 눈
        # -------------------------

        "snow_depth":
            to_float(
                weather.get("dsnw")
            ),

        "snow_3h":
            to_float(
                weather.get("hr3Fhsc")
            ),


        # -------------------------
        # 구름
        # -------------------------

        "total_cloud":
            to_float(
                weather.get("dc10Tca")
            ),

        "low_mid_cloud":
            to_float(
                weather.get("dc10LmcsCa")
            ),

        "cloud_type":
            weather.get("clfmAbbrCd"),

        "lowest_cloud_height":
            to_float(
                weather.get("lcsCh")
            ),


        # -------------------------
        # 시정 / 지면
        # -------------------------

        "visibility":
            to_float(
                weather.get("vs")
            ),

        "ground_temperature":
            to_float(
                weather.get("ts")
            ),

        "soil_temp_5cm":
            to_float(
                weather.get("m005Te")
            ),

        "soil_temp_10cm":
            to_float(
                weather.get("m01Te")
            ),

        "soil_temp_20cm":
            to_float(
                weather.get("m02Te")
            ),

        "soil_temp_30cm":
            to_float(
                weather.get("m03Te")
            ),
    }


# =========================================================
# 날짜 하나 수집
#
# 같은 지역 정류장끼리는 같은 시간 날씨를 공유하므로
# 기상청 API는 관측소별로 1회만 호출한 뒤
# 정류장별 데이터로 복제해서 저장한다.
# =========================================================

def collect_date(date):

    print()
    print("============================")
    print("날짜:", date)
    print("============================")


    # -----------------------------------------------------
    # 1. 해당 날짜에 필요한 기상관측소 데이터 수집
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
    # 2. 정류장별로 동일 지역 날씨 복제 후 저장
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

            # 이미 17시간 저장되어 있으면 SKIP
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
                    "→ 실제 날씨 데이터 없음"
                )


    return True


# =========================================================
# 날짜 범위 수집
# =========================================================

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
            print(
                "나중에 다시 실행해주세요."
            )

            return False


        current_date += timedelta(
            days=1
        )


    return True


# =========================================================
# 실행
# congestion.py와 동일한 날짜 범위
# =========================================================

if __name__ == "__main__":

    if not KMA_API_KEY:

        print()
        print("============================")
        print("KMA_API_KEY가 없습니다.")
        print(
            ".env에 KMA_API_KEY를 추가해주세요."
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
