import sqlite3
import time
from datetime import datetime, timedelta

import requests

from config import API_KEY, ROUTES, STATIONS_5001A, STATIONS_5001B
from database.db import save_congestion


URL = "https://apis.data.go.kr/1613000/RouteCongestionLevel/getRouteCongestionLevel"
DB_PATH = "data/busflow.db"

MAX_RETRIES = 5
RETRY_WAIT_SECONDS = 60
REQUEST_TIMEOUT = (10, 40)
REQUEST_INTERVAL = 1


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

    # -----------------------------------------------------
    # 최대 5번까지 API 요청
    # -----------------------------------------------------

    for attempt in range(1, MAX_RETRIES + 1):

        try:
            response = requests.get(
                URL,
                params=params,
                timeout=REQUEST_TIMEOUT
            )

        # -------------------------------------------------
        # Timeout
        # -------------------------------------------------

        except requests.exceptions.Timeout:

            print()
            print(
                f"응답 시간 초과 "
                f"({attempt}/{MAX_RETRIES})"
            )

            if attempt < MAX_RETRIES:
                print("1분 후 다시 시도합니다.")
                time.sleep(RETRY_WAIT_SECONDS)
                continue

            print("→ 해당 날짜 SKIP")
            return "SKIP"


        # -------------------------------------------------
        # 기타 네트워크 오류
        # -------------------------------------------------

        except requests.RequestException as error:

            print()
            print(
                f"네트워크 오류 "
                f"({attempt}/{MAX_RETRIES}):",
                error
            )

            if attempt < MAX_RETRIES:
                print("1분 후 다시 시도합니다.")
                time.sleep(RETRY_WAIT_SECONDS)
                continue

            print("→ 해당 날짜 SKIP")
            return "SKIP"


        # -------------------------------------------------
        # API 호출 한도 초과
        # -------------------------------------------------

        if response.status_code == 429:

            print()
            print("================================")
            print("API 호출 한도 초과 (429)")
            print("전체 수집을 중단합니다.")
            print("나중에 다시 실행하면 이어서 수집됩니다.")
            print("================================")
            print()

            return "STOP"


        # -------------------------------------------------
        # 서버 일시 오류
        # 500 / 502 / 503 / 504
        # -------------------------------------------------

        if response.status_code in (500, 502, 503, 504):

            print()
            print(
                f"서버 오류 {response.status_code} "
                f"({attempt}/{MAX_RETRIES})"
            )

            if attempt < MAX_RETRIES:
                print("1분 후 다시 시도합니다.")
                time.sleep(RETRY_WAIT_SECONDS)
                continue

            print(
                f"→ {response.status_code} 반복 발생, "
                "해당 날짜 SKIP"
            )

            return "SKIP"


        # -------------------------------------------------
        # 그 외 HTTP 오류
        # -------------------------------------------------

        if response.status_code != 200:

            print()
            print(
                "API 요청 실패:",
                response.status_code
            )

            return "STOP"


        # -------------------------------------------------
        # 정상 응답이면 반복문 종료
        # -------------------------------------------------

        break


    # =====================================================
    # JSON 변환
    # =====================================================

    try:
        data = response.json()

    except ValueError:

        print()
        print("JSON 변환 실패")
        print("→ 해당 날짜 SKIP")

        return "SKIP"


    # =====================================================
    # API 자체 오류 응답
    # =====================================================

    if "Response" not in data:

        error = data.get("Error", {})

        error_code = str(
            error.get("code", "")
        )

        error_message = error.get(
            "message",
            ""
        )


        # -------------------------------------------------
        # 데이터 없음
        # -------------------------------------------------

        if error_code == "50":
            return []


        print()
        print(
            "API 오류:",
            error_code,
            error_message
        )

        return "STOP"


    # =====================================================
    # 정상 데이터
    # =====================================================

    body = data["Response"]["body"]


    # 데이터 없음
    if int(body["totalCount"]) == 0:
        return []


    items = body["items"]["item"]


    # 데이터가 1개면 dict로 올 수 있어서 list로 변경
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


        # =================================================
        # 날짜 반복
        # =================================================

        while current_date <= last_date:

            date_str = current_date.strftime(
                "%Y%m%d"
            )


            # ------------------------------------------------
            # 이미 저장된 날짜
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
            # 전체 중단
            # ------------------------------------------------

            if items == "STOP":

                print()
                print("전체 수집 중단")

                return False


            # ------------------------------------------------
            # 해당 날짜만 실패
            # ------------------------------------------------

            if items == "SKIP":

                print("→ 해당 날짜 건너뜀")

                current_date += timedelta(days=1)

                continue


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


            # ------------------------------------------------
            # 실제 데이터 없음
            # ------------------------------------------------

            else:

                print(
                    "→ 실제 데이터 없음"
                )


            # ------------------------------------------------
            # API 과호출 방지
            # ------------------------------------------------

            time.sleep(REQUEST_INTERVAL)


            # 다음 날짜
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


    # -----------------------------------------------------
    # 5001A 중단
    # -----------------------------------------------------

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


    # -----------------------------------------------------
    # 5001B 중단
    # -----------------------------------------------------

    if not success_b:

        print()
        print("5001B 수집 중단")
        print("나중에 다시 실행해주세요.")

        raise SystemExit


    print()
    print("############################")
    print("전체 수집 완료")
    print("############################")