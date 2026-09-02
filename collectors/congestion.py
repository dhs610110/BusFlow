import sqlite3
import time
from datetime import datetime, timedelta

import requests

from config import API_KEY, ROUTES, STATIONS_5001A, STATIONS_5001B
from database.db import save_congestion


URL = "https://apis.data.go.kr/1613000/RouteCongestionLevel/getRouteCongestionLevel"
DB_PATH = "data/busflow.db"


# =========================================================
# 이미 DB에 저장되어 있는지 확인
# =========================================================

def already_collected(date, route_id, station_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM congestion
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

    return count > 0


# =========================================================
# 혼잡도 API 요청
# =========================================================

def get_congestion(
    date,
    route_id,
    station_id,
    ctpv_cd,
    sgg_cd
):
    params = {
        "serviceKey": API_KEY,
        "pageNo": 1,
        "numOfRows": 1000,
        "opr_ymd": date,
        "ctpv_cd": ctpv_cd,
        "sgg_cd": sgg_cd,
        "rte_id": route_id,
        "sttn_id": station_id,
        "dataType": "JSON",
    }

    try:
        response = requests.get(
            URL,
            params=params,
            timeout=15
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
        print("API 호출 한도 초과 (429)")
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
            "API 요청 실패:",
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
        print("JSON 변환 실패")
        print("수집을 중단합니다.")

        return "STOP"


    # -----------------------------------------------------
    # API 자체 오류 응답
    # -----------------------------------------------------

    if "Response" not in data:

        error = data.get("Error", {})

        error_code = str(
            error.get("code", "")
        )

        # 실제 데이터 없음
        if error_code == "50":
            return []

        print()
        print(
            "API 오류:",
            error_code,
            error.get("message", "")
        )

        return "STOP"


    # -----------------------------------------------------
    # 정상 응답
    # -----------------------------------------------------

    body = data["Response"]["body"]

    if int(body["totalCount"]) == 0:
        return []

    items = body["items"]["item"]

    if isinstance(items, dict):
        items = [items]

    return items


# =========================================================
# 정류장 여러 개 + 날짜 범위 수집
# =========================================================

def collect_station_range(
    start_date,
    end_date,
    route_id,
    stations
):

    for station in stations:

        station_id = station["id"]
        station_name = station["name"]
        ctpv_cd = station["ctpv_cd"]
        sgg_cd = station["sgg_cd"]

        print()
        print("============================")
        print("정류장:", station_name)
        print("station_id:", station_id)
        print("지역코드:", ctpv_cd, sgg_cd)
        print("============================")

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


            # ------------------------------------------------
            # 이미 받은 데이터면 API 호출 자체를 하지 않음
            # ------------------------------------------------

            if already_collected(
                date_str,
                route_id,
                station_id
            ):
                print(
                    date_str,
                    "/",
                    station_name,
                    "→ 이미 저장됨 (SKIP)"
                )

                current_date += timedelta(days=1)

                continue


            # ------------------------------------------------
            # API 요청
            # ------------------------------------------------

            print(
                date_str,
                "/",
                station_name,
                end=" "
            )

            items = get_congestion(
                date=date_str,
                route_id=route_id,
                station_id=station_id,
                ctpv_cd=ctpv_cd,
                sgg_cd=sgg_cd
            )


            # ------------------------------------------------
            # API 한도 / 오류 발생
            # ------------------------------------------------

            if items == "STOP":
                return False


            # ------------------------------------------------
            # 정상 데이터
            # ------------------------------------------------

            if items:
                save_congestion(items)

                print(
                    "→",
                    len(items),
                    "개 저장"
                )

            else:
                print("→ 실제 데이터 없음")


            # API 과호출 방지
            time.sleep(1)

            current_date += timedelta(days=1)


    return True


# =========================================================
# 실행
# =========================================================

if __name__ == "__main__":

    print()
    print("############################")
    print("5001A 수집 시작")
    print("############################")


    success_a = collect_station_range(
        start_date="20260201",
        end_date="20260807",
        route_id=ROUTES["5001A"],
        stations=STATIONS_5001A,
    )


    # A가 API 제한으로 중단되면
    # B까지 요청하지 않고 프로그램 종료

    if not success_a:

        print()
        print("5001A 수집 중단")
        print("나중에 다시 실행해주세요.")

        raise SystemExit


    print()
    print("############################")
    print("5001B 수집 시작")
    print("############################")


    success_b = collect_station_range(
        start_date="20260201",
        end_date="20260807",
        route_id=ROUTES["5001B"],
        stations=STATIONS_5001B,
    )


    if not success_b:

        print()
        print("5001B 수집 중단")
        print("나중에 다시 실행해주세요.")

        raise SystemExit


    print()
    print("############################")
    print("전체 수집 완료")
    print("############################")