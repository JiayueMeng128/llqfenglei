import json
import os
import glob
from datetime import datetime
from typing import Dict, List, Any

# ====== 配置区 ======
# 原始数据所在目录（根据您之前的脚本，通常是这个路径）
RAW_DATA_DIR = "data/raw_pages"
# 输出的干净数据文件
CLEAN_DATA_FILE = "data/clean_repositories.json"
# 输出的统计摘要文件
STATS_FILE = "data/extraction_stats.json"

def extract_essential_info(raw_item: Dict[str, Any]) -> Dict[str, Any]:
    """
    从原始API的单个item中提取核心信息。
    这是清洗过程的核心逻辑。
    """
    # 1. 基础信息 (必选)
    essential = {
        "id": raw_item["id"],
        "name": raw_item["name"],
        "full_name": raw_item["full_name"],
        "html_url": raw_item["html_url"],
        "description": raw_item.get("description") or "",  # 处理可能的null
        "stargazers_count": raw_item["stargazers_count"],
        "watchers_count": raw_item.get("watchers_count", raw_item["stargazers_count"]), # 通常与stars同
        "language": raw_item.get("language"),  # 可能是null
        "topics": raw_item.get("topics", []),  # GitHub标签，高质量关键词
        "created_at": raw_item["created_at"],
        "updated_at": raw_item["updated_at"],
        "size": raw_item.get("size", 0),  # 仓库大小（KB），可衡量项目规模
    }
    
    # 2. 可选但有用的信息
    optional_fields = ["homepage", "license", "forks_count", "open_issues_count", "archived", "disabled"]
    for field in optional_fields:
        value = raw_item.get(field)
        if value is not None:
            # 特殊处理license，通常我们只关心类型
            if field == "license" and isinstance(value, dict):
                essential["license"] = value.get("spdx_id") or value.get("key")
            else:
                essential[field] = value
    
    # 3. 计算或派生字段（对AI可能有帮助）
    #    例如：项目年龄（天）
    try:
        created = datetime.fromisoformat(raw_item["created_at"].replace("Z", "+00:00"))
        now = datetime.utcnow()
        essential["age_days"] = (now - created).days
    except:
        essential["age_days"] = None
    
    return essential

def main():
    print("🔍 开始提取和清洗 GitHub 仓库核心数据...")
    print("=" * 60)
    
    # 查找所有原始页面文件
    # 假设文件名格式为 page_001.json, page_002.json ...
    pattern = os.path.join(RAW_DATA_DIR, "page_*.json")
    raw_files = sorted(glob.glob(pattern))
    
    if not raw_files:
        print(f"[错误] 在目录 '{RAW_DATA_DIR}' 中没有找到 page_*.json 文件。")
        print("请确认：")
        print(f"  1. 目录路径是否正确: {os.path.abspath(RAW_DATA_DIR)}")
        print("  2. 您是否已经成功运行了数据采集脚本？")
        return
    
    print(f"[信息] 找到 {len(raw_files)} 个原始数据文件。")
    print(f"[信息] 开始处理，结果将保存到: {CLEAN_DATA_FILE}")
    print("-" * 60)
    
    all_repos = []  # 存放所有清洗后的仓库数据
    stats = {
        "total_files_processed": 0,
        "total_repos_extracted": 0,
        "repos_without_description": 0,
        "repos_without_language": 0,
        "repos_with_topics": 0,
        "languages_found": set(),
        "errors": []
    }
    
    # 逐个文件处理
    for i, file_path in enumerate(raw_files, 1):
        file_name = os.path.basename(file_path)
        print(f"  正在处理 ({i:3d}/{len(raw_files)}): {file_name}", end="")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 从API响应中提取 `items` 列表
            items = data.get('items', [])
            if not items:
                print(" -> [跳过] 无数据项")
                continue
            
            file_repo_count = 0
            for raw_item in items:
                try:
                    # 提取核心信息
                    clean_repo = extract_essential_info(raw_item)
                    all_repos.append(clean_repo)
                    file_repo_count += 1
                    
                    # 收集统计信息
                    if not clean_repo["description"]:
                        stats["repos_without_description"] += 1
                    if not clean_repo["language"]:
                        stats["repos_without_language"] += 1
                    else:
                        stats["languages_found"].add(clean_repo["language"])
                    if clean_repo["topics"]:
                        stats["repos_with_topics"] += 1
                        
                except KeyError as e:
                    stats["errors"].append(f"文件 {file_name} 中的仓库缺少关键字段: {e}")
                    continue
                except Exception as e:
                    stats["errors"].append(f"处理 {file_name} 中的仓库时出错: {e}")
                    continue
            
            stats["total_files_processed"] += 1
            stats["total_repos_extracted"] += file_repo_count
            print(f" -> [完成] 提取了 {file_repo_count:3d} 个仓库")
            
        except json.JSONDecodeError:
            print(f" -> [错误] JSON 解析失败")
            stats["errors"].append(f"文件 {file_name} 不是有效的JSON")
        except Exception as e:
            print(f" -> [错误] {e}")
            stats["errors"].append(f"处理文件 {file_name} 时出错: {e}")
    
    print("-" * 60)
    print(f"[信息] 文件处理完成。")
    print(f"[信息] 开始保存清洗后的数据...")
    
    # 保存清洗后的核心数据
    output_data = {
        "meta": {
            "extracted_at": datetime.now().isoformat(),
            "total_repositories": len(all_repos),
            "source_files": len(raw_files),
            "description": "清洗后的GitHub仓库核心数据集，适用于AI分析分类。"
        },
        "repositories": all_repos
    }
    
    with open(CLEAN_DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    print(f"[成功] 清洗后的数据已保存至: {CLEAN_DATA_FILE}")
    print(f"       包含 {len(all_repos)} 个仓库。")
    
    # 计算并保存统计信息
    stats["languages_found"] = list(stats["languages_found"])
    stats["languages_count"] = len(stats["languages_found"])
    stats["extraction_completed_at"] = datetime.now().isoformat()
    
    with open(STATS_FILE, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    
    # 打印统计摘要
    print("\n📊 数据提取统计摘要:")
    print("=" * 60)
    print(f"   处理的原始文件: {stats['total_files_processed']} 个")
    print(f"   提取的总仓库数: {stats['total_repos_extracted']} 个")
    print(f"   无描述的仓库: {stats['repos_without_description']} 个 ({stats['repos_without_description']/max(stats['total_repos_extracted'],1)*100:.1f}%)")
    print(f"   无语言的仓库: {stats['repos_without_language']} 个 ({stats['repos_without_language']/max(stats['total_repos_extracted'],1)*100:.1f}%)")
    print(f"   带有话题标签的仓库: {stats['repos_with_topics']} 个 ({stats['repos_with_topics']/max(stats['total_repos_extracted'],1)*100:.1f}%)")
    print(f"   发现的不同语言: {stats['languages_count']} 种")
    if stats['languages_count'] > 0:
        print(f"   前5种语言: {', '.join(sorted(stats['languages_found'])[:5])}")
    if stats['errors']:
        print(f"   遇到的错误数: {len(stats['errors'])} 个 (详见 {STATS_FILE})")
    
    # 显示数据样本
    if all_repos:
        print("\n🔍 数据样本 (前3个仓库):")
        print("-" * 40)
        for i, repo in enumerate(all_repos[:3], 1):
            print(f"{i}. {repo['full_name']}")
            print(f"   描述: {repo['description'][:80]}{'...' if len(repo['description']) > 80 else ''}")
            print(f"   语言: {repo.get('language', 'N/A')}, 星标: {repo['stargazers_count']}, 话题: {', '.join(repo['topics'][:3])}")
            print()
    
    print("=" * 60)
    print("✅ 数据清洗与提取完成！")
    print(f"   核心数据: {CLEAN_DATA_FILE}")
    print(f"   处理统计: {STATS_FILE}")

if __name__ == "__main__":
    main()