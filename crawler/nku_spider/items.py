# crawler/nku_spider/items.py
import scrapy

class NkuSpiderItem(scrapy.Item):
    # 基础信息
    url = scrapy.Field()
    title = scrapy.Field()
    content = scrapy.Field()
    attachments = scrapy.Field()
    attachment_names = scrapy.Field()
    
    raw_html = scrapy.Field()
    snapshot_path = scrapy.Field()
    page_tags = scrapy.Field()
    page_features = scrapy.Field()
    
    # 新增：用于 PageRank 拓扑图构建的当前页面出链集合
    out_links = scrapy.Field()