from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

CONFIG_PATH = Path(__file__).with_name(
    "weather_delay_config_dhs_gpt_commited.json"
)

with CONFIG_PATH.open("r", encoding="utf-8") as f:
    CONFIG = json.load(f)


def _parse_date(value: Any) -> date:
    if value is None:
        return datetime.now().date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    text = str(value).strip()
    for fmt, width in (
        ("%Y-%m-%d", 10),
        ("%Y%m%d", 8),
        ("%Y/%m/%d", 10),
    ):
        try:
            return datetime.strptime(text[:width], fmt).date()
        except ValueError:
            pass
    raise ValueError(f"지원하지 않는 날짜 형식: {value}")


def get_season(month: int) -> str:
    if month in (12, 1, 2):
        return "winter"
    if month in (3, 4, 5):
        return "spring"
    if month in (6, 7, 8):
        return "summer"
    return "fall"


def get_day_type(target_date: Any, is_public_holiday: bool = False) -> str:
    d = _parse_date(target_date)
    return "holiday" if is_public_holiday or d.weekday() >= 5 else "weekday"


def get_rain_delay_weight(season: str, rainfall_mm_per_hour: float) -> float:
    rain = max(0.0, float(rainfall_mm_per_hour or 0.0))
    if rain <= 0:
        return 1.0

    points = CONFIG["rain_delay_knots"][season]
    if rain >= float(points[-1]["rain_mm_per_hour"]):
        return float(points[-1]["delay_weight"])

    for left, right in zip(points, points[1:]):
        x0 = float(left["rain_mm_per_hour"])
        x1 = float(right["rain_mm_per_hour"])
        if x0 <= rain <= x1:
            y0 = float(left["delay_weight"])
            y1 = float(right["delay_weight"])
            if x1 == x0:
                return y1
            t = (rain - x0) / (x1 - x0)
            return y0 + t * (y1 - y0)

    return 1.0


def get_weather_delay_summary(target_date: Any, rainfall_mm_per_hour: float) -> dict:
    d = _parse_date(target_date)
    season = get_season(d.month)
    rain = max(0.0, float(rainfall_mm_per_hour or 0.0))
    weight = get_rain_delay_weight(season, rain)
    delay_percent = max(0.0, (weight - 1.0) * 100.0)

    notice = None
    if rain > 0 and delay_percent > 0:
        notice = (
            f"예상 강수량 {rain:g} mm/h의 비가 예보되어 "
            f"평소보다 약 {delay_percent:.1f}% 더 지연될 수 있습니다."
        )

    return {
        "season": season,
        "rainfall_mm_per_hour": round(rain, 2),
        "weather_delay_weight": round(weight, 4),
        "weather_delay_percent": round(delay_percent, 1),
        "weather_notice": notice,
    }


def get_baseline(
    target_date: Any,
    hour: int,
    is_public_holiday: bool = False,
) -> dict:
    d = _parse_date(target_date)
    season = get_season(d.month)
    day_type = get_day_type(d, is_public_holiday)

    supported = sorted({int(r["hour"]) for r in CONFIG["baseline"]})
    used_hour = min(supported, key=lambda h: abs(h - int(hour)))

    for row in CONFIG["baseline"]:
        if (
            row["season"] == season
            and row["day_type"] == day_type
            and int(row["hour"]) == used_hour
        ):
            result = dict(row)
            result["requested_hour"] = int(hour)
            result["used_hour"] = used_hour
            result["hour_was_clamped"] = int(hour) != used_hour
            return result

    raise KeyError(
        f"baseline not found: {season}/{day_type}/{used_hour}"
    )


def predict_highway_weather_adjusted(
    target_date: Any,
    hour: int,
    rainfall_mm_per_hour: float = 0.0,
    is_public_holiday: bool = False,
) -> dict:
    baseline = get_baseline(
        target_date,
        hour,
        is_public_holiday=is_public_holiday,
    )
    delay = get_weather_delay_summary(
        target_date,
        rainfall_mm_per_hour,
    )

    baseline_time = float(baseline["baseline_time_min"])
    weight = float(delay["weather_delay_weight"])
    final_time = baseline_time * weight
    distance = float(CONFIG["distance_km"])
    final_speed = distance / (final_time / 60.0)

    return {
        "base_speed": round(float(baseline["baseline_speed_kmh"]), 2),
        "predicted_speed": round(final_speed, 2),
        "rain_adjusted": float(rainfall_mm_per_hour or 0.0) > 0,
        "distance_km": distance,
        "highway_minutes": round(final_time, 1),
        "baseline_highway_minutes": round(baseline_time, 1),
        "weather_delay_percent": delay["weather_delay_percent"],
        "weather_delay_weight": delay["weather_delay_weight"],
        "weather_notice": delay["weather_notice"],
        "season": baseline["season"],
        "day_type": baseline["day_type"],
        "baseline_hour": baseline["used_hour"],
        "hour_was_clamped": baseline["hour_was_clamped"],
        "prediction_method": "seasonal_baseline_rainfall_weight_dhs_gpt_commited",
    }
