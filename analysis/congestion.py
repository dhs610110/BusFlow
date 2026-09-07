import sqlite3

DB_PATH = "data/busflow.db"


# 특정 조건의 평균 혼잡도 계산
def get_average_congestion(
    route_id,
    station_id,
    day_name,
    time_zone
):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT AVG(congestion), COUNT(*)
        FROM congestion
        WHERE route_id = ?
          AND station_id = ?
          AND dow_nm = ?
          AND time_zone = ?
    """, (
        route_id,
        station_id,
        day_name,
        time_zone
    ))

    average, count = cursor.fetchone()

    conn.close()

    return average, count


# 특정 조건의 개별 혼잡도 데이터 가져오기
def get_congestion_values(
    route_id,
    station_id,
    day_name,
    time_zone
):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            opr_ymd,
            congestion
        FROM congestion
        WHERE route_id = ?
          AND station_id = ?
          AND dow_nm = ?
          AND time_zone = ?
        ORDER BY opr_ymd, id
    """, (
        route_id,
        station_id,
        day_name,
        time_zone
    ))

    rows = cursor.fetchall()

    conn.close()

    return rows
# 날짜별 + 시간대별 혼잡도 통계
def get_daily_congestion_stats(
    route_id,
    station_id
):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            opr_ymd,
            dow_nm,
            time_zone,
            ROUND(AVG(
                CASE
                    WHEN congestion > 100 THEN 100
                    ELSE congestion
                END
            ), 1) AS avg_congestion,
            MIN(congestion) AS min_congestion,
            MIN(MAX(congestion), 100) AS max_congestion,
            COUNT(*) AS data_count
        FROM congestion
        WHERE route_id = ?
          AND station_id = ?
        GROUP BY opr_ymd, dow_nm, time_zone
        ORDER BY opr_ymd, time_zone
    """, (
        route_id,
        station_id
    ))

    rows = cursor.fetchall()

    conn.close()

    return rows


# 특정 조건의 혼잡도 통계 계산
def get_congestion_stats(
    route_id,
    station_id,
    day_name,
    time_zone
):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            ROUND(AVG(congestion), 1),
            MIN(congestion),
            MAX(congestion),
            MAX(congestion) - MIN(congestion),
            COUNT(*)
        FROM congestion
        WHERE route_id = ?
          AND station_id = ?
          AND dow_nm = ?
          AND time_zone = ?
    """, (
        route_id,
        station_id,
        day_name,
        time_zone
    ))

    row = cursor.fetchone()

    conn.close()

    return row


if __name__ == "__main__":

    stats = get_daily_congestion_stats(
        route_id="41006433",   # 5001A
        station_id="4111657"   # 기흥역
    )

    print("=== 기흥역 날짜별 / 시간대별 혼잡도 ===")

    for row in stats:
        date, day, hour, avg, min_cong, max_cong, count = row

        print(
            f"{date} | {day} | {hour}시 | "
            f"평균 {avg} | "
            f"최소 {min_cong} | "
            f"최대 {max_cong} | "
            f"{count}개"
        )