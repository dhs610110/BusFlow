from __future__ import annotations

from datetime import datetime

from services.weather_delay_service_dhs_gpt_commited import (
    predict_highway_weather_adjusted,
)


def predict_highway_time(
    hour,
    day_of_week=None,
    temperature=None,
    humidity=None,
    wind_speed=None,
    rainfall=0.0,
    target_date=None,
    is_public_holiday=False,
):
    """
    친구 코드의 predict_highway_time(...) 호출 형태를 유지하는 병렬 구현.
    기존 파일은 수정하지 않는다.

    이 구현은 현재 검증 범위인 06/07/08시에 사용하는 것을 전제로 한다.
    """
    if target_date is None:
        target_date = datetime.now().date()

    return predict_highway_weather_adjusted(
        target_date=target_date,
        hour=int(hour),
        rainfall_mm_per_hour=float(rainfall or 0.0),
        is_public_holiday=is_public_holiday,
    )
