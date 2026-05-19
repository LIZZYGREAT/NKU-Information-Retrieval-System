BOT_NAME = 'nku_spider'

SPIDER_MODULES = ['nku_spider.spiders']
NEWSPIDER_MODULE = 'nku_spider.spiders'

# 遵循爬虫协议 [cite: 13]
ROBOTSTXT_OBEY = True

# 并发与延迟控制，平衡抓取速度与服务器压力
CONCURRENT_REQUESTS = 32
DOWNLOAD_DELAY = 0.5 
RANDOMIZE_DOWNLOAD_DELAY = True

# 开启重试机制，应对网络波动
RETRY_ENABLED = True
RETRY_TIMES = 3

# 禁用 Cookie 防止被服务端 Session 追踪封禁
COOKIES_ENABLED = False

# 默认请求头伪装
DEFAULT_REQUEST_HEADERS = {
  'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
  'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
  'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36 NkuSearchEngineBot/1.0'
}

# 管道执行顺序配置（数字越小优先级越高）
ITEM_PIPELINES = {
   'nku_spider.pipelines.SnapshotFilePipeline': 100,
   'nku_spider.pipelines.ElasticSearchPipeline': 200,
   'nku_spider.pipelines.MySQLPipeline': 300,
}

# 网页快照基础存储路径（按需修改）
SNAPSHOT_STORAGE_PATH = '../backend/snapshots'

# 编码设置
FEED_EXPORT_ENCODING = 'utf-8'