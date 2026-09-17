from services.weather_delay_service_dhs_gpt_commited import (
    get_weather_delay_summary,
    predict_highway_weather_adjusted,
)


def test_rain_intensity_is_monotonic_in_summer():
    values = [
        get_weather_delay_summary("2026-07-15", r)["weather_delay_percent"]
        for r in [0, 1, 3, 10, 20]
    ]
    assert values == sorted(values)


def test_summer_weekday_7am_rain_increases_time():
    dry = predict_highway_weather_adjusted(
        "2026-07-15", 7, 0.0
    )
    rainy = predict_highway_weather_adjusted(
        "2026-07-15", 7, 4.2
    )
    assert rainy["highway_minutes"] > dry["highway_minutes"]
    assert rainy["weather_delay_percent"] > 0
