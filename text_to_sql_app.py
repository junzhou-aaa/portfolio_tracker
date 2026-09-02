import os
from dotenv import load_dotenv
from vanna.openai import OpenAI_Chat
from vanna.chromadb import ChromaDB_VectorStore

# 自动加载 .env.local 里的环境变量
load_dotenv(".env.local")

from openai import OpenAI

# 1. 初始化自定义的 Vanna 类 (结合本地向量库 ChromaDB 和 OpenAI 格式的 API)
class MyVanna(ChromaDB_VectorStore, OpenAI_Chat):
    def __init__(self, client=None, config=None):
        ChromaDB_VectorStore.__init__(self, config=config)
        OpenAI_Chat.__init__(self, client=client, config=config)

# 2. 读取必要的环境变量
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
DATABASE_URL = os.environ.get("DATABASE_URL")

if not GROQ_API_KEY or not DATABASE_URL:
    raise ValueError("请确保已经设置了 GROQ_API_KEY 和 DATABASE_URL 环境变量！")

# 3. 实例化 Groq 客户端并传给 Vanna
groq_client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

vn = MyVanna(client=groq_client, config={
    'model': 'openai/gpt-oss-120b', # 切换到 Groq 当前支持的最新模型
})

# 4. 连接到 Neon PostgreSQL 数据库
print("正在连接数据库...")
import urllib.parse
parsed_url = urllib.parse.urlparse(DATABASE_URL)
vn.connect_to_postgres(
    host=parsed_url.hostname,
    dbname=parsed_url.path[1:],
    user=parsed_url.username,
    password=parsed_url.password,
    port=parsed_url.port or 5432
)

# ==========================================
# 5. 核心：给大模型喂知识 (Training)
# ==========================================

print("正在训练表结构 (DDL)...")
vn.train(ddl="""
    CREATE TABLE analytics_events (
        event_id VARCHAR(64) PRIMARY KEY,
        distinct_id VARCHAR(128) NOT NULL,
        event_name VARCHAR(64) NOT NULL,
        timestamp TIMESTAMPTZ NOT NULL,
        current_url VARCHAR,
        referrer VARCHAR,
        browser VARCHAR,
        os VARCHAR,
        country VARCHAR(16),
        properties JSONB
    );
""")

print("正在训练业务术语 (Documentation)...")
vn.train(documentation="""
业务术语解释 (Business Logic for PostHog Events):
1. 当用户询问"浏览"、"访问"、"PV"、"页面被看"时，必须增加过滤条件: WHERE event_name = '$pageview'。
2. 当用户询问"点击"、"按钮"、"链接"时，必须增加过滤条件: WHERE event_name = '$autocapture'。同时具体的点击内容存放在 properties->>'$el_text' 中。
3. 当用户询问"离开"、"退出"网页时，对应的事件是: WHERE event_name = '$pageleave'。
4. "独立访客"、"UV"、"多少人" 对应的是去重计算: COUNT(DISTINCT distinct_id)。
5. 当筛选某一天的数据时，请注意转换 timestamp 的时区或直接比较日期。
""")

print("正在训练业务逻辑 SQL (目标 A/C/D)...")

# 目标 A: PV (页面浏览量) 和 UV (独立访客)
vn.train(
    question="每天有多少独立访客(UV)和页面浏览量(PV)？",
    sql="""
    SELECT 
        DATE(timestamp) as visit_date,
        COUNT(DISTINCT distinct_id) as uv,
        COUNT(*) as pv
    FROM analytics_events 
    WHERE event_name = '$pageview'
    GROUP BY 1
    ORDER BY 1 DESC;
    """
)

# 目标 D: 页面上的具体点击行为
vn.train(
    question="访客在网页上点击了哪些具体的链接或按钮？",
    sql="""
    SELECT 
        properties->>'$el_text' as button_text, 
        current_url,
        COUNT(*) as click_count
    FROM analytics_events 
    WHERE event_name = '$autocapture' 
      AND properties->>'$el_text' IS NOT NULL
      AND properties->>'$el_text' != ''
    GROUP BY 1, 2
    ORDER BY 3 DESC;
    """
)

# 目标 C: 页面停留时间 (利用上一个事件和下一个事件的时间差)
vn.train(
    question="访客在各个页面的平均停留时间是多少秒？",
    sql="""
    WITH user_events AS (
        SELECT 
            distinct_id, 
            current_url, 
            timestamp as current_time,
            LEAD(timestamp) OVER(PARTITION BY distinct_id ORDER BY timestamp) as next_time
        FROM analytics_events
    )
    SELECT 
        current_url, 
        ROUND(AVG(EXTRACT(EPOCH FROM (next_time - current_time)))::numeric, 2) as avg_dwell_time_seconds
    FROM user_events
    WHERE next_time IS NOT NULL 
      AND EXTRACT(EPOCH FROM (next_time - current_time)) < 3600 -- 过滤掉超过1小时的异常会话
    GROUP BY 1
    ORDER BY 2 DESC;
    """
)

print("✅ 训练完成！")

# 6. 启动自带的 Web 界面
print("正在启动 Web UI... 请在浏览器中打开提供的链接")
from vanna.flask import VannaFlaskApp
app = VannaFlaskApp(vn)
app.run(port=8501)
