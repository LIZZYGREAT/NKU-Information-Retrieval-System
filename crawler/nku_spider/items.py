import scrapy

class NkuSpiderItem(scrapy.Item):
    # 基础信息
    url = scrapy.Field()
    title = scrapy.Field()
    content = scrapy.Field()
    attachments = scrapy.Field()
    
    # 快照处理专用
    raw_html = scrapy.Field()       # 原始HTML文本，供落盘使用
    snapshot_path = scrapy.Field()  # 落盘后的相对路径，交由下游管道存入数据库