"""
爬虫数据管道模块

负责处理爬虫抓取到的数据，执行以下操作：
1. SnapshotFilePipeline: 保存网页快照到本地文件
2. ElasticSearchPipeline: 将页面数据索引到Elasticsearch
3. MySQLPipeline: 将页面缓存和链接关系写入MySQL

管道执行顺序：
SnapshotFilePipeline -> ElasticSearchPipeline -> MySQLPipeline
"""

import os
import sys
import json
import hashlib
import re
import pymysql
from pathlib import Path
from datetime import datetime
from urllib.parse import urljoin
from elasticsearch import Elasticsearch
from scrapy.exceptions import DropItem

# 添加项目根目录到Python路径
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from config.page_tagger import tag_page_crawl_only, normalize_title


def enrich_snapshot_html(raw_html: str, page_url: str) -> str:
    crawl_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    base_href = urljoin(page_url, './')
    banner = (
        f'<div id="dbms-snapshot-banner" style="position:sticky;top:0;z-index:999999;'
        f'background:#702f8a;color:#fff;padding:10px 16px;font:14px/1.5 sans-serif;'
        f'box-shadow:0 2px 6px rgba(0,0,0,.2);">'
        f'<strong>网页快照</strong> · 抓取于 {crawl_time} · '
        f'<a href="{page_url}" style="color:#ffe082" target="_blank" rel="noopener">查看原始页面</a>'
        f'</div>'
    )
    html = raw_html or ''
    if re.search(r'<head[^>]*>', html, re.I):
        if not re.search(r'<meta[^>]+charset', html, re.I):
            html = re.sub(r'(<head[^>]*>)', r'\1\n<meta charset="utf-8">', html, count=1, flags=re.I)
        if not re.search(r'<base[^>]+href', html, re.I):
            html = re.sub(r'(<head[^>]*>)', rf'\1\n<base href="{base_href}">', html, count=1, flags=re.I)
    else:
        html = f'<!DOCTYPE html><html><head><meta charset="utf-8"><base href="{base_href}"></head><body>{html}</body></html>'
    if re.search(r'<body[^>]*>', html, re.I):
        html = re.sub(r'(<body[^>]*>)', rf'\1\n{banner}', html, count=1, flags=re.I)
    else:
        html = banner + html
    html = re.sub(r'<script(?![^>]*application/ld\+json)[^>]*>[\s\S]*?</script>', '', html, flags=re.I)
    return html


class SnapshotFilePipeline:
    """
    网页快照保存管道
    
    将抓取到的HTML页面保存为本地文件，用于搜索结果中的快照预览功能
    
    文件命名规则：URL的MD5哈希值 + .html
    """

    def __init__(self, storage_path):
        """
        初始化快照管道
        
        :param storage_path: 快照文件存储目录
        """
        self.storage_path = storage_path
        # 确保存储目录存在
        if not os.path.exists(self.storage_path):
            os.makedirs(self.storage_path)

    @classmethod
    def from_crawler(cls, crawler):
        """
        从Scrapy配置中获取参数并实例化管道
        
        :param crawler: Scrapy爬虫实例
        :return: SnapshotFilePipeline实例
        """
        storage_path = crawler.settings.get('SNAPSHOT_STORAGE_PATH', './snapshots')
        return cls(storage_path)

    def process_item(self, item, spider):
        """
        处理爬取到的页面数据，保存快照
        
        :param item: 爬取到的数据项（NkuSpiderItem）
        :param spider: 爬虫实例
        :return: 更新后的数据项（包含snapshot_path字段）
        :raises DropItem: 缺少raw_html时丢弃数据项
        """
        # 检查是否包含原始HTML内容
        if 'raw_html' not in item or not item['raw_html']:
            raise DropItem(f"Missing raw_html in {item['url']}")

        # 使用URL的MD5哈希作为文件名（避免URL中的特殊字符）
        url_hash = hashlib.md5(item['url'].encode('utf-8')).hexdigest()
        file_path = os.path.join(self.storage_path, f"{url_hash}.html")

        # 写入快照文件
        try:
            enriched_html = enrich_snapshot_html(item['raw_html'], item['url'])
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(enriched_html)
        except IOError as e:
            spider.logger.error(f"Snapshot write failed for {item['url']}: {e}")
            raise DropItem("Snapshot write failed")

        # 更新数据项，添加快照路径
        item['snapshot_path'] = file_path
        # 删除原始HTML以节省内存
        del item['raw_html']
        return item


class ElasticSearchPipeline:
    """
    Elasticsearch索引管道
    
    将爬取到的页面数据索引到Elasticsearch，支持全文搜索
    
    文档结构：
    - url: 页面URL（作为文档ID）
    - title: 页面标题
    - title_norm: 规范化标题（用于去重）
    - content: 页面正文
    - attachments: 附件链接列表
    - tags: 页面标签（简洁版）
    - tags_kw: 关键词标签
    - tags_detail: 标签详情（包含置信度）
    - crawl_time: 爬取时间
    - pagerank: PageRank值（初始为0.001）
    """

    def __init__(self, index_name, es_host):
        """
        初始化ES管道
        
        :param index_name: Elasticsearch索引名称
        :param es_host: Elasticsearch主机地址
        """
        self.es = Elasticsearch(es_host)
        self.index_name = index_name

    @classmethod
    def from_crawler(cls, crawler):
        """
        从Scrapy配置中获取参数并实例化管道
        
        :param crawler: Scrapy爬虫实例
        :return: ElasticSearchPipeline实例
        """
        return cls(
            index_name=crawler.settings.get("ES_INDEX_NAME"),
            es_host=crawler.settings.get("ES_HOST"),
        )

    def process_item(self, item, spider):
        """
        处理爬取到的页面数据，索引到ES
        
        :param item: 爬取到的数据项
        :param spider: 爬虫实例
        :return: 更新后的数据项（包含page_tags字段）
        """
        # 使用标签器为页面添加分类标签
        enriched = tag_page_crawl_only(
            item.get("url", ""),
            item.get("title", "") or "",
            item.get("content", "") or "",
            page_features=item.get("page_features"),
        )
        tags = enriched["tags_kw"]
        title = item.get("title") or ""
        page_features = enriched.get("page_features") or item.get("page_features") or {}

        es_doc = {
            "url": item.get("url"),
            "title": title,
            "title_norm": normalize_title(title),
            "content": item.get("content"),
            "attachments": item.get("attachments", []),
            "attachment_names": item.get("attachment_names", []),
            "tags": tags,
            "tags_kw": tags,
            "tags_detail": enriched.get("tags_detail", []),
            "page_features": page_features,
            "tag_status": enriched.get("tag_status", "pending"),
            "crawl_time": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "pagerank": item.get("pagerank", 0.001),
        }
        
        # 保存标签信息到数据项
        item["page_tags"] = enriched

        # 索引到ES
        try:
            # 使用URL作为文档ID，便于更新和查找
            self.es.index(index=self.index_name, id=item['url'], document=es_doc)
        except Exception as e:
            spider.logger.error(f"ES indexing failed for {item['url']} into {self.index_name}: {e}")

        return item


class MySQLPipeline:
    """
    MySQL数据管道
    
    将爬取数据写入MySQL数据库，包含两个表：
    1. WebPageCache: 网页快照缓存表（URL -> 标题 -> 快照路径 -> 标签）
    2. PageLinks: 页面链接拓扑表（有向边，用于构建站点拓扑图）
    """

    def __init__(self, db_name, mysql_host, mysql_user, mysql_password):
        """
        初始化MySQL管道
        
        :param db_name: 数据库名称
        :param mysql_host: MySQL主机地址
        :param mysql_user: MySQL用户名
        :param mysql_password: MySQL密码
        """
        self.db_name = db_name
        self.mysql_host = mysql_host
        self.mysql_user = mysql_user
        self.mysql_password = mysql_password
        self.connection = None
        self.cursor = None

    @classmethod
    def from_crawler(cls, crawler):
        """
        从Scrapy配置中获取参数并实例化管道
        
        :param crawler: Scrapy爬虫实例
        :return: MySQLPipeline实例
        """
        return cls(
            db_name=crawler.settings.get("MYSQL_DATABASE"),
            mysql_host=crawler.settings.get("MYSQL_HOST"),
            mysql_user=crawler.settings.get("MYSQL_USER"),
            mysql_password=crawler.settings.get("MYSQL_PASSWORD"),
        )

    def open_spider(self, spider):
        """
        爬虫启动时建立数据库连接
        
        :param spider: 爬虫实例
        """
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
        """
        爬虫关闭时释放数据库连接
        
        :param spider: 爬虫实例
        """
        if self.cursor:
            self.cursor.close()
        if self.connection:
            self.connection.close()

    def process_item(self, item, spider):
        """
        处理爬取到的页面数据，写入MySQL
        
        :param item: 爬取到的数据项
        :param spider: 爬虫实例
        :return: 原始数据项
        """
        # 如果没有快照路径，跳过处理
        if 'snapshot_path' not in item:
            return item

        # 1. 写入网页快照缓存表
        pt = item.get("page_tags") or {}
        # 将标签信息序列化为JSON
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

        # 2. 写入PageLinks有向边拓扑表（用于构建站点拓扑图）
        if 'out_links' in item and item['out_links']:
            source_url = item['url']
            # 构建批量插入参数列表
            link_data = [(source_url, target_url) for target_url in item['out_links']]
            
            sql_links = """
                INSERT IGNORE INTO PageLinks (source_url, target_url) 
                VALUES (%s, %s)
            """
            try:
                # 批量插入链接关系
                self.cursor.executemany(sql_links, link_data)
                self.connection.commit()
            except pymysql.Error as e:
                self.connection.rollback()
                spider.logger.error(f"MySQL links insertion failed for {source_url}: {e}")

        return item