#!/usr/bin/env python3
"""
数据库结构升级脚本
为repositories表添加分类相关字段
"""

import sqlite3
import logging

def upgrade_database(db_path: str = "./data/github_repos_single_table.db"):
    """
    升级数据库结构，添加分类相关字段
    """
    logger = logging.getLogger(__name__)
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 1. 获取当前表结构
        cursor.execute("PRAGMA table_info(repositories)")
        columns = [col[1] for col in cursor.fetchall()]
        
        print("当前表结构:")
        for col in columns:
            print(f"  - {col}")
        
        # 2. 需要添加的字段
        new_columns = [
            ("category_l1", "TEXT", "一级分类"),
            ("category_l1_reason", "TEXT", "分类理由"),
            ("category_l1_model", "TEXT", "使用的模型"),
            ("category_l1_processed_at", "TIMESTAMP", "处理时间"),
            ("ai_raw_response", "TEXT", "AI原始响应"),
            ("classification_status", "TEXT DEFAULT 'pending'", "分类状态"),
            ("readme_clean", "TEXT", "清洗后的README")
        ]
        
        added_columns = []
        for col_name, col_type, description in new_columns:
            if col_name not in columns:
                try:
                    cursor.execute(f"ALTER TABLE repositories ADD COLUMN {col_name} {col_type}")
                    added_columns.append(f"{col_name} ({description})")
                    print(f"✅ 添加字段: {col_name}")
                except sqlite3.OperationalError as e:
                    print(f"⚠️  字段 {col_name} 可能已存在: {e}")
        
        # 3. 创建索引以提高查询性能
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_status ON repositories(classification_status)",
            "CREATE INDEX IF NOT EXISTS idx_serial ON repositories(serial_number)",
            "CREATE INDEX IF NOT EXISTS idx_stars ON repositories(stargazers_count DESC)",
            "CREATE INDEX IF NOT EXISTS idx_category ON repositories(category_l1)"
        ]
        
        for index_sql in indexes:
            cursor.execute(index_sql)
        
        conn.commit()
        
        print(f"\n✅ 数据库升级完成!")
        if added_columns:
            print(f"新增字段: {', '.join(added_columns)}")
        else:
            print("所有字段均已存在，无需新增")
        
        # 4. 统计当前数据状态
        cursor.execute("SELECT COUNT(*) FROM repositories")
        total = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM repositories WHERE readme IS NOT NULL")
        with_readme = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM repositories WHERE classification_status = 'completed'")
        completed = cursor.fetchone()[0]
        
        print(f"\n📊 数据统计:")
        print(f"  - 总仓库数: {total}")
        print(f"  - 有README的仓库: {with_readme}")
        print(f"  - 已分类的仓库: {completed}")
        print(f"  - 待分类的仓库: {total - completed}")
        
        conn.close()
        
    except Exception as e:
        logger.error(f"数据库升级失败: {e}")
        raise

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    else:
        db_path = "./data/github_repos_single_table.db"
    
    upgrade_database(db_path)