import scrapy
from nku_spider.items import NkuSpiderItem

class NankaiSpider(scrapy.Spider):
    name = 'nankai_main'
    
    # 泛化允许的域名，支持南开各类子站以扩大抓取面
    allowed_domains = ['nankai.edu.cn']
    
    start_urls = [
        # 1. 核心门户与新闻资讯
        'https://www.nankai.edu.cn/',             # 南开大学主站
        'https://news.nankai.edu.cn/',            # 南开新闻网
        
        # 2. 信息与工程学科 (你的专业相关领域)
        'https://cc.nankai.edu.cn/',              # 计算机学院
        'https://cs.nankai.edu.cn/',              # 软件学院 / 网络空间安全学院
        'https://ai.nankai.edu.cn/',              # 人工智能学院
        'https://ceo.nankai.edu.cn/',             # 电子信息与光学工程学院
        
        # 3. 基础理科
        'https://math.nankai.edu.cn/',            # 数学科学学院
        'https://physics.nankai.edu.cn/',         # 物理科学学院
        'https://chem.nankai.edu.cn/',            # 化学学院
        'https://env.nankai.edu.cn/',             # 环境科学与工程学院
        
        # 4. 人文与社会科学
        'https://history.nankai.edu.cn/',         # 历史学院
        'https://wxy.nankai.edu.cn/',             # 文学院
        'https://hyxy.nankai.edu.cn/',            # 汉语言文化学院
        'https://zf.nankai.edu.cn/',              # 周恩来政府管理学院
        
        # 5. 经济与商科
        'https://bs.nankai.edu.cn/',              # 商学院
        'https://eco.nankai.edu.cn/',             # 经济学院
        'https://finance.nankai.edu.cn/',         # 金融学院
        
        # 6. 教务、科研与行政服务 (获取文档附件和规章制度的主力)
        'http://jwc.nankai.edu.cn/',              # 教务处
        'https://graduate.nankai.edu.cn/',        # 研究生院
        'https://kyb.nankai.edu.cn/',             # 科学技术研究部
        'https://sie.nankai.edu.cn/'              # 国际教育学院
    ]
    
    def parse(self, response):
        # 仅处理 HTML 响应，过滤直接下载文件的链接回调
        if not hasattr(response, 'text'):
            return

        item = NkuSpiderItem()
        item['url'] = response.url
        
        # 1. 提取原始 HTML，供网页快照功能使用
        item['raw_html'] = response.text

        # 2. 提取标题
        item['title'] = response.xpath('//title/text()').get(default='无标题').strip()
        
        # 3. 提取纯净正文（剔除导航、页脚、脚本、样式）
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
        
        item['content'] = ' '.join([text.strip() for text in raw_text_list if text.strip()])

        # 4. 提取文档查询要求的附件链接 [cite: 20, 21]
        doc_links = response.xpath('//a[contains(@href, ".doc") or contains(@href, ".pdf") or contains(@href, ".xls")]/@href').getall()
        item['attachments'] = [response.urljoin(link) for link in doc_links]

        # 产出当前页面的数据条目
        yield item

        # 5. 提取新链接并继续爬取
        links = response.xpath('//a/@href').getall()
        for link in links:
            if link.startswith('javascript:') or link.startswith('mailto:'):
                continue
            
            # 过滤多媒体与压缩包等非网页资源
            if link.lower().endswith(('.jpg', '.png', '.gif', '.mp4', '.zip', '.rar', '.doc', '.docx', '.pdf', '.xls', '.xlsx')):
                continue
                
            yield response.follow(link, callback=self.parse)