import os
import requests
from dotenv import load_dotenv

load_dotenv()

GG_API_KEY = os.getenv("GG_API_KEY")

URL = "https://openapi.gg.go.kr/TBBMSSTATIONDWM"

TARGET_EB_IDS = {
    # 5001A
    "4111680",
    "4111677",
    "4196105",
    "4111675",
    "4111672",
    "4111670",
    "4111669",
    "4111667",
    "4111665",

    # 5003A 고유 구간
    "4196065",
    "4196071",
    "4196073",
    "4196109",
    "4196091",
    "4111877",
    "4111880",
    "4176807",
    "4111762",

    # A 공통 구간
    "4111662",
    "4111660",
    "4111659",
    "4111657",

    # B 서울 구간
    "4151626",
    "4151629",
    "4151633",
    "4151635",
    "4151638",
    "4105915",
}


def get_station_mapping():

    page = 1
    page_size = 1000

    found = {}

    while True:

        params = {
            "KEY": GG_API_KEY,
            "Type": "json",
            "pIndex": page,
            "pSize": page_size,
        }

        response = requests.get(
            URL,
            params=params,
            timeout=30
        )

        response.raise_for_status()

        data = response.json()

        rows = data["TBBMSSTATIONDWM"][1].get(
            "row",
            []
        )

        print(
            f"{page} 페이지 검색 중... "
            f"{len(found)}/{len(TARGET_EB_IDS)}"
        )

        for station in rows:

            eb_id = str(
                station.get("EB_STTN_ID", "")
            )

            if eb_id not in TARGET_EB_IDS:
                continue

            found[eb_id] = {
                "station_id": str(
                    station.get("STTN_ID", "")
                ),
                "name": station.get(
                    "STTN_NM", ""
                ),
                "station_no": station.get(
                    "STTN_NO"
                ),
            }

        # 전부 찾았으면 더 검색할 필요 없음
        if len(found) == len(TARGET_EB_IDS):
            break

        if len(rows) < page_size:
            break

        page += 1

    return found


if __name__ == "__main__":

    mappings = get_station_mapping()

    print()
    print("=" * 80)
    print("정류장 ID 변환 결과")
    print("=" * 80)

    for eb_id in sorted(TARGET_EB_IDS):

        station = mappings.get(eb_id)

        if station is None:

            print(
                f"{eb_id} | 찾지 못함"
            )

            continue

        print(
            f"{eb_id} | "
            f"{station['station_id']} | "
            f"{station['name']} | "
            f"{station['station_no']}"
        )