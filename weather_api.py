"""
weather_api.py
--------------
Talks to WeatherAPI.com and calculates a simple storm-risk score.
No AI in this file - just plain Python, so it is easy to read and test.
"""

import os
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv(encoding="utf-8-sig")  # reads WEATHER_API_KEY and GOOGLE_API_KEY from the .env file

BASE_URL = "https://api.weatherapi.com/v1/forecast.json"

# WeatherAPI condition codes that mean "thunder" (thunderstorm or thundery rain/snow)
THUNDER_CODES = {1087, 1273, 1276, 1279, 1282}


def fetch_forecast(city: str, days: int = 3) -> dict:
    """Download live weather + hourly forecast for any city in the world."""
    api_key = os.getenv("WEATHER_API_KEY")
    if not api_key:
        raise ValueError("WEATHER_API_KEY is missing. Add it to your .env file.")

    params = {"key": api_key, "q": city, "days": days, "alerts": "yes", "aqi": "no"}
    response = requests.get(BASE_URL, params=params, timeout=15)

    if response.status_code == 400:
        raise ValueError(f"Could not find a city called '{city}'. Check the spelling.")
    response.raise_for_status()
    return response.json()


def get_upcoming_hours(data: dict, hours: int = 12) -> list:
    """Return the next N hourly forecasts, starting from the current local hour."""
    local_now = datetime.strptime(data["location"]["localtime"], "%Y-%m-%d %H:%M")
    local_now = local_now.replace(minute=0)

    upcoming = []
    for day in data["forecast"]["forecastday"]:
        for hour in day["hour"]:
            hour_time = datetime.strptime(hour["time"], "%Y-%m-%d %H:%M")
            if hour_time >= local_now:
                upcoming.append(hour)
    return upcoming[:hours]


def calculate_storm_risk(hours: list) -> list:
    """
    Give every hour a storm-risk score.
    The more danger signs (thunder, strong gusts, heavy rain, falling
    pressure), the higher the score.
    Score  0-1 -> Low | 2-3 -> Moderate | 4-6 -> High | 7+ -> Severe
    """
    results = []
    previous_pressure = None

    for h in hours:
        score = 0
        reasons = []

        # 1) Thunder in the forecast is the strongest storm signal
        if h["condition"]["code"] in THUNDER_CODES:
            score += 4
            reasons.append("thunder expected")

        # 2) Strong wind gusts
        gust = h["gust_kph"]
        if gust >= 90:
            score += 4
            reasons.append(f"damaging gusts {gust} km/h")
        elif gust >= 60:
            score += 3
            reasons.append(f"very strong gusts {gust} km/h")
        elif gust >= 40:
            score += 2
            reasons.append(f"strong gusts {gust} km/h")
        elif gust >= 30:
            score += 1

        # 3) Heavy rain amount
        rain_mm = h["precip_mm"]
        if rain_mm >= 10:
            score += 3
            reasons.append(f"heavy rain {rain_mm} mm/h")
        elif rain_mm >= 4:
            score += 2
            reasons.append(f"moderate rain {rain_mm} mm/h")
        elif rain_mm >= 1:
            score += 1

        # 4) Chance of rain
        if h["chance_of_rain"] >= 80:
            score += 2
        elif h["chance_of_rain"] >= 60:
            score += 1

        # 5) Pressure dropping fast (2+ mb in one hour) often comes before a storm
        pressure = h["pressure_mb"]
        if previous_pressure is not None and previous_pressure - pressure >= 2:
            score += 1
            reasons.append("pressure falling fast")
        previous_pressure = pressure

        if score >= 7:
            level = "Severe"
        elif score >= 4:
            level = "High"
        elif score >= 2:
            level = "Moderate"
        else:
            level = "Low"

        results.append(
            {
                "time": h["time"],
                "condition": h["condition"]["text"],
                "temp_c": h["temp_c"],
                "rain_chance": h["chance_of_rain"],
                "precip_mm": rain_mm,
                "gust_kph": gust,
                "pressure_mb": pressure,
                "score": score,
                "risk": level,
                "reasons": ", ".join(reasons) if reasons else "none",
            }
        )
    return results


def get_alerts(data: dict) -> list:
    """Official weather alerts for the city (empty list if there are none)."""
    return data.get("alerts", {}).get("alert", [])