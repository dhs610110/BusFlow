import os
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("SERVICE_KEY")
print("API_KEY 존재 여부:", bool(API_KEY))

URL = (
    "https://apis.data.go.kr/6410000/"
    "buslocationservice/v2/getBusLocationListv2"
)

ROUTES = {
    "5001A": "41006433",
    "5001B": "41006248",

    
    "5003A": "41006409",
    "5003B": "41006064",
}


def get_realtime_bus_location(route_name, route_id):
    params = {
        "serviceKey": API_KEY,
        "routeId": route_id,
        "format": "json",
    }

    try:
        response = requests.get(
            URL,
            params=params,
            timeout=30,
        )

        print()
        print("=" * 60)
        print(f"{route_name} / route_id={route_id}")
        print("HTTP:", response.status_code)

        response.raise_for_status()

        data = response.json()

        # 일단 원본 응답 그대로 확인
        print(data)

        return data

    except requests.exceptions.Timeout:
        print(f"{route_name}: TIMEOUT")

    except requests.exceptions.RequestException as e:
        print(f"{route_name}: API 오류")
        print(e)

    except ValueError:
        print(f"{route_name}: JSON 변환 실패")
        print(response.text)

    return None


if __name__ == "__main__":
    for route_name, route_id in ROUTES.items():
        get_realtime_bus_location(route_name, route_id)

print("API_KEY 존재 여부:", bool(API_KEY))