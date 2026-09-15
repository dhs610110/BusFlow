import os
import sqlite3
import pandas as pd


# ==================================================
# 기본 경로
# ==================================================

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

DB_PATH = os.path.join(
    PROJECT_ROOT,
    "data",
    "realtime.db"
)

OUTPUT_PATH = os.path.join(
    PROJECT_ROOT,
    "analysis",
    "seat_drop_analysis.xlsx"
)


# ==================================================
# 서울 B 방향 주요 정류장
#
# realtime_location DB 기준
# ==================================================

SEOUL_B_STATIONS = {
    "121000002": "교육개발원입구",
    "121000004": "양재역",
    "121000006": "뱅뱅사거리",
    "121000008": "우성아파트",
    "121000010": "강남역",
    "122000616": "신논현역",
}


TARGET_ROUTES = [
    "5001B",
    "5003B",
]


# ==================================================
# DB 불러오기
# ==================================================

def load_data():

    connection = sqlite3.connect(
        DB_PATH
    )

    df = pd.read_sql_query(
        """
        SELECT
            collected_at,
            route_name,
            veh_id,
            station_id,
            station_seq,
            remain_seat_cnt
        FROM realtime_location
        WHERE route_name IN ('5001B', '5003B')
        ORDER BY
            route_name,
            veh_id,
            collected_at
        """,
        connection
    )

    connection.close()

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

    df["station_id"] = (
        df["station_id"]
        .astype(str)
    )

    df["remain_seat_cnt"] = pd.to_numeric(
        df["remain_seat_cnt"],
        errors="coerce"
    )

    # 서울 주요 정류장만
    df = df[
        df["station_id"].isin(
            SEOUL_B_STATIONS.keys()
        )
    ].copy()

    df["station_name"] = (
        df["station_id"]
        .map(
            SEOUL_B_STATIONS
        )
    )

    return df


# ==================================================
# 차량 운행 회차 분리
# ==================================================

def assign_trip_ids(df):

    df = df.copy()

    df = df.sort_values(
        [
            "route_name",
            "veh_id",
            "collected_at",
        ]
    )

    group_cols = [
        "route_name",
        "veh_id",
    ]

    df["prev_time"] = (
        df.groupby(
            group_cols
        )["collected_at"]
        .shift(1)
    )

    df["prev_seq"] = (
        df.groupby(
            group_cols
        )["station_seq"]
        .shift(1)
    )

    df["time_gap_min"] = (
        (
            df["collected_at"]
            -
            df["prev_time"]
        )
        .dt.total_seconds()
        / 60
    )

    # 새로운 회차 판단
    #
    # 1. 첫 관측
    # 2. 45분 이상 끊김
    # 3. station_seq가 크게 뒤로 돌아감
    df["new_trip"] = (
        df["prev_time"].isna()
        |
        (
            df["time_gap_min"]
            >= 45
        )
        |
        (
            df["station_seq"]
            <
            df["prev_seq"] - 5
        )
    ).astype(int)

    df["trip_no"] = (
        df.groupby(
            group_cols
        )["new_trip"]
        .cumsum()
    )

    return df


# ==================================================
# 각 차량/회차/정류장에서 대표값 선택
#
# 같은 정류장이 1~2분마다 반복되므로
# 마지막 관측을 대표값으로 사용
# ==================================================

def make_station_pass_samples(df):

    df = df.copy()

    station_samples = (
        df.sort_values(
            "collected_at"
        )
        .groupby(
            [
                "route_name",
                "veh_id",
                "trip_no",
                "station_id",
                "station_seq",
                "station_name",
            ],
            as_index=False
        )
        .last()
    )

    station_samples = (
        station_samples
        .sort_values(
            [
                "route_name",
                "veh_id",
                "trip_no",
                "station_seq",
            ]
        )
    )

    return station_samples


# ==================================================
# 정류장 간 좌석 변화 계산
# ==================================================

def calculate_seat_drops(
    station_samples
):

    df = station_samples.copy()

    group_cols = [
        "route_name",
        "veh_id",
        "trip_no",
    ]

    df["prev_station_id"] = (
        df.groupby(
            group_cols
        )["station_id"]
        .shift(1)
    )

    df["prev_station_name"] = (
        df.groupby(
            group_cols
        )["station_name"]
        .shift(1)
    )

    df["prev_station_seq"] = (
        df.groupby(
            group_cols
        )["station_seq"]
        .shift(1)
    )

    df["prev_seat"] = (
        df.groupby(
            group_cols
        )["remain_seat_cnt"]
        .shift(1)
    )

    df["prev_time"] = (
        df.groupby(
            group_cols
        )["collected_at"]
        .shift(1)
    )

    # ----------------------------------------------
    # 연속 정류장인지 확인
    # ----------------------------------------------

    df["seq_gap"] = (
        df["station_seq"]
        -
        df["prev_station_seq"]
    )

    # 주요 서울 정류장은 DB상 연속 seq
    df = df[
        df["seq_gap"] == 1
    ].copy()

    # ----------------------------------------------
    # 좌석 변화
    #
    # positive = 좌석 감소
    # negative = 좌석 증가
    # ----------------------------------------------

    df["seat_drop"] = (
        df["prev_seat"]
        -
        df["remain_seat_cnt"]
    )

    df["seat_change"] = (
        df["remain_seat_cnt"]
        -
        df["prev_seat"]
    )

    df["travel_min"] = (
        (
            df["collected_at"]
            -
            df["prev_time"]
        )
        .dt.total_seconds()
        / 60
    )

    # 말도 안 되는 매칭 제거
    df = df[
        (
            df["travel_min"] > 0
        )
        &
        (
            df["travel_min"] <= 30
        )
    ].copy()

    # ----------------------------------------------
    # 구간 이름
    # ----------------------------------------------

    df["section"] = (
        df["prev_station_name"]
        +
        " → "
        +
        df["station_name"]
    )

    # 구간 시작 시간 기준
    df["hour"] = (
        df["prev_time"]
        .dt.hour
    )

    df["date"] = (
        df["prev_time"]
        .dt.date
    )

    return df


# ==================================================
# 전체 구간 분석
# ==================================================

def make_section_summary(
    drops
):

    summary = (
        drops
        .groupby(
            [
                "route_name",
                "section",
                "prev_station_name",
                "station_name",
            ]
        )
        .agg(

            sample_count=(
                "seat_drop",
                "count"
            ),

            avg_seat_before=(
                "prev_seat",
                "mean"
            ),

            avg_seat_after=(
                "remain_seat_cnt",
                "mean"
            ),

            avg_seat_drop=(
                "seat_drop",
                "mean"
            ),

            median_seat_drop=(
                "seat_drop",
                "median"
            ),

            max_seat_drop=(
                "seat_drop",
                "max"
            ),

            seat_drop_rate=(
                "seat_drop",
                lambda x:
                    (
                        x > 0
                    ).mean()
                    * 100
            ),

            drop_5_plus_rate=(
                "seat_drop",
                lambda x:
                    (
                        x >= 5
                    ).mean()
                    * 100
            ),

            drop_10_plus_rate=(
                "seat_drop",
                lambda x:
                    (
                        x >= 10
                    ).mean()
                    * 100
            ),

            avg_travel_min=(
                "travel_min",
                "mean"
            ),

        )
        .reset_index()
    )

    numeric_cols = [
        "avg_seat_before",
        "avg_seat_after",
        "avg_seat_drop",
        "median_seat_drop",
        "max_seat_drop",
        "seat_drop_rate",
        "drop_5_plus_rate",
        "drop_10_plus_rate",
        "avg_travel_min",
    ]

    summary[
        numeric_cols
    ] = (
        summary[
            numeric_cols
        ]
        .round(1)
    )

    # 좌석 감소량 큰 순
    summary = summary.sort_values(
        [
            "route_name",
            "avg_seat_drop",
        ],
        ascending=[
            True,
            False,
        ]
    )

    return summary


# ==================================================
# 시간대별 분석
# ==================================================

def make_hourly_summary(
    drops
):

    summary = (
        drops
        .groupby(
            [
                "route_name",
                "hour",
                "section",
            ]
        )
        .agg(

            sample_count=(
                "seat_drop",
                "count"
            ),

            avg_seat_before=(
                "prev_seat",
                "mean"
            ),

            avg_seat_after=(
                "remain_seat_cnt",
                "mean"
            ),

            avg_seat_drop=(
                "seat_drop",
                "mean"
            ),

            median_seat_drop=(
                "seat_drop",
                "median"
            ),

            max_seat_drop=(
                "seat_drop",
                "max"
            ),

            drop_5_plus_rate=(
                "seat_drop",
                lambda x:
                    (
                        x >= 5
                    ).mean()
                    * 100
            ),

            drop_10_plus_rate=(
                "seat_drop",
                lambda x:
                    (
                        x >= 10
                    ).mean()
                    * 100
            ),

        )
        .reset_index()
    )

    numeric_cols = [
        "avg_seat_before",
        "avg_seat_after",
        "avg_seat_drop",
        "median_seat_drop",
        "max_seat_drop",
        "drop_5_plus_rate",
        "drop_10_plus_rate",
    ]

    summary[
        numeric_cols
    ] = (
        summary[
            numeric_cols
        ]
        .round(1)
    )

    return summary.sort_values(
        [
            "route_name",
            "hour",
            "avg_seat_drop",
        ],
        ascending=[
            True,
            True,
            False,
        ]
    )


# ==================================================
# 시간대별 가장 위험한 구간
# ==================================================

def make_worst_sections(
    hourly_summary
):

    if hourly_summary.empty:
        return pd.DataFrame()

    # 표본 최소 2개
    filtered = hourly_summary[
        hourly_summary[
            "sample_count"
        ]
        >= 2
    ].copy()

    if filtered.empty:
        return pd.DataFrame()

    # 노선 × 시간대별
    # 평균 좌석 감소량 가장 큰 구간
    idx = (
        filtered
        .groupby(
            [
                "route_name",
                "hour",
            ]
        )[
            "avg_seat_drop"
        ]
        .idxmax()
    )

    worst = (
        filtered
        .loc[idx]
        .sort_values(
            [
                "route_name",
                "hour",
            ]
        )
    )

    return worst


# ==================================================
# 콘솔 출력
# ==================================================

def print_results(
    section_summary,
    hourly_summary,
    worst_sections,
):

    print()
    print("=" * 90)
    print("전체 구간별 좌석 감소 분석")
    print("=" * 90)

    if section_summary.empty:
        print("분석 가능한 데이터 없음")
    else:
        print(
            section_summary
            .to_string(
                index=False
            )
        )

    print()
    print("=" * 90)
    print("퇴근 핵심 시간대 17~20시")
    print("=" * 90)

    evening = hourly_summary[
        hourly_summary["hour"]
        .between(
            17,
            20
        )
    ]

    if evening.empty:
        print("17~20시 분석 데이터 없음")
    else:
        print(
            evening[
                [
                    "route_name",
                    "hour",
                    "section",
                    "sample_count",
                    "avg_seat_before",
                    "avg_seat_after",
                    "avg_seat_drop",
                    "drop_5_plus_rate",
                ]
            ]
            .to_string(
                index=False
            )
        )

    print()
    print("=" * 90)
    print("시간대별 좌석 감소 최대 구간")
    print("=" * 90)

    if worst_sections.empty:
        print("데이터 없음")
    else:
        print(
            worst_sections[
                [
                    "route_name",
                    "hour",
                    "section",
                    "sample_count",
                    "avg_seat_drop",
                    "drop_5_plus_rate",
                ]
            ]
            .to_string(
                index=False
            )
        )


# ==================================================
# 저장
# ==================================================

def save_excel(
    drops,
    section_summary,
    hourly_summary,
    worst_sections,
):

    with pd.ExcelWriter(
        OUTPUT_PATH
    ) as writer:

        drops.to_excel(
            writer,
            sheet_name="raw_drops",
            index=False
        )

        section_summary.to_excel(
            writer,
            sheet_name="section_summary",
            index=False
        )

        hourly_summary.to_excel(
            writer,
            sheet_name="hourly_summary",
            index=False
        )

        worst_sections.to_excel(
            writer,
            sheet_name="worst_sections",
            index=False
        )

    print()
    print(
        "저장 완료:",
        OUTPUT_PATH
    )


# ==================================================
# 실행
# ==================================================

if __name__ == "__main__":

    print()
    print("=" * 90)
    print("Time Keeper 좌석 감소 구간 분석")
    print("=" * 90)

    df = load_data()

    print(
        "서울 B구간 realtime_location 행:",
        len(df)
    )

    df = assign_trip_ids(
        df
    )

    station_samples = (
        make_station_pass_samples(
            df
        )
    )

    print(
        "차량/회차/정류장 대표 관측:",
        len(station_samples)
    )

    drops = calculate_seat_drops(
        station_samples
    )

    print(
        "연속 정류장 좌석 변화 표본:",
        len(drops)
    )

    section_summary = (
        make_section_summary(
            drops
        )
    )

    hourly_summary = (
        make_hourly_summary(
            drops
        )
    )

    worst_sections = (
        make_worst_sections(
            hourly_summary
        )
    )

    print_results(
        section_summary,
        hourly_summary,
        worst_sections,
    )

    save_excel(
        drops,
        section_summary,
        hourly_summary,
        worst_sections,
    )