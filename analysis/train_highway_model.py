import os
import sqlite3

import numpy as np
import pandas as pd

from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
)
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


# ==================================================
# 1. 기본 경로
# ==================================================

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)

HIGHWAY_DB = os.path.join(
    PROJECT_ROOT,
    "data",
    "highway_speed.db"
)

WEATHER_DB = os.path.join(
    PROJECT_ROOT,
    "data",
    "weather.db"
)


# ==================================================
# 2. 고속도로 데이터 불러오기
# ==================================================

def load_highway_data():

    connection = sqlite3.connect(HIGHWAY_DB)

    query = """
        SELECT
            date,
            hour,
            AVG(avg_speed) AS avg_speed

        FROM highway_speed

        WHERE hour BETWEEN 6 AND 8

        GROUP BY
            date,
            hour

        ORDER BY
            date,
            hour
    """

    df = pd.read_sql_query(
        query,
        connection
    )

    connection.close()

    return df


# ==================================================
# 3. 날씨 데이터 불러오기
# ==================================================

def load_weather_data():

    connection = sqlite3.connect(WEATHER_DB)

    query = """
        SELECT

            substr(opr_ymd, 1, 4) || '-' ||
            substr(opr_ymd, 5, 2) || '-' ||
            substr(opr_ymd, 7, 2)
                AS date,

            CAST(
                substr(time_zone, 1, 2)
                AS INTEGER
            )
                AS hour,

            AVG(
                COALESCE(rainfall, 0)
            )
                AS rainfall,

            AVG(temperature)
                AS temperature,

            AVG(humidity)
                AS humidity,

            AVG(wind_speed)
                AS wind_speed

        FROM weather

        WHERE time_zone IN (
            '06~07',
            '07~08',
            '08~09'
        )

        GROUP BY
            opr_ymd,
            time_zone

        ORDER BY
            opr_ymd,
            time_zone
    """

    df = pd.read_sql_query(
        query,
        connection
    )

    connection.close()

    return df


# ==================================================
# 4. ML 데이터셋 생성
# ==================================================

def build_dataset():

    highway = load_highway_data()
    weather = load_weather_data()

    # 날짜 + 시간 기준 JOIN
    df = pd.merge(
        highway,
        weather,
        on=["date", "hour"],
        how="inner"
    )

    # 날짜 형식 변환
    df["date"] = pd.to_datetime(
        df["date"]
    )

    # 월요일 = 0
    # 화요일 = 1
    # ...
    # 일요일 = 6
    df["day_of_week"] = (
        df["date"].dt.dayofweek
    )

    # 비가 왔는지 여부
    # 0mm → 0
    # 0mm 초과 → 1

    # 평일만 사용
    df = df[
        df["day_of_week"] <= 4
    ].copy()

    # 결측치 제거
    df = df.dropna()

    # 날짜 / 시간순 정렬
    df = df.sort_values(
        ["date", "hour"]
    ).reset_index(drop=True)

    return df


# ==================================================
# 5. Feature 설정
# ==================================================

FEATURES = [
    "hour",
    "day_of_week",
    "temperature",
    "humidity",
    "wind_speed",
]

TARGET = "avg_speed"


# 범주형 변수
CATEGORICAL_FEATURES = [
    "hour",
    "day_of_week",
]


# 연속형 / 수치형 변수
NUMERIC_FEATURES = [
    "temperature",
    "humidity",
    "wind_speed",
]


# ==================================================
# 6. One-Hot Encoding
# ==================================================

def create_preprocessor():

    return ColumnTransformer(
        transformers=[
            (
                "categorical",
                OneHotEncoder(
                    handle_unknown="ignore"
                ),
                CATEGORICAL_FEATURES
            ),
            (
                "numeric",
                "passthrough",
                NUMERIC_FEATURES
            ),
        ]
    )


# ==================================================
# 7. Linear Regression 모델
# ==================================================

def create_linear_model():

    return Pipeline([
        (
            "preprocessor",
            create_preprocessor()
        ),
        (
            "model",
            LinearRegression()
        )
    ])


# ==================================================
# 8. Random Forest 모델
# ==================================================

def create_random_forest_model():

    return Pipeline([
        (
            "preprocessor",
            create_preprocessor()
        ),
        (
            "model",
            RandomForestRegressor(
                n_estimators=300,
                max_depth=6,
                min_samples_leaf=3,
                random_state=42
            )
        )
    ])


# ==================================================
# 9. 평가 함수
# ==================================================

def evaluate_model(
    model,
    X_train,
    y_train,
    X_test,
    y_test
):

    model.fit(
        X_train,
        y_train
    )

    predictions = model.predict(
        X_test
    )

    mae = mean_absolute_error(
        y_test,
        predictions
    )

    rmse = np.sqrt(
        mean_squared_error(
            y_test,
            predictions
        )
    )

    return mae, rmse


# ==================================================
# 10. Time Series Cross Validation
# ==================================================

def time_series_validation(df):

    X = df[FEATURES]
    y = df[TARGET]

    # 시간 순서를 유지한 5번의 검증
    tscv = TimeSeriesSplit(
        n_splits=5
    )

    linear_maes = []
    linear_rmses = []

    rf_maes = []
    rf_rmses = []

    print(
        "\n========================================"
    )

    print(
        "TIME SERIES CROSS VALIDATION"
    )

    print(
        "========================================"
    )

    for fold, (
        train_index,
        test_index
    ) in enumerate(
        tscv.split(X),
        start=1
    ):

        X_train = X.iloc[
            train_index
        ]

        X_test = X.iloc[
            test_index
        ]

        y_train = y.iloc[
            train_index
        ]

        y_test = y.iloc[
            test_index
        ]

        train_dates = df.iloc[
            train_index
        ]["date"]

        test_dates = df.iloc[
            test_index
        ]["date"]

        # 매 Fold마다 새 모델 생성
        linear_model = (
            create_linear_model()
        )

        rf_model = (
            create_random_forest_model()
        )

        # Linear Regression
        linear_mae, linear_rmse = (
            evaluate_model(
                linear_model,
                X_train,
                y_train,
                X_test,
                y_test
            )
        )

        # Random Forest
        rf_mae, rf_rmse = (
            evaluate_model(
                rf_model,
                X_train,
                y_train,
                X_test,
                y_test
            )
        )

        linear_maes.append(
            linear_mae
        )

        linear_rmses.append(
            linear_rmse
        )

        rf_maes.append(
            rf_mae
        )

        rf_rmses.append(
            rf_rmse
        )

        print(
            f"\n----- Fold {fold} -----"
        )

        print(
            "Train:",
            train_dates.min().date(),
            "~",
            train_dates.max().date()
        )

        print(
            "Test :",
            test_dates.min().date(),
            "~",
            test_dates.max().date()
        )

        print(
            "Linear MAE :",
            round(
                linear_mae,
                2
            ),
            "km/h"
        )

        print(
            "Linear RMSE:",
            round(
                linear_rmse,
                2
            ),
            "km/h"
        )

        print(
            "RF MAE     :",
            round(
                rf_mae,
                2
            ),
            "km/h"
        )

        print(
            "RF RMSE    :",
            round(
                rf_rmse,
                2
            ),
            "km/h"
        )

    # ==================================================
    # Cross Validation 평균
    # ==================================================

    linear_avg_mae = np.mean(
        linear_maes
    )

    linear_avg_rmse = np.mean(
        linear_rmses
    )

    rf_avg_mae = np.mean(
        rf_maes
    )

    rf_avg_rmse = np.mean(
        rf_rmses
    )

    print(
        "\n========================================"
    )

    print(
        "CROSS VALIDATION AVERAGE"
    )

    print(
        "========================================"
    )

    print(
        "\nLinear Regression"
    )

    print(
        "Average MAE :",
        round(
            linear_avg_mae,
            2
        ),
        "km/h"
    )

    print(
        "Average RMSE:",
        round(
            linear_avg_rmse,
            2
        ),
        "km/h"
    )

    print(
        "\nRandom Forest"
    )

    print(
        "Average MAE :",
        round(
            rf_avg_mae,
            2
        ),
        "km/h"
    )

    print(
        "Average RMSE:",
        round(
            rf_avg_rmse,
            2
        ),
        "km/h"
    )

    return {
        "linear_mae": linear_avg_mae,
        "linear_rmse": linear_avg_rmse,
        "rf_mae": rf_avg_mae,
        "rf_rmse": rf_avg_rmse,
    }


# ==================================================
# 11. 데이터셋 기본 정보
# ==================================================

def print_dataset_info(df):

    print(
        "\n========================================"
    )

    print(
        "ML DATASET"
    )

    print(
        "========================================"
    )

    print(
        df.head(20)
    )

    print(
        "\nRows:",
        len(df)
    )

    print(
        "\nDate range:"
    )

    print(
        df["date"].min().date(),
        "~",
        df["date"].max().date()
    )

    print(
        "\nRain samples:"
    )


    print(
        "\nAverage speed:"
    )

    print(
        round(
            df["avg_speed"].mean(),
            2
        ),
        "km/h"
    )


# ==================================================
# 12. 실행
# ==================================================

if __name__ == "__main__":

    dataset = build_dataset()

    print_dataset_info(
        dataset
    )

    results = time_series_validation(
        dataset
    )