import os
import hashlib
import pymysql
from elasticsearch import Elasticsearch
from scrapy.exceptions import DropItem

class SnapshotFilePipeline:
    """
    1. 文件处理管道：负责将原始 HTML 落盘，生成快照路径，并释放内存。
    """
    def __init__(self, storage_path):
        self.storage_path = storage_path
        if not os.path.exists(self.storage_path):
            os.makedirs(self.storage_path)

    @classmethod
    def from_crawler(cls, crawler):
        # 从 settings.py 获取快照存储路径
        storage_path = crawler.settings.get('SNAPSHOT_STORAGE_PATH', './snapshots')
        return cls(storage_path)

    def process_item(self, item, spider):
        if 'raw_html' not in item or not item['raw_html']:
            raise DropItem(f"Missing raw_html in {item['url']}")

        # 1. 使用 URL 的 MD5 哈希值作为文件名，避免特殊字符导致路径非法
        url_hash = hashlib.md5(item['url'].encode('utf-8')).hexdigest()
        file_name = f"{url_hash}.html"
        file_path = os.path.join(self.storage_path, file_name)

        # 2. 写入本地文件系统
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(item['raw_html'])
        except IOError as e:
            spider.logger.error(f"Failed to write snapshot for {item['url']}: {e}")
            raise DropItem("Snapshot write failed")

        # 3. 记录相对路径供后续数据库管道使用
        item['snapshot_path'] = file_path

        # 4. 显式删除 raw_html 字段，降低后续管道的内存占用
        del item['raw_html']

        return item


class ElasticSearchPipeline:
    """
    2. ElasticSearch 管道：负责将清洗后的文本数据写入 ES 构建倒排索引。
    """
    def __init__(self):
        # 实际部署时应将连接参数提取至 settings.py
        self.es = Elasticsearch(
            "http://localhost:9200", 
            # basic_auth=("elastic", "your_password") # 若有鉴权则取消注释
        )
        self.index_name = "nku_web_index"

    def process_item(self, item, spider):
        # 组装用于文本检索的数据包
        es_doc = {
            "url": item.get('url'),
            "title": item.get('title'),
            "content": item.get('content'),
            "attachments": item.get('attachments', [])
        }

        try:
            # 使用 URL 作为 ES 的文档 _id，实现自动去重与更新
            self.es.index(index=self.index_name, id=item['url'], document=es_doc)
        except Exception as e:
            spider.logger.error(f"ES indexing failed for {item['url']}: {e}")
            # 此处不抛出 DropItem，允许数据继续流向 MySQL
            
        return item


class MySQLPipeline:
    """
    3. MySQL 管道：负责将元数据（URL、快照路径、标题）写入关系型数据库。
    """
    def __init__(self):
        self.connection = None
        self.cursor = None

    def open_spider(self, spider):
        # 连接数据库，实际项目中参数应从 settings.py 读取
        self.connection = pymysql.connect(
            host='127.0.0.1',
            user='root',
            password='Qq142536789..', 
            database='nku_search_engine',
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
        self.cursor = self.connection.cursor()

    def close_spider(self, spider):
        if self.cursor:
            self.cursor.close()
        if self.connection:
            self.connection.close()

    def process_item(self, item, spider):
        # 忽略没有有效路径的数据
        if 'snapshot_path' not in item:
            return item

        # 插入 WebPageCache 表。使用 INSERT IGNORE 或 ON DUPLICATE KEY UPDATE 防止 URL 重复报错
        sql = """
            INSERT INTO WebPageCache (url, title, snapshot_path) 
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE 
            title = VALUES(title), snapshot_path = VALUES(snapshot_path)
        """
        try:
            self.cursor.execute(sql, (
                item.get('url'),
                item.get('title'),
                item.get('snapshot_path')
            ))
            self.connection.commit()
        except pymysql.Error as e:
            self.connection.rollback()
            spider.logger.error(f"MySQL insertion failed for {item['url']}: {e}")

        return item