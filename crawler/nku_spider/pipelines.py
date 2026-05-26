import os
import sys
import json
import hashlib
import pymysql
from pathlib import Path
from elasticsearch import Elasticsearch
from scrapy.exceptions import DropItem
import datetime

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from config.page_tagger import tag_page_enriched, normalize_title

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
        enriched = tag_page_enriched(
            item.get("url", ""),
            item.get("title", "") or "",
            item.get("content", "") or "",
        )
        tags = enriched["tags_kw"]
        title = item.get("title") or ""
        es_doc = {
            "url": item.get("url"),
            "title": title,
            "title_norm": normalize_title(title),
            "content": item.get("content"),
            "attachments": item.get("attachments", []),
            "tags": tags,
            "tags_kw": tags,
            "tags_detail": enriched.get("tags_detail", []),
            "crawl_time": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "pagerank": item.get("pagerank", 0.001),
        }
        item["page_tags"] = enriched

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

        # 1. 写入网页快照缓存表逻辑
        pt = item.get("page_tags") or {}
        tags_json = json.dumps(
            pt.get("tags_detail", pt) if isinstance(pt, dict) else pt,
            ensure_ascii=False,
        )
        sql_cache = """
            INSERT INTO WebPageCache (url, title, snapshot_path, tags)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
            title = VALUES(title), snapshot_path = VALUES(snapshot_path), tags = VALUES(tags)
        """
        try:
            self.cursor.execute(sql_cache, (
                item.get("url"),
                item.get("title"),
                item.get("snapshot_path"),
                tags_json,
            ))
            self.connection.commit()
        except pymysql.Error as e:
            self.connection.rollback()
            spider.logger.error(f"MySQL cache insertion failed for {item['url']}: {e}")

        # 2.写入 PageLinks 有向边拓扑表逻辑
        if 'out_links' in item and item['out_links']:
            source_url = item['url']
            # 构建批量插入参数列表
            link_data = [(source_url, target_url) for target_url in item['out_links']]
            
            sql_links = """
                INSERT IGNORE INTO PageLinks (source_url, target_url) 
                VALUES (%s, %s)
            """
            try:
                self.cursor.executemany(sql_links, link_data)
                self.connection.commit()
            except pymysql.Error as e:
                self.connection.rollback()
                spider.logger.error(f"MySQL links insertion failed for {source_url}: {e}")

        return item