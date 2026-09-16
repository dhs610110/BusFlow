import os
import io
import re
import zipfile
import sqlite3
from pathlib import Path

import pandas as pd


# =========================================================
# 경로 설정
# =========================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_ROOT / "data"

# 네가 다운로드한 원본 데이터들을 넣을 폴더
RAW_DIR = DATA_DIR / "highway_raw"

# VDS 위치/코드 정보 엑셀
VDS_INFO_FILE = RAW_DIR / (
    "12.+VDS기반+고속도로+지점별+교통+소통+통계+데이터"
    "(1시간+단위).xlsx"
)

# 2월~6월 초 데이터 압축파일
ARCHIVE_FILE = RAW_DIR / "아카이브.zip"

# 결과
OUTPUT_CSV = DATA_DIR / "highway_speed.csv"
OUTPUT_DB = DATA_DIR / "highway_speed.db"


# =========================================================
# 우리가 사용할 경부고속도로 구간
# =========================================================

ROUTE_NO = "0010"

# 경부고속도로
# 부산 → 서울 = 종점 방향(E)
TARGET_DIRECTION = "E"

# 수원신갈IC ~ 양재IC 근처
MIN_KM = 392.3
MAX_KM = 415.5


# =========================================================
# 컬럼 이름 자동 탐색
# =========================================================

def find_column(columns, keywords):
    """
    컬럼명 안에 keywords 중 하나가 들어가는 컬럼 찾기
    """

    for column in columns:

        normalized = str(column).replace(" ", "").upper()

        for keyword in keywords:

            if keyword.replace(" ", "").upper() in normalized:
                return column

    return None


# =========================================================
# VDS 위치정보 불러오기
# =========================================================

def load_target_vds():

    print("\n" + "=" * 60)
    print("VDS 위치정보 불러오기")
    print("=" * 60)

    excel = pd.ExcelFile(VDS_INFO_FILE)

    print("엑셀 시트:")
    for sheet in excel.sheet_names:
        print(" -", sheet)

    # 우리가 확인했던 시트
    sheet_name = "VDS코드(코드)"

    df = pd.read_excel(
        VDS_INFO_FILE,
        sheet_name=sheet_name
    )

    print("\n전체 VDS 개수:", len(df))
    print("컬럼:")
    print(df.columns.tolist())

    # -----------------------------------------------------
    # 컬럼 자동 탐색
    # -----------------------------------------------------

    vds_col = "VDS 코드"
    km_col = "Unnamed: 1"
    route_col = "Unnamed: 2"
    direction_col = "Unnamed: 3"

    print("\n사용 컬럼:")
    print("VDS:", vds_col)
    print("노선:", route_col)
    print("방향:", direction_col)
    print("이정:", km_col)

    if not all([
        vds_col,
        route_col,
        direction_col,
        km_col
    ]):

        raise ValueError(
            "\n필수 컬럼을 찾지 못했습니다.\n"
            f"VDS: {vds_col}\n"
            f"노선: {route_col}\n"
            f"방향: {direction_col}\n"
            f"이정: {km_col}\n"
        )

    # -----------------------------------------------------
    # 형식 정리
    # -----------------------------------------------------

    df[route_col] = (
        df[route_col]
        .astype(str)
        .str.strip()
        .str.replace(".0", "", regex=False)
        .str.zfill(4)
    )

    df[direction_col] = (
        df[direction_col]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    df[km_col] = pd.to_numeric(
        df[km_col],
        errors="coerce"
    )

    df[vds_col] = (
        df[vds_col]
        .astype(str)
        .str.strip()
    )

    # VDS 코드 앞 4자리 0010 = 경부고속도로
    gyeongbu = df[
        df[vds_col].str.startswith("0010", na=False)
    ].copy()

    print("\n" + "=" * 60)
    print("경부고속도로 VDS 확인")
    print("=" * 60)

    print("경부고속도로 VDS 행:", len(gyeongbu))

    print("\n방향 분포:")
    print(
        gyeongbu[direction_col]
        .value_counts(dropna=False)
    )

    print("\n이정 범위:")
    print(
        gyeongbu[km_col].min(),
        "~",
        gyeongbu[km_col].max()
    )

    # 서울방향 + 수원신갈 ~ 양재 구간
    target = gyeongbu[
        (gyeongbu[direction_col] == TARGET_DIRECTION)
        & (gyeongbu[km_col] >= MIN_KM)
        & (gyeongbu[km_col] <= MAX_KM)
    ].copy()

    if target.empty:
        print("\n[ERROR] 대상 VDS가 0개입니다.")
        print("ZIP 처리를 시작하지 않습니다.")
        raise SystemExit

    target = target[
        [
            vds_col,
            route_col,
            direction_col,
            km_col
        ]
    ].copy()

    target.columns = [
        "vds_id",
        "route_no",
        "direction",
        "km"
    ]

    target["route_no"] = ROUTE_NO

    target = (
        target
        .drop_duplicates("vds_id")
        .sort_values("km")
    )

    print("\n대상 VDS 개수:", len(target))

    print("\n대상 VDS:")
    print(
        target.to_string(index=False)
    )

    return target


# =========================================================
# CSV 인코딩 자동 처리
# =========================================================

def read_csv_auto(source):

    encodings = [
        "utf-8-sig",
        "cp949",
        "euc-kr",
        "utf-8"
    ]

    last_error = None

    for encoding in encodings:

        try:
            return pd.read_csv(
                source,
                encoding=encoding,
                low_memory=False
            )

        except Exception as error:
            last_error = error

            if hasattr(source, "seek"):
                source.seek(0)

    raise last_error


# =========================================================
# 날짜 추출
# =========================================================

def extract_date(filename):

    match = re.search(
        r"(20\d{6})",
        filename
    )

    if not match:
        return None

    date_str = match.group(1)

    return pd.to_datetime(
        date_str,
        format="%Y%m%d",
        errors="coerce"
    )


# =========================================================
# 하루치 CSV 정리
# =========================================================

def process_daily_csv(df, filename, target_vds):

    if df.empty:
        return pd.DataFrame()

    # -----------------------------------------------------
    # 컬럼 찾기
    # -----------------------------------------------------

    vds_col = find_column(
        df.columns,
        ["VDS_CD", "VDS_ID", "VDSID"]
    )

    speed_col = find_column(
        df.columns,
        ["SPD_AVG", "평균속도", "AVG_SPEED"]
    )

    volume_col = find_column(
        df.columns,
        ["TRFFCVLM", "교통량", "VOLUME"]
    )

    occupancy_col = find_column(
        df.columns,
        ["OCCPNCY", "점유율", "OCCUPANCY"]
    )

    hour_col = find_column(
        df.columns,
        ["SUM_HR","SUM_HH", "집계시", "시간", "HOUR"]
    )

    date_col = find_column(
        df.columns,
        ["SUM_YRMHDAT","SUM_YMD", "집계일자", "기준일자", "DATE"]
    )

    if not vds_col or not speed_col:
        print(f"[SKIP] 필수 컬럼 없음: {filename}")
        return pd.DataFrame()
    # =========================
    # 임시 디버깅
    # =========================

    # -----------------------------------------------------
    # 핵심 최적화:
    # 20만 행 전체를 변환하기 전에 목표 VDS 23개만 먼저 추출
    # -----------------------------------------------------

    target_ids = set(
        target_vds["vds_id"]
        .astype(str)
        .str.strip()
    )

    # 대부분 원본 VDS 값이 이미 정확한 문자열이므로
    # 먼저 가장 빠른 isin()으로 필터링한다.
    mask = df[vds_col].isin(target_ids)

    # 혹시 공백/형식 문제로 하나도 안 잡힌 경우에만
    # 문자열 정리를 한 번 수행한다.
    if not mask.any():
        normalized_vds = (
            df[vds_col]
            .astype(str)
            .str.strip()
        )
        mask = normalized_vds.isin(target_ids)

    df = df.loc[mask].copy()

    if df.empty:
        print(f"    [SKIP] 대상 VDS 없음: {filename}")
        return pd.DataFrame()

    # -----------------------------------------------------
    # 필요한 행만 정리
    # -----------------------------------------------------

    result = pd.DataFrame(index=df.index)

    result["vds_id"] = (
        df[vds_col]
        .astype(str)
        .str.strip()
    )

    result["avg_speed"] = pd.to_numeric(
        df[speed_col],
        errors="coerce"
    )

    if volume_col:
        result["traffic_volume"] = pd.to_numeric(
            df[volume_col],
            errors="coerce"
        )
    else:
        result["traffic_volume"] = None

    if occupancy_col:
        result["occupancy"] = pd.to_numeric(
            df[occupancy_col],
            errors="coerce"
        )
    else:
        result["occupancy"] = None

    if hour_col:
        result["hour"] = pd.to_numeric(
            df[hour_col],
            errors="coerce"
        )
    else:
        result["hour"] = None

    if date_col:
        raw_date = (
            df[date_col]
            .astype(str)
            .str.replace(".0", "", regex=False)
        )

        result["date"] = pd.to_datetime(
            raw_date,
            format="%Y%m%d",
            errors="coerce"
        )
    else:
        result["date"] = extract_date(filename)

    # 인덱스 정리
    result = result.reset_index(drop=True)

    # VDS 위치 정보 결합
    result = result.merge(
        target_vds,
        on="vds_id",
        how="left"
    )

    # -----------------------------------------------------
    # 비정상 데이터 제거
    # -----------------------------------------------------

    result = result[
        result["avg_speed"].notna()
    ]

    result = result[
        (result["avg_speed"] > 0)
        & (result["avg_speed"] <= 200)
    ]

    result["hour"] = pd.to_numeric(
        result["hour"],
        errors="coerce"
    )

    result = result[
        result["hour"].between(0, 23)
    ]

    print(
        f"    저장 대상 행: {len(result)}"
    )

    return result


# =========================================================
# ZIP 안의 CSV 읽기
# =========================================================

def process_zip_file(
    zip_path,
    target_vds
):

    results = []

    print("\nZIP 처리:", zip_path.name)

    with zipfile.ZipFile(
        zip_path,
        "r"
    ) as outer_zip:

        for name in outer_zip.namelist():

            # macOS가 ZIP에 자동으로 넣는 메타데이터는 무시
            if (
                name.startswith("__MACOSX/")
                or Path(name).name.startswith("._")
            ):
                continue

            # ---------------------------------------------
            # CSV 바로 들어있는 경우
            # ---------------------------------------------

            if name.lower().endswith(".csv"):

                print("  CSV:", name)

                raw = outer_zip.read(name)
                buffer = io.BytesIO(raw)

                try:
                    df = read_csv_auto(buffer)

                    processed = process_daily_csv(
                        df,
                        name,
                        target_vds
                    )

                    if not processed.empty:
                        results.append(processed)

                except Exception as e:
                    print("   오류:", e)

            # ---------------------------------------------
            # ZIP 안에 ZIP 있는 경우
            # ---------------------------------------------

            elif name.lower().endswith(".zip"):

                print("  내부 ZIP:", name)

                nested_raw = outer_zip.read(name)
                nested_buffer = io.BytesIO(nested_raw)

                try:
                    with zipfile.ZipFile(
                        nested_buffer,
                        "r"
                    ) as nested_zip:

                        for nested_name in nested_zip.namelist():

                            if (
                                nested_name.startswith("__MACOSX/")
                                or Path(nested_name).name.startswith("._")
                            ):
                                continue

                            if not nested_name.lower().endswith(".csv"):
                                continue

                            print("    CSV:", nested_name)

                            raw_csv = nested_zip.read(nested_name)
                            csv_buffer = io.BytesIO(raw_csv)

                            df = read_csv_auto(csv_buffer)

                            processed = process_daily_csv(
                                df,
                                nested_name,
                                target_vds
                            )

                            if not processed.empty:
                                results.append(processed)

                except Exception as e:
                    print("   내부 ZIP 오류:", e)

    return results


# =========================================================
# RAW 폴더의 개별 CSV 읽기
# =========================================================

def process_individual_csvs(
    target_vds
):

    results = []

    csv_files = sorted(
        RAW_DIR.glob("*.csv")
    )

    print(
        "\n개별 CSV 개수:",
        len(csv_files)
    )

    for csv_file in csv_files:

        print(
            "CSV 처리:",
            csv_file.name
        )

        try:

            df = read_csv_auto(
                csv_file
            )

            processed = process_daily_csv(
                df,
                csv_file.name,
                target_vds
            )

            if not processed.empty:
                results.append(
                    processed
                )

        except Exception as e:

            print(
                "오류:",
                csv_file.name,
                e
            )

    return results


# =========================================================
# SQLite 저장
# =========================================================

def save_to_database(df):

    print("\nDB 저장 중...")

    connection = sqlite3.connect(
        OUTPUT_DB
    )

    connection.execute(
        """
        DROP TABLE IF EXISTS highway_speed
        """
    )

    connection.execute(
        """
        CREATE TABLE highway_speed (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            date TEXT NOT NULL,
            hour INTEGER NOT NULL,

            vds_id TEXT NOT NULL,

            route_no TEXT,
            direction TEXT,

            km REAL,

            avg_speed REAL,
            traffic_volume INTEGER,
            occupancy REAL
        )
        """
    )

    save_df = df.copy()

    save_df["date"] = (
        pd.to_datetime(
            save_df["date"]
        )
        .dt.strftime("%Y-%m-%d")
    )

    save_df[
        [
            "date",
            "hour",
            "vds_id",
            "route_no",
            "direction",
            "km",
            "avg_speed",
            "traffic_volume",
            "occupancy"
        ]
    ].to_sql(
        "highway_speed",
        connection,
        if_exists="append",
        index=False
    )

    # 조회속도 개선
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_highway_date_hour
        ON highway_speed(date, hour)
        """
    )

    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_highway_vds
        ON highway_speed(vds_id)
        """
    )

    connection.commit()
    connection.close()

    print(
        "DB 저장 완료:",
        OUTPUT_DB
    )


# =========================================================
# 최종 통계
# =========================================================

def print_summary(df):

    print("\n" + "=" * 60)
    print("최종 결과")
    print("=" * 60)

    print(
        "총 행:",
        len(df)
    )

    print(
        "날짜:",
        df["date"].min(),
        "~",
        df["date"].max()
    )

    print(
        "날짜 수:",
        df["date"].dt.date.nunique()
    )

    print(
        "VDS 수:",
        df["vds_id"].nunique()
    )

    print(
        "이정 범위:",
        df["km"].min(),
        "~",
        df["km"].max()
    )

    print(
        "평균속도:",
        round(
            df["avg_speed"].mean(),
            2
        ),
        "km/h"
    )

    print("\n시간별 평균속도:")

    hourly = (
        df
        .groupby("hour")["avg_speed"]
        .mean()
        .round(2)
    )

    print(hourly)


# =========================================================
# 실행
# =========================================================

def main():

    DATA_DIR.mkdir(
        exist_ok=True
    )

    # 1.
    # VDS 위치정보에서
    # 경부고속도로 서울방향 구간 추출
    target_vds = load_target_vds()

    all_results = []

    # 2.
    # 아카이브 ZIP
    if ARCHIVE_FILE.exists():

        archive_results = process_zip_file(
            ARCHIVE_FILE,
            target_vds
        )

        all_results.extend(
            archive_results
        )

    else:

        print(
            "\n아카이브 없음:",
            ARCHIVE_FILE
        )

    # 3.
    # 별도로 받은 6월 CSV
    individual_results = (
        process_individual_csvs(
            target_vds
        )
    )

    all_results.extend(
        individual_results
    )

    # 4.
    # 합치기
    if not all_results:

        print(
            "\n처리 가능한 데이터가 없습니다."
        )

        return

    final_df = pd.concat(
        all_results,
        ignore_index=True
    )

    # 5.
    # 중복 제거
    final_df = (
        final_df
        .drop_duplicates(
            subset=[
                "date",
                "hour",
                "vds_id"
            ],
            keep="last"
        )
        .sort_values(
            [
                "date",
                "hour",
                "km"
            ]
        )
        .reset_index(
            drop=True
        )
    )

    # 날짜 형식 보장
    final_df["date"] = pd.to_datetime(
        final_df["date"]
    )

    # -----------------------------------------------------
    # CSV 저장
    # -----------------------------------------------------

    csv_df = final_df.copy()

    csv_df["date"] = (
        csv_df["date"]
        .dt.strftime("%Y-%m-%d")
    )

    csv_df.to_csv(
        OUTPUT_CSV,
        index=False,
        encoding="utf-8-sig"
    )

    print(
        "\nCSV 저장 완료:",
        OUTPUT_CSV
    )

    # -----------------------------------------------------
    # SQLite 저장
    # -----------------------------------------------------

    save_to_database(
        final_df
    )

    # -----------------------------------------------------
    # 결과 출력
    # -----------------------------------------------------

    print_summary(
        final_df
    )


if __name__ == "__main__":
    main()