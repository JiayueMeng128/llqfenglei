#!/usr/bin/env python3
"""
修正版 - 一键修复并运行分类处理器
"""

import os
import sys
import sqlite3

# 设置API配置
os.environ["OPENAILIKED_API_KEY"] = "sk-KeaqnqGEo8nsj7jUrA1lk26XkVuZfjWCxyLUpYkgPLsUVwli"
os.environ["OPENAILIKED_BASE_URL"] = "https://edge.tb.api.mkeai.com/v1"
os.environ["OPENAILIKED_MODEL"] = "deepseek-v3.2"

print("🌐 配置已设置:")
print(f"  API: {os.environ['OPENAILIKED_API_KEY'][:15]}...")
print(f"  端点: {os.environ['OPENAILIKED_BASE_URL']}")
print(f"  模型: {os.environ['OPENAILIKED_MODEL']}")

def fix_database():
    """修复数据库结构"""
    print("\n🔧 检查数据库...")
    db_path = "./data/github_repos_single_table.db"
    
    if not os.path.exists(db_path):
        print(f"❌ 数据库不存在: {db_path}")
        return False
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 检查并添加serial_number字段
    try:
        cursor.execute("ALTER TABLE repositories ADD COLUMN serial_number TEXT")
        print("✅ 添加serial_number字段")
    except sqlite3.OperationalError:
        print("✅ serial_number字段已存在")
    
    # 赋号
    print("🔢 正在为仓库分配序列号...")
    cursor.execute("SELECT id FROM repositories ORDER BY stargazers_count DESC")
    rows = cursor.fetchall()
    
    for idx, (repo_id,) in enumerate(rows, 1):
        sn = f"SN-{idx:04d}"
        cursor.execute("UPDATE repositories SET serial_number = ? WHERE id = ?", (sn, repo_id))
    
    conn.commit()
    conn.close()
    print(f"✅ 为 {len(rows)} 个仓库分配了序列号")
    return True

def create_simple_processor():
    """创建简单的处理器脚本"""
    print("\n🛠️ 创建处理器脚本...")
    
    script_content = '''#!/usr/bin/env python3
"""
简单版分类处理器
"""

import sqlite3
import json
import os
import uuid
from openai import OpenAI
from datetime import datetime

# 配置
API_KEY = os.getenv("OPENAILIKED_API_KEY")
BASE_URL = os.getenv("OPENAILIKED_BASE_URL")
MODEL_NAME = os.getenv("OPENAILIKED_MODEL", "deepseek-v3.2")

print(f"🚀 启动分类处理器")
print(f"使用模型: {MODEL_NAME}")

# 创建OpenAI客户端
client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

def create_tables():
    """创建必要的表"""
    conn = sqlite3.connect("./data/github_repos_single_table.db")
    cursor = conn.cursor()
    
    # 创建日志表
    cursor.execute('''CREATE TABLE IF NOT EXISTS ai_raw_logs (
        batch_id TEXT PRIMARY KEY,
        model_name TEXT,
        repo_sn_list TEXT,
        raw_response TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    conn.commit()
    conn.close()

def get_next_batch(batch_size=15):
    """获取下一批数据"""
    conn = sqlite3.connect("./data/github_repos_single_table.db")
    cursor = conn.cursor()
    
    # 检查可用的文本字段
    cursor.execute("PRAGMA table_info(repositories)")
    columns = [row[1] for row in cursor.fetchall()]
    
    text_field = None
    for field in ["enhanced_text", "readme", "description"]:
        if field in columns:
            text_field = field
            break
    
    if not text_field:
        print("❌ 没有可用的文本字段")
        conn.close()
        return None
    
    # 获取数据
    cursor.execute(f"""
        SELECT id, full_name, {text_field}, serial_number 
        FROM repositories 
        WHERE (classification_status IS NULL OR classification_status != 'completed')
          AND {text_field} IS NOT NULL
          AND LENGTH({text_field}) > 50
          AND serial_number IS NOT NULL
        ORDER BY serial_number
        LIMIT ?
    """, (batch_size,))
    
    rows = cursor.fetchall()
    
    if rows:
        # 标记为处理中
        repo_ids = [r[0] for r in rows]
        placeholders = ','.join(['?'] * len(repo_ids))
        cursor.execute(f"""
            UPDATE repositories 
            SET classification_status = 'processing'
            WHERE id IN ({placeholders})
        """, repo_ids)
        conn.commit()
    
    conn.close()
    return rows, text_field

def call_ai(prompt):
    """调用AI API"""
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=2000,
            response_format={"type": "json_object"}
        )
        return response
    except Exception as e:
        print(f"❌ AI调用失败: {e}")
        return None

def save_results(rows, mapping, raw_response):
    """保存结果"""
    conn = sqlite3.connect("./data/github_repos_single_table.db")
    cursor = conn.cursor()
    
    # 保存原始响应
    repo_sns = [row[3] for row in rows]
    batch_id = str(uuid.uuid4())
    cursor.execute("""
        INSERT INTO ai_raw_logs (batch_id, model_name, repo_sn_list, raw_response)
        VALUES (?, ?, ?, ?)
    """, (batch_id, MODEL_NAME, ",".join(repo_sns), raw_response))
    
    # 更新主表
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for row in rows:
        repo_id, full_name, text_content, sn = row
        category = mapping.get(sn, "未分类")
        
        cursor.execute("""
            UPDATE repositories 
            SET category_l1 = ?, 
                classification_status = 'completed', 
                category_l1_processed_at = ?,
                category_l1_reason = 'AI分类'
            WHERE id = ?
        """, (category, timestamp, repo_id))
    
    conn.commit()
    conn.close()
    return len(rows)

def show_progress():
    """显示进度"""
    conn = sqlite3.connect("./data/github_repos_single_table.db")
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM repositories")
    total = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM repositories WHERE classification_status = 'completed'")
    completed = cursor.fetchone()[0]
    
    conn.close()
    
    if total > 0:
        print(f"📊 进度: {completed}/{total} ({completed/total*100:.1f}%)")

def main():
    """主函数"""
    print("=" * 50)
    
    # 创建表
    create_tables()
    
    batch_count = 0
    total_processed = 0
    
    try:
        while True:
            # 获取一批数据
            result = get_next_batch(batch_size=10)
            if not result:
                print("✅ 所有仓库已处理完成！")
                break
            
            rows, text_field = result
            batch_count += 1
            
            print(f"\n📦 批次 #{batch_count}: {len(rows)} 个项目")
            
            # 构建提示词
            items = []
            for row in rows:
                _, full_name, text, sn = row
                preview = text[:300] + "..." if len(text) > 300 else text
                items.append(f"[{sn}] {full_name}: {preview}")
            
            prompt = f"""请分析以下 {len(rows)} 个浏览器相关项目，并为它们创建分类：

项目列表：
{chr(10).join(items)}

请返回JSON格式：
{{
  "categories": ["分类1", "分类2", "分类3"],
  "mapping": {{"SN-0001": "分类1", "SN-0002": "分类2"}}
}}

注意：
1. 使用中文分类名称
2. 每个项目必须有分类
3. 分类要具体（如"浏览器自动化工具"，不要只是"工具"）"""
            
            print("🤖 调用AI进行分类...")
            response = call_ai(prompt)
            
            if not response:
                print("⚠️  跳过此批次")
                continue
            
            # 解析结果
            raw_json = response.choices[0].message.content
            try:
                result_data = json.loads(raw_json)
                mapping = result_data.get("mapping", {})
                
                # 确保所有SN都有分类
                for row in rows:
                    sn = row[3]
                    if sn not in mapping:
                        mapping[sn] = "其他"
                
                # 保存结果
                processed = save_results(rows, mapping, raw_json)
                total_processed += processed
                
                print(f"✅ 处理完成")
                print(f"   生成了 {len(result_data.get('categories', []))} 个分类")
                
                # 显示分布
                from collections import Counter
                dist = Counter(mapping.values())
                print(f"   分类分布: {dict(dist)}")
                
            except json.JSONDecodeError as e:
                print(f"❌ JSON解析失败: {e}")
                print(f"AI响应: {raw_json[:200]}...")
            
            # 每批显示进度
            if batch_count % 3 == 0:
                show_progress()
            
            # 短暂延迟
            import time
            time.sleep(1)
    
    except KeyboardInterrupt:
        print(f"\n⏸️  用户中断，已处理 {batch_count} 个批次")
    
    print(f"\n🎉 处理统计:")
    print(f"   总批次: {batch_count}")
    print(f"   总项目: {total_processed}")
    show_progress()

if __name__ == "__main__":
    main()
'''
    
    # 保存脚本
    with open("scripts/simple_classifier.py", "w", encoding="utf-8") as f:
        f.write(script_content)
    
    print("✅ 处理器脚本已创建: scripts/simple_classifier.py")
    return "scripts/simple_classifier.py"

def show_current_status():
    """显示当前状态"""
    print("\n📊 当前数据库状态:")
    
    db_path = "./data/github_repos_single_table.db"
    if not os.path.exists(db_path):
        print("❌ 数据库不存在")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 总仓库数
        cursor.execute("SELECT COUNT(*) FROM repositories")
        total = cursor.fetchone()[0]
        
        # 分类状态
        cursor.execute("""
            SELECT 
                COALESCE(classification_status, '未处理') as status,
                COUNT(*) as count
            FROM repositories 
            GROUP BY classification_status
        """)
        
        print(f"总仓库数: {total}")
        print("\n分类状态分布:")
        for status, count in cursor.fetchall():
            percentage = count / total * 100
            print(f"  {status}: {count} ({percentage:.1f}%)")
        
        # 已分类的仓库
        cursor.execute("SELECT category_l1, COUNT(*) FROM repositories WHERE classification_status = 'completed' GROUP BY category_l1")
        categories = cursor.fetchall()
        
        if categories:
            print("\n📈 分类分布:")
            for category, count in categories:
                if category:
                    print(f"  {category}: {count}")
        
    except Exception as e:
        print(f"❌ 查询失败: {e}")
    
    conn.close()

def main():
    """主函数"""
    print("=" * 60)
    print("GitHub仓库分类处理器")
    print("=" * 60)
    
    # 1. 修复数据库
    if not fix_database():
        return
    
    # 2. 显示当前状态
    show_current_status()
    
    # 3. 创建处理器
    processor_script = create_simple_processor()
    
    print("\n" + "=" * 60)
    print("🚀 准备就绪！")
    print("\n请选择:")
    print("1. 立即开始分类处理")
    print("2. 先运行一个测试批次（5个项目）")
    print("3. 只显示状态，不处理")
    
    choice = input("\n请输入选择 (1/2/3): ").strip()
    
    if choice == "1":
        print("\n开始完整处理...")
        import subprocess
        subprocess.run([sys.executable, processor_script])
        
    elif choice == "2":
        print("\n运行测试批次...")
        # 修改脚本，只处理5个
        with open(processor_script, "r", encoding="utf-8") as f:
            content = f.read()
        
        test_content = content.replace("batch_size=10", "batch_size=5")
        test_script = "scripts/test_classifier.py"
        with open(test_script, "w", encoding="utf-8") as f:
            f.write(test_content)
        
        import subprocess
        subprocess.run([sys.executable, test_script])
        
    else:
        print("\n当前状态:")
        show_current_status()

if __name__ == "__main__":
    main()