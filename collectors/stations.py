import time

import requests

from config import ROUTES


URL = (
    "https://tbo.stcis.go.kr/tsdw/open-api/p/"
    "BusRoutespecificStopInformation/"
    "BusRoutespecificStopInformation"
)


def get_stations(date, route_id, sgg_cd):
    all_stations = []
    page = 1

    while True:
        params = {
            "opr_ymd": date,
            "ctpv_cd": "41",
            "sgg_cd": sgg_cd,
            "rte_id": route_id,
            "pageNo": page,
        }

        response = requests.get(
            URL,
            params=params,
            timeout=15
        )

        response.raise_for_status()

        data = response.json()

        # 차단 또는 비정상 응답 확인
        if "Response" not in data:
            print("비정상 응답:", data)
            break

        body = data["Response"]["body"]

        # 데이터가 없는 경우
        if int(body["totalCount"]) == 0:
            break

        items = body["items"]["item"]

        all_stations.extend(items)

        total_count = int(body["totalCount"])

        print(
            sgg_cd,
            "페이지:",
            page,
            "/ 현재",
            len(all_stations),
            "개"
        )

        # 전부 가져왔으면 종료
        if len(all_stations) >= total_count:
            break

        page += 1

        # 1분 5회 초과 방지
        time.sleep(13)

    return all_stations


if __name__ == "__main__":
    all_stations = []

    # -------------------------
    # 1. 처인구 정류장
    # -------------------------

    print("처인구 정류장 수집 시작")

    stations_cheoin = get_stations(
        date="20260805",
        route_id=ROUTES["5001A"],
        sgg_cd="41461",
    )

    all_stations.extend(stations_cheoin)

    print("처인구 수집 완료:", len(stations_cheoin), "개")


    # -------------------------
    # 호출 제한 초기화 대기
    # -------------------------

    print("65초 대기...")
    time.sleep(65)


    # -------------------------
    # 2. 기흥구 정류장
    # -------------------------

    print("기흥구 정류장 수집 시작")

    stations_giheung = get_stations(
        date="20260805",
        route_id=ROUTES["5001A"],
        sgg_cd="41463",
    )

    all_stations.extend(stations_giheung)

    print("기흥구 수집 완료:", len(stations_giheung), "개")


    # -------------------------
    # 3. 15 ~ 27번 정류장 추출
    # -------------------------

    target_stations = []

    for station in all_stations:
        seq = int(station["sttn_seq"])

        if 15 <= seq <= 27:
            target_stations.append(station)


    # -------------------------
    # 4. 정류장 순서대로 정렬
    # -------------------------

    target_stations.sort(
        key=lambda station: int(station["sttn_seq"])
    )


    # -------------------------
    # 5. 결과 출력
    # -------------------------

    print()
    print("대상 정류장 수:", len(target_stations))
    print("--------------------------------")

    for station in target_stations:
        print(
            station["sttn_seq"],
            station["sttn_id"],
            station["sttn_nm"]
        )