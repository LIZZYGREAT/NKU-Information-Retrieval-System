# backend/scripts/compute_pagerank.py
import pymysql
import networkx as nx
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk
from app.core.config import settings

def calculate_and_sync_pagerank():
    # 1. 从 MySQL 读取全量拓扑有向边
    connection = pymysql.connect(
        host=settings.MYSQL_HOST,
        user=settings.MYSQL_USER,
        password=settings.MYSQL_PASSWORD,
        database=settings.MYSQL_DATABASE,
        cursorclass=pymysql.cursors.DictCursor
    )
    
    edges = []
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT source_url, target_url FROM PageLinks")
            rows = cursor.fetchall()
            for row in rows:
                edges.append((row['source_url'], row['target_url']))
    finally:
        connection.close()

    if not edges:
        print("PageLinks 表中无拓扑数据，跳过计算。")
        return

    # 2. 构建 NetworkX 有向图并计算 PageRank
    print(f"开始构建图拓扑，边总数: {len(edges)}")
    G = nx.DiGraph()
    G.add_edges_from(edges)
    
    print("开始执行 PageRank 迭代计算...")
    # alpha=0.85 为标准阻尼系数
    pr_dict = nx.pagerank(G, alpha=0.85, max_iter=100, tol=1e-6)
    print(f"计算完成，节点总数: {len(pr_dict)}")

    # 3. 使用 Bulk API 批量异步刷入 Elasticsearch
    es = Elasticsearch(settings.ES_HOST)
    actions = [
        {
            "_op_type": "update",
            "_index": settings.ES_INDEX_NAME,
            "_id": url,
            "doc": {"pagerank": float(score)}
        }
        for url, score in pr_dict.items()
    ]
    
    print("开始向 Elasticsearch 批量同步 PageRank 分值...")
    success, errors = bulk(es, actions, raise_on_error=False)
    print(f"同步结束。成功更新: {success} 条记录，失败: {len(errors)} 条。")

if __name__ == "__main__":
    calculate_and_sync_pagerank()