import requests
import json
import os
import time
from datetime import datetime
from typing import Optional, Dict, Any

# ====== 配置区 ======
# 请务必使用刚刚测试成功的有效令牌
GITHUB_TOKEN = ""

HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "User-Agent": "Resilient-GitHub-Crawler/1.0"
}

SEARCH_QUERY = "browser"
RESULTS_PER_PAGE = 10
TOTAL_PAGES = 100  # GitHub网页端显示的上限
MAX_RETRIES = 5    # 单页最大重试次数

# ====== 路径设置 ======
DATA_DIR = "data"
RAW_PAGES_DIR = os.path.join(DATA_DIR, "raw_pages")
CHECKPOINT_FILE = os.path.join(DATA_DIR, "checkpoint.json")
ERROR_LOG_FILE = os.path.join(DATA_DIR, "error_log.json")
SESSION_STATS_FILE = os.path.join(DATA_DIR, "session_stats.json")

os.makedirs(RAW_PAGES_DIR, exist_ok=True)

# ====== 核心函数 ======
def make_request(url: str, params: Dict, retry_count: int = 0) -> Optional[requests.Response]:
    """发起带错误处理和指数退避重试的请求"""
    if retry_count >= MAX_RETRIES:
        print(f"        [✗] 已达最大重试次数({MAX_RETRIES})，放弃。")
        return None

    try:
        response = requests.get(url, headers=HEADERS, params=params, timeout=45)
        status = response.status_code

        # 检查速率限制头部
        remaining = response.headers.get('X-RateLimit-Remaining')
        limit = response.headers.get('X-RateLimit-Limit')
        if remaining and limit:
            print(f"        [i] 配额：{remaining}/{limit}", end='')

        # 处理不同状态码
        if status == 200:
            print(" -> ✅ 成功")
            return response
        elif status == 401:
            print(f" -> ❌ 认证失效(401)")
            # 等待较长时间后重试
            wait = 30 * (2 ** retry_count)  # 指数退避
            print(f"        [⏳] 等待{wait}秒后重试...")
            time.sleep(wait)
            return make_request(url, params, retry_count + 1)
        elif status == 403:
            # 检查是速率限制还是其他禁止访问
            if remaining == '0':
                reset_time = int(response.headers.get('X-RateLimit-Reset', 0))
                wait_seconds = max(reset_time - int(time.time()) + 2, 60)  # 重置后多等2秒
                print(f" -> ⏳ 速率限制(403)，等待{wait_seconds}秒...")
                time.sleep(wait_seconds)
                return make_request(url, params, retry_count + 1)
            else:
                print(f" -> ⚠️  其他403错误，跳过")
                return None
        elif status == 429:
            # 滥用速率限制，需要更长时间等待
            retry_after = int(response.headers.get('Retry-After', 60))
            wait = retry_after * (2 ** retry_count)
            print(f" -> 🚫 触发滥用限制(429)，等待{wait}秒...")
            time.sleep(wait)
            return make_request(url, params, retry_count + 1)
        elif status == 422:
            print(" -> ℹ️  参数错误(422)，可能已无更多页面。")
            return None
        elif status == 503:
            wait = 30 * (2 ** retry_count)
            print(f" -> 🚧 服务不可用(503)，等待{wait}秒...")
            time.sleep(wait)
            return make_request(url, params, retry_count + 1)
        else:
            print(f" -> ❗ 意外错误({status})")
            return None

    except requests.exceptions.Timeout:
        print(f"        [⌛] 请求超时，第{retry_count+1}次重试...")
        time.sleep(10 * (retry_count + 1))
        return make_request(url, params, retry_count + 1)
    except requests.exceptions.ConnectionError:
        print(f"        [🔌] 连接错误，第{retry_count+1}次重试...")
        time.sleep(15 * (retry_count + 1))
        return make_request(url, params, retry_count + 1)
    except Exception as e:
        print(f"        [💥] 未知异常: {e}")
        return None

def log_error(page: int, error_type: str, details: str):
    """记录错误到日志文件"""
    error_entry = {
        "timestamp": datetime.now().isoformat(),
        "page": page,
        "type": error_type,
        "details": details
    }
    logs = []
    if os.path.exists(ERROR_LOG_FILE):
        try:
            with open(ERROR_LOG_FILE, 'r', encoding='utf-8') as f:
                logs = json.load(f)
        except:
            pass
    logs.append(error_entry)
    with open(ERROR_LOG_FILE, 'w', encoding='utf-8') as f:
        json.dump(logs, f, indent=2, ensure_ascii=False)

def save_checkpoint(page: int, total: int, stats: Dict):
    """保存进度和统计信息"""
    checkpoint = {
        "last_successful_page": page,
        "total_repositories": total,
        "updated_at": datetime.now().isoformat(),
        "session_stats": stats
    }
    with open(CHECKPOINT_FILE, 'w', encoding='utf-8') as f:
        json.dump(checkpoint, f, indent=2, ensure_ascii=False)

def load_checkpoint() -> Dict:
    """加载之前的进度"""
    if os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {"last_successful_page": 0, "total_repositories": 0}

def main():
    print("🚀 GitHub 仓库稳健采集器 - 启动")
    print("=" * 60)

    # 加载进度
    checkpoint = load_checkpoint()
    start_page = checkpoint.get("last_successful_page", 0) + 1
    total_repos = checkpoint.get("total_repositories", 0)

    print(f"[i] 上次进度: 第 {start_page-1} 页，累计 {total_repos} 仓库")
    print(f"[i] 本次将从: 第 {start_page} 页开始")

    # 初始化会话统计
    stats = {
        "session_start": datetime.now().isoformat(),
        "pages_attempted": 0,
        "pages_succeeded": 0,
        "pages_failed": 0,
        "requests_made": 0,
        "total_wait_time": 0
    }

    all_repos = []
    session_start_time = time.time()

    # 主采集循环
    for current_page in range(start_page, TOTAL_PAGES + 1):
        print(f"\n📄 [第 {current_page:3d}/{TOTAL_PAGES} 页]")
        stats["pages_attempted"] += 1

        # 发起请求
        url = "https://api.github.com/search/repositories"
        params = {
            "q": SEARCH_QUERY,
            "sort": "stars",
            "order": "desc",
            "page": current_page,
            "per_page": RESULTS_PER_PAGE
        }

        response = make_request(url, params)
        stats["requests_made"] += 1

        if response is None:
            print(f"    [❌] 页面 {current_page} 抓取彻底失败。")
            stats["pages_failed"] += 1
            log_error(current_page, "FATAL", "请求返回None，所有重试均失败")
            # 跳过此页，继续下一页
            continue

        # 处理成功响应
        try:
            data = response.json()
        except json.JSONDecodeError:
            print(f"    [⚠️] 页面 {current_page} 响应不是有效JSON，跳过。")
            stats["pages_failed"] += 1
            log_error(current_page, "INVALID_JSON", "响应无法解析为JSON")
            continue

        items = data.get('items', [])
        if not items:
            print(f"    [ℹ️] 页面 {current_page} 无数据，可能已达末尾。")
            break

        # 保存原始数据
        raw_filename = f"page_{current_page:03d}.json"
        raw_path = os.path.join(RAW_PAGES_DIR, raw_filename)
        with open(raw_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"    [💾] 原始数据已保存: {raw_filename}")

        # 提取信息
        for item in items:
            all_repos.append({
                "id": item['id'],
                "full_name": item['full_name'],
                "stars": item['stargazers_count'],
                "language": item.get('language'),
                "description": item.get('description', ''),
                "url": item['html_url'],
                "page_captured": current_page
            })

        total_repos += len(items)
        stats["pages_succeeded"] += 1

        # 更新检查点（每成功一页就保存）
        save_checkpoint(current_page, total_repos, stats)

        print(f"    [✅] 捕获 {len(items)} 仓库，累计 {total_repos}")

        # 礼貌间隔，避免请求过快
        time.sleep(1.8)

    # ====== 收尾工作 ======
    session_duration = time.time() - session_start_time
    stats["session_end"] = datetime.now().isoformat()
    stats["session_duration_seconds"] = round(session_duration, 2)

    print("\n" + "=" * 60)
    print("🏁 采集会话结束")
    print(f"   尝试页数: {stats['pages_attempted']}")
    print(f"   成功页数: {stats['pages_succeeded']}")
    print(f"   失败页数: {stats['pages_failed']}")
    print(f"   累计仓库: {total_repos}")
    print(f"   总耗时: {stats['session_duration_seconds']} 秒")
    print("=" * 60)

    # 保存最终清单（如果抓到了数据）
    if all_repos:
        manifest = {
            "query": SEARCH_QUERY,
            "total_pages_crawled": checkpoint.get("last_successful_page", 0) + stats["pages_succeeded"],
            "total_repositories": total_repos,
            "crawled_at": datetime.now().isoformat(),
            "session_stats": stats,
            "repositories": all_repos  # 包含所有仓库的列表
        }
        manifest_file = os.path.join(DATA_DIR, "complete_manifest.json")
        with open(manifest_file, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        print(f"[💾] 完整清单已保存至: {manifest_file}")

    # 保存本次会话统计
    with open(SESSION_STATS_FILE, 'w', encoding='utf-8') as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    print(f"\n📁 数据文件位置:")
    print(f"   原始分页数据: {RAW_PAGES_DIR}/")
    print(f"   完整仓库清单: {DATA_DIR}/complete_manifest.json")
    print(f"   会话统计: {SESSION_STATS_FILE}")
    print(f"   错误日志: {ERROR_LOG_FILE}")
    print(f"   进度检查点: {CHECKPOINT_FILE}")
    print("=" * 60)
    print("✅ 脚本执行完毕。")

if __name__ == "__main__":
    main()