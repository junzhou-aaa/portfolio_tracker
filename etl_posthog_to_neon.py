import os
import requests
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime, timedelta, timezone

POSTHOG_API_KEY = os.environ["POSTHOG_API_KEY"]
POSTHOG_PROJECT_ID = os.environ["POSTHOG_PROJECT_ID"]
DATABASE_URL = os.environ["DATABASE_URL"]

def fetch_posthog_events():
    base_url = "https://eu.posthog.com"
    after_time = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    
    url = f"{base_url}/api/projects/{POSTHOG_PROJECT_ID}/events?after={after_time}"
    headers = {"Authorization": f"Bearer {POSTHOG_API_KEY}"}
    
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json().get("results", [])

def transform_and_load(events):
    if not events:
        print("No new events to load.")
        return

    records = []
    for ev in events:
        props = ev.get("properties", {})
        records.append((
            ev.get("id"),
            ev.get("distinct_id"),
            ev.get("event"),
            ev.get("timestamp"),
            props.get("$current_url"),
            props.get("$referrer"),
            props.get("$browser"),
            props.get("$os"),
            props.get("$geoip_country_code"),
            psycopg2.extras.Json(props)
        ))

    query = """
        INSERT INTO analytics_events (
            event_id, distinct_id, event_name, timestamp,
            current_url, referrer, browser, os, country, properties
        ) VALUES %s
        ON CONFLICT (event_id) DO NOTHING;
    """

    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            execute_values(cur, query, records)
            conn.commit()
    print(f"Successfully processed {len(records)} events into Neon.")

if __name__ == "__main__":
    raw_events = fetch_posthog_events()
    transform_and_load(raw_events)
