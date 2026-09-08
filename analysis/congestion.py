import sqlite3
import pandas as pd


CONGESTION_DB = "data/busflow.db"
WEATHER_DB = "weather.db"


# --------------------------------------------------
# 노선 이름
# --------------------------------------------------

ROUTE_NAMES = {
    "41006433": "5001A",
    "41006248": "5001B",
    "41006409": "5003A",
    "41006064": "5003B",
}


# --------------------------------------------------
# 1. 혼잡도 데이터 불러오기
# --------------------------------------------------

def load_congestion():

    conn = sqlite3.connect(CONGESTION_DB)

    df = pd.read_sql_query("""
        SELECT
            opr_ymd,
            dow_nm,
            route_id,
            station_id,
            station_seq,
            time_zone,
            congestion
        FROM congestion
    """, conn)

    conn.close()

    # 100 초과 혼잡도는 100으로 처리
    df["congestion"] = df["congestion"].clip(upper=100)

    # 노선 이름 추가
    df["route_name"] = df["route_id"].map(ROUTE_NAMES)

    return df


# --------------------------------------------------
# 2. 날씨 데이터 불러오기
# --------------------------------------------------

def load_weather():

    conn = sqlite3.connect(WEATHER_DB)

    df = pd.read_sql_query("""
        SELECT
            opr_ymd,
            time_zone,
            weather_station_id,
            weather_station_name,
            temperature,
            rainfall,
            humidity,
            wind_speed,
            snow_depth
        FROM weather
    """, conn)

    conn.close()

    # 07~08 -> 07
    df["time_zone"] = df["time_zone"].str[:2]

    # ID 타입 통일
    df["weather_station_id"] = (
        df["weather_station_id"].astype(str)
    )

    # 친구가 확인해준 기준
    # rainfall NULL = 강수 없음
    # snow_depth NULL = 적설 없음
    df["rainfall"] = df["rainfall"].fillna(0)
    df["snow_depth"] = df["snow_depth"].fillna(0)

    # 파생 변수
    df["is_rain"] = (
        df["rainfall"] > 0
    ).astype(int)

    df["is_snow"] = (
        df["snow_depth"] > 0
    ).astype(int)

    # 같은 날짜/시간/관측소 중복 제거
    df = df.drop_duplicates(
        subset=[
            "opr_ymd",
            "time_zone",
            "weather_station_id"
        ]
    )

    return df


# --------------------------------------------------
# 3. 혼잡도 데이터에 기상관측소 지정
# --------------------------------------------------

def add_weather_station(congestion):

    # 기본값
    # 용인/기흥 구간 -> 수원 기상관측소
    congestion["weather_station_id"] = "119"

    # 현재 우리가 수집한 5001B 정류장은 서울 구간
    # -> 서울 기상관측소
    congestion.loc[
        congestion["route_id"] == "41006248",
        "weather_station_id"
    ] = "108"

    return congestion


# --------------------------------------------------
# 4. 혼잡도 + 날씨 결합
# --------------------------------------------------

def merge_congestion_weather():

    congestion = load_congestion()
    weather = load_weather()

    congestion = add_weather_station(congestion)

    df = pd.merge(
        congestion,
        weather,
        on=[
            "opr_ymd",
            "time_zone",
            "weather_station_id"
        ],
        how="left"
    )

    return df


# --------------------------------------------------
# 5. 날짜별 / 시간대별 혼잡도 통계
# --------------------------------------------------

def make_daily_stats(df):

    stats = (
        df.groupby([
            "opr_ymd",
            "dow_nm",
            "route_id",
            "route_name",
            "station_id",
            "station_seq",
            "time_zone"
        ])
        .agg(
            avg_congestion=("congestion", "mean"),
            min_congestion=("congestion", "min"),
            max_congestion=("congestion", "max"),
            data_count=("congestion", "count"),

            temperature=("temperature", "first"),
            rainfall=("rainfall", "first"),
            is_rain=("is_rain", "first"),
            humidity=("humidity", "first"),
            wind_speed=("wind_speed", "first"),
            snow_depth=("snow_depth", "first"),
            is_snow=("is_snow", "first"),
            weather_station=("weather_station_name", "first")
        )
        .reset_index()
    )

    # 같은 날짜 / 같은 시간대 내 혼잡도 변동폭
    stats["congestion_range"] = (
        stats["max_congestion"]
        - stats["min_congestion"]
    )

    stats["avg_congestion"] = (
        stats["avg_congestion"].round(1)
    )

    return stats


# --------------------------------------------------
# 실행
# --------------------------------------------------

if __name__ == "__main__":

    # --------------------------------------------------
    # 데이터 결합
    # --------------------------------------------------

    df = merge_congestion_weather()

    print("=== 혼잡도 + 날씨 결합 ===")
    print("전체 데이터:", len(df))

    print()
    print("=== 날씨 결측 개수 ===")

    print(
        df[
            [
                "temperature",
                "rainfall",
                "humidity",
                "wind_speed",
                "snow_depth"
            ]
        ].isna().sum()
    )

    # --------------------------------------------------
    # 날짜 / 시간별 통계 생성
    # --------------------------------------------------

    stats = make_daily_stats(df)

    # --------------------------------------------------
    # 1. 혼잡도 변동폭 TOP 20
    # --------------------------------------------------

    print()
    print("=== 혼잡도 변동폭 TOP 20 ===")

    variable = (
        stats[
            stats["data_count"] >= 3
        ]
        .sort_values(
            "congestion_range",
            ascending=False
        )
    )

    print(
        variable[
            [
                "opr_ymd",
                "dow_nm",
                "route_name",
                "station_id",
                "time_zone",
                "avg_congestion",
                "min_congestion",
                "max_congestion",
                "congestion_range",
                "data_count",
                "temperature",
                "rainfall"
            ]
        ]
        .head(20)
        .to_string(index=False)
    )

    # --------------------------------------------------
    # 2. 정류장 × 시간대별 혼잡도 변동 발생 빈도
    # --------------------------------------------------

    print()
    print("=== 정류장 × 시간대별 혼잡도 변동 발생 빈도 ===")

    valid = stats[
        stats["data_count"] >= 3
    ].copy()

    valid["range_over_40"] = (
        valid["congestion_range"] >= 40
    )

    valid["range_over_60"] = (
        valid["congestion_range"] >= 60
    )

    variability_summary = (
        valid.groupby([
            "route_name",
            "station_id",
            "time_zone"
        ])
        .agg(
            observed_days=("opr_ymd", "count"),
            avg_range=("congestion_range", "mean"),
            max_range=("congestion_range", "max"),
            range40_days=("range_over_40", "sum"),
            range60_days=("range_over_60", "sum")
        )
        .reset_index()
    )

    variability_summary["range40_rate"] = (
        variability_summary["range40_days"]
        / variability_summary["observed_days"]
        * 100
    ).round(1)

    variability_summary["range60_rate"] = (
        variability_summary["range60_days"]
        / variability_summary["observed_days"]
        * 100
    ).round(1)

    variability_summary["avg_range"] = (
        variability_summary["avg_range"].round(1)
    )

    result = (
        variability_summary[
            variability_summary["observed_days"] >= 10
        ]
        .sort_values(
            "range40_rate",
            ascending=False
        )
    )

    print(
        result
        .head(20)
        .to_string(index=False)
    )

    # --------------------------------------------------
    # 3. 비 오는 시간 vs 비 안 오는 시간
    # --------------------------------------------------

    print()
    print("=== 비 오는 시간 vs 비 안 오는 시간 ===")

    weather_valid = stats[
        (stats["data_count"] >= 3)
        & (stats["is_rain"].notna())
    ].copy()

    weather_valid["rain_type"] = (
        weather_valid["is_rain"].map({
            0: "비 안 옴",
            1: "비 옴"
        })
    )

    rain_summary = (
        weather_valid.groupby(
            "rain_type"
        )
        .agg(
            observed_cases=("opr_ymd", "count"),
            avg_congestion=("avg_congestion", "mean"),
            avg_range=("congestion_range", "mean"),
            max_range=("congestion_range", "max")
        )
        .reset_index()
    )

    rain_summary["avg_congestion"] = (
        rain_summary["avg_congestion"].round(1)
    )

    rain_summary["avg_range"] = (
        rain_summary["avg_range"].round(1)
    )

    print(
        rain_summary.to_string(index=False)
    )

    # --------------------------------------------------
    # 4. 출퇴근 시간대 강수 영향
    # --------------------------------------------------

    print()
    print("=== 출퇴근 시간대 강수 영향 ===")

    peak = weather_valid[
        (
            (weather_valid["route_name"] == "5001A")
            & (
                weather_valid["time_zone"].isin([
                    "06",
                    "07",
                    "08",
                    "09"
                ])
            )
        )
        |
        (
            (weather_valid["route_name"] == "5001B")
            & (
                weather_valid["time_zone"].isin([
                    "17",
                    "18",
                    "19",
                    "20"
                ])
            )
        )
    ].copy()

    peak_summary = (
        peak.groupby([
            "route_name",
            "rain_type"
        ])
        .agg(
            observed_cases=("opr_ymd", "count"),
            avg_congestion=("avg_congestion", "mean"),
            avg_range=("congestion_range", "mean")
        )
        .reset_index()
    )

    peak_summary["avg_congestion"] = (
        peak_summary["avg_congestion"].round(1)
    )

    peak_summary["avg_range"] = (
        peak_summary["avg_range"].round(1)
    )

    print(
        peak_summary.to_string(index=False)
    )

        # --------------------------------------------------
    # 5. 강수량 단계별 혼잡도 분석
    # --------------------------------------------------

    print()
    print("=== 강수량 단계별 혼잡도 영향 ===")

    # 날씨 데이터가 존재하고
    # 혼잡도 관측값이 최소 3개인 경우만 사용
    rain_level_data = stats[
        (stats["data_count"] >= 3)
        & (stats["rainfall"].notna())
    ].copy()

    # 강수량 단계 구분
    def classify_rainfall(rainfall):

        if rainfall == 0:
            return "0_비 없음"

        elif rainfall <= 1:
            return "1_약한 비"

        elif rainfall <= 5:
            return "2_보통 비"

        else:
            return "3_강한 비"

    rain_level_data["rain_level"] = (
        rain_level_data["rainfall"].apply(
            classify_rainfall
        )
    )

    # 전체 데이터 비교
    rain_level_summary = (
        rain_level_data.groupby(
            "rain_level"
        )
        .agg(
            observed_cases=("opr_ymd", "count"),
            avg_rainfall=("rainfall", "mean"),
            avg_congestion=("avg_congestion", "mean"),
            avg_range=("congestion_range", "mean"),
            max_range=("congestion_range", "max")
        )
        .reset_index()
    )

    rain_level_summary["avg_rainfall"] = (
        rain_level_summary["avg_rainfall"].round(2)
    )

    rain_level_summary["avg_congestion"] = (
        rain_level_summary["avg_congestion"].round(1)
    )

    rain_level_summary["avg_range"] = (
        rain_level_summary["avg_range"].round(1)
    )

    print()
    print("[전체]")

    print(
        rain_level_summary.to_string(
            index=False
        )
    )

    # --------------------------------------------------
    # 출퇴근 시간만 별도 분석
    # --------------------------------------------------

    rain_peak = rain_level_data[
        (
            (rain_level_data["route_name"] == "5001A")
            & (
                rain_level_data["time_zone"].isin([
                    "06",
                    "07",
                    "08",
                    "09"
                ])
            )
        )
        |
        (
            (rain_level_data["route_name"] == "5001B")
            & (
                rain_level_data["time_zone"].isin([
                    "17",
                    "18",
                    "19",
                    "20"
                ])
            )
        )
    ].copy()

    rain_peak_summary = (
        rain_peak.groupby([
            "route_name",
            "rain_level"
        ])
        .agg(
            observed_cases=("opr_ymd", "count"),
            avg_rainfall=("rainfall", "mean"),
            avg_congestion=("avg_congestion", "mean"),
            avg_range=("congestion_range", "mean")
        )
        .reset_index()
    )

    rain_peak_summary["avg_rainfall"] = (
        rain_peak_summary["avg_rainfall"].round(2)
    )

    rain_peak_summary["avg_congestion"] = (
        rain_peak_summary["avg_congestion"].round(1)
    )

    rain_peak_summary["avg_range"] = (
        rain_peak_summary["avg_range"].round(1)
    )

    print()
    print("[출퇴근 시간대]")

    print(
        rain_peak_summary.to_string(
            index=False
        )
    )

        # --------------------------------------------------
    # 6. 분석 결과 Excel 저장
    # --------------------------------------------------

    print()
    print("=== 분석 결과 Excel 저장 ===")

    OUTPUT_FILE = "analysis/analysis_results.xlsx"

    # TOP 20 데이터
    top20_export = variable[
        [
            "opr_ymd",
            "dow_nm",
            "route_name",
            "station_id",
            "time_zone",
            "avg_congestion",
            "min_congestion",
            "max_congestion",
            "congestion_range",
            "data_count",
            "temperature",
            "rainfall"
        ]
    ].head(20)

    with pd.ExcelWriter(
        OUTPUT_FILE,
        engine="openpyxl"
    ) as writer:

        # 혼잡도 변동폭 TOP 20
        top20_export.to_excel(
            writer,
            sheet_name="변동폭_TOP20",
            index=False
        )

        # 정류장 × 시간대 변동성
        result.to_excel(
            writer,
            sheet_name="정류장_시간대_변동성",
            index=False
        )

        # 비 오는 시간 vs 안 오는 시간
        rain_summary.to_excel(
            writer,
            sheet_name="강수여부_전체",
            index=False
        )

        # 출퇴근 시간대 비 영향
        peak_summary.to_excel(
            writer,
            sheet_name="강수여부_출퇴근",
            index=False
        )

        # 강수량 단계별 전체
        rain_level_summary.to_excel(
            writer,
            sheet_name="강수량단계_전체",
            index=False
        )

        # 강수량 단계별 출퇴근
        rain_peak_summary.to_excel(
            writer,
            sheet_name="강수량단계_출퇴근",
            index=False
        )

    print(f"저장 완료: {OUTPUT_FILE}")

        # --------------------------------------------------
    # 7. 요일 영향 분석
    # --------------------------------------------------

    print()
    print("=== 요일별 혼잡도 영향 분석 ===")

    # 날씨와 관계없이 혼잡도 관측값이
    # 최소 3개 존재하는 날짜/시간대만 사용
    day_data = stats[
        stats["data_count"] >= 3
    ].copy()

    # 요일 순서 지정
    DAY_ORDER = [
        "월요일",
        "화요일",
        "수요일",
        "목요일",
        "금요일",
        "토요일",
        "일요일"
    ]

    day_data["dow_nm"] = pd.Categorical(
        day_data["dow_nm"],
        categories=DAY_ORDER,
        ordered=True
    )

    # --------------------------------------------------
    # 7-1. 전체 요일별 비교
    # --------------------------------------------------

    day_summary = (
        day_data.groupby(
            "dow_nm",
            observed=True
        )
        .agg(
            observed_cases=("opr_ymd", "count"),
            avg_congestion=("avg_congestion", "mean"),
            avg_range=("congestion_range", "mean"),
            max_range=("congestion_range", "max")
        )
        .reset_index()
    )

    day_summary["avg_congestion"] = (
        day_summary["avg_congestion"].round(1)
    )

    day_summary["avg_range"] = (
        day_summary["avg_range"].round(1)
    )

    print()
    print("[전체 요일별]")

    print(
        day_summary.to_string(index=False)
    )

    # --------------------------------------------------
    # 7-2. 5001A 출근시간 요일별
    # --------------------------------------------------

    morning_5001a = day_data[
        (day_data["route_name"] == "5001A")
        & (
            day_data["time_zone"].isin([
                "06",
                "07",
                "08",
                "09"
            ])
        )
    ].copy()

    morning_day_summary = (
        morning_5001a.groupby(
            "dow_nm",
            observed=True
        )
        .agg(
            observed_cases=("opr_ymd", "count"),
            avg_congestion=("avg_congestion", "mean"),
            avg_range=("congestion_range", "mean"),
            max_range=("congestion_range", "max")
        )
        .reset_index()
    )

    morning_day_summary["avg_congestion"] = (
        morning_day_summary["avg_congestion"].round(1)
    )

    morning_day_summary["avg_range"] = (
        morning_day_summary["avg_range"].round(1)
    )

    print()
    print("[5001A 출근 06~09시]")

    print(
        morning_day_summary.to_string(index=False)
    )

    # --------------------------------------------------
    # 7-3. 5001B 퇴근시간 요일별
    # --------------------------------------------------

    evening_5001b = day_data[
        (day_data["route_name"] == "5001B")
        & (
            day_data["time_zone"].isin([
                "17",
                "18",
                "19",
                "20"
            ])
        )
    ].copy()

    evening_day_summary = (
        evening_5001b.groupby(
            "dow_nm",
            observed=True
        )
        .agg(
            observed_cases=("opr_ymd", "count"),
            avg_congestion=("avg_congestion", "mean"),
            avg_range=("congestion_range", "mean"),
            max_range=("congestion_range", "max")
        )
        .reset_index()
    )

    evening_day_summary["avg_congestion"] = (
        evening_day_summary["avg_congestion"].round(1)
    )

    evening_day_summary["avg_range"] = (
        evening_day_summary["avg_range"].round(1)
    )

    print()
    print("[5001B 퇴근 17~20시]")

    print(
        evening_day_summary.to_string(index=False)
    )

    # --------------------------------------------------
    # 7-4. 노선 × 시간 × 요일까지 세부 분석
    # --------------------------------------------------

    day_detail = (
        day_data.groupby(
            [
                "route_name",
                "station_id",
                "time_zone",
                "dow_nm"
            ],
            observed=True
        )
        .agg(
            observed_cases=("opr_ymd", "count"),
            avg_congestion=("avg_congestion", "mean"),
            avg_range=("congestion_range", "mean")
        )
        .reset_index()
    )

    day_detail["avg_congestion"] = (
        day_detail["avg_congestion"].round(1)
    )

    day_detail["avg_range"] = (
        day_detail["avg_range"].round(1)
    )

    # --------------------------------------------------
    # 7-5. Excel 저장
    # --------------------------------------------------

    DAY_OUTPUT_FILE = "analysis/day_analysis.xlsx"

    with pd.ExcelWriter(
        DAY_OUTPUT_FILE,
        engine="openpyxl"
    ) as writer:

        day_summary.to_excel(
            writer,
            sheet_name="요일_전체",
            index=False
        )

        morning_day_summary.to_excel(
            writer,
            sheet_name="5001A_출근",
            index=False
        )

        evening_day_summary.to_excel(
            writer,
            sheet_name="5001B_퇴근",
            index=False
        )

        day_detail.to_excel(
            writer,
            sheet_name="요일_상세",
            index=False
        )

    print()
    print(
        f"요일 분석 Excel 저장 완료: {DAY_OUTPUT_FILE}"
    )


        # --------------------------------------------------
    # 8. 요일 × 시간대별 평균 혼잡도
    # --------------------------------------------------

    print()
    print("=== 요일 × 시간대별 평균 혼잡도 ===")

    DAY_ORDER = [
        "월요일",
        "화요일",
        "수요일",
        "목요일",
        "금요일",
        "토요일",
        "일요일"
    ]

    # --------------------------------------------------
    # 8-1. 5001A
    # --------------------------------------------------

    day_hour_5001a = (
        stats[
            stats["route_name"] == "5001A"
        ]
        .groupby(
            ["time_zone", "dow_nm"],
            observed=True
        )
        .agg(
            avg_congestion=("avg_congestion", "mean"),
            observed_cases=("opr_ymd", "count")
        )
        .reset_index()
    )

    day_hour_5001a["avg_congestion"] = (
        day_hour_5001a["avg_congestion"].round(1)
    )

    # 피벗 테이블 생성
    pivot_5001a = day_hour_5001a.pivot(
        index="time_zone",
        columns="dow_nm",
        values="avg_congestion"
    )

    # 요일 순서 정렬
    pivot_5001a = pivot_5001a.reindex(
        columns=DAY_ORDER
    )

    print()
    print("[5001A 요일 × 시간대]")

    print(
        pivot_5001a.to_string()
    )

    # --------------------------------------------------
    # 8-2. 5001B
    # --------------------------------------------------

    day_hour_5001b = (
        stats[
            stats["route_name"] == "5001B"
        ]
        .groupby(
            ["time_zone", "dow_nm"],
            observed=True
        )
        .agg(
            avg_congestion=("avg_congestion", "mean"),
            observed_cases=("opr_ymd", "count")
        )
        .reset_index()
    )

    day_hour_5001b["avg_congestion"] = (
        day_hour_5001b["avg_congestion"].round(1)
    )

    pivot_5001b = day_hour_5001b.pivot(
        index="time_zone",
        columns="dow_nm",
        values="avg_congestion"
    )

    pivot_5001b = pivot_5001b.reindex(
        columns=DAY_ORDER
    )

    print()
    print("[5001B 요일 × 시간대]")

    print(
        pivot_5001b.to_string()
    )

    # --------------------------------------------------
    # Excel 저장
    # --------------------------------------------------

    DAY_HOUR_OUTPUT = "analysis/day_hour_analysis.xlsx"

    with pd.ExcelWriter(
        DAY_HOUR_OUTPUT,
        engine="openpyxl"
    ) as writer:

        # 보기 좋은 피벗표
        pivot_5001a.to_excel(
            writer,
            sheet_name="5001A_요일시간"
        )

        pivot_5001b.to_excel(
            writer,
            sheet_name="5001B_요일시간"
        )

        # 원본 상세 데이터
        day_hour_5001a.to_excel(
            writer,
            sheet_name="5001A_상세",
            index=False
        )

        day_hour_5001b.to_excel(
            writer,
            sheet_name="5001B_상세",
            index=False
        )

    print()
    print(
        f"요일 × 시간대 Excel 저장 완료: {DAY_HOUR_OUTPUT}"
    )

        # --------------------------------------------------
    # 9. 정류장 × 요일 × 시간대 평균 혼잡도
    # --------------------------------------------------

    print()
    print("=== 정류장 × 요일 × 시간대 분석 ===")

    DAY_ORDER = [
        "월요일",
        "화요일",
        "수요일",
        "목요일",
        "금요일",
        "토요일",
        "일요일"
    ]

    # --------------------------------------------------
    # 9-1. 모든 정류장 상세 통계
    # --------------------------------------------------

    station_day_hour = (
        stats.groupby(
            [
                "route_name",
                "station_id",
                "station_seq",
                "time_zone",
                "dow_nm"
            ],
            observed=True
        )
        .agg(
            observed_cases=("opr_ymd", "count"),
            avg_congestion=("avg_congestion", "mean"),
            avg_range=("congestion_range", "mean")
        )
        .reset_index()
    )

    station_day_hour["avg_congestion"] = (
        station_day_hour["avg_congestion"].round(1)
    )

    station_day_hour["avg_range"] = (
        station_day_hour["avg_range"].round(1)
    )

    # --------------------------------------------------
    # 9-2. 5001A 기흥역만 추출
    # station_id = 4111657
    # --------------------------------------------------

    giheung = station_day_hour[
        (station_day_hour["route_name"] == "5001A")
        & (station_day_hour["station_id"] == "4111657")
    ].copy()

    # 시간 × 요일 피벗
    giheung_pivot = giheung.pivot(
        index="time_zone",
        columns="dow_nm",
        values="avg_congestion"
    )

    giheung_pivot = giheung_pivot.reindex(
        columns=DAY_ORDER
    )

    print()
    print("[5001A 기흥역 - 요일 × 시간대 평균 혼잡도]")

    print(
        giheung_pivot.to_string()
    )

    # --------------------------------------------------
    # 9-3. 기흥역 변동폭도 별도로 보기
    # --------------------------------------------------

    giheung_range_pivot = giheung.pivot(
        index="time_zone",
        columns="dow_nm",
        values="avg_range"
    )

    giheung_range_pivot = giheung_range_pivot.reindex(
        columns=DAY_ORDER
    )

    print()
    print("[5001A 기흥역 - 요일 × 시간대 평균 변동폭]")

    print(
        giheung_range_pivot.to_string()
    )

    # --------------------------------------------------
    # 9-4. Excel 저장
    # --------------------------------------------------

    STATION_OUTPUT = "analysis/station_day_hour_analysis.xlsx"

    with pd.ExcelWriter(
        STATION_OUTPUT,
        engine="openpyxl"
    ) as writer:

        # 모든 정류장 상세
        station_day_hour.to_excel(
            writer,
            sheet_name="전체_정류장_상세",
            index=False
        )

        # 기흥역 평균 혼잡도
        giheung_pivot.to_excel(
            writer,
            sheet_name="기흥역_평균혼잡도"
        )

        # 기흥역 평균 변동폭
        giheung_range_pivot.to_excel(
            writer,
            sheet_name="기흥역_평균변동폭"
        )

        # 기흥역 원본 형태
        giheung.to_excel(
            writer,
            sheet_name="기흥역_상세",
            index=False
        )

    print()
    print(
        f"정류장 분석 Excel 저장 완료: {STATION_OUTPUT}"
    )

        # --------------------------------------------------
    # 10. 학기 / 방학 + 공휴일 분석
    # --------------------------------------------------

    print()
    print("=== 학기 / 방학 + 공휴일 영향 분석 ===")

    calendar_data = stats.copy()

    # --------------------------------------------------
    # 10-1. 날짜 처리
    # --------------------------------------------------

    calendar_data["date"] = pd.to_datetime(
        calendar_data["opr_ymd"],
        format="%Y%m%d"
    )

    calendar_data["month"] = (
        calendar_data["date"].dt.month
    )

    # --------------------------------------------------
    # 10-2. 학기 / 방학 구분
    #
    # 사용자 기준:
    # 3~6월 = 학기
    # 1, 2, 7, 8월 = 방학
    # --------------------------------------------------

    def classify_period(month):

        if month in [3, 4, 5, 6]:
            return "학기"

        elif month in [1, 2, 7, 8]:
            return "방학"

        else:
            return "기타"

    calendar_data["period"] = (
        calendar_data["month"].apply(
            classify_period
        )
    )

    # --------------------------------------------------
    # 10-3. 2026년 공휴일
    # --------------------------------------------------

    HOLIDAYS_2026 = {
        "20260216": "설날 연휴",
        "20260217": "설날",
        "20260218": "설날 연휴",

        "20260301": "삼일절",
        "20260302": "삼일절 대체공휴일",

        "20260505": "어린이날",
        "20260524": "부처님오신날",
        "20260525": "부처님오신날 대체공휴일",

        "20260603": "전국동시지방선거",
        "20260606": "현충일",

        "20260815": "광복절",
        "20260817": "광복절 대체공휴일",
    }

    calendar_data["holiday_name"] = (
        calendar_data["opr_ymd"].map(
            HOLIDAYS_2026
        )
    )

    calendar_data["is_holiday"] = (
        calendar_data["holiday_name"].notna()
    ).astype(int)

    calendar_data["holiday_type"] = (
        calendar_data["is_holiday"].map({
            0: "공휴일 아님",
            1: "공휴일"
        })
    )

    # 관측값 최소 3개
    calendar_valid = calendar_data[
        calendar_data["data_count"] >= 3
    ].copy()

    # --------------------------------------------------
    # 10-4. 학기 vs 방학 전체 비교
    # --------------------------------------------------

    period_summary = (
        calendar_valid[
            calendar_valid["period"].isin([
                "학기",
                "방학"
            ])
        ]
        .groupby("period")
        .agg(
            observed_cases=("opr_ymd", "count"),
            avg_congestion=("avg_congestion", "mean"),
            avg_range=("congestion_range", "mean"),
            max_range=("congestion_range", "max")
        )
        .reset_index()
    )

    period_summary["avg_congestion"] = (
        period_summary["avg_congestion"].round(1)
    )

    period_summary["avg_range"] = (
        period_summary["avg_range"].round(1)
    )

    print()
    print("[전체 - 학기 vs 방학]")

    print(
        period_summary.to_string(
            index=False
        )
    )

    # --------------------------------------------------
    # 10-5. 5001A 출근시간 학기 vs 방학
    # --------------------------------------------------

    morning_period = calendar_valid[
        (calendar_valid["route_name"] == "5001A")
        & (
            calendar_valid["time_zone"].isin([
                "06", "07", "08", "09"
            ])
        )
        & (
            calendar_valid["period"].isin([
                "학기",
                "방학"
            ])
        )
    ].copy()

    morning_period_summary = (
        morning_period.groupby("period")
        .agg(
            observed_cases=("opr_ymd", "count"),
            avg_congestion=("avg_congestion", "mean"),
            avg_range=("congestion_range", "mean")
        )
        .reset_index()
    )

    morning_period_summary["avg_congestion"] = (
        morning_period_summary[
            "avg_congestion"
        ].round(1)
    )

    morning_period_summary["avg_range"] = (
        morning_period_summary[
            "avg_range"
        ].round(1)
    )

    print()
    print("[5001A 출근 06~09시 - 학기 vs 방학]")

    print(
        morning_period_summary.to_string(
            index=False
        )
    )

    # --------------------------------------------------
    # 10-6. 5001B 퇴근시간 학기 vs 방학
    # --------------------------------------------------

    evening_period = calendar_valid[
        (calendar_valid["route_name"] == "5001B")
        & (
            calendar_valid["time_zone"].isin([
                "17", "18", "19", "20"
            ])
        )
        & (
            calendar_valid["period"].isin([
                "학기",
                "방학"
            ])
        )
    ].copy()

    evening_period_summary = (
        evening_period.groupby("period")
        .agg(
            observed_cases=("opr_ymd", "count"),
            avg_congestion=("avg_congestion", "mean"),
            avg_range=("congestion_range", "mean")
        )
        .reset_index()
    )

    evening_period_summary["avg_congestion"] = (
        evening_period_summary[
            "avg_congestion"
        ].round(1)
    )

    evening_period_summary["avg_range"] = (
        evening_period_summary[
            "avg_range"
        ].round(1)
    )

    print()
    print("[5001B 퇴근 17~20시 - 학기 vs 방학]")

    print(
        evening_period_summary.to_string(
            index=False
        )
    )

    # --------------------------------------------------
    # 10-7. 공휴일 vs 비공휴일
    # --------------------------------------------------

    holiday_summary = (
        calendar_valid.groupby(
            "holiday_type"
        )
        .agg(
            observed_cases=("opr_ymd", "count"),
            avg_congestion=("avg_congestion", "mean"),
            avg_range=("congestion_range", "mean"),
            max_range=("congestion_range", "max")
        )
        .reset_index()
    )

    holiday_summary["avg_congestion"] = (
        holiday_summary[
            "avg_congestion"
        ].round(1)
    )

    holiday_summary["avg_range"] = (
        holiday_summary[
            "avg_range"
        ].round(1)
    )

    print()
    print("[전체 - 공휴일 vs 비공휴일]")

    print(
        holiday_summary.to_string(
            index=False
        )
    )

    # --------------------------------------------------
    # 10-8. 공휴일별 상세
    # --------------------------------------------------

    holiday_detail = (
        calendar_valid[
            calendar_valid["is_holiday"] == 1
        ]
        .groupby([
            "opr_ymd",
            "holiday_name",
            "route_name"
        ])
        .agg(
            observed_cases=("station_id", "count"),
            avg_congestion=("avg_congestion", "mean"),
            avg_range=("congestion_range", "mean")
        )
        .reset_index()
    )

    holiday_detail["avg_congestion"] = (
        holiday_detail[
            "avg_congestion"
        ].round(1)
    )

    holiday_detail["avg_range"] = (
        holiday_detail[
            "avg_range"
        ].round(1)
    )

    print()
    print("[공휴일 상세]")

    print(
        holiday_detail.to_string(
            index=False
        )
    )

    # --------------------------------------------------
    # 10-9. 요일 × 시간 × 학기/방학
    # --------------------------------------------------

    period_day_hour = (
        calendar_valid[
            calendar_valid["period"].isin([
                "학기",
                "방학"
            ])
        ]
        .groupby([
            "route_name",
            "period",
            "dow_nm",
            "time_zone"
        ],
            observed=True
        )
        .agg(
            observed_cases=("opr_ymd", "count"),
            avg_congestion=("avg_congestion", "mean"),
            avg_range=("congestion_range", "mean")
        )
        .reset_index()
    )

    period_day_hour["avg_congestion"] = (
        period_day_hour[
            "avg_congestion"
        ].round(1)
    )

    period_day_hour["avg_range"] = (
        period_day_hour[
            "avg_range"
        ].round(1)
    )

    # --------------------------------------------------
    # 10-10. Excel 저장
    # --------------------------------------------------

    CALENDAR_OUTPUT = (
        "analysis/calendar_analysis.xlsx"
    )

    with pd.ExcelWriter(
        CALENDAR_OUTPUT,
        engine="openpyxl"
    ) as writer:

        period_summary.to_excel(
            writer,
            sheet_name="학기방학_전체",
            index=False
        )

        morning_period_summary.to_excel(
            writer,
            sheet_name="5001A출근_학기방학",
            index=False
        )

        evening_period_summary.to_excel(
            writer,
            sheet_name="5001B퇴근_학기방학",
            index=False
        )

        holiday_summary.to_excel(
            writer,
            sheet_name="공휴일_전체",
            index=False
        )

        holiday_detail.to_excel(
            writer,
            sheet_name="공휴일_상세",
            index=False
        )

        period_day_hour.to_excel(
            writer,
            sheet_name="학기방학_요일시간",
            index=False
        )

    print()
    print(
        f"달력 분석 Excel 저장 완료: "
        f"{CALENDAR_OUTPUT}"
    )


        # --------------------------------------------------
    # 11. 정류장별 시간대 × 요일 평균 혼잡도
    # --------------------------------------------------

    print()
    print("=== 정류장별 시간대 × 요일 평균 혼잡도 ===")

    DAY_ORDER = [
        "월요일",
        "화요일",
        "수요일",
        "목요일",
        "금요일",
        "토요일",
        "일요일"
    ]

    # 원본 혼잡도 데이터를 기준으로 계산
    station_avg = (
        df.groupby(
            [
                "route_name",
                "station_id",
                "station_seq",
                "time_zone",
                "dow_nm"
            ],
            observed=True
        )
        .agg(
            avg_congestion=("congestion", "mean"),
            data_count=("congestion", "count")
        )
        .reset_index()
    )

    station_avg["avg_congestion"] = (
        station_avg["avg_congestion"].round(1)
    )

    # --------------------------------------------------
    # Excel 저장
    # --------------------------------------------------

    OUTPUT_FILE = (
        "analysis/station_weekday_hour_average.xlsx"
    )

    with pd.ExcelWriter(
        OUTPUT_FILE,
        engine="openpyxl"
    ) as writer:

        # 전체 상세 데이터도 첫 시트에 저장
        station_avg.to_excel(
            writer,
            sheet_name="전체_상세",
            index=False
        )

        # 노선 → 정류장 순서대로 반복
        stations = (
            station_avg[
                [
                    "route_name",
                    "station_id",
                    "station_seq"
                ]
            ]
            .drop_duplicates()
            .sort_values(
                [
                    "route_name",
                    "station_seq"
                ]
            )
        )

        for _, station in stations.iterrows():

            route_name = station["route_name"]
            station_id = station["station_id"]
            station_seq = station["station_seq"]

            station_data = station_avg[
                (station_avg["route_name"] == route_name)
                & (station_avg["station_id"] == station_id)
            ].copy()

            # ------------------------------------------
            # 시간대 × 요일 피벗
            # ------------------------------------------

            pivot = station_data.pivot(
                index="time_zone",
                columns="dow_nm",
                values="avg_congestion"
            )

            # 요일 순서
            pivot = pivot.reindex(
                columns=DAY_ORDER
            )

            # 시간 순서
            pivot = pivot.sort_index()

            # ------------------------------------------
            # 시트 이름
            #
            # 예:
            # 5001A_27_4111657
            # ------------------------------------------

            sheet_name = (
                f"{route_name}_"
                f"{station_seq}_"
                f"{station_id}"
            )

            # Excel 시트 이름 최대 31자
            sheet_name = sheet_name[:31]

            pivot.to_excel(
                writer,
                sheet_name=sheet_name
            )

    print()
    print(
        f"저장 완료: {OUTPUT_FILE}"
    )