import os

import requests
from dotenv import load_dotenv


load_dotenv()

API_KEY = os.getenv("DATA_API_KEY")

URL = (
    "https://apis.data.go.kr/6410000/"
    "busarrivalservice/v2/getBusArrivalListv2"
)

# 우리가 기존에 사용하던 기흥역 ID
STATION_ID = "228000682"


def get_arrival_list():

    print("API KEY 존재:", bool(API_KEY))
    print("조회 stationId:", STATION_ID)

    params = {
        "serviceKey": API_KEY,
        "stationId": STATION_ID,
        "format": "json",
    }

    try:
        response = requests.get(
            URL,
            params=params,
            timeout=30
        )

        print()
        print("HTTP:", response.status_code)
        print("요청 URL:")

        response.raise_for_status()

        print()
        print("=== 응답 ===")

        try:
            data = response.json()
            print(data)

        except ValueError:
            print("JSON 변환 실패")
            print(response.text)
            return None

        return data

    except requests.exceptions.Timeout:
        print("TIMEOUT")

    except requests.exceptions.RequestException as e:
        print("API 요청 오류:")
        print(e)

    return None


if __name__ == "__main__":
    get_arrival_list()