import json
import sqlite3
import logging
from datetime import datetime

# ====== 配置区 ======
INPUT_JSON_FILE = "data/repos_with_readmes.json"
DATABASE_FILE = "data/github_repos_single_table.db"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

def setup_single_table(conn):
    """创建单一宽表"""
    cursor = conn.cursor()
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS repositories (
        -- 核心ID与名称
        id INTEGER PRIMARY KEY,
        node_id TEXT,
        name TEXT NOT NULL,
        full_name TEXT UNIQUE NOT NULL,
        html_url TEXT,
        
        -- 关键描述信息
        description TEXT,
        homepage TEXT,
        
        -- 状态与类型
        fork INTEGER DEFAULT 0,
        archived INTEGER DEFAULT 0,
        disabled INTEGER DEFAULT 0,
        private INTEGER DEFAULT 0,
        visibility TEXT,
        is_template INTEGER DEFAULT 0,
        
        -- 时间戳
        created_at TEXT,
        updated_at TEXT,
        pushed_at TEXT,
        
        -- 统计信息
        size INTEGER,
        stargazers_count INTEGER DEFAULT 0,
        watchers_count INTEGER DEFAULT 0,
        forks_count INTEGER DEFAULT 0,
        open_issues_count INTEGER DEFAULT 0,
        
        -- 技术栈
        language TEXT,
        default_branch TEXT,
        
        -- 功能开关
        has_issues INTEGER DEFAULT 1,
        has_projects INTEGER DEFAULT 0,
        has_downloads INTEGER DEFAULT 0,
        has_wiki INTEGER DEFAULT 0,
        has_pages INTEGER DEFAULT 0,
        has_discussions INTEGER DEFAULT 0,
        allow_forking INTEGER DEFAULT 1,
        web_commit_signoff_required INTEGER DEFAULT 0,
        
        -- 评分与许可证
        score REAL,
        license_json TEXT,  -- 存储整个license对象
        
        -- README相关
        readme_content TEXT,
        readme_info_json TEXT,  -- 存储readme_info对象
        
        -- 嵌套对象（JSON格式存储）
        owner_json TEXT,        -- 存储整个owner对象
        topics_json TEXT,       -- 存储topics数组
        permissions_json TEXT,  -- 存储permissions对象
        
        -- 元数据
        imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # 创建常用查询索引
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_language ON repositories (language)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_stars ON repositories (stargazers_count DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_created ON repositories (created_at DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_has_readme ON repositories (readme_content IS NOT NULL)")
    
    conn.commit()
    logger.info("✅ 单表结构创建完成。")

def import_data():
    """主导入函数"""
    logger.info(f"🚀 开始导入数据，源文件: {INPUT_JSON_FILE}")
    
    # 1. 读取数据
    try:
        with open(INPUT_JSON_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        logger.error(f"❌ 读取JSON文件失败: {e}")
        return
    
    repos = data.get('repositories', [])
    total = len(repos)
    logger.info(f"📊 找到 {total} 个仓库。")
    
    if total == 0:
        logger.warning("⚠️ 没有数据，退出。")
        return
    
    # 2. 连接数据库
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    setup_single_table(conn)
    cursor = conn.cursor()
    
    # 3. 插入数据
    success_count = 0
    for i, repo in enumerate(repos, 1):
        if i % 100 == 0:
            logger.info(f"📦 处理进度: {i}/{total}")
        
        try:
            # 准备JSON字段
            owner_json = json.dumps(repo.get('owner', {}), ensure_ascii=False)
            topics_json = json.dumps(repo.get('topics', []), ensure_ascii=False)
            license_json = json.dumps(repo.get('license', {}), ensure_ascii=False)
            permissions_json = json.dumps(repo.get('permissions', {}), ensure_ascii=False)
            readme_info_json = json.dumps(repo.get('readme_info', {}), ensure_ascii=False)
            
            cursor.execute("""
            INSERT OR REPLACE INTO repositories (
                id, node_id, name, full_name, html_url, description, homepage,
                fork, archived, disabled, private, visibility, is_template,
                created_at, updated_at, pushed_at,
                size, stargazers_count, watchers_count, forks_count, open_issues_count,
                language, default_branch,
                has_issues, has_projects, has_downloads, has_wiki, has_pages, 
                has_discussions, allow_forking, web_commit_signoff_required,
                score, license_json,
                readme_content, readme_info_json,
                owner_json, topics_json, permissions_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 
                     ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                repo['id'],
                repo.get('node_id'),
                repo['name'],
                repo['full_name'],
                repo.get('html_url'),
                repo.get('description'),
                repo.get('homepage'),
                repo.get('fork', False),
                repo.get('archived', False),
                repo.get('disabled', False),
                repo.get('private', False),
                repo.get('visibility'),
                repo.get('is_template', False),
                repo.get('created_at'),
                repo.get('updated_at'),
                repo.get('pushed_at'),
                repo.get('size'),
                repo.get('stargazers_count'),
                repo.get('watchers_count'),
                repo.get('forks_count'),
                repo.get('open_issues_count'),
                repo.get('language'),
                repo.get('default_branch'),
                repo.get('has_issues', True),
                repo.get('has_projects', False),
                repo.get('has_downloads', True),
                repo.get('has_wiki', False),
                repo.get('has_pages', False),
                repo.get('has_discussions', False),
                repo.get('allow_forking', True),
                repo.get('web_commit_signoff_required', False),
                repo.get('score'),
                license_json,
                repo.get('readme_content'),
                readme_info_json,
                owner_json,
                topics_json,
                permissions_json
            ))
            success_count += 1
            
        except KeyError as e:
            logger.error(f"跳过 {repo.get('full_name', '未知')}: 缺少字段 {e}")
        except sqlite3.Error as e:
            logger.error(f"数据库错误 {repo.get('full_name', '未知')}: {e}")
            conn.rollback()
    
    # 4. 提交并生成报告
    conn.commit()
    
    cursor.execute("SELECT COUNT(*) as cnt FROM repositories")
    db_count = cursor.fetchone()['cnt']
    
    cursor.execute("""
        SELECT language, COUNT(*) as cnt 
        FROM repositories 
        WHERE language IS NOT NULL 
        GROUP BY language 
        ORDER BY cnt DESC 
        LIMIT 5
    """)
    top_langs = cursor.fetchall()
    
    conn.close()
    
    # 打印报告
    logger.info("="*60)
    logger.info("🏁 导入完成!")
    logger.info(f"   尝试导入: {total}")
    logger.info(f"   成功入库: {success_count}")
    logger.info(f"   数据库现存: {db_count}")
    logger.info("   语言分布 Top 5:")
    for row in top_langs:
        logger.info(f"     - {row['language']}: {row['cnt']}")
    logger.info(f"   数据库文件: {DATABASE_FILE}")
    logger.info("="*60)

if __name__ == "__main__":
    import_data()