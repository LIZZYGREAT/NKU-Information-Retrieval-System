import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_TYPE = os.getenv("ENV_TYPE", "dev")
load_dotenv(PROJECT_ROOT / f".env.{ENV_TYPE}")

MYSQL_HOST = os.environ["MYSQL_HOST"]
MYSQL_USER = os.environ["MYSQL_USER"]
MYSQL_PASSWORD = os.environ["MYSQL_PASSWORD"]
MYSQL_DATABASE = os.environ["MYSQL_DATABASE"]
ES_HOST = os.environ.get("ES_HOST", "http://localhost:9200")
ES_INDEX_NAME = os.environ["ES_INDEX_NAME"]

BOT_NAME = 'nku_spider'

SPIDER_MODULES = ['nku_spider.spiders']
NEWSPIDER_MODULE = 'nku_spider.spiders'

ROBOTSTXT_OBEY = True

CONCURRENT_REQUESTS = 32
DOWNLOAD_DELAY = 0.5
RANDOMIZE_DOWNLOAD_DELAY = True

RETRY_ENABLED = True
RETRY_TIMES = 3

COOKIES_ENABLED = False

DEFAULT_REQUEST_HEADERS = {
  'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
  'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
  'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36 NkuSearchEngineBot/1.0'
}

ITEM_PIPELINES = {
   'nku_spider.pipelines.SnapshotFilePipeline': 100,
   'nku_spider.pipelines.ElasticSearchPipeline': 200,
   'nku_spider.pipelines.MySQLPipeline': 300,
}

SNAPSHOT_STORAGE_PATH = '../backend/snapshots'

FEED_EXPORT_ENCODING = 'utf-8'
