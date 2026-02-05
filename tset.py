#!/usr/bin/env python3
"""
检查新代码与现有数据库的兼容性
"""

import sqlite3
import sys

def check_database_compatibility(db_path: str = "./data/github_repos_single_table.db"):
    """检查数据库兼容性"""
    
    print("🔍 检查新代码与数据库的兼容性")
    print("=" * 60)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 1. 检查表结构
    cursor.execute("PRAGMA table_info(repositories)")
    columns = {row[1]: row[2] for row in cursor.fetchall()}
    
    print("📋 表结构检查:")
    
    # 新代码需要的字段
    required_fields = {
        "id": "INTEGER PRIMARY KEY",
        "full_name": "TEXT",
        "enhanced_text": "TEXT",  # 新代码特有
        "serial_number": "TEXT",
        "classification_status": "TEXT",
        "category_l1": "TEXT",
        "category_l1_processed_at": "TIMESTAMP"
    }
    
    missing_fields = []
    existing_fields = []
    
    for field, expected_type in required_fields.items():
        if field in columns:
            actual_type = columns[field]
            status = "✅"
            if expected_type not in actual_type:
                status = f"⚠️  (类型不匹配: 期望{expected_type}, 实际{actual_type})"
            existing_fields.append((field, status))
        else:
            missing_fields.append(field)
    
    if existing_fields:
        print("  已有字段:")
        for field, status in existing_fields:
            print(f"    {field}: {status}")
    
    if missing_fields:
        print("  缺失字段:")
        for field in missing_fields:
            print(f"    ❌ {field}")
    
    # 2. 检查enhanced_text替代方案
    print(f"\n🔧 enhanced_text字段替代方案:")
    
    text_field_options = ["readme_clean", "readme", "description"]
    available_fields = []
    
    for field in text_field_options:
        if field in columns:
            # 检查是否有数据
            cursor.execute(f"SELECT COUNT(*) FROM repositories WHERE {field} IS NOT NULL AND LENGTH({field}) > 0")
            count = cursor.fetchone()[0]
            available_fields.append((field, count))
    
    if available_fields:
        for field, count in available_fields:
            total = cursor.execute("SELECT COUNT(*) FROM repositories").fetchone()[0]
            percentage = (count / total * 100) if total > 0 else 0
            print(f"    {field}: {count}/{total} ({percentage:.1f}%) 有数据")
    else:
        print("    ❌ 没有可用的文本字段")
    
    # 3. 检查ai_raw_logs表
    print(f"\n📊 ai_raw_logs表检查:")
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ai_raw_logs'")
    if cursor.fetchone():
        cursor.execute("SELECT COUNT(*) FROM ai_raw_logs")
        count = cursor.fetchone()[0]
        print(f"    ✅ 表已存在，有 {count} 条记录")
        
        cursor.execute("PRAGMA table_info(ai_raw_logs)")
        log_columns = [row[1] for row in cursor.fetchall()]
        print(f"    字段: {', '.join(log_columns)}")
    else:
        print("    ⚠️  表不存在，新代码会创建它")
    
    # 4. 数据质量检查
    print(f"\n📈 数据质量检查:")
    
    # 检查待处理数据
    cursor.execute("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN classification_status = 'completed' THEN 1 ELSE 0 END) as completed,
            SUM(CASE WHEN classification_status IS NULL OR classification_status != 'completed' THEN 1 ELSE 0 END) as pending
        FROM repositories
    """)
    
    total, completed, pending = cursor.fetchone()
    
    print(f"    总仓库数: {total}")
    print(f"    已分类: {completed} ({completed/total*100:.1f}%)")
    print(f"    待分类: {pending}")
    
    # 检查serial_number分布
    cursor.execute("SELECT COUNT(DISTINCT serial_number) FROM repositories WHERE serial_number IS NOT NULL")
    unique_sn = cursor.fetchone()[0]
    print(f"    唯一serial_number: {unique_sn}")
    
    # 5. 测试新代码的查询
    print(f"\n🔍 测试新代码的查询语句:")
    
    test_query = """
        SELECT id, full_name, serial_number 
        FROM repositories 
        WHERE classification_status IS NULL OR classification_status != 'completed'
        LIMIT 5
    """
    
    try:
        cursor.execute(test_query)
        results = cursor.fetchall()
        
        if results:
            print(f"    ✅ 查询成功，返回 {len(results)} 条记录")
            print(f"    示例记录:")
            for row in results[:3]:
                print(f"      ID: {row[0]}, 名称: {row[1]}, SN: {row[2]}")
        else:
            print(f"    ⚠️  查询成功，但没有待处理记录")
            
    except Exception as e:
        print(f"    ❌ 查询失败: {e}")
    
    conn.close()
    
    # 总结
    print(f"\n{'='*60}")
    print("📋 兼容性总结:")
    
    if missing_fields:
        print(f"❌ 关键字段缺失: {', '.join(missing_fields)}")
        print(f"   需要添加这些字段或修改代码")
    else:
        print(f"✅ 所有必需字段都存在")
    
    if "enhanced_text" in missing_fields:
        print(f"⚠️  缺少enhanced_text字段，建议:")
        if available_fields:
            best_field = max(available_fields, key=lambda x: x[1])[0]
            print(f"   使用 {best_field} 作为替代")
    
    return len(missing_fields) == 0

def create_fixed_version():
    """创建修复版的代码"""
    
    fixed_code = '''import sqlite3
import json
import os
import uuid
from openai import OpenAI
from datetime import datetime

# --- 从环境变量读取配置 ---
API_KEY = os.getenv("OPENAILIKED_API_KEY")
BASE_URL = os.getenv("OPENAILIKED_BASE_URL")
MODEL_NAME = os.getenv("OPENAILIKED_MODEL", "deepseek-chat")

if not API_KEY or not BASE_URL:
    print("❌ 错误: 请设置 OPENAILIKED_API_KEY 和 OPENAILIKED_BASE_URL 环境变量")
    exit(1)

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

def init_log_table(conn):
    """创建 AI 原始响应日志表"""
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ai_raw_logs (
            batch_id TEXT PRIMARY KEY,
            model_name TEXT,
            repo_sn_list TEXT,
            raw_response TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()

def get_best_text_field(conn):
    """确定使用哪个文本字段"""
    cursor = conn.cursor()
    
    # 检查字段存在性
    cursor.execute("PRAGMA table_info(repositories)")
    columns = [row[1] for row in cursor.fetchall()]
    
    # 优先级列表
    field_priority = ["readme_clean", "readme", "description"]
    
    for field in field_priority:
        if field in columns:
            # 检查数据质量
            cursor.execute(f"SELECT COUNT(*) FROM repositories WHERE {field} IS NOT NULL AND LENGTH({field}) > 100")
            count = cursor.fetchone()[0]
            if count > 0:
                return field
    
    return None

def process_batch(db_path, batch_size=15, max_retries=3):
    conn = sqlite3.connect(db_path)
    init_log_table(conn)
    cursor = conn.cursor()
    
    # 1. 确定使用的文本字段
    text_field = get_best_text_field(conn)
    if not text_field:
        print("❌ 错误: 没有可用的文本字段")
        conn.close()
        return False
    
    print(f"📝 使用文本字段: {text_field}")
    
    # 2. 提取待处理数据 (排除正在处理的)
    cursor.execute("""
        SELECT id, full_name, {}, serial_number 
        FROM repositories 
        WHERE (classification_status IS NULL OR classification_status NOT IN ('completed', 'processing'))
          AND {} IS NOT NULL
          AND LENGTH({}) > 100
        ORDER BY serial_number
        LIMIT ?
    """.format(text_field, text_field, text_field), (batch_size,))
    
    rows = cursor.fetchall()
    if not rows:
        conn.close()
        print("✅ 所有仓库已处理完成")
        return False
    
    # 3. 标记为处理中
    repo_ids = [r[0] for r in rows]
    placeholders = ','.join(['?'] * len(repo_ids))
    cursor.execute(f"""
        UPDATE repositories 
        SET classification_status = 'processing'
        WHERE id IN ({placeholders})
    """, repo_ids)
    conn.commit()
    
    # 4. 构造 AI 提示词
    items_list = []
    repo_sns = []
    
    for r in rows:
        repo_id, full_name, text_content, sn = r
        # 截断文本，保留关键信息
        preview = text_content[:800] + "..." if len(text_content) > 800 else text_content
        items_list.append(f"[{sn}] {full_name}: {preview}")
        repo_sns.append(sn)
    
    prompt = f"""
你是一个浏览器技术专家。请分析以下 {len(rows)} 个项目的描述，并为其创建有意义的分类。

## 项目列表：
{chr(10).join(items_list)}

## 任务要求：
1. 根据项目的功能、技术栈、用途，创建 3-6 个分类
2. 每个项目必须且只能分配到一个分类
3. 分类应该具体且有区分度（例如："浏览器自动化工具"而非"工具"）

## 输出格式：
请严格按照以下JSON格式输出：

{{
  "categories": ["分类A", "分类B", "分类C"],
  "mapping": {{
    "SN-0001": "分类A",
    "SN-0002": "分类B"
  }},
  "summary": {{
    "total_items": {len(rows)},
    "category_distribution": {{"分类A": 数量, "分类B": 数量}}
  }}
}}

## 注意：
- 使用中文分类名称
- 确保所有 SN 都有对应的分类
"""
    
    print(f"📦 正在处理批次: {repo_sns[0]} ~ {repo_sns[-1]} ({len(rows)}个项目)")
    
    # 5. 调用 AI 模型（带重试）
    for attempt in range(max_retries):
        try:
            print(f"  尝试 #{attempt + 1}...")
            
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=2000,
                response_format={"type": "json_object"}
            )
            
            raw_json_str = response.choices[0].message.content
            res_json = json.loads(raw_json_str)
            
            # 验证响应格式
            if "mapping" not in res_json:
                raise ValueError("AI响应缺少mapping字段")
            
            mapping = res_json.get("mapping", {})
            
            # 验证所有SN都有分类
            missing_sns = [sn for sn in repo_sns if sn not in mapping]
            if missing_sns:
                print(f"  ⚠️  以下SN没有分类: {missing_sns}")
                # 为缺失的SN分配默认分类
                default_category = res_json.get("categories", ["其他"])[0]
                for sn in missing_sns:
                    mapping[sn] = default_category
            
            # 6. 原始响应存证
            batch_uuid = str(uuid.uuid4())
            cursor.execute("""
                INSERT INTO ai_raw_logs (batch_id, model_name, repo_sn_list, raw_response)
                VALUES (?, ?, ?, ?)
            """, (batch_uuid, MODEL_NAME, ",".join(repo_sns), raw_json_str))
            
            # 7. 回填主表结果
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for r in rows:
                repo_id, full_name, text_content, sn = r
                category = mapping.get(sn, "未分类")
                
                cursor.execute("""
                    UPDATE repositories 
                    SET category_l1 = ?, 
                        classification_status = 'completed', 
                        category_l1_processed_at = ?,
                        category_l1_reason = 'AI批量分类'
                    WHERE id = ?
                """, (category, timestamp, repo_id))
            
            conn.commit()
            print(f"  ✅ 批次处理完成")
            
            # 打印分类统计
            categories = res_json.get("categories", [])
            print(f"    生成分类: {len(categories)}个")
            
            # 统计分类分布
            from collections import Counter
            category_counts = Counter(mapping.values())
            print(f"    分类分布: {dict(category_counts)}")
            
            break  # 成功则退出重试循环
            
        except Exception as e:
            print(f"  ❌ 尝试 {attempt + 1} 失败: {e}")
            
            if attempt == max_retries - 1:
                print(f"  ⚠️  所有重试失败，标记为错误")
                # 标记为错误状态
                for repo_id in repo_ids:
                    cursor.execute("""
                        UPDATE repositories 
                        SET classification_status = 'error'
                        WHERE id = ?
                    """, (repo_id,))
                conn.commit()
            else:
                import time
                time.sleep(2)  # 等待后重试
    
    conn.close()
    return True

def main():
    DB_PATH = "./data/github_repos_single_table.db"
    
    print("🚀 启动 OpenAI 兼容API批处理器")
    print("=" * 50)
    
    # 检查数据库
    if not os.path.exists(DB_PATH):
        print(f"❌ 数据库不存在: {DB_PATH}")
        return
    
    batch_count = 0
    while True:
        success = process_batch(DB_PATH, batch_size=15)
        
        if not success:
            break
        
        batch_count += 1
        print(f"--- 已完成第 {batch_count} 轮批处理 ---")
        
        # 每5批暂停一下
        if batch_count % 5 == 0:
            import time
            time.sleep(1)
    
    print(f"🎉 处理完成！共处理 {batch_count} 个批次")

if __name__ == "__main__":
    main()
'''
    
    # 保存修复版代码
    output_path = "scripts/batch_processor_openai_fixed.py"
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(fixed_code)
    
    print(f"\n🔧 已创建修复版代码: {output_path}")
    print("主要改进:")
    print("  1. ✅ 自动选择最佳文本字段 (readme_clean > readme > description)")
    print("  2. ✅ 添加重试机制 (最多3次)")
    print("  3. ✅ 改进状态管理 (processing -> completed/error)")
    print("  4. ✅ 增强提示词，要求更具体的分类")
    print("  5. ✅ 验证AI响应格式和数据完整性")
    print("  6. ✅ 更好的错误处理和恢复")

def main():
    """主函数"""
    print("🔄 新代码兼容性分析")
    print("=" * 60)
    
    db_path = "./data/github_repos_single_table.db"
    
    if not os.path.exists(db_path):
        print(f"❌ 数据库不存在: {db_path}")
        return
    
    # 运行兼容性检查
    is_compatible = check_database_compatibility(db_path)
    
    if not is_compatible:
        print(f"\n⚠️  兼容性问题检测到，建议使用修复版代码")
        create_fixed_version()
    else:
        print(f"\n✅ 代码与数据库兼容，可以直接运行")
        
        # 提供运行建议
        print(f"\n🚀 运行建议:")
        print(f"  1. 设置环境变量:")
        print(f'     export OPENAILIKED_API_KEY="your_api_key"')
        print(f'     export OPENAILIKED_BASE_URL="https://api.deepseek.com"')
        print(f'     export OPENAILIKED_MODEL="deepseek-chat"  # 可选')
        print(f"  2. 运行原始代码:")
        print(f"     python your_script.py")
        print(f"  3. 或运行修复版代码:")
        print(f"     python scripts/batch_processor_openai_fixed.py")

if __name__ == "__main__":
    main()