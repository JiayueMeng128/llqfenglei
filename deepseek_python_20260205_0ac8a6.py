import re
import sqlite3
import time

DATABASE_FILE = "data/github_repos_single_table.db"

def add_enhanced_text_column():
    """确保原表存在 enhanced_text 字段"""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE repositories ADD COLUMN enhanced_text TEXT")
        print("✓ 已添加 enhanced_text 字段")
    except sqlite3.OperationalError:
        print("- enhanced_text 字段已存在")
    conn.commit()
    conn.close()

def create_enhanced_text(description: str, cleaned_readme: str) -> str:
    """
    智能合并 description 和清洗后的 readme。
    生成最适合 AI 分析的连贯项目描述。
    """
    parts = []
    
    # 1. 优先使用 description（如果存在且有意义）
    if description and len(description.strip()) > 10:
        clean_desc = description.strip()
        # 确保描述以句号结尾，增强连贯性
        if not clean_desc.endswith(('.', '!', '?')):
            clean_desc += '.'
        parts.append(clean_desc)
    
    # 2. 添加清洗后的 README（如果存在）
    if cleaned_readme and len(cleaned_readme.strip()) > 50:
        # 智能去重：如果README开头与description高度相似，则跳过开头部分
        readme_to_add = cleaned_readme.strip()
        if parts and len(parts[0]) > 20:
            # 检查前100个字符的相似度
            desc_prefix = parts[0][:50].lower()
            readme_prefix = readme_to_add[:100].lower()
            if desc_prefix in readme_prefix:
                # 找到第一个换行符之后的内容开始添加
                first_newline = readme_to_add.find('\n')
                if first_newline > 0:
                    readme_to_add = readme_to_add[first_newline:].strip()
        
        parts.append(readme_to_add)
    
    # 3. 合并并控制总长度
    enhanced = "\n\n".join(parts)
    
    # 长度控制（针对AI上下文窗口优化）
    if len(enhanced) > 3000:
        # 优先保留 description，截断README部分
        if parts and len(parts[0]) < 500:
            # description部分较短，尝试保留README的开头章节
            allowed_readme_length = 3000 - len(parts[0]) - 100  # 留出缓冲
            if len(parts[1]) > allowed_readme_length:
                # 在段落边界处截断
                truncate_point = parts[1].rfind('\n\n', 0, allowed_readme_length)
                if truncate_point == -1 or truncate_point < allowed_readme_length * 0.5:
                    truncate_point = parts[1].rfind('.', 0, allowed_readme_length)
                if truncate_point == -1 or truncate_point < allowed_readme_length * 0.5:
                    truncate_point = allowed_readme_length
                
                parts[1] = parts[1][:truncate_point] + "..."
        
        enhanced = "\n\n".join(parts)
        
        # 最终硬截断（在句子边界）
        if len(enhanced) > 3200:
            last_period = enhanced.rfind('.', 0, 3000)
            last_newline = enhanced.rfind('\n\n', 0, 3000)
            trunc_point = max(last_period, last_newline)
            if trunc_point > 2000:
                enhanced = enhanced[:trunc_point + 1]
            else:
                enhanced = enhanced[:3000] + "..."
    
    return enhanced.strip()

def update_enhanced_text_for_all():
    """
    为所有记录生成 enhanced_text。
    此函数应在 README 清洗完成后运行。
    """
    print("\n" + "="*60)
    print("生成增强文本 (合并 Description 与 README)")
    print("="*60)
    
    add_enhanced_text_column()
    
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 获取需要处理的记录
    cursor.execute("""
        SELECT id, full_name, description, readme_cleaned, enhanced_text
        FROM repositories
        WHERE readme_cleaned IS NOT NULL
        ORDER BY id
    """)
    
    records = cursor.fetchall()
    print(f"找到 {len(records)} 条已清洗的README记录")
    
    stats = {'total': len(records), 'updated': 0, 'skipped': 0}
    
    for i, record in enumerate(records, 1):
        # 如果已有enhanced_text且不为空，可跳过（根据需求调整）
        if record['enhanced_text'] and len(record['enhanced_text']) > 10:
            stats['skipped'] += 1
            continue
        
        enhanced = create_enhanced_text(
            record['description'], 
            record['readme_cleaned']
        )
        
        cursor.execute("""
            UPDATE repositories 
            SET enhanced_text = ?
            WHERE id = ?
        """, (enhanced, record['id']))
        
        stats['updated'] += 1
        
        if i % 100 == 0:
            print(f"  进度: {i}/{len(records)}")
    
    conn.commit()
    
    # 统计enhanced_text的长度分布
    cursor.execute("""
        SELECT 
            COUNT(*) as total,
            AVG(LENGTH(enhanced_text)) as avg_len,
            MIN(LENGTH(enhanced_text)) as min_len,
            MAX(LENGTH(enhanced_text)) as max_len,
            SUM(CASE WHEN enhanced_text IS NULL OR LENGTH(enhanced_text) = 0 THEN 1 ELSE 0 END) as empty_count
        FROM repositories
    """)
    
    len_stats = cursor.fetchone()
    conn.close()
    
    print("\n📊 增强文本生成完成:")
    print(f"   总记录数: {stats['total']}")
    print(f"   本次更新: {stats['updated']}")
    print(f"   跳过已存在: {stats['skipped']}")
    print(f"   平均长度: {len_stats['avg_len']:.0f} 字符")
    print(f"   长度范围: {len_stats['min_len']} - {len_stats['max_len']} 字符")
    print(f"   空值记录: {len_stats['empty_count']}")
    
    return stats

def show_enhanced_samples(limit: int = 3):
    """展示增强文本的样本"""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            full_name,
            description,
            LENGTH(readme_cleaned) as readme_len,
            LENGTH(enhanced_text) as enhanced_len,
            substr(enhanced_text, 1, 300) as preview
        FROM repositories
        WHERE enhanced_text IS NOT NULL AND LENGTH(enhanced_text) > 0
        ORDER BY RANDOM()
        LIMIT ?
    """, (limit,))
    
    samples = cursor.fetchall()
    conn.close()
    
    if samples:
        print(f"\n🔍 增强文本样本（随机{len(samples)}个）:")
        print("-" * 70)
        for i, (name, desc, r_len, e_len, preview) in enumerate(samples, 1):
            desc_preview = desc[:80] + "..." if desc and len(desc) > 80 else (desc or "无描述")
            print(f"{i}. {name}")
            print(f"   原描述: {desc_preview}")
            print(f"   清洗后README长度: {r_len} 字符")
            print(f"   增强文本长度: {e_len} 字符")
            print(f"   增强文本预览: {preview}...")
            print()

# ====== 整合到主流程 ======
# 如果您希望一次性完成清洗和合并，可以在原 process_all_repos_in_place 函数后直接调用：
def complete_processing_pipeline():
    """
    完整的处理流程：清洗README + 生成增强文本
    """
    # 1. 首先运行原有的README清洗（假设您已有的函数）
    # process_all_repos_in_place()
    
    # 2. 然后生成增强文本
    update_enhanced_text_for_all()
    
    # 3. 展示样本
    show_enhanced_samples(3)
    
    print("\n✅ 流程完成！enhanced_text 字段已包含合并后的项目描述。")

if __name__ == "__main__":
    # 直接运行生成增强文本
    update_enhanced_text_for_all()
    show_enhanced_samples(3)
    
    # 提供查询示例
    print("\n💡 增强文本查询示例:")
    print("""
-- 1. 查看增强文本的长度分布
SELECT 
    CASE 
        WHEN LENGTH(enhanced_text) < 100 THEN '极短(<100)'
        WHEN LENGTH(enhanced_text) < 500 THEN '短(100-500)'
        WHEN LENGTH(enhanced_text) < 1500 THEN '中(500-1500)'
        WHEN LENGTH(enhanced_text) < 3000 THEN '长(1500-3000)'
        ELSE '极长(>3000)'
    END as length_range,
    COUNT(*) as count
FROM repositories
WHERE enhanced_text IS NOT NULL
GROUP BY length_range
ORDER BY MIN(LENGTH(enhanced_text));

-- 2. 查找同时拥有description和README的优质样本
SELECT full_name, description, enhanced_text
FROM repositories
WHERE description IS NOT NULL 
  AND LENGTH(description) > 20
  AND LENGTH(enhanced_text) > 200
ORDER BY stargazers_count DESC
LIMIT 5;

-- 3. 直接用于AI分析的最佳候选
SELECT id, full_name, enhanced_text
FROM repositories
WHERE enhanced_text IS NOT NULL 
  AND LENGTH(enhanced_text) BETWEEN 300 AND 2500
ORDER BY RANDOM()
LIMIT 10;
    """)