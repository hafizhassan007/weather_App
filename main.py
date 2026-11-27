import os

from dotenv import load_dotenv
from langchain.tools import tool
from deepagents import create_deep_agent
from langchain.messages import HumanMessage

from weather_api import fetch_forecast, get_upcoming_hours, calculate_storm_risk
from pdf_report import create_pdf
from outlook import outlook_as_text

load_dotenv(encoding="utf-8-sig")  # Load environment variables from .env file


@tool
def get_weather(city: str) -> str:
    '''Gives the live, current weather in a given city.'''
    cur = fetch_forecast(city, days=1)["current"]
    return (
        f"The current weather in {city} is {cur['condition']['text']}, "
        f"{cur['temp_c']}C, wind {cur['wind_kph']} km/h, humidity {cur['humidity']}%."
    )


@tool(description='Predicts storms and rain in the next hours (1 to 72) for a given city.')
def predict_storm(city: str, hours: int = 12) -> str:
    data = fetch_forecast(city, days=3)
    risks = calculate_storm_risk(get_upcoming_hours(data, max(1, min(hours, 72))))
    return "\n".join(
        f"{r['time']}: risk {r['risk']}, {r['condition']}, rain chance {r['rain_chance']}%, "
        f"gusts {r['gust_kph']} km/h, reasons: {r['reasons']}"
        for r in risks
    )


@tool(description='Gives the daily forecast for the next days (1 to 3) for a given city.')
def get_daily_forecast(city: str, days: int = 3) -> str:
    data = fetch_forecast(city, days=max(1, min(days, 3)))
    return "\n".join(
        f"{d['date']}: {d['day']['condition']['text']}, max {d['day']['maxtemp_c']}C / "
        f"min {d['day']['mintemp_c']}C, rain chance {d['day']['daily_chance_of_rain']}%, "
        f"max wind {d['day']['maxwind_kph']} km/h"
        for d in data["forecast"]["forecastday"]
    )


@tool(description='Gives a 30 day outlook for a city: a real forecast for days 1-16, then typical weather from past years for days 17-30.')
def get_monthly_outlook(city: str) -> str:
    return outlook_as_text(city)


@tool(description='Saves a weather analysis as a PDF file. Use when the user asks for a report.')
def save_pdf(city: str, title: str, report_text: str) -> str:
    return f"REPORT_SAVED: {create_pdf(city, title, report_text)}"


agent = create_deep_agent(
    model=os.getenv('MODEL_NAME', 'google_genai:gemini-3.1-flash-lite'),  # change MODEL_NAME in .env to switch model
    tools=[get_weather, predict_storm, get_daily_forecast, get_monthly_outlook, save_pdf],
    system_prompt="You are a weather and storm prediction assistant. Always use the tools for live data. "
                  "For forecasts longer than a day use get_daily_forecast (up to 3 days) and predict_storm with hours up to 72. For a month or 30 days use get_monthly_outlook and always tell the user that days 17-30 are typical weather, not a real forecast. Never invent numbers. Use '# Heading' and '- bullet' lines in PDF reports, no emojis.",
)

if __name__ == "__main__":
    question = input('Ask Something about the weather: ')

    response = agent.invoke({"messages": [HumanMessage(content=question)]})

    print(response["messages"][-1].text)