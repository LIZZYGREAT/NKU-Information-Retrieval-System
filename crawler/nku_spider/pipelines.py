import os
import hashlib
import pymysql
from elasticsearch import Elasticsearch
from scrapy.exceptions import DropItem

class SnapshotFilePipeline:
    def __init__(self, storage_path):
        self.storage_path = storage_path
        if not os.path.exists(self.storage_path):
            os.makedirs(self.storage_path)

    @classmethod
    def from_crawler(cls, crawler):
        storage_path = crawler.settings.get('SNAPSHOT_STORAGE_PATH', './snapshots')
        return cls(storage_path)

    def process_item(self, item, spider):
        if 'raw_html' not in item or not item['raw_html']:
            raise DropItem(f"Missing raw_html in {item['url']}")

        url_hash = hashlib.md5(item['url'].encode('utf-8')).hexdigest()
        file_path = os.path.join(self.storage_path, f"{url_hash}.html")

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(item['raw_html'])
        except IOError as e:
            spider.logger.error(f"Snapshot write failed for {item['url']}: {e}")
            raise DropItem("Snapshot write failed")

        item['snapshot_path'] = file_path
        del item['raw_html']
        return item


class ElasticSearchPipeline:
    def __init__(self, index_name, es_host):
        self.es = Elasticsearch(es_host)
        self.index_name = index_name

    @classmethod
    def from_crawler(cls, crawler):
        return cls(
            index_name=crawler.settings.get("ES_INDEX_NAME"),
            es_host=crawler.settings.get("ES_HOST"),
        )

    def process_item(self, item, spider):
        es_doc = {
            "url": item.get('url'),
            "title": item.get('title'),
            "content": item.get('content'),
            "attachments": item.get('attachments', [])
        }

        try:
            self.es.index(index=self.index_name, id=item['url'], document=es_doc)
        except Exception as e:
            spider.logger.error(f"ES indexing failed for {item['url']} into {self.index_name}: {e}")

        return item


class MySQLPipeline:
    def __init__(self, db_name, mysql_host, mysql_user, mysql_password):
        self.db_name = db_name
        self.mysql_host = mysql_host
        self.mysql_user = mysql_user
        self.mysql_password = mysql_password
        self.connection = None
        self.cursor = None

    @classmethod
    def from_crawler(cls, crawler):
        return cls(
            db_name=crawler.settings.get("MYSQL_DATABASE"),
            mysql_host=crawler.settings.get("MYSQL_HOST"),
            mysql_user=crawler.settings.get("MYSQL_USER"),
            mysql_password=crawler.settings.get("MYSQL_PASSWORD"),
        )

    def open_spider(self, spider):
        spider.logger.info(f"正在连接数据库: {self.db_name}")
        self.connection = pymysql.connect(
            host=self.mysql_host,
            user=self.mysql_user,
            password=self.mysql_password,
            database=self.db_name,
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
        if 'snapshot_path' not in item:
            return item

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
            spider.logger.error(f"MySQL insertion failed in {self.db_name} for {item['url']}: {e}")

        return item
