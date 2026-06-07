"""
南开大学站内爬虫核心模块

负责抓取南开大学校内各站点的网页内容，提取标题、正文、附件链接等信息，并构建站点拓扑图。

爬虫策略：
1. 广度优先遍历从起始URL开始
2. 仅爬取nankai.edu.cn域名下的页面
3. 过滤多媒体文件和下载链接
4. 提取正文时剔除导航、页脚等噪声内容
"""

import scrapy
from nku_spider.items import NkuSpiderItem


class NankaiSpider(scrapy.Spider):
    """
    南开大学站内爬虫类
    
    爬取范围：
    - 主站门户与新闻资讯
    - 信息与工程学科（计算机、软件、人工智能、电子信息）
    - 基础理科（数学、物理、化学、环境）
    - 人文与社会科学
    - 经济与商科
    - 教务、科研与行政服务
    """
    
    name = 'nankai_main'  # 爬虫名称，用于启动爬虫
    
    # 允许爬取的域名范围，限制在南开校内域名
    allowed_domains = ['nankai.edu.cn']
    
    # 起始爬取URL列表，覆盖南开主要站点
    start_urls = [
        # 1. 核心门户与新闻资讯
        'https://www.nankai.edu.cn/',             # 南开大学主站
        'https://news.nankai.edu.cn/',            # 南开新闻网
        
        # 2. 信息与工程学科
        'https://cc.nankai.edu.cn/',              # 计算机学院
        'https://cs.nankai.edu.cn/',              # 软件学院/网络空间安全学院
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
        
        # 6. 教务、科研与行政服务（获取文档附件和规章制度）
        'http://jwc.nankai.edu.cn/',              # 教务处
        'https://graduate.nankai.edu.cn/',        # 研究生院
        'https://kyb.nankai.edu.cn/',             # 科学技术研究部
        'https://sie.nankai.edu.cn/'              # 国际教育学院
    ]
    
    def parse(self, response):
        """
        页面解析核心方法
        
        :param response: Scrapy响应对象，包含页面内容
        :return: 生成NkuSpiderItem数据项和后续爬取请求
        
        解析流程：
        1. 检查响应是否为HTML
        2. 提取页面URL和原始HTML（用于快照）
        3. 提取页面标题
        4. 提取纯净正文（剔除导航、页脚等噪声）
        5. 提取附件链接（doc/pdf/xls等）
        6. 提取有效出链并构建拓扑关系
        7. 生成后续爬取请求
        """
        # 仅处理HTML响应，过滤直接下载文件的链接回调
        if not hasattr(response, 'text'):
            return

        # 初始化数据项
        item = NkuSpiderItem()
        item['url'] = response.url
        
        # 1. 提取原始HTML，供网页快照功能使用
        item['raw_html'] = response.text

        # 2. 提取标题（从<title>标签）
        item['title'] = response.xpath('//title/text()').get(default='无标题').strip()
        
        # 3. 提取纯净正文（剔除导航、页脚、脚本、样式等噪声）
        # 使用XPath过滤掉非正文区域
        raw_text_list = response.xpath('''
            //body//text()[
                not(ancestor::script) and           # 排除脚本内容
                not(ancestor::style) and            # 排除样式内容
                not(ancestor::header) and           # 排除页眉
                not(ancestor::footer) and           # 排除页脚
                not(ancestor::nav) and              # 排除导航
                not(ancestor::div[contains(@class, "header")]) and
                not(ancestor::div[contains(@class, "footer")]) and
                not(ancestor::div[contains(@class, "nav")]) and
                not(ancestor::div[contains(@class, "bottom")])
            ]
        ''').getall()
        
        # 拼接纯净正文，过滤空白字符
        item['content'] = ' '.join([text.strip() for text in raw_text_list if text.strip()])

        # 4. 提取文档附件链接（满足文档搜索需求）
        doc_links = response.xpath('//a[contains(@href, ".doc") or contains(@href, ".pdf") or contains(@href, ".xls")]/@href').getall()
        # 转换为绝对URL
        item['attachments'] = [response.urljoin(link) for link in doc_links]

        # 5. 提取新链接并继续爬取，同时收集有效出链构建拓扑
        valid_out_links = set()  # 使用集合去重
        links = response.xpath('//a/@href').getall()
        
        for link in links:
            # 跳过JavaScript和邮件链接
            if link.startswith('javascript:') or link.startswith('mailto:'):
                continue
            
            # 过滤多媒体与压缩包等非网页资源
            if link.lower().endswith(('.jpg', '.png', '.gif', '.mp4', '.zip', '.rar', '.doc', '.docx', '.pdf', '.xls', '.xlsx')):
                continue
            
            # 拼接绝对路径并加入当前页面的出链集合
            full_link = response.urljoin(link)
            valid_out_links.add(full_link)
                
            # 生成后续爬取请求
            yield response.follow(link, callback=self.parse)
            
        # 将出链列表存入数据项（用于构建站点拓扑图）
        item['out_links'] = list(valid_out_links)

        # 产出当前页面的数据条目（传递给Pipeline处理）
        yield item