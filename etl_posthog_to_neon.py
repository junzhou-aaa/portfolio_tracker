import os
import requests
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, Column, String, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import declarative_base, sessionmaker

# 1. 环境变量读取
POSTHOG_API_KEY = os.environ["POSTHOG_API_KEY"]
POSTHOG_PROJECT_ID = os.environ["POSTHOG_PROJECT_ID"]
DATABASE_URL = os.environ["DATABASE_URL"]

# 2. Pydantic 数据模型定义 (清洗与强类型转换)
class PostHogEvent(BaseModel):
    event_id: str = Field(alias='id')
    distinct_id: str
    event_name: str = Field(alias='event')
    timestamp: datetime
    properties: dict = Field(default_factory=dict)

    @property
    def parsed_properties(self):
        # 提取关键属性，其余保留在 JSONB 中
        return {
            "current_url": self.properties.get("$current_url"),
            "referrer": self.properties.get("$referrer"),
            "browser": self.properties.get("$browser"),
            "os": self.properties.get("$os"),
            "country": self.properties.get("$geoip_country_code")
        }

# 3. SQLAlchemy ORM 模型定义
Base = declarative_base()
class AnalyticsEvent(Base):
    __tablename__ = 'analytics_events'
    event_id = Column(String(64), primary_key=True)
    distinct_id = Column(String(128), nullable=False)
    event_name = Column(String(64), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    current_url = Column(String)
    referrer = Column(String)
    browser = Column(String)
    os = Column(String)
    country = Column(String(16))
    properties = Column(JSONB, server_default='{}')

def fetch_events():
    url = f"https://eu.posthog.com/api/projects/{POSTHOG_PROJECT_ID}/events"
    after_time = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    headers = {"Authorization": f"Bearer {POSTHOG_API_KEY}"}
    
    response = requests.get(url, headers=headers, params={"after": after_time})
    response.raise_for_status()
    return response.json().get("results", [])

def load_to_neon(raw_events):
    if not raw_events:
        print("No events to process.")
        return

    # 初始化数据库引擎
    engine = create_engine(DATABASE_URL)
    
    insert_values = []
    for raw in raw_events:
        try:
            # Pydantic 校验与清洗
            event = PostHogEvent(**raw)
            props = event.parsed_properties
            
            insert_values.append({
                "event_id": event.event_id,
                "distinct_id": event.distinct_id,
                "event_name": event.event_name,
                "timestamp": event.timestamp,
                "current_url": props["current_url"],
                "referrer": props["referrer"],
                "browser": props["browser"],
                "os": props["os"],
                "country": props["country"],
                "properties": event.properties
            })
        except Exception as e:
            print(f"Skipping malformed event {raw.get('id')}: {e}")

    if not insert_values:
        return

    # SQLAlchemy 批量插入（含去重冲突处理）
    with engine.begin() as conn:
        stmt = pg_insert(AnalyticsEvent).values(insert_values)
        stmt = stmt.on_conflict_do_nothing(index_elements=['event_id'])
        conn.execute(stmt)
        
    print(f"Successfully loaded {len(insert_values)} events using Pydantic & SQLAlchemy.")

if __name__ == "__main__":
    events = fetch_events()
    load_to_neon(events)
