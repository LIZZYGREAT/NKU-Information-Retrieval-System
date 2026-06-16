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
from config.page_features import extract_headings, build_page_features

DOC_EXTENSIONS = (
    '.doc', '.docx', '.pdf', '.xls', '.xlsx', '.ppt', '.pptx',
    '.txt', '.csv', '.wps', '.rtf', '.zip',
)


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
        'https://zfxy.nankai.edu.cn/',
        'https://bs.nankai.edu.cn/',
        'https://economics.nankai.edu.cn/',
        'https://finance.nankai.edu.cn/',
        'http://jwc.nankai.edu.cn/',
        'https://graduate.nankai.edu.cn/',
        'https://std.nankai.edu.cn/',
        'https://sie.nankai.edu.cn/',              # 国际教育学院

        'https://zsb.nankai.edu.cn/', 
        'https://yzb.nankai.edu.cn/', 
        'https://rsc.nankai.edu.cn/', 
        'https://international.nankai.edu.cn/', 
        'https://nktw.nankai.edu.cn/', 
        'https://sky.nankai.edu.cn/', 
        'https://medical.nankai.edu.cn/', 
        'https://pharmacy.nankai.edu.cn/', 
        'https://skleoc.nankai.edu.cn/', 
        'https://sklmcb.nankai.edu.cn/', 
        'https://klfpm.nankai.edu.cn/', 
        'https://lpmc.nankai.edu.cn/', 
        'https://teda.nankai.edu.cn/', 
        'https://enstd.nankai.edu.cn/',


        'http://www.lib.nankai.edu.cn/', 
        'https://archives.nankai.edu.cn/', 
        'https://xs.nankai.edu.cn/', 
        'https://kexie.nankai.edu.cn/', 
        'https://career.nankai.edu.cn/', 
        'https://xds.nankai.edu.cn/', 
        'https://xgb.nankai.edu.cn/', 
        'https://czfw.nankai.edu.cn/', 
        'https://fuxue.nankai.edu.cn/', 
        'https://mail.nankai.edu.cn/', 
        'https://stat.nankai.edu.cn/', 
        'https://cyber.nankai.edu.cn/', 
        'https://cfc.nankai.edu.cn/', 
        'https://iap.nankai.edu.cn/', 
        'https://phil.nankai.edu.cn/', 
        'https://fld.nankai.edu.cn/', 
        'https://zfxy.nankai.edu.cn/', 
        'https://marx.nankai.edu.cn/', 
        'https://lyxy.nankai.edu.cn/', 
        'https://tc.nankai.edu.cn/', 
        'https://bj.nankai.edu.cn/', 
        'https://jp.nankai.edu.cn/', 
        'https://by.nankai.edu.cn/', 
        'https://tyb.nankai.edu.cn/', 
        'https://cj.nankai.edu.cn/', 
        'https://cim.nankai.edu.cn/', 
        'https://combi.nankai.edu.cn/', 
        'https://matphys.nankai.edu.cn/', 
        'https://nano.nankai.edu.cn/', 
        'https://biotech.nankai.edu.cn/', 
        'https://nktw.nankai.edu.cn/stushe/', 
        'https://acm.nankai.edu.cn/', 
        'https://anime.nankai.edu.cn/', 
        'https://dance.nankai.edu.cn/', 
        'https://music.nankai.edu.cn/', 
        'https://volunteer.nankai.edu.cn/'
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
        raw_text_list = response.xpath(
            '//body//text()['
            'not(ancestor::script) and '
            'not(ancestor::style) and '
            'not(ancestor::header) and '
            'not(ancestor::footer) and '
            'not(ancestor::nav) and '
            'not(ancestor::div[contains(@class, "header")]) and '
            'not(ancestor::div[contains(@class, "footer")]) and '
            'not(ancestor::div[contains(@class, "nav")]) and '
            'not(ancestor::div[contains(@class, "bottom")])'
            ']'
        ).getall()
        
        # 拼接纯净正文，过滤空白字符
        item['content'] = ' '.join([text.strip() for text in raw_text_list if text.strip()])

        attachments = []
        attachment_names = []
        seen_urls = set()
        for a in response.xpath('//a[@href]'):
            href = (a.xpath('@href').get() or '').strip()
            if not href or href.startswith(('javascript:', 'mailto:', '#')):
                continue
            path_lower = href.lower().split('?')[0].split('#')[0]
            if not any(path_lower.endswith(ext) for ext in DOC_EXTENSIONS):
                continue
            full_url = response.urljoin(href)
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)
            name = ' '.join(t.strip() for t in a.xpath('.//text()').getall() if t.strip())
            if not name:
                name = href.rstrip('/').split('/')[-1].split('?')[0]
            attachments.append(full_url)
            attachment_names.append(name)

        item['attachments'] = attachments
        item['attachment_names'] = attachment_names
        if attachment_names:
            item['content'] = item['content'] + ' ' + ' '.join(attachment_names)

        headings = extract_headings(response)
        item['page_features'] = build_page_features(
            response.url,
            item['title'],
            item['content'],
            headings=headings,
        )

        valid_out_links = set()
        links = response.xpath('//a/@href').getall()
        
        for link in links:
            # 跳过JavaScript和邮件链接
            if link.startswith('javascript:') or link.startswith('mailto:'):
                continue
            
            # 过滤多媒体与压缩包等非网页资源
            if link.lower().endswith(('.jpg', '.png', '.gif', '.mp4', '.rar') + DOC_EXTENSIONS):
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