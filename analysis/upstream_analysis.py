import os
import sqlite3
import pandas as pd


# ==================================================
# 프로젝트 경로
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
    "upstream_analysis.xlsx"
)


# ==================================================
# 선행 정류장 → 탑승 정류장
# ==================================================

UPSTREAM_PAIRS = {

    # ----------------------------------------------
    # 5003A 출근
    # ----------------------------------------------

    "5003A": [
        ("동백이마트", "어정역"),
        ("어정역", "어정풍림아파트"),
        ("어정풍림아파트", "갈천마을"),
        ("갈천마을", "지석역"),
        ("지석역", "어정삼거리.강남마을"),
        ("어정삼거리.강남마을", "강남대역.강남대입구"),
        ("강남대역.강남대입구", "수원컨트리클럽"),
        ("수원컨트리클럽", "기흥역"),
    ],

    # ----------------------------------------------
    # 5001A 출근
    # ----------------------------------------------

    "5001A": [
        ("삼가역.두산위브", "효자고개.용인정신병원"),
        ("효자고개.용인정신병원", "인정프린스.흥국생명연수원"),
        ("인정프린스.흥국생명연수원", "수원동.쌍용아파트"),
        ("수원동.쌍용아파트", "상지석.대우.진흥아파트"),
        ("상지석.대우.진흥아파트", "현대출고장.고인돌"),
        ("현대출고장.고인돌", "어정삼거리.강남마을"),
        ("어정삼거리.강남마을", "강남대역.강남대입구"),
        ("강남대역.강남대입구", "수원컨트리클럽"),
        ("수원컨트리클럽", "기흥역"),
    ],

    # ----------------------------------------------
    # B 퇴근
    # 버스 진행 순서 기준
    # ----------------------------------------------

    "5001B": [
        ("교육개발원입구", "양재역"),
        ("양재역", "뱅뱅사거리"),
        ("뱅뱅사거리", "우성아파트"),
        ("우성아파트", "강남역"),
        ("강남역", "신논현역"),
    ],

    "5003B": [
        ("교육개발원입구", "양재역"),
        ("양재역", "뱅뱅사거리"),
        ("뱅뱅사거리", "우성아파트"),
        ("우성아파트", "강남역"),
        ("강남역", "신논현역"),
    ],
}


# ==================================================
# DB
# ==================================================

def get_connection():

    connection = sqlite3.connect(
        DB_PATH
    )

    return connection


# ==================================================
# 실시간 도착정보 통합
# ==================================================

def load_realtime_arrivals():

    connection = get_connection()

    df_a = pd.read_sql_query(
        """
        SELECT *
        FROM realtime_arrival_a
        """,
        connection
    )

    df_b = pd.read_sql_query(
        """
        SELECT *
        FROM realtime_arrival_b
        """,
        connection
    )

    connection.close()

    df = pd.concat(
        [
            df_a.assign(direction="A"),
            df_b.assign(direction="B"),
        ],
        ignore_index=True
    )

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

    return df


# ==================================================
# 1번 + 2번 버스를 차량 단위 long format으로 변환
# ==================================================

def make_vehicle_rows(df):

    first = df[
        [
            "collected_at",
            "date",
            "hour",
            "route_name",
            "station_id",
            "station_name",
            "veh_id_1",
            "predict_time_sec_1",
            "remain_seat_cnt_1",
        ]
    ].copy()

    first.columns = [
        "collected_at",
        "date",
        "hour",
        "route_name",
        "station_id",
        "station_name",
        "veh_id",
        "predict_time_sec",
        "remain_seat_cnt",
    ]

    second = df[
        [
            "collected_at",
            "date",
            "hour",
            "route_name",
            "station_id",
            "station_name",
            "veh_id_2",
            "predict_time_sec_2",
            "remain_seat_cnt_2",
        ]
    ].copy()

    second.columns = [
        "collected_at",
        "date",
        "hour",
        "route_name",
        "station_id",
        "station_name",
        "veh_id",
        "predict_time_sec",
        "remain_seat_cnt",
    ]

    vehicles = pd.concat(
        [first, second],
        ignore_index=True
    )

    vehicles = vehicles[
        vehicles["veh_id"].notna()
    ].copy()

    vehicles["veh_id"] = (
        vehicles["veh_id"]
        .astype(str)
    )

    vehicles["remain_seat_cnt"] = (
        pd.to_numeric(
            vehicles["remain_seat_cnt"],
            errors="coerce"
        )
    )

    return vehicles


# ==================================================
# pair 좌석 변화 분석
# ==================================================

def analyze_upstream_pairs(vehicles):

    results = []

    # --------------------------------------------------
    # 설정
    # --------------------------------------------------

    # 같은 차량이라도 이 시간 이상 관측이 끊기면
    # 다른 운행 회차라고 간주
    TRIP_GAP_MIN = 45

    # upstream → boarding 매칭 허용 최대 시간
    MAX_PAIR_MIN = 30

    # --------------------------------------------------
    # 기본 정리
    # --------------------------------------------------

    vehicles = vehicles.copy()

    vehicles["collected_at"] = pd.to_datetime(
        vehicles["collected_at"]
    )

    vehicles["date"] = (
        vehicles["collected_at"]
        .dt.date
    )

    vehicles = vehicles.sort_values(
        [
            "route_name",
            "date",
            "veh_id",
            "collected_at",
        ]
    )

    # --------------------------------------------------
    # 차량별 운행 회차(trip) 분리
    # --------------------------------------------------

    vehicles["prev_time"] = (
        vehicles
        .groupby(
            [
                "route_name",
                "date",
                "veh_id",
            ]
        )["collected_at"]
        .shift(1)
    )

    vehicles["gap_min"] = (
        (
            vehicles["collected_at"]
            -
            vehicles["prev_time"]
        )
        .dt.total_seconds()
        / 60
    )

    vehicles["new_trip"] = (
        vehicles["prev_time"].isna()
        |
        (
            vehicles["gap_min"]
            >= TRIP_GAP_MIN
        )
    ).astype(int)

    vehicles["trip_no"] = (
        vehicles
        .groupby(
            [
                "route_name",
                "date",
                "veh_id",
            ]
        )["new_trip"]
        .cumsum()
    )

    # --------------------------------------------------
    # pair 분석
    # --------------------------------------------------

    matched_rows = []

    for route_name, pairs in UPSTREAM_PAIRS.items():

        route_df = vehicles[
            vehicles["route_name"]
            == route_name
        ].copy()

        if route_df.empty:
            continue

        for upstream, boarding in pairs:

            pair_df = route_df[
                route_df["station_name"].isin(
                    [
                        upstream,
                        boarding,
                    ]
                )
            ].copy()

            if pair_df.empty:
                continue

            # ------------------------------------------
            # 한 차량의 한 운행 회차씩 처리
            # ------------------------------------------

            grouped = pair_df.groupby(
                [
                    "date",
                    "route_name",
                    "veh_id",
                    "trip_no",
                ]
            )

            for (
                date,
                route,
                veh_id,
                trip_no,
            ), trip_df in grouped:

                upstream_df = (
                    trip_df[
                        trip_df["station_name"]
                        == upstream
                    ]
                    .sort_values(
                        "collected_at"
                    )
                    .copy()
                )

                boarding_df = (
                    trip_df[
                        trip_df["station_name"]
                        == boarding
                    ]
                    .sort_values(
                        "collected_at"
                    )
                    .copy()
                )

                if (
                    upstream_df.empty
                    or boarding_df.empty
                ):
                    continue

                # --------------------------------------
                # 가능한 downstream 관측을 하나씩 보면서
                # 그 직전의 가장 가까운 upstream 관측 선택
                # --------------------------------------

                used_upstream_times = set()

                for _, boarding_row in (
                    boarding_df.iterrows()
                ):

                    candidates = upstream_df[
                        upstream_df[
                            "collected_at"
                        ]
                        <=
                        boarding_row[
                            "collected_at"
                        ]
                    ].copy()

                    if candidates.empty:
                        continue

                    candidates[
                        "time_diff_min"
                    ] = (
                        (
                            boarding_row[
                                "collected_at"
                            ]
                            -
                            candidates[
                                "collected_at"
                            ]
                        )
                        .dt.total_seconds()
                        / 60
                    )

                    candidates = candidates[
                        (
                            candidates[
                                "time_diff_min"
                            ]
                            >= 0
                        )
                        &
                        (
                            candidates[
                                "time_diff_min"
                            ]
                            <= MAX_PAIR_MIN
                        )
                    ].copy()

                    if candidates.empty:
                        continue

                    # 가장 가까운 upstream 관측
                    upstream_row = (
                        candidates
                        .sort_values(
                            "time_diff_min"
                        )
                        .iloc[0]
                    )

                    upstream_time = (
                        upstream_row[
                            "collected_at"
                        ]
                    )

                    # 같은 upstream 관측을
                    # 여러 번 중복 사용하지 않기
                    if upstream_time in used_upstream_times:
                        continue

                    used_upstream_times.add(
                        upstream_time
                    )

                    upstream_seat = (
                        upstream_row[
                            "remain_seat_cnt"
                        ]
                    )

                    boarding_seat = (
                        boarding_row[
                            "remain_seat_cnt"
                        ]
                    )

                    if (
                        pd.isna(upstream_seat)
                        or pd.isna(boarding_seat)
                    ):
                        continue

                    observed_min = (
                        boarding_row[
                            "collected_at"
                        ]
                        -
                        upstream_row[
                            "collected_at"
                        ]
                    ).total_seconds() / 60

                    matched_rows.append({

                        "date":
                            date,

                        "route_name":
                            route,

                        "veh_id":
                            veh_id,

                        "trip_no":
                            trip_no,

                        "upstream_station":
                            upstream,

                        "boarding_station":
                            boarding,

                        "upstream_time":
                            upstream_row[
                                "collected_at"
                            ],

                        "boarding_time":
                            boarding_row[
                                "collected_at"
                            ],

                        "hour":
                            upstream_row[
                                "collected_at"
                            ].hour,

                        "upstream_seat":
                            upstream_seat,

                        "boarding_seat":
                            boarding_seat,

                        "seat_change":
                            (
                                boarding_seat
                                -
                                upstream_seat
                            ),

                        "travel_observed_min":
                            observed_min,
                    })

                    # 한 회차에서 같은 pair는
                    # 대표 표본 하나만 사용
                    break

    # --------------------------------------------------
    # 매칭 결과 없음
    # --------------------------------------------------

    if not matched_rows:
        return pd.DataFrame()

    matched_df = pd.DataFrame(
        matched_rows
    )

    # --------------------------------------------------
    # 이상치 제거
    # --------------------------------------------------

    matched_df = matched_df[
        (
            matched_df[
                "travel_observed_min"
            ]
            >= 0
        )
        &
        (
            matched_df[
                "travel_observed_min"
            ]
            <= MAX_PAIR_MIN
        )
    ].copy()

    if matched_df.empty:
        return pd.DataFrame()

    # --------------------------------------------------
    # 시간대별 집계
    # --------------------------------------------------

    summary = (
        matched_df
        .groupby(
            [
                "route_name",
                "hour",
                "upstream_station",
                "boarding_station",
            ]
        )
        .agg(

            sample_count=(
                "veh_id",
                "count"
            ),

            avg_upstream_seat=(
                "upstream_seat",
                "mean"
            ),

            avg_boarding_seat=(
                "boarding_seat",
                "mean"
            ),

            median_upstream_seat=(
                "upstream_seat",
                "median"
            ),

            median_boarding_seat=(
                "boarding_seat",
                "median"
            ),

            avg_seat_change=(
                "seat_change",
                "mean"
            ),

            median_seat_change=(
                "seat_change",
                "median"
            ),

            seat_decrease_rate=(
                "seat_change",
                lambda x:
                    (
                        x < 0
                    ).mean()
                    * 100
            ),

            boarding_under_5_rate=(
                "boarding_seat",
                lambda x:
                    (
                        x <= 5
                    ).mean()
                    * 100
            ),

            boarding_under_10_rate=(
                "boarding_seat",
                lambda x:
                    (
                        x <= 10
                    ).mean()
                    * 100
            ),

            avg_observed_minutes=(
                "travel_observed_min",
                "mean"
            ),

        )
        .reset_index()
    )

    # --------------------------------------------------
    # 반올림
    # --------------------------------------------------

    numeric_columns = [
        "avg_upstream_seat",
        "avg_boarding_seat",
        "median_upstream_seat",
        "median_boarding_seat",
        "avg_seat_change",
        "median_seat_change",
        "seat_decrease_rate",
        "boarding_under_5_rate",
        "boarding_under_10_rate",
        "avg_observed_minutes",
    ]

    summary[
        numeric_columns
    ] = (
        summary[
            numeric_columns
        ]
        .round(1)
    )

    # 표본 많은 순이 아니라
    # 노선 → 시간 → 정류장 순으로 보기
    summary = summary.sort_values(
        [
            "route_name",
            "hour",
            "upstream_station",
        ]
    )

    return summary

    results = []

    for route_name, pairs in UPSTREAM_PAIRS.items():

        route_df = vehicles[
            vehicles["route_name"]
            == route_name
        ].copy()

        for upstream, boarding in pairs:

            upstream_df = route_df[
                route_df["station_name"]
                == upstream
            ].copy()

            boarding_df = route_df[
                route_df["station_name"]
                == boarding
            ].copy()

            if (
                upstream_df.empty
                or boarding_df.empty
            ):
                continue

            # --------------------------------------
            # 같은 날짜 + 같은 차량 기준
            #
            # 한 정류장에서 여러 번 찍힌 경우
            # 대표값 하나 사용
            # --------------------------------------

            upstream_samples = (
                upstream_df
                .sort_values(
                    "collected_at"
                )
                .drop_duplicates(
                    subset=[
                        "date",
                        "route_name",
                        "veh_id",
                    ],
                    keep="last"
                )
            )

            boarding_samples = (
                boarding_df
                .sort_values(
                    "collected_at"
                )
                .drop_duplicates(
                    subset=[
                        "date",
                        "route_name",
                        "veh_id",
                    ],
                    keep="last"
                )
            )

            merged = pd.merge(
                upstream_samples,
                boarding_samples,
                on=[
                    "date",
                    "route_name",
                    "veh_id",
                ],
                suffixes=(
                    "_upstream",
                    "_boarding"
                )
            )

            if merged.empty:
                continue

            # 실제 시간 순서가 맞는 것만
            merged = merged[
                merged[
                    "collected_at_boarding"
                ]
                >=
                merged[
                    "collected_at_upstream"
                ]
            ].copy()

            if merged.empty:
                continue

            merged["seat_change"] = (
                merged[
                    "remain_seat_cnt_boarding"
                ]
                -
                merged[
                    "remain_seat_cnt_upstream"
                ]
            )

            merged["travel_observed_min"] = (
                (
                    merged[
                        "collected_at_boarding"
                    ]
                    -
                    merged[
                        "collected_at_upstream"
                    ]
                )
                .dt.total_seconds()
                / 60
            )

            # 너무 긴 값은
            # 다른 회차가 섞였을 가능성
            merged = merged[
                merged["travel_observed_min"]
                <= 60
            ].copy()

            if merged.empty:
                continue

            # 선행 정류장 관측 시간대를 기준
            merged["hour"] = (
                merged[
                    "collected_at_upstream"
                ]
                .dt.hour
            )

            for hour, group in merged.groupby(
                "hour"
            ):

                upstream_seats = (
                    group[
                        "remain_seat_cnt_upstream"
                    ]
                )

                boarding_seats = (
                    group[
                        "remain_seat_cnt_boarding"
                    ]
                )

                results.append({

                    "route_name":
                        route_name,

                    "hour":
                        hour,

                    "upstream_station":
                        upstream,

                    "boarding_station":
                        boarding,

                    "sample_count":
                        len(group),

                    "avg_upstream_seat":
                        upstream_seats.mean(),

                    "avg_boarding_seat":
                        boarding_seats.mean(),

                    "median_upstream_seat":
                        upstream_seats.median(),

                    "median_boarding_seat":
                        boarding_seats.median(),

                    "avg_seat_change":
                        group[
                            "seat_change"
                        ].mean(),

                    "median_seat_change":
                        group[
                            "seat_change"
                        ].median(),

                    "seat_decrease_rate":
                        (
                            group[
                                "seat_change"
                            ]
                            < 0
                        ).mean()
                        * 100,

                    "boarding_under_5_rate":
                        (
                            boarding_seats
                            <= 5
                        ).mean()
                        * 100,

                    "boarding_under_10_rate":
                        (
                            boarding_seats
                            <= 10
                        ).mean()
                        * 100,

                    "avg_observed_minutes":
                        group[
                            "travel_observed_min"
                        ].mean(),
                })

    result_df = pd.DataFrame(
        results
    )

    if not result_df.empty:

        numeric_columns = [
            "avg_upstream_seat",
            "avg_boarding_seat",
            "median_upstream_seat",
            "median_boarding_seat",
            "avg_seat_change",
            "median_seat_change",
            "seat_decrease_rate",
            "boarding_under_5_rate",
            "boarding_under_10_rate",
            "avg_observed_minutes",
        ]

        result_df[
            numeric_columns
        ] = (
            result_df[
                numeric_columns
            ]
            .round(1)
        )

    return result_df


# ==================================================
# 배차간격 분석
# ==================================================

def analyze_headway(df):

    headway = df[
        [
            "collected_at",
            "route_name",
            "station_name",
            "predict_time_sec_1",
            "predict_time_sec_2",
            "remain_seat_cnt_1",
            "remain_seat_cnt_2",
        ]
    ].copy()

    headway[
        "predict_time_sec_1"
    ] = pd.to_numeric(
        headway[
            "predict_time_sec_1"
        ],
        errors="coerce"
    )

    headway[
        "predict_time_sec_2"
    ] = pd.to_numeric(
        headway[
            "predict_time_sec_2"
        ],
        errors="coerce"
    )

    headway[
        "remain_seat_cnt_1"
    ] = pd.to_numeric(
        headway[
            "remain_seat_cnt_1"
        ],
        errors="coerce"
    )

    headway[
        "remain_seat_cnt_2"
    ] = pd.to_numeric(
        headway[
            "remain_seat_cnt_2"
        ],
        errors="coerce"
    )

    # ----------------------------------------------
    # 2번 ETA - 1번 ETA
    # ----------------------------------------------

    headway["headway_min"] = (
        (
            headway[
                "predict_time_sec_2"
            ]
            -
            headway[
                "predict_time_sec_1"
            ]
        )
        / 60
    )

    # 이상값 제거
    headway = headway[
        (
            headway["headway_min"] > 0
        )
        &
        (
            headway["headway_min"] <= 40
        )
    ].copy()

    headway["hour"] = (
        headway[
            "collected_at"
        ]
        .dt.hour
    )

    headway["seat_gain"] = (
        headway[
            "remain_seat_cnt_2"
        ]
        -
        headway[
            "remain_seat_cnt_1"
        ]
    )

    # ----------------------------------------------
    # 배차 그룹
    # ----------------------------------------------

    headway["headway_group"] = pd.cut(
        headway["headway_min"],
        bins=[
            0,
            5,
            10,
            15,
            999,
        ],
        labels=[
            "0~5분",
            "5~10분",
            "10~15분",
            "15분+",
        ],
        right=False
    )

    result = (
        headway
        .groupby(
            [
                "route_name",
                "hour",
                "station_name",
                "headway_group",
            ],
            observed=True
        )
        .agg(

            sample_count=(
                "headway_min",
                "count"
            ),

            avg_headway=(
                "headway_min",
                "mean"
            ),

            median_headway=(
                "headway_min",
                "median"
            ),

            avg_first_seat=(
                "remain_seat_cnt_1",
                "mean"
            ),

            avg_second_seat=(
                "remain_seat_cnt_2",
                "mean"
            ),

            avg_seat_gain=(
                "seat_gain",
                "mean"
            ),

            second_more_seat_rate=(
                "seat_gain",
                lambda x:
                    (x > 0)
                    .mean()
                    * 100
            ),

            second_over_10_rate=(
                "remain_seat_cnt_2",
                lambda x:
                    (x >= 10)
                    .mean()
                    * 100
            ),

            second_under_5_rate=(
                "remain_seat_cnt_2",
                lambda x:
                    (x <= 5)
                    .mean()
                    * 100
            ),
        )
        .reset_index()
    )

    round_columns = [
        "avg_headway",
        "median_headway",
        "avg_first_seat",
        "avg_second_seat",
        "avg_seat_gain",
        "second_more_seat_rate",
        "second_over_10_rate",
        "second_under_5_rate",
    ]

    result[
        round_columns
    ] = (
        result[
            round_columns
        ]
        .round(1)
    )

    return result


# ==================================================
# 추천용 간단 지표
# ==================================================

def make_station_recommendation_table(
    pair_result,
    headway_result,
):

    if pair_result.empty:
        return pd.DataFrame()

    recommendation = (
        pair_result.copy()
    )

    # ----------------------------------------------
    # 앞 정류장에서 탔을 때
    # 좌석 확보 이점
    #
    # 음수 seat_change가 클수록
    # 앞에서 타는 가치가 큼
    # ----------------------------------------------

    recommendation[
        "upstream_advantage"
    ] = (
        -recommendation[
            "avg_seat_change"
        ]
    )

    def classify(row):

        advantage = row[
            "upstream_advantage"
        ]

        low_seat_rate = row[
            "boarding_under_5_rate"
        ]

        if (
            advantage >= 10
            and low_seat_rate >= 50
        ):
            return "앞 정류장 이동 적극 고려"

        elif (
            advantage >= 5
            and low_seat_rate >= 30
        ):
            return "앞 정류장 이동 고려"

        elif low_seat_rate >= 50:
            return "뒤차 좌석 확인 필요"

        else:
            return "현재 정류장 이용 가능"

    recommendation[
        "rough_recommendation"
    ] = recommendation.apply(
        classify,
        axis=1
    )

    return recommendation


# ==================================================
# 저장
# ==================================================

def save_results(
    pair_result,
    headway_result,
    recommendation
):

    with pd.ExcelWriter(
        OUTPUT_PATH
    ) as writer:

        pair_result.to_excel(
            writer,
            sheet_name="upstream_pairs",
            index=False
        )

        headway_result.to_excel(
            writer,
            sheet_name="headway",
            index=False
        )

        recommendation.to_excel(
            writer,
            sheet_name="recommendation",
            index=False
        )

    print()
    print(
        "분석 결과 저장:"
    )

    print(
        OUTPUT_PATH
    )


# ==================================================
# 실행
# ==================================================

if __name__ == "__main__":

    df = load_realtime_arrivals()

    print()
    print("=" * 80)
    print("Time Keeper 선행 정류장 분석")
    print("=" * 80)

    print()
    print(
        "전체 실시간 관측값:",
        len(df)
    )

    vehicles = make_vehicle_rows(
        df
    )

    print(
        "차량 관측 행:",
        len(vehicles)
    )

    # ----------------------------------------------
    # 선행 정류장 분석
    # ----------------------------------------------

    pair_result = (
        analyze_upstream_pairs(
            vehicles
        )
    )

    print()
    print("=" * 100)
    print("선행 정류장 → 탑승 정류장 좌석 변화")
    print("=" * 100)

    if pair_result.empty:

        print(
            "분석 가능한 pair가 없습니다."
        )

    else:

        print(
            pair_result
            .to_string(
                index=False
            )
        )

    # ----------------------------------------------
    # 배차 분석
    # ----------------------------------------------

    headway_result = (
        analyze_headway(
            df
        )
    )

    print()
    print("=" * 100)
    print("배차간격 × 뒤차 좌석 분석")
    print("=" * 100)

    print(
        headway_result
        .to_string(
            index=False
        )
    )

    # ----------------------------------------------
    # 추천용 테이블
    # ----------------------------------------------

    recommendation = (
        make_station_recommendation_table(
            pair_result,
            headway_result,
        )
    )

    print()
    print("=" * 100)
    print("러프 추천 규칙")
    print("=" * 100)

    if not recommendation.empty:

        print(
            recommendation[
                [
                    "route_name",
                    "hour",
                    "upstream_station",
                    "boarding_station",
                    "sample_count",
                    "avg_seat_change",
                    "boarding_under_5_rate",
                    "rough_recommendation",
                ]
            ]
            .to_string(
                index=False
            )
        )

    save_results(
        pair_result,
        headway_result,
        recommendation,
    )
