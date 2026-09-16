import os

import joblib
import pandas as pd


# ==================================================
# 기본 경로
# ==================================================

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)

MODEL_PATH = os.path.join(
    PROJECT_ROOT,
    "models",
    "highway_speed_model.pkl"
)


# ==================================================
# 설정값
# ==================================================

# 분석한 고속도로 구간
# 약 392.5 km ~ 415.3 km
HIGHWAY_DISTANCE_KM = 22.8

# 실제 데이터 분석 결과
# 출근시간대 강수 시 약 8% 속도 감소 경향
RAIN_SPEED_FACTOR = 0.92


# ==================================================
# 모델 로드
# ==================================================

_model = joblib.load(
    MODEL_PATH
)


# ==================================================
# 고속도로 속도 예측
# ==================================================

def predict_highway_speed(
    hour,
    day_of_week,
    temperature,
    humidity,
    wind_speed,
    rainfall=0.0,
):
    """
    출근시간대 고속도로 평균속도를 예측한다.

    day_of_week:
        월요일 = 0
        화요일 = 1
        수요일 = 2
        목요일 = 3
        금요일 = 4

    rainfall:
        강수량(mm)
        0보다 크면 강수 보정을 적용한다.
    """

    input_data = pd.DataFrame([
        {
            "hour": hour,
            "day_of_week": day_of_week,
            "temperature": temperature,
            "humidity": humidity,
            "wind_speed": wind_speed,
        }
    ])

    # Random Forest 기본 예측
    base_speed = float(
        _model.predict(
            input_data
        )[0]
    )

    # 강수 보정
    if rainfall > 0:
        adjusted_speed = (
            base_speed
            * RAIN_SPEED_FACTOR
        )
    else:
        adjusted_speed = base_speed

    return {
        "base_speed": round(
            base_speed,
            2
        ),
        "predicted_speed": round(
            adjusted_speed,
            2
        ),
        "rain_adjusted": rainfall > 0,
    }


# ==================================================
# 고속도로 예상 이동시간
# ==================================================

def predict_highway_time(
    hour,
    day_of_week,
    temperature,
    humidity,
    wind_speed,
    rainfall=0.0,
):

    speed_result = predict_highway_speed(
        hour=hour,
        day_of_week=day_of_week,
        temperature=temperature,
        humidity=humidity,
        wind_speed=wind_speed,
        rainfall=rainfall,
    )

    predicted_speed = (
        speed_result[
            "predicted_speed"
        ]
    )

    highway_minutes = (
        HIGHWAY_DISTANCE_KM
        / predicted_speed
        * 60
    )

    return {
        **speed_result,

        "distance_km":
            HIGHWAY_DISTANCE_KM,

        "highway_minutes":
            round(
                highway_minutes,
                1
            ),
    }