import time
import requests

from config import API_KEY, ROUTES


URL = (
    "https://apis.data.go.kr/1613000/"
    "RouteCongestionLevel/getRouteCongestionLevel"
)


params = {
    "serviceKey": API_KEY,
    "pageNo": 1,
    "numOfRows": 100,
    "opr_ymd": "20260805",

    # 경기 용인
    "ctpv_cd": "41",
    "sgg_cd": "41463",

    "rte_id": ROUTES["5001A"],
    "sttn_id": "4111657",  # 기흥역6번출구

    "dataType": "JSON",
}


print("5001A 기흥역 테스트 시작")

start = time.time()

try:
    response = requests.get(
        URL,
        params=params,
        timeout=120
    )

    print()
    print("응답 성공")
    print("HTTP:", response.status_code)
    print(
        "응답 시간:",
        round(time.time() - start, 2),
        "초"
    )

    print(response.text[:1000])

except requests.exceptions.ReadTimeout:
    print()
    print(
        "READ TIMEOUT:",
        round(time.time() - start, 2),
        "초"
    )

except requests.exceptions.ConnectTimeout:
    print()
    print(
        "CONNECT TIMEOUT:",
        round(time.time() - start, 2),
        "초"
    )

except requests.RequestException as error:
    print()
    print(type(error).__name__)
    print(error)