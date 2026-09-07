from datetime import datetime, timedelta

from collectors.congestion import (
    already_collected,
    get_congestion,
)
from config import ROUTES, STATIONS_5001B
from database.db import save_congestion


# 신논현역 찾기
station = next(
    station
    for station in STATIONS_5001B
    if station["id"] == "4105915"
)

route_id = ROUTES["5001B"]

station_id = station["id"]
station_name = station["name"]
ctpv_cd = station["ctpv_cd"]
sgg_cd = station["sgg_cd"]


# 역순 날짜
current_date = datetime.strptime(
    "20260807",
    "%Y%m%d"
)

last_date = datetime.strptime(
    "20260201",
    "%Y%m%d"
)


print()
print("############################")
print("5001B 신논현역 역순 보충 수집")
print("20260807 → 20260201")
print("############################")


while current_date >= last_date:

    date_str = current_date.strftime(
        "%Y%m%d"
    )

    # 이미 저장된 날짜
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

        current_date -= timedelta(days=1)
        continue


    # API 요청
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


    # 전체 중단
    if items == "STOP":
        print()
        print("전체 수집 중단")
        break


    # 해당 날짜만 실패
    if items == "SKIP":
        print("→ 해당 날짜 건너뜀")

        current_date -= timedelta(days=1)
        continue


    # 데이터 저장
    if items:
        save_congestion(items)

        print(
            "→",
            len(items),
            "개 저장"
        )

    else:
        print("→ 실제 데이터 없음")


    # 다음 날짜 (역순)
    current_date -= timedelta(days=1)


print()
print("############################")
print("신논현역 역순 수집 종료")
print("############################")