import os
import sys
import sqlite3

import pandas as pd


# ==================================================
# 프로젝트 경로 설정
# ==================================================

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

sys.path.append(PROJECT_ROOT)

from config import REALTIME_STATION_NAMES


DB_PATH = os.path.join(
    PROJECT_ROOT,
    "data",
    "realtime.db"
)


# ==================================================
# 퇴근 분석 설정
# ==================================================

TARGET_ROUTES = [
    "5001B",
    "5003B",
]

EVENING_START_HOUR = 17
EVENING_END_HOUR = 22

EVENING_BOARDING_STATIONS = [
    "신논현역",
    "강남역",
    "우성아파트",
    "뱅뱅사거리",
    "양재역",
    "교육개발원입구",
]

# ==================================================
# 실시간 위치 데이터 불러오기
# ==================================================

def load_realtime_data():

    connection = sqlite3.connect(
        DB_PATH
    )

    df = pd.read_sql_query(
        """
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
        """,
        connection
    )

    connection.close()

    # ----------------------------------------------
    # 시간 형식 변환
    # ----------------------------------------------

    df["collected_at"] = pd.to_datetime(
        df["collected_at"]
    )

    df["date"] = (
        df["collected_at"]
        .dt.date
    )

    df["hour"] = (
        df["collected_at"]
        .dt.hour
    )

    # ----------------------------------------------
    # 정류장 이름 매핑
    # ----------------------------------------------

    df["station_name"] = (
        df["station_id"]
        .astype(str)
        .map(
            REALTIME_STATION_NAMES
        )
    )

    df["station_name"] = (
        df["station_name"]
        .fillna(
            "매핑되지 않은 정류장"
        )
    )

    return df


# ==================================================
# 퇴근 데이터 필터링
# ==================================================

def filter_evening_data(df):

    evening = df[
        df["route_name"].isin(
            TARGET_ROUTES
        )
    ].copy()

    evening = evening[
        (
            evening["hour"]
            >= EVENING_START_HOUR
        )
        &
        (
            evening["hour"]
            <= EVENING_END_HOUR
        )
    ].copy()

    return evening


# ==================================================
# 특정 차량 추적
# ==================================================

def show_vehicle_history(
    df,
    veh_id
):

    vehicle = df[
        df["veh_id"].astype(str)
        == str(veh_id)
    ].copy()

    if vehicle.empty:
        print(
            "해당 차량 데이터가 없습니다."
        )
        return

    vehicle = vehicle.sort_values(
        "collected_at"
    )

    route_name = (
        vehicle.iloc[0][
            "route_name"
        ]
    )

    plate_no = (
        vehicle.iloc[0][
            "plate_no"
        ]
    )

    print()
    print("=" * 100)

    print(
        f"{route_name} | "
        f"차량 {veh_id} | "
        f"{plate_no}"
    )

    print("=" * 100)

    for _, row in vehicle.iterrows():

        print(
            f"{row['collected_at']} | "
            f"seq={row['station_seq']} | "
            f"{row['station_name']} | "
            f"잔여 {row['remain_seat_cnt']}석"
        )


# ==================================================
# 차량별 좌석 변화
# ==================================================

def make_vehicle_changes(df):

    changes = df.copy()

    changes = changes.sort_values(
        [
            "date",
            "route_name",
            "veh_id",
            "collected_at",
        ]
    )

    group_columns = [
        "date",
        "route_name",
        "veh_id",
    ]

    changes["previous_seat"] = (
        changes.groupby(
            group_columns
        )["remain_seat_cnt"]
        .shift(1)
    )

    changes["previous_station"] = (
        changes.groupby(
            group_columns
        )["station_name"]
        .shift(1)
    )

    changes["previous_station_seq"] = (
        changes.groupby(
            group_columns
        )["station_seq"]
        .shift(1)
    )

    changes["seat_change"] = (
        changes[
            "remain_seat_cnt"
        ]
        -
        changes[
            "previous_seat"
        ]
    )

    return changes


# ==================================================
# 실제 정류장 이동이 발생한 행
# ==================================================

def show_station_changes(df):

    changes = make_vehicle_changes(
        df
    )

    # 매핑되지 않은 정류장 제거
    changes = changes[
        (
            changes["station_name"]
            != "매핑되지 않은 정류장"
        )
        &
        (
            changes["previous_station"]
            != "매핑되지 않은 정류장"
        )
    ].copy()

    # 실제 정류장 이동만
    changes = changes[
        changes["station_name"]
        != changes["previous_station"]
    ].copy()

    # 첫 번째 관측 제거
    changes = changes[
        changes[
            "previous_station"
        ].notna()
    ].copy()

    print()
    print("=" * 110)
    print(
        "차량별 정류장 이동 / 좌석 변화"
    )
    print("=" * 110)

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
        .tail(40)
        .to_string(
            index=False
        )
    )

    return changes


# ==================================================
# 차량 1대 × 정류장 1개 = 하나의 표본
# ==================================================

def make_station_samples(df):

    samples = df[
        df["station_name"]
        != "매핑되지 않은 정류장"
    ].copy()

    # 같은 날짜 / 같은 차량 /
    # 같은 정류장에서 여러 번 찍힌 경우
    # 마지막 관측 하나만 사용
    samples = (
        samples
        .sort_values(
            "collected_at"
        )
        .drop_duplicates(
            subset=[
                "date",
                "route_name",
                "veh_id",
                "station_id",
            ],
            keep="last"
        )
    )

    return samples


# ==================================================
# 정류장별 잔여좌석 위험도
# ==================================================

def show_station_risk(df):

    samples = make_station_samples(
        df
    )

    if samples.empty:

        print()
        print(
            "퇴근시간 정류장 데이터가 없습니다."
        )

        return pd.DataFrame()

    result = (
        samples
        .groupby(
            [
                "route_name",
                "station_name",
            ]
        )
        .agg(
            vehicle_count=(
                "veh_id",
                "count"
            ),

            avg_seat=(
                "remain_seat_cnt",
                "mean"
            ),

            median_seat=(
                "remain_seat_cnt",
                "median"
            ),

            zero_seat_rate=(
                "remain_seat_cnt",
                lambda x:
                    (x == 0)
                    .mean()
                    * 100
            ),

            under_5_rate=(
                "remain_seat_cnt",
                lambda x:
                    (x <= 5)
                    .mean()
                    * 100
            ),

            under_10_rate=(
                "remain_seat_cnt",
                lambda x:
                    (x <= 10)
                    .mean()
                    * 100
            ),
        )
        .reset_index()
    )

    round_columns = [
        "avg_seat",
        "median_seat",
        "zero_seat_rate",
        "under_5_rate",
        "under_10_rate",
    ]

    result[
        round_columns
    ] = (
        result[
            round_columns
        ]
        .round(1)
    )

    print()
    print("=" * 110)
    print(
        "퇴근시간 정류장별 잔여좌석 위험도"
    )
    print("=" * 110)

    print(
        result.to_string(
            index=False
        )
    )

    return result


# ==================================================
# 시간대 × 정류장 좌석 위험도
# ==================================================

def show_hourly_station_risk(df):

    samples = make_station_samples(
        df
    )

    if samples.empty:
        return pd.DataFrame()

    result = (
        samples
        .groupby(
            [
                "route_name",
                "hour",
                "station_name",
            ]
        )
        .agg(
            vehicle_count=(
                "veh_id",
                "count"
            ),

            avg_seat=(
                "remain_seat_cnt",
                "mean"
            ),

            median_seat=(
                "remain_seat_cnt",
                "median"
            ),

            under_5_rate=(
                "remain_seat_cnt",
                lambda x:
                    (x <= 5)
                    .mean()
                    * 100
            ),

            under_10_rate=(
                "remain_seat_cnt",
                lambda x:
                    (x <= 10)
                    .mean()
                    * 100
            ),
        )
        .reset_index()
    )

    result[
        [
            "avg_seat",
            "median_seat",
            "under_5_rate",
            "under_10_rate",
        ]
    ] = (
        result[
            [
                "avg_seat",
                "median_seat",
                "under_5_rate",
                "under_10_rate",
            ]
        ]
        .round(1)
    )

    print()
    print("=" * 120)

    print(
        "퇴근시간 시간대 × 정류장 "
        "잔여좌석 위험도"
    )

    print("=" * 120)

    print(
        result.to_string(
            index=False
        )
    )

    return result


# ==================================================
# 시간대별 노선 비교
# ==================================================

def show_route_hour_summary(df):

    samples = make_station_samples(
        df
    )

    if samples.empty:
        return pd.DataFrame()

    # 퇴근 시 실제 탑승 정류장만 사용
    boarding_samples = samples[
        samples["station_name"].isin(
            EVENING_BOARDING_STATIONS
        )
    ].copy()

    if boarding_samples.empty:
        return pd.DataFrame()

    result = (
        boarding_samples
        .groupby(
            [
                "route_name",
                "hour",
            ]
        )
        .agg(
            observation_count=(
                "veh_id",
                "count"
            ),

            avg_seat=(
                "remain_seat_cnt",
                "mean"
            ),

            median_seat=(
                "remain_seat_cnt",
                "median"
            ),

            under_5_rate=(
                "remain_seat_cnt",
                lambda x:
                    (x <= 5)
                    .mean()
                    * 100
            ),
        )
        .reset_index()
    )

    result[
        [
            "avg_seat",
            "median_seat",
            "under_5_rate",
        ]
    ] = (
        result[
            [
                "avg_seat",
                "median_seat",
                "under_5_rate",
            ]
        ]
        .round(1)
    )

    print()
    print("=" * 100)

    print(
        "퇴근시간 서울 탑승 정류장 기준 "
        "노선별 / 시간대별 좌석 비교"
    )

    print("=" * 100)

    print(
        result.to_string(
            index=False
        )
    )

    return result

# ==================================================
# 좌석이 급격히 줄어드는 구간
# ==================================================

def show_seat_drop_sections(df):

    changes = make_vehicle_changes(
        df
    )

    changes = changes[
        changes[
            "previous_station"
        ].notna()
    ].copy()

    changes = changes[
        (
            changes["station_name"]
            != "매핑되지 않은 정류장"
        )
        &
        (
            changes["previous_station"]
            != "매핑되지 않은 정류장"
        )
    ].copy()

    changes = changes[
        changes["station_name"]
        != changes["previous_station"]
    ].copy()

    if changes.empty:
        return pd.DataFrame()

    result = (
        changes
        .groupby(
            [
                "route_name",
                "previous_station",
                "station_name",
            ]
        )
        .agg(
            sample_count=(
                "seat_change",
                "count"
            ),

            avg_seat_change=(
                "seat_change",
                "mean"
            ),

            median_seat_change=(
                "seat_change",
                "median"
            ),
        )
        .reset_index()
    )

    result[
        [
            "avg_seat_change",
            "median_seat_change",
        ]
    ] = (
        result[
            [
                "avg_seat_change",
                "median_seat_change",
            ]
        ]
        .round(1)
    )

    # 가장 좌석이 많이 줄어드는 구간부터
    result = result.sort_values(
        "avg_seat_change"
    )

    print()
    print("=" * 120)

    print(
        "좌석이 많이 감소하는 정류장 구간"
    )

    print("=" * 120)

    print(
        result
        .head(30)
        .to_string(
            index=False
        )
    )

    return result


# ==================================================
# 분석 결과 Excel 저장
# ==================================================

def save_results(
    station_risk,
    hourly_station_risk,
    route_hour_summary,
    seat_drop_sections,
):

    output_path = os.path.join(
        PROJECT_ROOT,
        "analysis",
        "realtime_evening_analysis.xlsx"
    )

    with pd.ExcelWriter(
        output_path
    ) as writer:

        station_risk.to_excel(
            writer,
            sheet_name="station_risk",
            index=False
        )

        hourly_station_risk.to_excel(
            writer,
            sheet_name="hour_station",
            index=False
        )

        route_hour_summary.to_excel(
            writer,
            sheet_name="route_hour",
            index=False
        )

        seat_drop_sections.to_excel(
            writer,
            sheet_name="seat_drop",
            index=False
        )

    print()
    print(
        "분석 결과 저장:"
    )
    print(
        output_path
    )


# ==================================================
# 실행
# ==================================================

if __name__ == "__main__":

    df = load_realtime_data()

    print()
    print(
        "전체 실시간 관측값:",
        len(df)
    )

    print(
        "전체 차량 수:",
        df["veh_id"].nunique()
    )

    # ----------------------------------------------
    # 퇴근 데이터만
    # ----------------------------------------------

    evening_df = filter_evening_data(
        df
    )

    print()
    print(
        "퇴근시간 관측값:",
        len(evening_df)
    )

    print(
        "퇴근시간 차량 수:",
        evening_df[
            "veh_id"
        ].nunique()
    )

    print()
    print(
        "퇴근시간 노선별 관측값"
    )

    print(
        evening_df
        .groupby(
            "route_name"
        )
        .size()
    )

    # ----------------------------------------------
    # 분석
    # ----------------------------------------------

    show_station_changes(
        evening_df
    )

    station_risk = (
        show_station_risk(
            evening_df
        )
    )

    hourly_station_risk = (
        show_hourly_station_risk(
            evening_df
        )
    )

    route_hour_summary = (
        show_route_hour_summary(
            evening_df
        )
    )

    seat_drop_sections = (
        show_seat_drop_sections(
            evening_df
        )
    )

    # ----------------------------------------------
    # Excel 저장
    # ----------------------------------------------

    save_results(
        station_risk,
        hourly_station_risk,
        route_hour_summary,
        seat_drop_sections,
    )