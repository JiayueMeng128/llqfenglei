#!/usr/bin/env python3
"""
调试版 - 检查数据库读取逻辑
"""

import sqlite3
import json
import sys

def debug_database_read(db_path: str):
    """调试数据库读取逻辑"""
    print("🔍 开始调试数据库读取...")
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 1. 首先检查数据库总行数
    cursor.execute("SELECT COUNT(*) as total FROM repositories")
    total_rows = cursor.fetchone()["total"]
    print(f"📊 数据库总行数: {total_rows}")
    
    # 2. 检查有多少行enhanced_text不为空
    cursor.execute("""
        SELECT COUNT(*) as count 
        FROM repositories 
        WHERE enhanced_text IS NOT NULL 
        AND LENGTH(enhanced_text) > 50
    """)
    valid_rows = cursor.fetchone()["count"]
    print(f"📊 有效仓库数（enhanced_text > 50）: {valid_rows}")
    
    # 3. 查看星标最高的前10个项目
    print("\n⭐ 星标最高的前10个项目:")
    cursor.execute("""
        SELECT id, full_name, stargazers_count, 
               LENGTH(enhanced_text) as text_length
        FROM repositories 
        WHERE enhanced_text IS NOT NULL 
          AND LENGTH(enhanced_text) > 50
        ORDER BY stargazers_count DESC 
        LIMIT 10
    """)
    
    top_repos = cursor.fetchall()
    for i, repo in enumerate(top_repos, 1):
        print(f"{i:2d}. {repo['full_name']:60} ⭐{repo['stargazers_count']:7} 文本长度:{repo['text_length']:5}")
    
    # 4. 检查星标最高的那个项目为什么可能被过滤掉
    print("\n🔎 检查星标最高的项目（无论enhanced_text如何）:")
    cursor.execute("""
        SELECT id, full_name, stargazers_count,
               enhanced_text,
               LENGTH(enhanced_text) as text_len
        FROM repositories 
        ORDER BY stargazers_count DESC 
        LIMIT 1
    """)
    
    top_repo = cursor.fetchone()
    print(f"项目名称: {top_repo['full_name']}")
    print(f"星标数: {top_repo['stargazers_count']}")
    print(f"enhanced_text长度: {top_repo['text_len']}")
    print(f"enhanced_text前100字符: {top_repo['enhanced_text'][:100] if top_repo['enhanced_text'] else '空'}")
    
    # 5. 查看enhanced_text为空的统计
    print("\n📝 enhanced_text状态统计:")
    cursor.execute("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN enhanced_text IS NULL THEN 1 ELSE 0 END) as null_count,
            SUM(CASE WHEN enhanced_text IS NOT NULL AND LENGTH(enhanced_text) <= 50 THEN 1 ELSE 0 END) as short_count,
            SUM(CASE WHEN enhanced_text IS NOT NULL AND LENGTH(enhanced_text) > 50 THEN 1 ELSE 0 END) as valid_count
        FROM repositories
    """)
    
    stats = cursor.fetchone()
    print(f"总数: {stats['total']}")
    print(f"enhanced_text为NULL: {stats['null_count']}")
    print(f"enhanced_text长度≤50: {stats['short_count']}")
    print(f"enhanced_text长度>50: {stats['valid_count']}")
    
    # 6. 执行你的原始查询并打印排序结果
    print("\n🔢 你的原始查询结果（按星标降序）:")
    cursor.execute("""
        SELECT id, full_name, enhanced_text, stargazers_count
        FROM repositories 
        WHERE enhanced_text IS NOT NULL 
          AND LENGTH(enhanced_text) > 50
        ORDER BY stargazers_count DESC
    """)
    
    all_valid_repos = cursor.fetchall()
    print(f"查询返回行数: {len(all_valid_repos)}")
    
    # 打印前20个
    print("前20个项目:")
    for i, repo in enumerate(all_valid_repos[:20], 1):
        print(f"{i:3d}. ID:{repo['id']:5} {repo['full_name']:60} ⭐{repo['stargazers_count']:6}")
    
    # 7. 检查ID连续性
    print("\n📈 检查ID分布:")
    ids = [repo['id'] for repo in all_valid_repos]
    print(f"ID范围: {min(ids)} - {max(ids)}")
    print(f"ID总数: {len(ids)}")
    
    # 找出缺失的大ID
    all_ids = set(range(1, max(ids) + 1))
    valid_ids = set(ids)
    missing_ids = all_ids - valid_ids
    
    # 检查缺失的ID是否因为enhanced_text太短
    print(f"\n🔍 检查前5个缺失的ID:")
    for missing_id in sorted(list(missing_ids))[:5]:
        cursor.execute("""
            SELECT full_name, stargazers_count, 
                   LENGTH(enhanced_text) as text_len
            FROM repositories 
            WHERE id = ?
        """, (missing_id,))
        
        missing_repo = cursor.fetchone()
        if missing_repo:
            print(f"ID {missing_id}: {missing_repo['full_name']:60} "
                  f"⭐{missing_repo['stargazers_count']:6} "
                  f"文本长度:{missing_repo['text_len']}")
    
    conn.close()
    
    return {
        "total_rows": total_rows,
        "valid_rows": valid_rows,
        "top_repos": top_repos,
        "all_valid_repos": all_valid_repos
    }

def main():
    if len(sys.argv) < 2:
        print("用法: python debug_db.py <数据库路径>")
        sys.exit(1)
    
    db_path = sys.argv[1]
    debug_database_read(db_path)

if __name__ == "__main__":
    main()