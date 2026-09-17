from __future__ import annotations

import os
import re
from datetime import datetime, timedelta

import requests

from config import KMA_API_KEY

URL = (
    "https://apis.data.go.kr/1360000/"
    "VilageFcstInfoService_2.0/getVilageFcst"
)

# BusFlow의 기존 기상 수집이 용인권을 수원 관측소(119)에 매핑하는 점을 따라
# 기본 예보 격자도 수원권으로 둔다. 필요하면 환경변수로 즉시 교체 가능.
DEFAULT_NX = int(os.getenv("KMA_FORECAST_NX", "60"))
DEFAULT_NY = int(os.getenv("KMA_FORECAST_NY", "121"))

BASE_TIMES = [2, 5, 8, 11, 14, 17, 20, 23]


def _latest_base_datetime(now: datetime) -> datetime:
    # 발표 직후 API 반영 지연을 감안해 15분 여유
    candidates = []
    today = now.replace(minute=0, second=0, microsecond=0)
    for h in BASE_TIMES:
        candidates.append(today.replace(hour=h) + timedelta(minutes=15))

    usable = [dt for dt in candidates if dt <= now]
    if usable:
        selected = max(usable)
        return selected.replace(minute=0)

    yesterday = today - timedelta(days=1)
    return yesterday.replace(hour=23)


def _parse_precipitation(value) -> float:
    if value is None:
        return 0.0

    text = str(value).strip()
    if not text or "강수없음" in text:
        return 0.0

    if "미만" in text:
        m = re.search(r"([\d.]+)", text)
        return float(m.group(1)) / 2.0 if m else 0.0

    nums = [float(x) for x in re.findall(r"[\d.]+", text)]

    if "~" in text and len(nums) >= 2:
        return (nums[0] + nums[1]) / 2.0

    if "이상" in text and nums:
        return nums[0]

    return nums[0] if nums else 0.0


def _condition_from(sky, pty) -> str:
    pty = str(pty or "0")
    if pty in {"1", "4"}:
        return "비"
    if pty in {"2", "3"}:
        return "눈/비"
    if str(sky) == "4":
        return "흐림"
    if str(sky) == "3":
        return "구름많음"
    return "맑음"


def _emoji_from(condition: str) -> str:
    if "비" in condition:
        return "🌧️"
    if "눈" in condition:
        return "🌨️"
    if "흐림" in condition:
        return "☁️"
    if "구름" in condition:
        return "🌤️"
    return "☀️"


def fetch_forecast(
    target_datetime: datetime | None = None,
    nx: int = DEFAULT_NX,
    ny: int = DEFAULT_NY,
) -> dict:
    if not KMA_API_KEY:
        raise RuntimeError("KMA_API_KEY가 없습니다.")

    now = datetime.now()
    target = target_datetime or now
    base_dt = _latest_base_datetime(now)

    params = {
        "serviceKey": KMA_API_KEY,
        "pageNo": 1,
        "numOfRows": 1000,
        "dataType": "JSON",
        "base_date": base_dt.strftime("%Y%m%d"),
        "base_time": base_dt.strftime("%H00"),
        "nx": nx,
        "ny": ny,
    }

    response = requests.get(URL, params=params, timeout=12)
    response.raise_for_status()
    data = response.json()

    header = data["response"]["header"]
    if header.get("resultCode") != "00":
        raise RuntimeError(
            f"KMA forecast error: "
            f"{header.get('resultCode')} {header.get('resultMsg')}"
        )

    items = data["response"]["body"]["items"]["item"]

    target_date = target.strftime("%Y%m%d")
    target_hour = target.strftime("%H00")

    grouped = {}
    for item in items:
        key = (
            str(item.get("fcstDate")),
            str(item.get("fcstTime")),
        )
        grouped.setdefault(key, {})[item.get("category")] = item.get("fcstValue")

    exact = grouped.get((target_date, target_hour))

    if exact is None:
        # 요청 시각과 정확히 일치하는 예보가 없으면 가장 가까운 예보시각 선택
        parsed = []
        for (d, t), values in grouped.items():
            try:
                dt = datetime.strptime(d + t, "%Y%m%d%H%M")
            except ValueError:
                continue
            parsed.append((abs((dt - target).total_seconds()), dt, values))

        if not parsed:
            raise RuntimeError("KMA 예보 데이터가 비어 있습니다.")

        _, selected_dt, exact = min(parsed, key=lambda x: x[0])
    else:
        selected_dt = target.replace(minute=0, second=0, microsecond=0)

    rainfall = _parse_precipitation(exact.get("PCP"))
    condition = _condition_from(exact.get("SKY"), exact.get("PTY"))

    def f(key):
        try:
            return float(exact.get(key))
        except (TypeError, ValueError):
            return None

    return {
        "forecast_datetime": selected_dt.strftime("%Y-%m-%d %H:%M"),
        "temperature": f("TMP"),
        "humidity": f("REH"),
        "wind_speed": f("WSD"),
        "rainfall": rainfall,
        "precipitation": rainfall,
        "condition": condition,
        "emoji": _emoji_from(condition),
        "precipitation_probability": f("POP"),
        "source": "KMA_VilageFcst",
        "grid": {"nx": nx, "ny": ny},
    }
