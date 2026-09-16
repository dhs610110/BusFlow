import os

import joblib
import pandas as pd


# ==================================================
# 모델 경로
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
# 모델 불러오기
# ==================================================

model = joblib.load(
    MODEL_PATH
)


# ==================================================
# 테스트할 상황
# ==================================================
#
# 예시:
# 화요일 오전 8시
# 강수량 1.0 mm
# 기온 20도
# 습도 80%
# 풍속 2.0 m/s
#
# day_of_week
# 월=0
# 화=1
# 수=2
# 목=3
# 금=4
# ==================================================

test_data = pd.DataFrame([
    {
        "hour": 8,
        "day_of_week": 1,
        "rainfall": 0.0,
        "temperature": 20.0,
        "humidity": 80.0,
        "wind_speed": 2.0,
    }
])


# ==================================================
# 고속도로 평균속도 예측
# ==================================================

predicted_speed = model.predict(
    test_data
)[0]


# ==================================================
# 고속도로 이동시간 계산
# ==================================================
#
# 분석 대상 구간:
# 약 392.5 km ~ 415.3 km
#
# 거리 약 22.8 km
# ==================================================

HIGHWAY_DISTANCE_KM = 22.8

highway_minutes = (
    HIGHWAY_DISTANCE_KM
    / predicted_speed
    * 60
)


# ==================================================
# 결과 출력
# ==================================================

print(
    "\n===== HIGHWAY SPEED PREDICTION ====="
)

print(
    "Hour:",
    test_data.iloc[0]["hour"]
)

print(
    "Day of week:",
    test_data.iloc[0]["day_of_week"]
)

print(
    "Rainfall:",
    test_data.iloc[0]["rainfall"],
    "mm"
)

print(
    "Temperature:",
    test_data.iloc[0]["temperature"],
    "°C"
)

print(
    "Humidity:",
    test_data.iloc[0]["humidity"],
    "%"
)

print(
    "Wind speed:",
    test_data.iloc[0]["wind_speed"],
    "m/s"
)

print(
    "\nPredicted highway speed:",
    round(
        predicted_speed,
        2
    ),
    "km/h"
)

print(
    "Estimated highway time:",
    round(
        highway_minutes,
        1
    ),
    "minutes"
)