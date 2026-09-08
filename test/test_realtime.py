import os

import requests
from dotenv import load_dotenv


load_dotenv()

API_KEY = os.getenv("DATA_API_KEY")

URL = (
    "https://apis.data.go.kr/6410000/"
    "buslocationservice/v2/getBusLocationListv2"
)

# 실시간 BMS 기준 routeId
ROUTES = {
    "5001A": "228000429",
    "5001B": "228000176",
    "5003A": "228000431",
    "5003B": "228000182",
}


def test_bus_location(route_name, route_id):

    params = {
        "serviceKey": API_KEY,
        "routeId": route_id,
        "format": "json",
    }

    print()
    print("=" * 70)
    print(f"{route_name} 위치 조회")
    print(f"routeId: {route_id}")
    print("=" * 70)

    try:
        response = requests.get(
            URL,
            params=params,
            timeout=30,
        )

        print("HTTP:", response.status_code)

        response.raise_for_status()

        data = response.json()

        header = data["response"]["msgHeader"]

        print("resultCode:", header.get("resultCode"))
        print("resultMessage:", header.get("resultMessage"))
        print("queryTime:", header.get("queryTime"))

        body = data["response"].get("msgBody")

        if not body:
            print("msgBody 없음")
            return

        buses = body.get("busLocationList", [])

        if not buses:
            print("운행 차량 없음")
            return

        print(f"현재 운행 차량 수: {len(buses)}")
        print()

        for bus in buses:

            print(
                f"vehId={bus.get('vehId')} | "
                f"plate={bus.get('plateNo')} | "
                f"stationSeq={bus.get('stationSeq')} | "
                f"stationId={bus.get('stationId')} | "
                f"remainSeat={bus.get('remainSeatCnt')} | "
                f"crowded={bus.get('crowded')} | "
                f"stateCd={bus.get('stateCd')}"
            )

    except requests.exceptions.Timeout:
        print("TIMEOUT")

    except requests.exceptions.RequestException as e:
        print("요청 오류:", e)

    except (ValueError, KeyError) as e:
        print("응답 파싱 오류:", e)


if __name__ == "__main__":

    if not API_KEY:
        print("DATA_API_KEY가 없습니다.")
        raise SystemExit

    for route_name, route_id in ROUTES.items():
        test_bus_location(route_name, route_id)