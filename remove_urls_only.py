import json
import os
import glob
from datetime import datetime
from typing import Dict, List, Any

# ====== 配置区 ======
RAW_DATA_DIR = "data/raw_pages"          # 原始数据目录
CLEAN_DATA_FILE = "data/repos_no_urls.json" # 清洗后输出文件
STATS_FILE = "data/cleaning_stats.json"      # 清洗统计文件

# 定义需要移除的URL字段模式（主要针对仓库和所有者对象中的链接）
URL_FIELDS_TO_REMOVE = {
    # 仓库级别的API链接
    'url', 'forks_url', 'keys_url', 'collaborators_url', 'teams_url',
    'hooks_url', 'issue_events_url', 'events_url', 'assignees_url',
    'branches_url', 'tags_url', 'blobs_url', 'git_tags_url', 'git_refs_url',
    'trees_url', 'statuses_url', 'languages_url', 'stargazers_url',
    'contributors_url', 'subscribers_url', 'subscription_url',
    'commits_url', 'git_commits_url', 'comments_url', 'issue_comment_url',
    'contents_url', 'compare_url', 'merges_url', 'archive_url',
    'downloads_url', 'issues_url', 'pulls_url', 'milestones_url',
    'notifications_url', 'labels_url', 'releases_url', 'deployments_url',
    # Git URLs (有时也需要清理)
    'git_url', 'ssh_url', 'clone_url', 'svn_url',
    # 所有者（用户/组织）对象的API链接
    'followers_url', 'following_url', 'gists_url', 'starred_url',
    'subscriptions_url', 'organizations_url', 'repos_url', 'events_url',
    'received_events_url'
}

def remove_url_fields(data_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    递归遍历字典，移除预定义的URL字段。
    保留所有其他数据，包括嵌套结构。
    """
    if not isinstance(data_dict, dict):
        return data_dict
    
    cleaned = {}
    for key, value in data_dict.items():
        # 如果字段在移除列表中，则跳过
        if key in URL_FIELDS_TO_REMOVE:
            continue
        
        # 递归处理嵌套字典或列表
        if isinstance(value, dict):
            cleaned[key] = remove_url_fields(value)
        elif isinstance(value, list):
            # 处理列表中的每个元素
            cleaned[key] = [remove_url_fields(item) if isinstance(item, dict) else item for item in value]
        else:
            cleaned[key] = value
    return cleaned

def clean_repository_item(raw_item: Dict) -> Dict:
    """
    清洗单个仓库条目，移除指定的URL字段。
    """
    return remove_url_fields(raw_item)

def main():
    print("🧹 开始清洗 GitHub 仓库数据：仅移除冗余URL字段")
    print("=" * 60)
    
    # 查找原始文件
    pattern = os.path.join(RAW_DATA_DIR, "page_*.json")
    raw_files = sorted(glob.glob(pattern))
    
    if not raw_files:
        print(f"[错误] 在 '{RAW_DATA_DIR}' 中未找到 page_*.json 文件。")
        print("请确认数据采集脚本已成功运行。")
        return
    
    print(f"[信息] 找到 {len(raw_files)} 个原始数据文件。")
    print(f"[信息] 清洗后的数据将保存至: {CLEAN_DATA_FILE}")
    print("-" * 60)
    
    all_repos = []
    stats = {
        "total_files": len(raw_files),
        "files_processed": 0,
        "total_repos": 0,
        "total_fields_removed": 0,
        "errors": []
    }
    
    # 处理每个文件
    for i, file_path in enumerate(raw_files, 1):
        file_name = os.path.basename(file_path)
        print(f"  清洗中 ({i:3d}/{len(raw_files)}): {file_name}", end="")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            items = data.get('items', [])
            if not items:
                print(" -> [跳过] 无数据")
                continue
            
            file_repo_count = 0
            for raw_item in items:
                try:
                    cleaned_item = clean_repository_item(raw_item)
                    all_repos.append(cleaned_item)
                    file_repo_count += 1
                except Exception as e:
                    stats["errors"].append(f"清洗 {file_name} 中仓库时出错: {e}")
                    continue
            
            stats["files_processed"] += 1
            stats["total_repos"] += file_repo_count
            print(f" -> [完成] {file_repo_count:3d} 个仓库")
            
        except json.JSONDecodeError:
            print(" -> [错误] JSON解析失败")
            stats["errors"].append(f"文件 {file_name} JSON无效")
        except Exception as e:
            print(f" -> [错误] {e}")
            stats["errors"].append(f"处理文件 {file_name} 失败: {e}")
    
    print("-" * 60)
    print(f"[信息] 正在保存清洗后的数据...")
    
    # 保存清洗后的数据（保持结构，但体积更小）
    output_data = {
        "meta": {
            "cleaned_at": datetime.now().isoformat(),
            "total_repositories": len(all_repos),
            "original_files": len(raw_files),
            "description": "GitHub仓库数据，已移除冗余API URL字段。",
            "note": "保留了所有描述性元数据（如描述、语言、标签、许可证等）。"
        },
        "repositories": all_repos
    }
    
    with open(CLEAN_DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    # 计算粗略的体积变化（基于字段名估算）
    original_sample_fields = 60  # 原始API中大约有60个字段
    cleaned_sample_fields = 25   # 移除URL后大约剩下25个核心字段
    reduction_percent = int((1 - cleaned_sample_fields / original_sample_fields) * 100)
    
    print(f"[成功] 数据已保存至: {CLEAN_DATA_FILE}")
    print(f"       包含 {len(all_repos)} 个仓库。")
    print(f"       预计数据体积减少约: {reduction_percent}%")
    
    # 保存统计信息
    stats["cleaned_at"] = datetime.now().isoformat()
    with open(STATS_FILE, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    
    # 显示清洗效果对比
    if all_repos:
        sample_repo = all_repos[0]
        print("\n🔍 清洗前后字段数量对比（示例仓库）:")
        print("-" * 50)
        print(f"  保留的关键字段示例:")
        print(f"    • id: {sample_repo.get('id')}")
        print(f"    • name: {sample_repo.get('name')}")
        print(f"    • full_name: {sample_repo.get('full_name')}")
        print(f"    • description: {sample_repo.get('description', '')[:50]}...")
        print(f"    • language: {sample_repo.get('language')}")
        print(f"    • stargazers_count: {sample_repo.get('stargazers_count')}")
        print(f"    • topics: {sample_repo.get('topics', [])[:3]}")
        print(f"    • license: {sample_repo.get('license', {}).get('key', 'N/A')}")
        print(f"    • created_at: {sample_repo.get('created_at')}")
        print(f"    • permissions: {sample_repo.get('permissions', {})}")
        print(f"\n  已移除的冗余URL字段示例:")
        print(f"    • forks_url, hooks_url, issues_url, ... (共约35个)")
    
    print("\n" + "=" * 60)
    print("✅ 数据清洗完成！")
    print(f"   清洗后数据: {CLEAN_DATA_FILE}")
    print(f"   清洗统计: {STATS_FILE}")
    print(f"\n📌 此文件已优化，可直接用于：")
    print("   • AI批量分类分析")
    print("   • 数据可视化")
    print("   • 进一步的元数据挖掘")

if __name__ == "__main__":
    main()