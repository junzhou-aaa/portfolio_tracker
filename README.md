# Wix Portfolio Analytics ETL Pipeline

This project is a lightweight, zero-maintenance (Serverless) modern data engineering pipeline. It is designed to automatically collect visitor behavior data from my personal portfolio website (built with Wix), perform daily data cleansing and ingestion, and provide a reliable, structured fact table for downstream AI analytics (Text-to-SQL).

## Architecture Overview

**Data Flow:**
Wix Portfolio (Web Tracking) ➡️ PostHog (Event Hub) ➡️ GitHub Actions (Orchestration) ➡️ Python ETL (Transform) ➡️ Neon (Serverless PostgreSQL)

**Core Tech Stack:**
- **Data Collection (Source):** PostHog (JS Snippet auto-capture + Custom events)
- **Data Extraction & Transformation (Transform):** Python 3.11, Pydantic (Strong type validation), SQLAlchemy (ORM)
- **Data Storage (Storage):** Neon.tech (Serverless PostgreSQL)
- **Task Orchestration:** GitHub Actions (Cron schedule trigger)

## Key Engineering Features

- **100% Serverless:** Utilizes GitHub Actions' ephemeral containers and Neon's scale-to-zero capabilities to achieve fully automated execution with zero infrastructure maintenance.
- **Strong Type Validation:** Implements Pydantic to intercept and validate semi-structured nested JSON data from PostHog, ensuring database schema integrity and data accuracy.
- **Idempotent Writes & Fault Tolerance:** Leverages PostgreSQL's `ON CONFLICT DO NOTHING` and globally unique `event_id`s to guarantee that no duplicate records are created, even in the event of network timeouts or overlapping workflow triggers.
- **Secure Credential Isolation:** All database connection strings and API keys are securely managed via GitHub Secrets, keeping the public codebase clean and secure.

## Database Schema

The core fact table `analytics_events` is structured as follows:

| Field Name | Type | Description |
|---|---|---|
| `event_id` | `VARCHAR(64)` | Primary key, PostHog's original UUID, used for idempotent deduplication |
| `distinct_id` | `VARCHAR(128)` | Unique visitor identifier |
| `event_name` | `VARCHAR(64)` | Name of the event (e.g., `$pageview`, `$autocapture`) |
| `timestamp` | `TIMESTAMPTZ` | UTC timestamp of the event occurrence |
| `current_url`, `referrer`, `browser`, `os`, `country` | `VARCHAR` / `TEXT` | Core business dimensions flattened from the event properties |
| `properties` | `JSONB` | Redundant raw storage for all unparsed nested property trees |

## Deployment & Local Run Guide

1. **Clone the repository and install dependencies:**
   ```bash
   git clone https://github.com/YourUsername/wix-portfolio-tracker.git
   cd wix-portfolio-tracker
   pip install -r requirements.txt
   ```

2. **Configure Environment Variables:**
   Before running locally or pushing to GitHub, you need to prepare the following three Secrets:
   - `POSTHOG_API_KEY`: PostHog Personal API Key (Requires Read access for Events).
   - `POSTHOG_PROJECT_ID`: Your numeric PostHog Project ID.
   - `DATABASE_URL`: The full connection string for your Neon PostgreSQL database.

3. **Run Locally:**
   ```bash
   export POSTHOG_API_KEY="phx_..."
   export POSTHOG_PROJECT_ID="12345"
   export DATABASE_URL="postgresql://..."
   python etl_posthog_to_neon.py
   ```

## Future Roadmap

- **Orchestration Upgrade:** Migrate from GitHub Actions to Apache Airflow to implement finer-grained task dependency management and historical execution monitoring.
- **Intelligent Analytics Layer:** Integrate DeepSeek and the Vanna.ai (RAG framework) on top of the Neon database to build a Text-to-SQL engine, enabling interactive insights into website traffic using natural language.
