"""Weather from Open-Meteo: free, no account and no API key."""

import os
from typing import Optional

from ..registry import tool

GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST = "https://api.open-meteo.com/v1/forecast"

# WMO weather codes -> words
_CODES = {
    0: "clear sky", 1: "mostly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "freezing fog",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    56: "freezing drizzle", 57: "heavy freezing drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain",
    66: "freezing rain", 67: "heavy freezing rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains",
    80: "light showers", 81: "showers", 82: "violent showers",
    85: "snow showers", 86: "heavy snow showers",
    95: "thunderstorm", 96: "thunderstorm with hail", 99: "severe thunderstorm with hail",
}


def describe(code) -> str:
    return _CODES.get(int(code), "unknown conditions")


def _get(url: str, params: dict) -> dict:
    import requests
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _lookup(name: str, count: int = 1) -> list:
    data = _get(GEOCODE, {"name": name, "count": count, "language": "en"})
    return data.get("results") or []


def geocode(place: str) -> Optional[dict]:
    found = _lookup(place, 5)
    if found:
        # Several places can share a name: prefer the biggest (Delhi, India over a tiny village).
        return max(found, key=lambda c: c.get("population") or 0)
    # Probably a typo ("ahemdabad"): look at places starting with the same first letters
    # and take the closest spelling.
    import difflib
    want = place.strip().lower()
    best, best_score = None, 0.0
    for prefix in (want[:3], want[:2]):
        if len(prefix) < 2:
            continue
        try:
            candidates = _lookup(prefix, 30)
        except Exception:
            continue
        for c in candidates:
            score = difflib.SequenceMatcher(None, want, (c.get("name") or "").lower()).ratio()
            if score > best_score:
                best, best_score = c, score
    return best if best_score >= 0.75 else None


def _city_file():
    from .. import store
    return store.data_dir() / "city.txt"


def default_city() -> str:
    """JARVIS_CITY from .env, else the last city you asked about."""
    env = os.environ.get("JARVIS_CITY", "").strip()
    if env:
        return env
    try:
        return _city_file().read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _remember_city(city: str) -> None:
    try:
        _city_file().write_text(city, encoding="utf-8")
    except OSError:
        pass


def forecast_for(lat: float, lon: float) -> dict:
    return _get(FORECAST, {
        "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 3,
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
    })


def weather_report(city: str) -> dict:
    """Structured weather, used by both the tool and the web UI."""
    asked = (city or "").strip()
    city = (asked or default_city()).strip()
    if not city:
        raise ValueError("Which city? Say for example: weather in Mumbai. I'll remember it next time.")
    place = geocode(city)
    if place is None:
        raise ValueError(f"I couldn't find a place called '{city}'.")
    data = forecast_for(place["latitude"], place["longitude"])
    if asked:
        _remember_city(asked)
    cur, daily = data["current"], data["daily"]
    days = []
    for i, date in enumerate(daily["time"]):
        days.append({
            "date": date,
            "summary": describe(daily["weather_code"][i]),
            "high": daily["temperature_2m_max"][i],
            "low": daily["temperature_2m_min"][i],
            "rain_chance": daily["precipitation_probability_max"][i],
        })
    place_name = ", ".join(p for p in (place.get("name"), place.get("admin1"), place.get("country")) if p)
    return {
        "place": place_name,
        "temp": cur["temperature_2m"],
        "feels_like": cur["apparent_temperature"],
        "humidity": cur["relative_humidity_2m"],
        "wind": cur["wind_speed_10m"],
        "summary": describe(cur["weather_code"]),
        "days": days,
    }


@tool()
def get_weather(city: str = "") -> str:
    """Get the current weather and a 3-day forecast for a city.

    Args:
        city: City name, e.g. Mumbai. Leave empty to use the default city.
    """
    try:
        w = weather_report(city)
    except ValueError as exc:
        # Not an "Error:" on purpose: a missing city is a question for you, not a reason to ask the AI.
        return str(exc) if not city and not default_city() else f"Error: {exc}"
    lines = [f"{w['place']}: {w['summary']}, {w['temp']:.0f}°C (feels {w['feels_like']:.0f}°C), "
             f"humidity {w['humidity']}%, wind {w['wind']:.0f} km/h"]
    for d in w["days"]:
        rain = f", rain {d['rain_chance']}%" if d["rain_chance"] is not None else ""
        lines.append(f"  {d['date']}: {d['summary']}, {d['low']:.0f} to {d['high']:.0f}°C{rain}")
    return "\n".join(lines)
