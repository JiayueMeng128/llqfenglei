import requests
import json
import os
import time
from datetime import datetime

# --- 配置区 ---
# 重要：请在环境中设置 GITHUB_PAT，或在下面直接替换为你的令牌
GITHUB_TOKEN = os.getenv("")
SEARCH_QUERY = "browser"  # 搜索关键词
RESULTS_PER_PAGE = 10     # 与网页一致，每页10条
TOTAL_PAGES = 100         # 硬限制：100页

HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json"
}

# 路径设置
RAW_PAGES_DIR = "data/raw_pages"  # 存放每一页的原始JSON
MANIFEST_FILE = "data/manifest.json"  # 最终合并的清单
CHECKPOINT_FILE = "data/checkpoint.json"  # 进度文件

def save_json(data, path):
    """保存数据到JSON文件"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_json(path):
    """从JSON文件加载数据"""
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return None
    return None

def fetch_one_page(page_num):
    """抓取单页数据"""
    url = "https://api.github.com/search/repositories"
    params = {
        "q": SEARCH_QUERY,
        "sort": "stars",
        "order": "desc",
        "page": page_num,
        "per_page": RESULTS_PER_PAGE
    }
    
    try:
        print(f"  正在请求第 {page_num} 页...")
        response = requests.get(url, headers=HEADERS, params=params, timeout=30)
        response.raise_for_status()  # 检查HTTP错误
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"    请求失败: {e}")
        if hasattr(e.response, 'status_code'):
            if e.response.status_code == 403:
                print("    [!] 触发速率限制，程序将暂停60秒...")
                time.sleep(60)
                return fetch_one_page(page_num)  # 重试一次
        return None

def main():
    print("="*60)
    print("GitHub 仓库列表抓取 (试运行)")
    print(f"搜索词: {SEARCH_QUERY}")
    print(f"模式: 抓取前 {TOTAL_PAGES} 页，每页 {RESULTS_PER_PAGE} 条")
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)

    # 1. 加载进度
    checkpoint = load_json(CHECKPOINT_FILE) or {"last_page": 0, "total_items": 0}
    start_page = checkpoint["last_page"] + 1
    
    if start_page > TOTAL_PAGES:
        print(f"[!] 进度显示已完成所有{TOTAL_PAGES}页。")
        return

    print(f"[*] 从第 {start_page} 页开始继续...")

    all_repos = []
    
    # 2. 逐页抓取循环
    for page in range(start_page, TOTAL_PAGES + 1):
        print(f"\n[第 {page}/{TOTAL_PAGES} 页]")
        
        # 发送请求
        page_data = fetch_one_page(page)
        if page_data is None:
            print(f"    [!] 第 {page} 页抓取失败，跳过。")
            continue
        
        # 检查是否有数据
        items = page_data.get('items', [])
        if not items:
            print(f"    [!] 第 {page} 页数据为空，提前结束。")
            break
        
        # 3. 立即保存原始页面数据
        page_filename = f"page_{page:03d}.json"
        page_path = os.path.join(RAW_PAGES_DIR, page_filename)
        save_json(page_data, page_path)
        print(f"    [√] 原始数据已保存: {page_filename}")
        
        # 4. 提取关键信息到内存列表
        for item in items:
            all_repos.append({
                "id": item['id'],
                "name": item['name'],
                "full_name": item['full_name'],
                "html_url": item['html_url'],
                "description": item.get('description', ''),
                "stargazers_count": item['stargazers_count'],
                "language": item.get('language'),
                "created_at": item['created_at'],
                "updated_at": item['updated_at'],
                "page_captured": page  # 记录来自哪一页
            })
        
        # 5. 更新进度（每一步都保存）
        checkpoint.update({
            "last_page": page,
            "total_items": checkpoint["total_items"] + len(items),
            "last_update": datetime.now().isoformat()
        })
        save_json(checkpoint, CHECKPOINT_FILE)
        print(f"    本页捕获: {len(items)} 条，累计: {checkpoint['total_items']} 条")
        
        # 6. 请求间隔（避免触发限制）
        time.sleep(1.2)  # 关键：礼貌的爬取间隔
    
    # 7. 抓取完成，保存最终清单
    print(f"\n[*] 抓取完成。正在生成总清单...")
    final_manifest = {
        "query": SEARCH_QUERY,
        "total_pages_crawled": checkpoint["last_page"],
        "total_repositories": checkpoint["total_items"],
        "crawled_at": datetime.now().isoformat(),
        "repositories": all_repos
    }
    save_json(final_manifest, MANIFEST_FILE)
    
    # 8. 生成一份简明的CSV摘要，方便快速查看
    try:
        import csv
        csv_path = "data/repository_summary.csv"
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['page', 'stars', 'language', 'full_name', 'description'])
            writer.writeheader()
            for repo in all_repos:
                writer.writerow({
                    'page': repo['page_captured'],
                    'stars': repo['stargazers_count'],
                    'language': repo['language'] or '',
                    'full_name': repo['full_name'],
                    'description': repo['description'][:100] if repo['description'] else ''  # 截断长描述
                })
        print(f"    [√] 已生成CSV摘要: {csv_path}")
    except ImportError:
        print("    [!] 未找到csv模块，跳过生成CSV。")
    
    print("\n" + "="*60)
    print("[完成] 试运行抓取结束！")
    print(f"总计处理: {checkpoint['last_page']} 页")
    print(f"总计捕获: {checkpoint['total_items']} 个仓库")
    print(f"数据位置:")
    print(f"  - 原始分页数据: {RAW_PAGES_DIR}/")
    print(f"  - 合并清单: {MANIFEST_FILE}")
    print(f"  - 抓取进度: {CHECKPOINT_FILE}")
    print("="*60)

if __name__ == "__main__":
    main()