# BusFlow dhs_gpt_commited overlay

친구가 만든 기존 파일은 수정하지 않습니다.

실행:
```bash
python app_dhs_gpt_commited.py
```

추가 파일:
- `app_dhs_gpt_commited.py`
- `services/weather_delay_config_dhs_gpt_commited.json`
- `services/weather_delay_service_dhs_gpt_commited.py`
- `services/weather_forecast_dhs_gpt_commited.py`
- `services/highway_predictor_dhs_gpt_commited.py`
- `tests/test_weather_delay_dhs_gpt_commited.py`

동작:
- 기존 `app.py`의 Flask app과 추천 로직을 import해서 재사용
- 원본 `app.py`, `services/highway_predictor.py`, HTML은 디스크에서 수정하지 않음
- 실행 중에만 `/api/weather`, `/api/recommend-v2`를 추가
- 메인 HTML도 응답 시점에만 날씨 지연 문구 영역을 주입
- 출근 06~08시는 계절×평일/휴일 baseline + 강수량(mm/h) 지연 가중치 사용
- 그 외 시간대는 친구의 기존 `highway_predictor.py`를 그대로 사용
