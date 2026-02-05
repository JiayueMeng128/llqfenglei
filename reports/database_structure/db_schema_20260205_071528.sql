CREATE INDEX idx_created ON repositories (created_at DESC);
CREATE INDEX idx_has_readme ON repositories (readme_content IS NOT NULL);
CREATE INDEX idx_language ON repositories (language);
CREATE INDEX idx_stars ON repositories (stargazers_count DESC);
CREATE TABLE repos_enhanced (
        repo_id INTEGER PRIMARY KEY,
        full_name TEXT NOT NULL,
        original_description TEXT,
        readme_optimized TEXT,
        enhanced_text TEXT,
        processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (repo_id) REFERENCES repositories (id)
    );
CREATE TABLE repositories (
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
    , readme_cleaned TEXT, processing_notes TEXT, processed_at TIMESTAMP, enhanced_text TEXT);