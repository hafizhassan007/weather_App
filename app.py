"""
app.py
------
The website (built with Streamlit). Run it with:
    uv run streamlit run app.py

Three pages (choose from the sidebar):
  1. Ask the Agent  - chat with the deep agent
  2. Live Weather   - live conditions + storm risk table + chart
  3. PDF Reports    - download every analysis the agent saved
"""

import os

import pandas as pd
import streamlit as st
from langchain_core.messages import AIMessage, HumanMessage

from main import agent  # the agent lives in main.py
from outlook import get_30_day_outlook
from pdf_report import REPORTS_DIR, create_pdf
from weather_api import (
    calculate_storm_risk,
    fetch_forecast,
    get_alerts,
    get_upcoming_hours,
)

st.set_page_config(page_title="Storm Prediction Agent", page_icon="⛈️", layout="wide")


# ---------- helpers ----------------------------------------------------------

@st.cache_data(ttl=300)  # remember results for 5 minutes to save API calls
def load_forecast(city: str) -> dict:
    return fetch_forecast(city, days=3)


@st.cache_data(ttl=3600)  # remember for 1 hour
def load_outlook(city: str):
    return get_30_day_outlook(city)


def find_saved_report(messages) -> str | None:
    """Look through the agent's steps for the PDF path returned by save_report_pdf."""
    for msg in messages:
        if getattr(msg, "type", "") == "tool" and "REPORT_SAVED:" in str(msg.content):
            path = str(msg.content).split("REPORT_SAVED:")[1].strip().splitlines()[0]
            if os.path.exists(path):
                return path
    return None


def download_button(path: str, key: str):
    with open(path, "rb") as f:
        st.download_button(
            "⬇️ Download PDF report",
            data=f.read(),
            file_name=os.path.basename(path),
            mime="application/pdf",
            key=key,
        )


# ---------- sidebar ----------------------------------------------------------

st.sidebar.title("⛈️ Storm Agent")
page = st.sidebar.radio("Go to", ["💬 Ask the Agent", "🌍 Live Weather", "📅 30-day Outlook", "📄 PDF Reports"])

st.sidebar.divider()
st.sidebar.caption(
    "**How it works**\n\n"
    "1. Live data comes from WeatherAPI.com\n"
    "2. A Deep Agent decides which tools to use\n"
    "3. Storm risk is calculated from gusts, rain, thunder and pressure\n"
    "4. Reports are saved as PDFs you can download"
)


# ---------- page 1: chat -----------------------------------------------------

if page == "💬 Ask the Agent":
    st.title("💬 Ask the Weather Agent")
    st.write("Ask about live weather, storms or rain in any city. "
             "Say **“create a PDF report”** to get a news-ready file.")

    if "messages" not in st.session_state:
        st.session_state.messages = []  # each item: role, content, report

    # Example questions (click to ask)
    cols = st.columns(3)
    examples = [
        "Will there be a storm in Miami in the next 12 hours?",
        "Live weather in Tokyo",
        "Analyze rain in London for the next 6 hours and create a PDF report",
    ]
    for col, example in zip(cols, examples):
        if col.button(example, use_container_width=True):
            st.session_state.pending = example

    # Show the conversation so far
    for i, m in enumerate(st.session_state.messages):
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
            if m.get("report"):
                download_button(m["report"], key=f"dl_{i}")
            elif m["role"] == "assistant":
                # No PDF yet -> let the user make one from this answer
                if st.button("📄 Save this answer as PDF", key=f"mk_{i}"):
                    m["report"] = create_pdf("Weather Analysis", "Weather Analysis", m["content"])
                    st.rerun()

    prompt = st.chat_input("Ask about weather, storms or rain...") or st.session_state.pop("pending", None)

    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        history = [
            HumanMessage(content=m["content"]) if m["role"] == "user"
            else AIMessage(content=m["content"])
            for m in st.session_state.messages
        ]
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Checking live weather..."):
                try:
                    result = agent.invoke({"messages": history})
                    answer = result["messages"][-1].text
                    report = find_saved_report(result["messages"][len(history):])
                except Exception as e:
                    answer, report = f"Sorry, something went wrong: {e}", None
        st.session_state.messages.append(
            {"role": "assistant", "content": answer, "report": report}
        )
        st.rerun()


# ---------- page 2: live weather --------------------------------------------

elif page == "🌍 Live Weather":
    st.title("🌍 Live Weather & Storm Risk")
    city = st.text_input("Enter any city in the world", value="Lahore")
    hours = st.slider("Hours to look ahead", 3, 72, 12)

    if city:
        try:
            data = load_forecast(city)
            loc, cur = data["location"], data["current"]
            st.subheader(f"{loc['name']}, {loc['region']}, {loc['country']}")
            st.caption(f"Local time: {loc['localtime']}  |  Now: {cur['condition']['text']}")

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Temperature", f"{cur['temp_c']} °C", f"feels {cur['feelslike_c']} °C", delta_color="off")
            c2.metric("Humidity", f"{cur['humidity']} %")
            c3.metric("Wind", f"{cur['wind_kph']} km/h", f"gusts {cur['gust_kph']}", delta_color="off")
            c4.metric("Pressure", f"{cur['pressure_mb']} mb")

            for alert in get_alerts(data):
                st.warning(f"⚠️ {alert.get('headline', alert.get('event', 'Weather alert'))}")

            risks = calculate_storm_risk(get_upcoming_hours(data, hours))
            worst = max(risks, key=lambda r: r["score"])
            message = f"Highest storm risk in the next {hours} hours: **{worst['risk']}** at {worst['time']}"
            if worst["risk"] in ("High", "Severe"):
                st.error("⛈️ " + message)
            elif worst["risk"] == "Moderate":
                st.warning("🌦️ " + message)
            else:
                st.success("☀️ " + message)

            df = pd.DataFrame(risks)
            df["hour"] = df["time"].str[5:]  # e.g. 11-26 18:00
            st.line_chart(df.set_index("hour")[["rain_chance", "gust_kph"]])
            st.dataframe(
                df[["hour", "condition", "risk", "rain_chance", "precip_mm", "gust_kph", "reasons"]],
                use_container_width=True, hide_index=True,
            )
        except Exception as e:
            st.error(f"Could not load weather: {e}")


# ---------- page 3: 30-day outlook ------------------------------------------

elif page == "📅 30-day Outlook":
    st.title("📅 30-day Outlook")
    st.info("Days 1-16 are a real forecast. Days 17-30 show typical weather for those dates "
            "from the last 5 years, because nobody can forecast exact weather a month ahead.")
    city = st.text_input("Enter any city in the world", value="Lahore", key="outlook_city")

    if city:
        try:
            rows, place = load_outlook(city)
            df = pd.DataFrame(rows)
            df["day"] = df["date"].str[5:]  # e.g. 11-26

            st.subheader(place)
            c1, c2, c3 = st.columns(3)
            c1.metric("Hottest day", f"{df['tmax'].max()} °C")
            c2.metric("Coldest night", f"{df['tmin'].min()} °C")
            c3.metric("Likely rainy days", int((df["rain_chance"] >= 60).sum()))

            st.caption("Temperature (°C)")
            st.line_chart(df.set_index("day")[["tmax", "tmin"]])
            st.caption("Rain chance (%)")
            st.bar_chart(df.set_index("day")["rain_chance"])
            st.dataframe(
                df[["date", "type", "tmax", "tmin", "rain_chance", "precip_mm", "note"]],
                use_container_width=True, hide_index=True,
            )
            st.caption("Weather data by Open-Meteo.com")
        except Exception as e:
            st.error(f"Could not load the outlook: {e}")


# ---------- page 4: reports --------------------------------------------------

else:
    st.title("📄 PDF Reports")
    st.write("Every analysis saved by the agent appears here, newest first.")

    files = []
    if os.path.isdir(REPORTS_DIR):
        files = sorted((f for f in os.listdir(REPORTS_DIR) if f.endswith(".pdf")), reverse=True)

    if not files:
        st.info("No reports yet. Go to **Ask the Agent** and ask for a PDF report.")
    for name in files:
        col1, col2 = st.columns([4, 1])
        col1.write(f"📄 {name}")
        with open(os.path.join(REPORTS_DIR, name), "rb") as f:
            col2.download_button("Download", f.read(), file_name=name,
                                 mime="application/pdf", key=f"report_{name}")