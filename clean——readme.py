import json
import re
import sqlite3
from typing import Dict, List, Any, Optional, Tuple

# ====== 配置区 ======
DATABASE_FILE = "data/github_repos_single_table.db"
ENHANCED_TABLE_NAME = "repos_enhanced"

def clean_readme_for_ai(raw_readme_text: str, target_length: int = 1800) -> str:
    """
    核心清洗函数：为AI分类优化README，移除噪音，提取核心描述。
    策略：优先提取高权重章节（如介绍、功能），其次进行智能摘要。
    """
    if not raw_readme_text:
        return ""

    text = raw_readme_text
    # 1. 基础清理：移除HTML标签、Markdown图片和链接
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)
    text = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'```[\s\S]*?```', '', text)

    lines = text.split('\n')
    key_sections = {
        r'^(#+\s*)?(about|介绍|概述|description)': 10,
        r'^(#+\s*)?(features?|特性|功能)': 9,
        r'^(#+\s*)?(getting started|快速开始|usage|使用)': 8,
        r'^(#+\s*)?(installation|安装)': 7,
        r'^(#+\s*)?(examples?|示例|api)': 5,
    }
    
    extracted_sections = []
    current_section = None
    current_content = []
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line or 'shields.io' in line or 'badgen.net' in line:
            i += 1
            continue
        
        is_section_header = False
        section_weight = 0
        for pattern, weight in key_sections.items():
            if re.search(pattern, line, re.IGNORECASE):
                is_section_header = True
                section_weight = weight
                break
        
        if is_section_header:
            if current_section is not None and current_content:
                extracted_sections.append((current_section['weight'], '\n'.join(current_content[:20])))
            current_section = {'title': line, 'weight': section_weight}
            current_content = []
        elif current_section is not None and len(line) > 10:
            current_content.append(line)
        i += 1
    
    if current_section is not None and current_content:
        extracted_sections.append((current_section['weight'], '\n'.join(current_content[:20])))
    
    # 按权重排序并合并高权重内容
    extracted_sections.sort(reverse=True)
    high_priority_text = '\n\n'.join([content for _, content in extracted_sections if _ >= 5])
    
    final_text = high_priority_text if high_priority_text else '\n'.join([l for l in lines[:5] if len(l.strip()) > 20])
    
    if len(final_text) > target_length:
        final_text = final_text[:target_length] + "..."
    
    return final_text.strip()

def setup_enhanced_table(conn: sqlite3.Connection):
    """创建或更新增强表结构"""
    cursor = conn.cursor()
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS {ENHANCED_TABLE_NAME} (
        repo_id INTEGER PRIMARY KEY,
        full_name TEXT NOT NULL,
        original_description TEXT,
        readme_optimized TEXT,
        enhanced_text TEXT,
        processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (repo_id) REFERENCES repositories (id)
    )
    """)
    conn.commit()

def process_and_enhance_repos():
    """
    主处理函数：从原始表读取，清洗，存入增强表。
    返回处理统计信息。
    """
    print("启动数据增强处理...")
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    setup_enhanced_table(conn)
    cursor = conn.cursor()

    # 读取数据，按星标排序优先处理热门仓库
    cursor.execute("""
        SELECT id, full_name, description, readme_content 
        FROM repositories 
        WHERE readme_content IS NOT NULL 
        ORDER BY stargazers_count DESC
    """)
    repos = cursor.fetchall()
    
    stats = {'total': len(repos), 'processed': 0, 'with_readme': 0}
    for repo in repos:
        try:
            repo_id, full_name, description, raw_readme = repo['id'], repo['full_name'], repo['description'], repo['readme_content']
            
            # 使用统一的AI优化函数清洗README
            cleaned_readme = clean_readme_for_ai(raw_readme, target_length=2000)
            
            # 构建增强文本：结合项目描述和清洗后的README
            enhanced_parts = []
            if description:
                enhanced_parts.append(f"项目描述: {description}")
            if cleaned_readme:
                enhanced_parts.append(f"项目详情:\n{cleaned_readme}")
            enhanced_text = "\n\n".join(enhanced_parts)
            
            # 存入增强表
            cursor.execute(f"""
                INSERT OR REPLACE INTO {ENHANCED_TABLE_NAME} 
                (repo_id, full_name, original_description, readme_optimized, enhanced_text)
                VALUES (?, ?, ?, ?, ?)
            """, (repo_id, full_name, description, cleaned_readme, enhanced_text))
            
            stats['processed'] += 1
            if raw_readme:
                stats['with_readme'] += 1
                
        except Exception as e:
            print(f"处理仓库 {repo.get('full_name', 'Unknown')} 时出错: {e}")
            continue
    
    conn.commit()
    
    # 生成统计报告
    if stats['with_readme'] > 0:
        cursor.execute(f"""
            SELECT AVG(LENGTH(readme_content)) as avg_orig, 
                   AVG(LENGTH(readme_optimized)) as avg_clean 
            FROM repositories r 
            JOIN {ENHANCED_TABLE_NAME} e ON r.id = e.repo_id
        """)
        avg_stats = cursor.fetchone()
        print(f"\n处理完成。统计：共{stats['total']}个仓库，成功处理{stats['processed']}个。")
        print(f"README平均长度: {avg_stats['avg_orig']:.0f}字符 -> 清洗后: {avg_stats['avg_clean']:.0f}字符")
    
    conn.close()
    return stats

if __name__ == "__main__":
    # 用户可选择执行完整的清洗和增强流程
    process_and_enhance_repos()
    
    # 后续可在此处添加：调用AI进行批次分类的代码
    print("\n下一步建议: 数据已准备就绪，可开始AI批次分类。")