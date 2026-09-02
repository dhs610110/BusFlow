from collectors.congestion import get_congestion
from config import ROUTES, STATIONS_5001A


station = STATIONS_5001A[0]

items = get_congestion(
    date="20260805",
    route_id=ROUTES["5001A"],
    station_id=station["id"],
    ctpv_cd=station["ctpv_cd"],
    sgg_cd=station["sgg_cd"],
)


if items == "STOP":
    print("API 호출 실패")

elif not items:
    print("데이터 없음")

else:
    print("정류장:", station["name"])
    print("받은 데이터 수:", len(items))

    print()
    print("tzon 값:")

    for item in items:
        print(item["tzon"])
