"""
outlook.py
----------
30-day weather outlook using the FREE Open-Meteo API (no key needed).

IMPORTANT: no weather service can forecast exact weather 30 days ahead.
So we combine two honest things:
  * Days 1-16  -> a real forecast
  * Days 17-30 -> "typical weather" for those dates, averaged from the last 5 years
"""

from datetime import date, timedelta

import requests

from weather_api import fetch_forecast

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
THUNDER_CODES = {95, 96, 99}  # WMO weather codes for thunderstorms


def get_coordinates(city: str):
    """Use WeatherAPI to find the latitude/longitude of any city."""
    loc = fetch_forecast(city, days=1)["location"]
    return loc["lat"], loc["lon"], f"{loc['name']}, {loc['country']}"


def shift_years_back(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year - years)
    except ValueError:  # 29 February
        return d.replace(year=d.year - years, day=28)


def get_real_forecast(lat, lon, days=16) -> list:
    params = {
        "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": days,
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,"
                 "precipitation_sum,precipitation_probability_max,wind_gusts_10m_max",
    }
    r = requests.get(FORECAST_URL, params=params, timeout=20)
    r.raise_for_status()
    d = r.json()["daily"]

    rows = []
    for i, day in enumerate(d["time"]):
        thunder = d["weather_code"][i] in THUNDER_CODES
        rows.append({
            "date": day,
            "type": "Forecast",
            "tmax": d["temperature_2m_max"][i],
            "tmin": d["temperature_2m_min"][i],
            "rain_chance": d["precipitation_probability_max"][i] or 0,
            "precip_mm": d["precipitation_sum"][i] or 0,
            "note": "thunderstorm possible" if thunder else f"gusts up to {d['wind_gusts_10m_max'][i]} km/h",
        })
    return rows


def get_typical_weather(lat, lon, start: date, end: date, years=5) -> list:
    """Average the same calendar dates from the last N years."""
    by_day = {}  # (month, day) -> list of (tmax, tmin, rain_mm)
    for y in range(1, years + 1):
        params = {
            "latitude": lat, "longitude": lon, "timezone": "auto",
            "start_date": shift_years_back(start, y).isoformat(),
            "end_date": shift_years_back(end, y).isoformat(),
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
        }
        r = requests.get(ARCHIVE_URL, params=params, timeout=20)
        r.raise_for_status()
        d = r.json()["daily"]
        for i, day in enumerate(d["time"]):
            if d["temperature_2m_max"][i] is None:
                continue
            key = (int(day[5:7]), int(day[8:10]))
            by_day.setdefault(key, []).append(
                (d["temperature_2m_max"][i], d["temperature_2m_min"][i], d["precipitation_sum"][i] or 0)
            )

    rows, current = [], start
    while current <= end:
        values = by_day.get((current.month, current.day))
        if values:
            n = len(values)
            rows.append({
                "date": current.isoformat(),
                "type": "Typical",
                "tmax": round(sum(v[0] for v in values) / n, 1),
                "tmin": round(sum(v[1] for v in values) / n, 1),
                "rain_chance": round(100 * sum(1 for v in values if v[2] >= 1.0) / n),
                "precip_mm": round(sum(v[2] for v in values) / n, 1),
                "note": f"average of last {n} years",
            })
        current += timedelta(days=1)
    return rows


def get_30_day_outlook(city: str):
    """Returns (rows, place_name). Rows = 16 forecast days + 14 typical days."""
    lat, lon, place = get_coordinates(city)
    rows = get_real_forecast(lat, lon, 16)
    try:
        today = date.today()
        rows += get_typical_weather(lat, lon, today + timedelta(days=16), today + timedelta(days=29))
    except Exception:
        pass  # if the history service fails we still return the 16-day forecast
    return rows, place


def outlook_as_text(city: str) -> str:
    """Plain-text version for the AI agent."""
    rows, place = get_30_day_outlook(city)
    lines = [
        f"30-day outlook for {place}.",
        "Rows marked Forecast are a real forecast (days 1-16). "
        "Rows marked Typical are averages from the last 5 years, NOT a forecast.",
    ]
    for r in rows:
        lines.append(
            f"{r['date']} [{r['type']}]: max {r['tmax']}C / min {r['tmin']}C, "
            f"rain chance {r['rain_chance']}%, rain {r['precip_mm']} mm, {r['note']}"
        )
    return "\n".join(lines)