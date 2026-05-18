import scrapy

class NankaiSpider(scrapy.Spider):
    name = 'nankai_main'
    allowed_domains = ['nankai.edu.cn']
    start_urls = ['https://www.nankai.edu.cn/']

    def parse(self, response):
        # 1. 提取标题
        title = response.xpath('//title/text()').get(default='无标题').strip()
        
        # 2. 升级版正文提取：强力降噪
        # 通过 not(ancestor::xxx) 语法，硬性剔除属于导航、页脚、脚本、样式表中的文本节点
        raw_text_list = response.xpath('''
            //body//text()[
                not(ancestor::script) and
                not(ancestor::style) and
                not(ancestor::header) and
                not(ancestor::footer) and
                not(ancestor::nav) and
                not(ancestor::div[contains(@class, "header")]) and
                not(ancestor::div[contains(@class, "footer")]) and
                not(ancestor::div[contains(@class, "nav")]) and
                not(ancestor::div[contains(@class, "bottom")])
            ]
        ''').getall()
        
        clean_content = ' '.join([text.strip() for text in raw_text_list if text.strip()])

        # 3. 针对作业要求的“文档查询”：提取当前页面的 doc/pdf/xls 附件链接
        doc_links = response.xpath('//a[contains(@href, ".doc") or contains(@href, ".pdf") or contains(@href, ".xls")]/@href').getall()
        # 将相对路径转换为绝对路径
        doc_links = [response.urljoin(link) for link in doc_links]

        # 4. 组装数据并 yield
        yield {
            'url': response.url,
            'title': title,
            # 测试阶段为了直观，我们暂时限制 content 输出前 500 字，正式跑 10 万数据时记得把 [:500] 删掉
            'content': clean_content[:500], 
            'attachments': doc_links
        }

        # 5. 提取新链接并继续爬取
        links = response.xpath('//a/@href').getall()
        for link in links:
            if link.startswith('javascript:') or link.startswith('mailto:'):
                continue
            
            # 过滤掉图片、视频等不需要爬取的静态资源链接，防止爬虫卡死
            if link.lower().endswith(('.jpg', '.png', '.gif', '.mp4', '.zip', '.rar')):
                continue
                
            yield response.follow(link, callback=self.parse)