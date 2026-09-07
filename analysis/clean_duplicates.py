import sqlite3
import shutil
from datetime import datetime

DB_PATH = "data/busflow.db"

# 정상 패턴이 너무 짧으면 우연히 같은 값이 나온 것일 수 있으므로
# 최소 5개 이상의 패턴만 중복으로 정리
MIN_PATTERN_LENGTH = 5


# ==========================================
# 1. DB 백업
# ==========================================
def backup_database():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    backup_path = (
        f"data/busflow_backup_before_cleanup_{timestamp}.db"
    )

    shutil.copy2(DB_PATH, backup_path)

    print()
    print("DB 백업 완료")
    print(backup_path)
    print()

    return backup_path


# ==========================================
# 2. DB 데이터 가져오기
# ==========================================
def get_groups():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            id,
            opr_ymd,
            route_id,
            station_id,
            time_zone,
            congestion
        FROM congestion
        ORDER BY
            opr_ymd,
            route_id,
            station_id,
            id
    """)

    rows = cursor.fetchall()
    conn.close()

    groups = {}

    for (
        row_id,
        opr_ymd,
        route_id,
        station_id,
        time_zone,
        congestion
    ) in rows:

        key = (
            opr_ymd,
            route_id,
            station_id
        )

        if key not in groups:
            groups[key] = []

        groups[key].append({
            "id": row_id,
            "time_zone": time_zone,
            "congestion": congestion
        })

    return groups


# ==========================================
# 3. 완전히 반복되는 패턴 찾기
# ==========================================
def find_repeated_pattern(rows):

    data = [
        (
            row["time_zone"],
            row["congestion"]
        )
        for row in rows
    ]

    total = len(data)

    if total < 2:
        return None

    # 반복 횟수가 가장 큰 경우부터 확인
    # 예:
    # 9개 패턴 × 4회라면
    # 18개 × 2회가 아니라 9개 × 4회로 탐지
    for repeat_count in range(total, 1, -1):

        if total % repeat_count != 0:
            continue

        pattern_length = total // repeat_count

        # 너무 짧은 패턴은 자동 삭제하지 않음
        if pattern_length < MIN_PATTERN_LENGTH:
            continue

        pattern = data[:pattern_length]

        if pattern * repeat_count == data:

            return {
                "repeat_count": repeat_count,
                "pattern_length": pattern_length,
                "total_rows": total
            }

    return None


# ==========================================
# 4. 중복 제거
# ==========================================
def clean_duplicates():

    groups = get_groups()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cleaned_groups = 0
    deleted_rows = 0

    print("=== 중복 데이터 정리 ===")
    print()

    for key, rows in groups.items():

        result = find_repeated_pattern(rows)

        if result is None:
            continue

        repeat_count = result["repeat_count"]
        pattern_length = result["pattern_length"]

        # 첫 번째 정상 패턴은 남김
        # 그 뒤의 반복 데이터만 삭제
        rows_to_delete = rows[pattern_length:]

        ids_to_delete = [
            row["id"]
            for row in rows_to_delete
        ]

        cursor.executemany(
            """
            DELETE FROM congestion
            WHERE id = ?
            """,
            [
                (row_id,)
                for row_id in ids_to_delete
            ]
        )

        cleaned_groups += 1
        deleted_rows += len(ids_to_delete)

        print(
            f"{key[0]} / "
            f"{key[1]} / "
            f"{key[2]}"
        )

        print(
            f"  반복: {repeat_count}회"
        )

        print(
            f"  정상 데이터: {pattern_length}개 유지"
        )

        print(
            f"  중복 데이터: {len(ids_to_delete)}개 삭제"
        )

        print("-" * 60)

    conn.commit()
    conn.close()

    print()
    print("=" * 60)
    print("정리 완료")
    print("정리한 그룹:", cleaned_groups)
    print("삭제한 행:", deleted_rows)
    print("=" * 60)


# ==========================================
# 실행
# ==========================================
if __name__ == "__main__":

    print()
    print("BusFlow 중복 데이터 정리를 시작합니다.")

    backup_database()

    clean_duplicates()