import json
import sqlite3
import logging
from datetime import datetime
from typing import Dict, List, Any

# ====== 配置区 ======
INPUT_JSON_FILE = "data/repos_with_readmes.json"
DATABASE_FILE = "data/github_browser_repos.db"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def setup_database_schema(conn: sqlite3.Connection):
    """创建数据库表结构"""
    cursor = conn.cursor()
    
    # 1. 所有者表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS owners (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        login TEXT UNIQUE NOT NULL,
        github_id INTEGER NOT NULL,
        avatar_url TEXT,
        type TEXT,
        site_admin INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # 2. 仓库表 - 核心表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS repositories (
        id INTEGER PRIMARY KEY,
        node_id TEXT,
        name TEXT NOT NULL,
        full_name TEXT UNIQUE NOT NULL,
        owner_id INTEGER,
        html_url TEXT,
        description TEXT,
        fork INTEGER DEFAULT 0,
        created_at TEXT,
        updated_at TEXT,
        pushed_at TEXT,
        homepage TEXT,
        size INTEGER,
        stargazers_count INTEGER DEFAULT 0,
        watchers_count INTEGER DEFAULT 0,
        language TEXT,
        has_issues INTEGER DEFAULT 1,
        has_projects INTEGER DEFAULT 0,
        has_downloads INTEGER DEFAULT 0,
        has_wiki INTEGER DEFAULT 0,
        has_pages INTEGER DEFAULT 0,
        has_discussions INTEGER DEFAULT 0,
        forks_count INTEGER DEFAULT 0,
        open_issues_count INTEGER DEFAULT 0,
        archived INTEGER DEFAULT 0,
        disabled INTEGER DEFAULT 0,
        allow_forking INTEGER DEFAULT 1,
        is_template INTEGER DEFAULT 0,
        web_commit_signoff_required INTEGER DEFAULT 0,
        visibility TEXT,
        default_branch TEXT,
        score REAL,
        license_key TEXT,
        license_name TEXT,
        license_spdx_id TEXT,
        readme_content TEXT,
        readme_size INTEGER,
        readme_html_url TEXT,
        FOREIGN KEY (owner_id) REFERENCES owners (id)
    )
    """)
    
    # 3. 仓库主题表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS repository_topics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        repo_id INTEGER NOT NULL,
        topic TEXT NOT NULL,
        FOREIGN KEY (repo_id) REFERENCES repositories (id),
        UNIQUE(repo_id, topic)
    )
    """)
    
    # 4. 权限表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS permissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        repo_id INTEGER UNIQUE NOT NULL,
        admin INTEGER DEFAULT 0,
        maintain INTEGER DEFAULT 0,
        push INTEGER DEFAULT 0,
        triage INTEGER DEFAULT 0,
        pull INTEGER DEFAULT 1,
        FOREIGN KEY (repo_id) REFERENCES repositories (id)
    )
    """)
    
    # 创建索引
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_repos_language ON repositories (language)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_repos_stars ON repositories (stargazers_count DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_repos_owner ON repositories (owner_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_topics_repo ON repository_topics (repo_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_topics_topic ON repository_topics (topic)")
    
    conn.commit()
    logger.info("数据库表结构创建完成。")

def import_json_to_database(json_file: str, db_file: str):
    """主函数：读取JSON并导入数据库"""
    logger.info(f"开始导入数据，源文件: {json_file}")
    
    # 1. 读取JSON数据
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        logger.error(f"读取JSON文件失败: {e}")
        return
    
    repos = data.get('repositories', [])
    total_repos = len(repos)
    logger.info(f"从JSON中读取到 {total_repos} 个仓库。")
    
    if total_repos == 0:
        logger.warning("没有找到仓库数据，退出。")
        return
    
    # 2. 连接数据库
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 3. 设置数据库架构
    setup_database_schema(conn)
    
    # 4. 遍历并插入数据
    owner_cache = {}
    imported_count = 0
    errors = []
    
    for i, repo in enumerate(repos, 1):
        if i % 100 == 0:
            logger.info(f"处理进度: {i}/{total_repos}")
        
        try:
            # --- 插入或获取所有者信息 ---
            owner = repo.get('owner', {})
            owner_login = owner.get('login')
            
            if owner_login and owner_login not in owner_cache:
                cursor.execute("""
                INSERT OR IGNORE INTO owners (login, github_id, avatar_url, type, site_admin)
                VALUES (?, ?, ?, ?, ?)
                """, (
                    owner_login,
                    owner.get('id'),
                    owner.get('avatar_url'),
                    owner.get('type'),
                    owner.get('site_admin', False)
                ))
                conn.commit()
                
                cursor.execute("SELECT id FROM owners WHERE login = ?", (owner_login,))
                result = cursor.fetchone()
                owner_cache[owner_login] = result['id'] if result else None
            
            owner_id = owner_cache.get(owner_login)
            
            # --- 处理许可证信息（修复了NoneType问题）---
            license_info = repo.get('license')
            license_key = license_name = license_spdx_id = None
            if isinstance(license_info, dict):
                license_key = license_info.get('key')
                license_name = license_info.get('name')
                license_spdx_id = license_info.get('spdx_id')
            
            # --- 插入仓库主信息 ---
            cursor.execute("""
            INSERT OR REPLACE INTO repositories (
                id, node_id, name, full_name, owner_id, html_url, description,
                fork, created_at, updated_at, pushed_at, homepage, size,
                stargazers_count, watchers_count, language,
                has_issues, has_projects, has_downloads, has_wiki, has_pages,
                has_discussions, forks_count, open_issues_count,
                archived, disabled, allow_forking, is_template,
                web_commit_signoff_required, visibility, default_branch, score,
                license_key, license_name, license_spdx_id,
                readme_content, readme_size, readme_html_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 
                     ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                repo['id'],
                repo.get('node_id'),
                repo['name'],
                repo['full_name'],
                owner_id,
                repo.get('html_url'),
                repo.get('description'),
                repo.get('fork', False),
                repo.get('created_at'),
                repo.get('updated_at'),
                repo.get('pushed_at'),
                repo.get('homepage'),
                repo.get('size'),
                repo.get('stargazers_count'),
                repo.get('watchers_count'),
                repo.get('language'),
                repo.get('has_issues', True),
                repo.get('has_projects', False),
                repo.get('has_downloads', True),
                repo.get('has_wiki', False),
                repo.get('has_pages', False),
                repo.get('has_discussions', False),
                repo.get('forks_count', 0),
                repo.get('open_issues_count', 0),
                repo.get('archived', False),
                repo.get('disabled', False),
                repo.get('allow_forking', True),
                repo.get('is_template', False),
                repo.get('web_commit_signoff_required', False),
                repo.get('visibility'),
                repo.get('default_branch'),
                repo.get('score'),
                license_key,  # 可能是None
                license_name, # 可能是None
                license_spdx_id, # 可能是None
                repo.get('readme_content'),
                repo.get('readme_info', {}).get('size'),
                repo.get('readme_info', {}).get('html_url')
            ))
            
            repo_id = repo['id']
            
            # --- 插入主题标签 ---
            topics = repo.get('topics', [])
            if topics:
                for topic in topics:
                    cursor.execute("""
                    INSERT OR IGNORE INTO repository_topics (repo_id, topic)
                    VALUES (?, ?)
                    """, (repo_id, topic))
            
            # --- 插入权限信息 ---
            perms = repo.get('permissions', {})
            if perms:
                cursor.execute("""
                INSERT OR REPLACE INTO permissions (repo_id, admin, maintain, push, triage, pull)
                VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    repo_id,
                    perms.get('admin', False),
                    perms.get('maintain', False),
                    perms.get('push', False),
                    perms.get('triage', False),
                    perms.get('pull', True)
                ))
            
            imported_count += 1
            
        except KeyError as e:
            error_msg = f"仓库 {repo.get('full_name', 'Unknown')} 缺少关键字段: {e}"
            logger.error(error_msg)
            errors.append(error_msg)
            continue
        except sqlite3.Error as e:
            error_msg = f"插入仓库 {repo.get('full_name', 'Unknown')} 时数据库错误: {e}"
            logger.error(error_msg)
            errors.append(error_msg)
            conn.rollback()
            continue
    
    # 5. 提交并关闭连接
    conn.commit()
    
    # 生成统计信息
    cursor.execute("SELECT COUNT(*) as count FROM repositories")
    db_count = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(DISTINCT topic) as topics FROM repository_topics")
    topics_count = cursor.fetchone()['topics']
    
    cursor.execute("SELECT language, COUNT(*) as count FROM repositories WHERE language IS NOT NULL GROUP BY language ORDER BY count DESC LIMIT 5")
    top_languages = cursor.fetchall()
    
    conn.close()
    
    # 6. 打印导入报告
    print("\n" + "="*60)
    print("✅ 数据导入完成!")
    print("="*60)
    print(f"   尝试导入: {total_repos} 个仓库")
    print(f"   成功入库: {imported_count} 个仓库")
    print(f"   数据库现存: {db_count} 个仓库")
    print(f"   唯一主题标签: {topics_count} 个")
    print(f"\n   最常用编程语言:")
    for lang in top_languages:
        print(f"      - {lang['language']}: {lang['count']} 个")
    
    if errors:
        print(f"\n   ⚠️  遇到 {len(errors)} 个错误 (详见日志)")
        with open("data/import_errors.log", "w") as f:
            for err in errors:
                f.write(err + "\n")
        print(f"   错误日志已保存至: data/import_errors.log")
    
    print(f"\n   数据库文件: {db_file}")
    print("="*60)

if __name__ == "__main__":
    import_json_to_database(INPUT_JSON_FILE, DATABASE_FILE)