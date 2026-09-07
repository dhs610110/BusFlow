
from collectors.congestion import collect_station_range
from config import ROUTES, STATIONS_5001B


# 신논현역만 선택
missing_sinnonhyeon = [
    station
    for station in STATIONS_5001B
    if station["id"] == "4105915"
]


print()
print("############################")
print("5001B 신논현역 보충 수집")
print("############################")


success = collect_station_range(
    start_date="20260201",
    end_date="20260807",
    route_id=ROUTES["5001B"],
    stations=missing_sinnonhyeon,
)


if not success:
    print()
    print("신논현역 보충 수집 중단")
    raise SystemExit


print()
print("############################")
print("신논현역 보충 수집 완료")
print("############################")

