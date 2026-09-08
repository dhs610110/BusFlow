import os
import sys
import sqlite3
import pandas as pd

# 프로젝트 최상위 BusFlow 폴더를 Python 경로에 추가
PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)

sys.path.append(PROJECT_ROOT)

from config import REALTIME_STATION_NAMES


DB_PATH = os.path.join(
    PROJECT_ROOT,
    "data",
    "realtime.db"
)


DB_PATH = "data/realtime.db"


# ==================================================
# 실시간 위치 데이터 불러오기
# ==================================================

def load_realtime_data():

    connection = sqlite3.connect(DB_PATH)

    df = pd.read_sql_query("""
        SELECT
            collected_at,
            query_time,
            route_name,
            route_id,
            veh_id,
            plate_no,
            station_id,
            station_seq,
            remain_seat_cnt,
            crowded,
            state_cd
        FROM realtime_location
        ORDER BY collected_at
    """, connection)

    connection.close()

    # 정류장 ID → 정류장 이름
    df["station_name"] = (
        df["station_id"]
        .astype(str)
        .map(REALTIME_STATION_NAMES)
    )

    df["station_name"] = (
        df["station_name"]
        .fillna("매핑되지 않은 정류장")
    )

    return df


# ==================================================
# 특정 차량 추적
# ==================================================

def show_vehicle_history(df, veh_id):

    vehicle = df[
        df["veh_id"].astype(str) == str(veh_id)
    ].copy()

    if vehicle.empty:
        print("해당 차량 데이터가 없습니다.")
        return

    vehicle = vehicle.sort_values(
        "collected_at"
    )

    route_name = vehicle.iloc[0]["route_name"]
    plate_no = vehicle.iloc[0]["plate_no"]

    print()
    print("=" * 80)
    print(
        f"{route_name} | "
        f"차량 {veh_id} | "
        f"{plate_no}"
    )
    print("=" * 80)

    for _, row in vehicle.iterrows():

        print(
            f"{row['collected_at']} | "
            f"seq={row['station_seq']} | "
            f"{row['station_name']} | "
            f"잔여 {row['remain_seat_cnt']}석"
        )


# ==================================================
# 차량별 좌석 변화 계산
# ==================================================

def make_vehicle_changes(df):

    df = df.copy()

    df = df.sort_values(
        [
            "route_name",
            "veh_id",
            "collected_at"
        ]
    )

    # 같은 차량의 직전 관측값
    df["previous_seat"] = (
        df.groupby(
            ["route_name", "veh_id"]
        )["remain_seat_cnt"]
        .shift(1)
    )

    df["previous_station"] = (
        df.groupby(
            ["route_name", "veh_id"]
        )["station_name"]
        .shift(1)
    )

    # 현재 좌석 - 이전 좌석
    df["seat_change"] = (
        df["remain_seat_cnt"]
        - df["previous_seat"]
    )

    return df


# ==================================================
# 실제 정류장 이동이 발생한 행만 보기
# ==================================================

def show_station_changes(df):

    # 차량별 이전 좌석/이전 정류장 계산
    changes = make_vehicle_changes(df)

    # 매핑되지 않은 구간 제거
    changes = changes[
        (changes["station_name"] != "매핑되지 않은 정류장")
        &
        (changes["previous_station"] != "매핑되지 않은 정류장")
    ].copy()

    # 같은 정류장에 계속 머문 관측 제거
    changes = changes[
        changes["station_name"]
        != changes["previous_station"]
    ].copy()

    # 첫 관측값 제거
    changes = changes[
        changes["previous_station"].notna()
    ].copy()

    print()
    print("=" * 100)
    print("차량별 정류장 이동 / 좌석 변화")
    print("=" * 100)

    columns = [
        "collected_at",
        "route_name",
        "veh_id",
        "previous_station",
        "station_name",
        "previous_seat",
        "remain_seat_cnt",
        "seat_change",
    ]

    print(
        changes[columns]
        .tail(30)
        .to_string(index=False)
    )

    # ==================================================
# 차량 1대 × 정류장 1개 = 하나의 관측으로 정리
# ==================================================

def make_station_samples(df):

    samples = df[
        df["station_name"] != "매핑되지 않은 정류장"
    ].copy()

    # 수집 시각을 datetime으로 변환
    samples["collected_at"] = pd.to_datetime(
        samples["collected_at"]
    )

    # 날짜 생성
    samples["date"] = (
        samples["collected_at"]
        .dt.date
    )

    # 하루 동안 같은 차량이 같은 정류장에서
    # 여러 번 관측된 경우 마지막 관측 하나만 사용
    samples = (
        samples
        .sort_values("collected_at")
        .drop_duplicates(
            subset=[
                "date",
                "route_name",
                "veh_id",
                "station_id"
            ],
            keep="last"
        )
    )

    return samples

# ==================================================
# 정류장별 잔여좌석 위험도
# ==================================================

def show_station_risk(df):

    samples = make_station_samples(df)

    result = (
        samples
        .groupby(
            ["route_name", "station_name"]
        )
        .agg(
            vehicle_count=("veh_id", "count"),

            avg_seat=(
                "remain_seat_cnt",
                "mean"
            ),

            zero_seat_rate=(
                "remain_seat_cnt",
                lambda x: (x == 0).mean() * 100
            ),

            under_5_rate=(
                "remain_seat_cnt",
                lambda x: (x <= 5).mean() * 100
            ),

            under_10_rate=(
                "remain_seat_cnt",
                lambda x: (x <= 10).mean() * 100
            ),
        )
        .reset_index()
    )

    result["avg_seat"] = (
        result["avg_seat"].round(1)
    )

    result["zero_seat_rate"] = (
        result["zero_seat_rate"].round(1)
    )

    result["under_5_rate"] = (
        result["under_5_rate"].round(1)
    )

    result["under_10_rate"] = (
        result["under_10_rate"].round(1)
    )

    print()
    print("=" * 100)
    print("정류장별 잔여좌석 위험도")
    print("=" * 100)

    print(
        result.to_string(index=False)
    )

    return result

# ==================================================
# 실행
# ==================================================

if __name__ == "__main__":

    df = load_realtime_data()

    print()
    print("전체 실시간 관측값:", len(df))

    print(
        "수집 차량 수:",
        df["veh_id"].nunique()
    )

    print()
    print("노선별 관측값")

    print(
        df.groupby("route_name")
        .size()
    )

    # 우리가 아까 추적한 5001A 차량
    show_vehicle_history(
        df,
        "228010523"
    )

    # 모든 차량의 정류장 이동 분석
    show_station_changes(df)

    show_station_risk(df)
    