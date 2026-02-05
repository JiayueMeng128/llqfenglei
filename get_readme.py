import json
import base64
import time
import os
from datetime import datetime
from typing import Dict, List, Any, Optional

# ====== 配置区 ======
# 请确保使用你测试成功的有效令牌
GITHUB_TOKEN = ""

HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "User-Agent": "README-Crawler/1.0"
}

# 输入文件：你清洗后的仓库数据
CLEANED_DATA_FILE = "data/repos_no_urls.json"
# 输出文件：最终包含README的数据
OUTPUT_DATA_FILE = "data/repos_with_readmes.json"
# 进度跟踪文件
PROGRESS_FILE = "data/readme_progress.json"
# 错误日志文件
ERROR_LOG_FILE = "data/readme_errors.json"

# ====== 辅助函数 ======
def save_json(data, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_json(path):
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return None
    return None

def fetch_readme_for_repo(full_name: str) -> Dict[str, Any]:
    """调用GitHub API获取指定仓库的README"""
    url = f"https://api.github.com/repos/{full_name}/readme"
    try:
        import requests  # 放函数内，确保失败时能捕获
        response = requests.get(url, headers=HEADERS, timeout=30)
        
        # 读取速率限制信息
        remaining = response.headers.get('X-RateLimit-Remaining', '?')
        print(f"       [配额剩余: {remaining}]", end="")
        
        if response.status_code == 200:
            return {"status": "success", "data": response.json()}
        elif response.status_code == 404:
            return {"status": "no_readme", "error": "README not found"}
        elif response.status_code == 403:
            if remaining == '0':
                reset_time = int(response.headers.get('X-RateLimit-Reset', 0))
                wait_time = max(reset_time - int(time.time()) + 2, 60)
                return {"status": "rate_limit", "wait_seconds": wait_time}
            else:
                return {"status": "api_error", "error": f"403 Forbidden"}
        else:
            return {"status": "error", "error": f"HTTP {response.status_code}: {response.text[:100]}"}
    except Exception as e:
        return {"status": "exception", "error": str(e)}

def decode_readme_content(readme_data: Dict) -> Optional[str]:
    """解码API返回的README内容（Base64格式）"""
    if readme_data.get("encoding") == "base64":
        try:
            content = base64.b64decode(readme_data["content"]).decode('utf-8')
            return content
        except:
            return None
    return readme_data.get("content")  # 如果不是base64，直接返回

def main():
    print("="*70)
    print("GitHub 仓库 README 批量获取工具")
    print("="*70)
    
    # 1. 加载清洗后的仓库数据
    print("[1/4] 加载仓库清单...")
    cleaned_data = load_json(CLEANED_DATA_FILE)
    if not cleaned_data:
        print(f"  错误: 无法读取文件 {CLEANED_DATA_FILE}")
        return
    
    all_repos = cleaned_data.get("repositories", [])
    total_repos = len(all_repos)
    print(f"  找到 {total_repos} 个待处理仓库。")
    
    # 2. 加载进度
    print("[2/4] 加载处理进度...")
    progress = load_json(PROGRESS_FILE) or {
        "last_processed_index": -1,
        "processed_count": 0,
        "success_count": 0,
        "no_readme_count": 0,
        "error_count": 0,
        "start_time": datetime.now().isoformat()
    }
    
    start_index = progress["last_processed_index"] + 1
    if start_index >= total_repos:
        print(f"  所有仓库已处理完毕！总计: {progress['processed_count']} 个")
        return
    
    print(f"  从第 {start_index + 1} 个仓库开始继续 (已处理 {progress['processed_count']} 个)")
    
    # 3. 初始化输出数据
    output_data = {
        "meta": {
            **cleaned_data.get("meta", {}),
            "readmes_added_at": datetime.now().isoformat(),
            "note": "此文件在清洗数据基础上增加了'readme_content'和'readme_info'字段"
        },
        "repositories": []  # 我们将逐步填充
    }
    
    # 4. 主处理循环
    print("[3/4] 开始获取 README...")
    consecutive_errors = 0
    
    for idx in range(start_index, total_repos):
        repo = all_repos[idx]
        full_name = repo["full_name"]
        current_number = idx + 1
        
        print(f"\n  [{current_number}/{total_repos}] {full_name}")
        
        # 获取README
        result = fetch_readme_for_repo(full_name)
        
        # 处理特殊状态
        if result["status"] == "rate_limit":
            wait = result.get("wait_seconds", 60)
            print(f"    ⏳ 触发速率限制，等待 {wait} 秒...")
            time.sleep(wait)
            result = fetch_readme_for_repo(full_name)  # 重试一次
        
        # 准备输出对象
        repo_with_readme = {**repo}  # 复制原数据
        
        if result["status"] == "success":
            readme_info = result["data"]
            # 解码内容
            readme_content = decode_readme_content(readme_info)
            if readme_content:
                # 可选：对超长README进行截断以节省空间
                max_length = 20000  # 保留约2万个字符
                if len(readme_content) > max_length:
                    repo_with_readme["readme_content"] = readme_content[:max_length] + f"\n\n... (已截断，完整内容 {len(readme_content)} 字符)"
                else:
                    repo_with_readme["readme_content"] = readme_content
                
                # 保留原始API返回的部分信息（不含大的content字段）
                repo_with_readme["readme_info"] = {
                    "name": readme_info.get("name"),
                    "path": readme_info.get("path"),
                    "size": readme_info.get("size"),
                    "html_url": readme_info.get("html_url"),
                    "download_url": readme_info.get("download_url")
                }
                print(f"    ✅ 成功获取 ({readme_info.get('size', 0)} 字节)")
                progress["success_count"] += 1
                consecutive_errors = 0
            else:
                repo_with_readme["readme_info"] = {"error": "无法解码README内容"}
                print(f"    ⚠️  获取成功但内容解码失败")
                progress["error_count"] += 1
                consecutive_errors += 1
                
        elif result["status"] == "no_readme":
            repo_with_readme["readme_info"] = {"status": "no_readme"}
            print(f"    ℹ️  无README文件")
            progress["no_readme_count"] += 1
            consecutive_errors = 0
        else:
            # 记录错误详情
            error_detail = {
                "full_name": full_name,
                "status": result["status"],
                "error": result.get("error"),
                "timestamp": datetime.now().isoformat()
            }
            # 保存到错误日志
            error_log = load_json(ERROR_LOG_FILE) or []
            error_log.append(error_detail)
            save_json(error_log, ERROR_LOG_FILE)
            
            repo_with_readme["readme_info"] = {"error": result.get("error", "unknown")}
            print(f"    ❌ 失败: {result.get('error', 'Unknown error')}")
            progress["error_count"] += 1
            consecutive_errors += 1
        
        # 添加到输出列表
        output_data["repositories"].append(repo_with_readme)
        
        # 更新进度
        progress["last_processed_index"] = idx
        progress["processed_count"] += 1
        progress["last_update"] = datetime.now().isoformat()
        
        # 每处理10个或每次失败后立即保存进度和输出
        if idx % 10 == 0 or result["status"] not in ["success", "no_readme"]:
            save_json(progress, PROGRESS_FILE)
            save_json(output_data, OUTPUT_DATA_FILE)
            print(f"      已保存进度和临时输出")
        
        # 连续错误过多则暂停
        if consecutive_errors >= 5:
            print(f"\n    ⚠️  连续失败 {consecutive_errors} 次，暂停程序，请检查网络或令牌状态。")
            print(f"    进度已保存，可稍后重新运行脚本继续。")
            break
        
        # 基础休眠，避免请求过快 (根据你的令牌速率调整)
        time.sleep(1.2)
    
    # 5. 最终保存
    print("\n[4/4] 保存最终结果...")
    progress["end_time"] = datetime.now().isoformat()
    save_json(progress, PROGRESS_FILE)
    
    # 确保最终输出包含所有已处理的仓库
    save_json(output_data, OUTPUT_DATA_FILE)
    
    # 生成报告
    total_time = datetime.fromisoformat(progress["end_time"]) - datetime.fromisoformat(progress["start_time"])
    print("\n" + "="*70)
    print("🏁 README 获取任务报告")
    print("="*70)
    print(f"   处理仓库总数: {progress['processed_count']}")
    print(f"   成功获取数:   {progress['success_count']}")
    print(f"   无README数:   {progress['no_readme_count']}")
    print(f"   失败数:       {progress['error_count']}")
    print(f"   总耗时:       {total_time}")
    print(f"\n   输出文件:      {OUTPUT_DATA_FILE}")
    print(f"   进度文件:      {PROGRESS_FILE}")
    print(f"   错误日志:      {ERROR_LOG_FILE}")
    
    if progress['processed_count'] < total_repos:
        remaining = total_repos - progress['processed_count']
        print(f"\n⚠️  注意: 还有 {remaining} 个仓库待处理。")
        print(f"   直接重新运行本脚本即可从断点继续。")
    else:
        print(f"\n✅ 所有仓库处理完毕！")

if __name__ == "__main__":
    main()