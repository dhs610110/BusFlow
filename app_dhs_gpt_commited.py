from __future__ import annotations

from contextvars import ContextVar
from datetime import datetime
from pathlib import Path

from flask import Response, jsonify, request

import app as friend_app

from services.highway_predictor_dhs_gpt_commited import (
    predict_highway_time as dhs_predict_highway_time,
)
from services.weather_delay_service_dhs_gpt_commited import (
    get_weather_delay_summary,
)
from services.weather_forecast_dhs_gpt_commited import (
    fetch_forecast,
)


app = friend_app.app
PROJECT_ROOT = Path(__file__).resolve().parent

_selected_date = ContextVar(
    "dhs_gpt_commited_selected_date",
    default=None,
)

_friend_predict_highway_time = friend_app.predict_highway_time


def _dhs_predict_adapter(*args, **kwargs):
    hour = kwargs.get("hour")
    if hour is None and args:
        hour = args[0]

    # 새 계절/강수 모델은 확보 데이터 범위인 출근 06~08시에만 사용.
    # 그 외 시간은 친구의 기존 함수를 그대로 사용한다.
    if int(hour) not in (6, 7, 8):
        return _friend_predict_highway_time(*args, **kwargs)

    kwargs["target_date"] = (
        _selected_date.get()
        or datetime.now().date()
    )
    return dhs_predict_highway_time(*args, **kwargs)


friend_app.predict_highway_time = _dhs_predict_adapter


def _inject_weather_notice_ui(html: str) -> str:
    old_chip = """<div class="weather-chip">
              추천 계산에 기상 조건을 반영할 수 있도록 연결 예정
            </div>"""

    new_chip = """<div id="weatherDelayNotice" class="weather-chip" hidden></div>"""

    if old_chip in html:
        html = html.replace(old_chip, new_chip, 1)

    addon = r"""
<script id="weatherDelayAddon_dhs_gpt_commited">
  async function refreshWeatherDelayNotice_dhs_gpt_commited(){
    const box=document.querySelector("#weatherDelayNotice");
    if(!box) return;

    try{
      const response=await fetch("/api/weather");
      if(!response.ok) throw new Error("weather api failed");
      const data=await response.json();

      if(data.weather_notice){
        box.textContent=data.weather_notice;
        box.hidden=false;
      }else{
        box.textContent="";
        box.hidden=true;
      }
    }catch(error){
      box.textContent="";
      box.hidden=true;
    }
  }

  window.addEventListener(
    "load",
    refreshWeatherDelayNotice_dhs_gpt_commited
  );
</script>
"""

    if "weatherDelayAddon_dhs_gpt_commited" not in html:
        html = html.replace("</body>", addon + "\n</body>", 1)

    return html


def timekeeper_dhs_gpt_commited():
    source = (
        PROJECT_ROOT / "Time_Keeper_mid_prototype.html"
    ).read_text(encoding="utf-8")

    return Response(
        _inject_weather_notice_ui(source),
        mimetype="text/html",
    )


# 친구의 /, /timekeeper 라우트는 그대로 두되,
# 이 병렬 app 실행 시에만 view function을 런타임 교체한다.
app.view_functions["timekeeper"] = timekeeper_dhs_gpt_commited


@app.get("/api/weather")
def weather_api_dhs_gpt_commited():
    target_text = request.args.get("datetime")
    if target_text:
        try:
            target = datetime.fromisoformat(target_text)
        except ValueError:
            return jsonify({"error": "invalid_datetime"}), 400
    else:
        target = datetime.now()

    try:
        weather = fetch_forecast(target)
        delay = get_weather_delay_summary(
            target.date(),
            weather.get("rainfall", 0.0),
        )

        result = {
            **weather,
            **delay,
        }

        rainfall = result.get("rainfall", 0.0)
        pop = result.get("precipitation_probability")
        condition = result.get("condition", "현재 날씨")

        detail = f"{condition} · 예상 강수 {rainfall:g} mm/h"
        if pop is not None:
            detail += f" · 강수확률 {pop:.0f}%"

        result["summary"] = detail
        return jsonify(result)

    except Exception as e:
        return jsonify({
            "error": "weather_forecast_failed",
            "message": str(e),
            "temperature": None,
            "humidity": None,
            "wind_speed": None,
            "rainfall": 0.0,
            "precipitation": 0.0,
            "condition": "날씨 API 대기",
            "emoji": "🌙",
            "weather_delay_percent": 0.0,
            "weather_delay_weight": 1.0,
            "weather_notice": None,
            "summary": "기상청 예보를 불러오지 못했습니다.",
        }), 503


@app.post("/api/recommend-v2")
def recommend_v2_dhs_gpt_commited():
    data = request.get_json(silent=True) or {}

    commute_mode = data.get("commute_mode", "morning")
    date_string = data.get("date")

    if not date_string:
        return jsonify({"error": "date 값이 필요합니다."}), 400

    departure_time = data.get("departure_time")
    arrival_time = data.get("arrival_time")

    if not departure_time:
        departure_time = (
            "07:00"
            if commute_mode == "morning"
            else "17:30"
        )

    if not arrival_time:
        arrival_time = (
            "08:50"
            if commute_mode == "morning"
            else "19:00"
        )

    try:
        target_dt = datetime.strptime(
            f"{date_string} {departure_time}",
            "%Y-%m-%d %H:%M",
        )
    except ValueError:
        return jsonify({
            "error": "날짜/시간 형식이 올바르지 않습니다."
        }), 400

    # 선택한 시각의 예보를 recommendation에 자동 주입
    try:
        weather = fetch_forecast(target_dt)
    except Exception:
        weather = {
            "temperature": None,
            "humidity": None,
            "wind_speed": None,
            "rainfall": 0.0,
        }

    mapped = {
        "date": date_string,
        "start_station": data.get("start_station"),
        "departure_time": departure_time,
        "arrival_time": arrival_time,
        "destination": data.get("destination"),
        "weather": {
            "temperature": weather.get("temperature"),
            "humidity": weather.get("humidity"),
            "wind_speed": weather.get("wind_speed"),
            "rainfall": weather.get("rainfall", 0.0),
        },
    }

    token = _selected_date.set(date_string)

    try:
        # 친구 recommend() 로직 자체는 건드리지 않고 그대로 재사용한다.
        with app.test_request_context(
            "/api/recommend",
            method="POST",
            json=mapped,
        ):
            return friend_app.recommend()
    finally:
        _selected_date.reset(token)


if __name__ == "__main__":
    app.run(
        debug=True,
        port=5001,
    )
