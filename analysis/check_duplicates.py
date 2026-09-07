import sqlite3
from collections import defaultdict

DB_PATH = "data/busflow.db"


def get_grouped_data():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            opr_ymd,
            route_id,
            station_id,
            time_zone,
            congestion,
            id
        FROM congestion
        ORDER BY
            opr_ymd,
            route_id,
            station_id,
            id
    """)

    rows = cursor.fetchall()
    conn.close()

    grouped = defaultdict(list)

    for opr_ymd, route_id, station_id, time_zone, congestion, row_id in rows:
        key = (
            opr_ymd,
            route_id,
            station_id
        )

        grouped[key].append(
            (time_zone, congestion)
        )

    return grouped


def find_repeated_pattern(data):
    total = len(data)

    if total < 2:
        return None

    # 반복 횟수가 가장 큰 것부터 검사
    # = 가장 짧은 원본 패턴을 찾음
    for repeat_count in range(total, 1, -1):

        if total % repeat_count != 0:
            continue

        pattern_length = total // repeat_count
        pattern = data[:pattern_length]

        if pattern * repeat_count == data:
            return {
                "repeat_count": repeat_count,
                "pattern_length": pattern_length,
                "total_rows": total,
                "pattern": pattern
            }

    return None


def check_duplicates():
    grouped = get_grouped_data()

    suspicious = []

    for key, data in grouped.items():

        result = find_repeated_pattern(data)

        if result is not None:
            suspicious.append({
                "opr_ymd": key[0],
                "route_id": key[1],
                "station_id": key[2],
                **result
            })

    return suspicious


if __name__ == "__main__":

    suspicious = check_duplicates()

    print()
    print("=== 중복 의심 데이터 ===")
    print()

    if not suspicious:
        print("중복 패턴이 발견되지 않았습니다.")

    else:

        for item in suspicious:

            print(
                f"{item['opr_ymd']} / "
                f"{item['route_id']} / "
                f"{item['station_id']}"
            )

            print(
                f"반복 횟수: {item['repeat_count']}회"
            )

            print(
                f"전체 행: {item['total_rows']}개"
            )

            print(
                f"정상 예상 행: {item['pattern_length']}개"
            )

            print(
                "첫 패턴:",
                item["pattern"][:20]
            )

            print("-" * 60)

        print()
        print("중복 의심 그룹 수:", len(suspicious))