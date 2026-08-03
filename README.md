# 🌧️ Mazha-Radar (മഴ-Radar)

[![Ernakulam Weather Tracker](https://github.com/jooohith/Mazha-Radar/actions/workflows/check_weather.yml/badge.svg)](https://github.com/jooohith/Mazha-Radar/actions/workflows/check_weather.yml)
![Python 3.10](https://img.shields.io/badge/Python-3.10-blue.svg)
![Discord Webhook](https://img.shields.io/badge/Discord-Webhook-5865F2.svg?logo=discord&logoColor=white)
[![IMD Kerala](https://img.shields.io/badge/Data_Source-IMD_Kerala-orange.svg)](https://mausam.imd.gov.in/thiruvananthapuram/)

> **Automated Ernakulam Rainfall & District Holiday Tracker**  
> *Mazha-Radar* monitors official India Meteorological Department (IMD) daily bulletin updates and real-time news outlets for Ernakulam district holiday declarations, dispatching styled alerts directly to Discord.

---

## ✨ Features

* **⚡ Real-Time IMD PDF Parsing**: Automatically fetches and extracts 5-day district rainfall intensity and probability directly from IMD Thiruvananthapuram's bulletin.
* **🚨 District Holiday Tracker**: Uses Google News RSS to catch fresh Ernakulam District Collector holiday declarations from major outlets (Manorama, Mathrubhumi, Asianet, TOI, etc.).
* **📅 Date-Aware News Filtering**: Strict timestamp and calendar filters ignore stale news from past days, ensuring alerts trigger *only* for today or tomorrow.
* **🎙️ AI Presenter Persona**: Summarizes weekly forecasts into engaging, humanized weather updates and commuting advisories.
* **📊 Visual Severity Indicators**: Converts technical IMD codes (`ISOL. H`, `L TO M`, etc.) into intuitive severity progress bars and dynamic embed card colors.
* **🤖 Fully Automated**: Driven by GitHub Actions on a cron schedule—no servers or paid hosting required.

---

## 🛠️ Architecture & Workflow

```text
  ┌─────────────────────────────────┐
  │   GitHub Actions (Every 3h)     │
  └────────────────┬────────────────┘
                   │
         ┌─────────┴─────────┐
         ▼                   ▼
┌──────────────────┐   ┌──────────────────────┐
│  IMD Kerala PDF  │   │   Google News RSS    │
│  Daily Forecast  │   │ (Ernakulam Holidays) │
└────────┬─────────┘   └──────────┬───────────┘
         │                        │
         └─────────┬──────────────┘
                   ▼
       ┌───────────────────────┐
       │     main.py Engine    │
       │ (Parses & Evaluates)  │
       └───────────┬───────────┘
                   │
                   ▼
       ┌───────────────────────┐
       │   Discord Webhook     │
       │  (Rich Embed Alert)   │
       └───────────────────────┘
