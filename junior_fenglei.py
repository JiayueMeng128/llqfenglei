#!/usr/bin/env python3
"""
适配版L1分类处理器
针对 github_repos_single_table.db 数据库结构
"""

import sqlite3
import json
import os
import time
import requests
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
import hashlib

# --- 配置 ---
class Config:
    DB_PATH = "./data/github_repos_single_table.db"
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    
    # 批次配置
    BATCH_SIZE = 15
    MAX_RETRIES = 3
    RETRY_DELAY = 5
    
    # 模型策略
    MODEL_CONFIG = {
        "primary": {
            "name": "deepseek",
            "endpoint": "https://api.deepseek.com/v1/chat/completions",
            "model": "deepseek-chat"
        },
        "fallback": {
            "name": "openai",
            "endpoint": "https://api.openai.com/v1/chat/completions",
            "model": "gpt-3.5-turbo"
        }
    }
    
    # 日志
    LOG_DIR = "./logs"
    os.makedirs(LOG_DIR, exist_ok=True)

# --- 日志设置 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(Config.LOG_DIR, "batch_processor.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- 数据库适配器 ---
class DatabaseAdapter:
    """适配你的数据库结构"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
    
    def get_next_batch(self, batch_size: int = 15) -> List[Dict]:
        """获取下一批待处理仓库"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # 查询待处理的仓库，按序列号排序
            cursor.execute('''
                SELECT 
                    id,
                    serial_number,
                    full_name,
                    description,
                    language,
                    stargazers_count as stars,
                    readme
                FROM repositories 
                WHERE (classification_status IS NULL OR classification_status = 'pending')
                  AND readme IS NOT NULL
                  AND LENGTH(readme) > 100
                ORDER BY serial_number
                LIMIT ?
            ''', (batch_size,))
            
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def update_classification_result(self, repo_id: int, result: Dict):
        """更新分类结果"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE repositories 
                SET category_l1 = ?,
                    category_l1_reason = ?,
                    category_l1_model = ?,
                    category_l1_processed_at = ?,
                    ai_raw_response = ?,
                    classification_status = 'completed',
                    readme_clean = ?
                WHERE id = ?
            ''', (
                result.get('category'),
                result.get('reason'),
                result.get('model_used'),
                datetime.now(),
                json.dumps(result.get('raw_response', {}), ensure_ascii=False),
                result.get('readme_clean', ''),
                repo_id
            ))
            
            conn.commit()
    
    def create_batch_record(self, repo_ids: List[int], model: str) -> str:
        """创建批次记录（返回批次ID）"""
        batch_id = hashlib.md5(
            f"{'_'.join(map(str, repo_ids))}_{datetime.now().timestamp()}".encode()
        ).hexdigest()[:8]
        
        # 可以在数据库中记录批次信息，这里简单返回
        logger.info(f"创建批次 {batch_id}: {len(repo_ids)} 个仓库")
        return batch_id
    
    def get_progress_stats(self) -> Dict:
        """获取处理进度统计"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM repositories")
            total = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM repositories WHERE classification_status = 'completed'")
            completed = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM repositories WHERE readme IS NOT NULL")
            with_readme = cursor.fetchone()[0]
            
            cursor.execute("SELECT category_l1, COUNT(*) FROM repositories WHERE classification_status = 'completed' GROUP BY category_l1")
            categories = cursor.fetchall()
            
            return {
                'total': total,
                'completed': completed,
                'with_readme': with_readme,
                'categories': dict(categories) if categories else {}
            }

# --- AI模型调用器 ---
class AIModelCaller:
    """AI模型调用器"""
    
    def __init__(self):
        self.api_keys = {
            'deepseek': Config.DEEPSEEK_API_KEY,
            'openai': Config.OPENAI_API_KEY
        }
    
    def call_model(self, model_type: str, prompt: str) -> Optional[Dict]:
        """调用AI模型"""
        if model_type == 'deepseek' and self.api_keys['deepseek']:
            return self._call_deepseek(prompt)
        elif model_type == 'openai' and self.api_keys['openai']:
            return self._call_openai(prompt)
        else:
            logger.error(f"无法调用模型 {model_type}: API密钥未设置")
            return None
    
    def _call_deepseek(self, prompt: str) -> Optional[Dict]:
        """调用DeepSeek API"""
        headers = {
            "Authorization": f"Bearer {self.api_keys['deepseek']}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": Config.MODEL_CONFIG['primary']['model'],
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 4000,
            "response_format": {"type": "json_object"}
        }
        
        try:
            start_time = time.time()
            response = requests.post(
                Config.MODEL_CONFIG['primary']['endpoint'],
                json=payload,
                headers=headers,
                timeout=30
            )
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                result = response.json()
                return self._parse_response(result, 'deepseek', response_time)
            else:
                logger.error(f"DeepSeek API错误: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"调用DeepSeek API失败: {e}")
            return None
    
    def _call_openai(self, prompt: str) -> Optional[Dict]:
        """调用OpenAI API"""
        headers = {
            "Authorization": f"Bearer {self.api_keys['openai']}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": Config.MODEL_CONFIG['fallback']['model'],
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 4000,
            "response_format": {"type": "json_object"}
        }
        
        try:
            start_time = time.time()
            response = requests.post(
                Config.MODEL_CONFIG['fallback']['endpoint'],
                json=payload,
                headers=headers,
                timeout=30
            )
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                result = response.json()
                return self._parse_response(result, 'openai', response_time)
            else:
                logger.error(f"OpenAI API错误: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"调用OpenAI API失败: {e}")
            return None
    
    def _parse_response(self, response: Dict, model_name: str, response_time: float) -> Dict:
        """解析API响应"""
        try:
            content = json.loads(response['choices'][0]['message']['content'])
            return {
                'raw_response': response,
                'content': content,
                'model_used': model_name,
                'response_time': response_time,
                'token_usage': response.get('usage', {})
            }
        except Exception as e:
            logger.error(f"解析AI响应失败: {e}")
            return None

# --- README清洗器 ---
class ReadmeCleaner:
    """README内容清洗器"""
    
    @staticmethod
    def clean_readme(readme_text: str, max_length: int = 1500) -> str:
        """清洗README内容"""
        if not readme_text:
            return ""
        
        # 1. 移除Markdown图片和链接
        import re
        
        # 移除图片 ![alt](url)
        cleaned = re.sub(r'!\[.*?\]\(.*?\)', '', readme_text)
        
        # 移除HTML标签
        cleaned = re.sub(r'<[^>]+>', '', cleaned)
        
        # 移除代码块
        cleaned = re.sub(r'```[\s\S]*?```', '', cleaned)
        
        # 移除行内代码
        cleaned = re.sub(r'`[^`]*`', '', cleaned)
        
        # 移除过长的行（可能是base64编码等）
        lines = cleaned.split('\n')
        lines = [line for line in lines if len(line) < 200]
        
        # 2. 提取核心内容（通常是前几段）
        cleaned_text = '\n'.join(lines)
        
        # 3. 截断到指定长度
        if len(cleaned_text) > max_length:
            # 尝试在句子边界截断
            if '.' in cleaned_text[:max_length]:
                last_period = cleaned_text[:max_length].rfind('.')
                if last_period > max_length * 0.7:  # 确保保留大部分内容
                    cleaned_text = cleaned_text[:last_period + 1]
                else:
                    cleaned_text = cleaned_text[:max_length] + "..."
            else:
                cleaned_text = cleaned_text[:max_length] + "..."
        
        return cleaned_text.strip()

# --- 提示词构建器 ---
class PromptBuilder:
    """构建分类提示词"""
    
    @staticmethod
    def build_classification_prompt(batch_data: List[Dict]) -> str:
        """构建分类提示词"""
        
        # 准备批次数据
        batch_items = []
        cleaner = ReadmeCleaner()
        
        for i, repo in enumerate(batch_data, 1):
            # 清洗README
            readme_clean = cleaner.clean_readme(repo.get('readme', ''))
            
            batch_items.append(f"""
仓库 #{i} [{repo.get('serial_number', 'N/A')}]:
- 名称: {repo.get('full_name', 'N/A')}
- 描述: {repo.get('description', '暂无描述')}
- 语言: {repo.get('language', 'N/A')}
- 星标: {repo.get('stars', 0)}
- README核心内容: {readme_clean[:800]}...
""")
        
        batch_text = "\n".join(batch_items)
        
        prompt = f"""你是一个浏览器技术专家和分类学家。请分析以下 {len(batch_data)} 个GitHub仓库的README内容。

## 任务要求
1. 为这批仓库创建3-6个有意义的分类
2. 每个分类应有明确的定义和标准
3. 将每个仓库分配到最合适的分类中
4. 提供详细的分类理由

## 仓库数据
{batch_text}

## 输出格式
请严格按照以下JSON格式输出：

{{
  "categories": [
    {{
      "id": "cat_1",
      "name": "分类名称（中文）",
      "description": "分类描述",
      "criteria": ["分类标准1", "分类标准2"]
    }}
  ],
  "classifications": [
    {{
      "full_name": "仓库全名",
      "category_id": "cat_1",
      "reason": "详细的分类理由，引用README中的关键信息",
      "confidence": 0.95
    }}
  ],
  "summary": {{
    "total_repos": {len(batch_data)},
    "category_distribution": {{"cat_1": 数量, "cat_2": 数量}},
    "key_insights": "本批次的主要发现"
  }}
}}

## 注意事项
- 分类应基于技术架构、功能用途、目标用户等维度
- 避免过于宽泛的分类（如"工具"）
- 每个仓库只能分配到一个主分类
- 置信度范围：0.0-1.0"""
        
        return prompt

# --- 主处理器 ---
class BatchProcessor:
    """主批处理器"""
    
    def __init__(self):
        self.db = DatabaseAdapter(Config.DB_PATH)
        self.ai = AIModelCaller()
        self.cleaner = ReadmeCleaner()
        self.processed_count = 0
        
    def run(self):
        """运行批处理器"""
        logger.info("🚀 启动L1分类处理器")
        
        # 显示初始统计
        stats = self.db.get_progress_stats()
        self._print_stats(stats)
        
        # 确认开始
        response = input("\n是否开始处理？(y/N): ").strip().lower()
        if response != 'y':
            logger.info("操作已取消")
            return
        
        batch_num = 0
        
        while True:
            # 获取下一批数据
            batch_data = self.db.get_next_batch(Config.BATCH_SIZE)
            if not batch_data:
                logger.info("✅ 所有仓库处理完成！")
                self._print_final_summary()
                break
            
            batch_num += 1
            repo_ids = [repo['id'] for repo in batch_data]
            batch_id = self.db.create_batch_record(repo_ids, Config.MODEL_CONFIG['primary']['name'])
            
            logger.info(f"\n📦 处理批次 #{batch_num} (ID: {batch_id})")
            logger.info(f"   包含仓库: {len(batch_data)}个")
            
            # 构建提示词
            prompt = PromptBuilder.build_classification_prompt(batch_data)
            
            # 调用AI（带重试机制）
            ai_result = None
            model_type = Config.MODEL_CONFIG['primary']['name']
            
            for attempt in range(Config.MAX_RETRIES):
                logger.info(f"   尝试 #{attempt+1} 使用模型: {model_type}")
                ai_result = self.ai.call_model(model_type, prompt)
                
                if ai_result:
                    break
                
                logger.warning(f"   请求失败，{Config.RETRY_DELAY}秒后重试...")
                time.sleep(Config.RETRY_DELAY)
                
                # 最后一次重试切换模型
                if attempt == Config.MAX_RETRIES - 2 and model_type != Config.MODEL_CONFIG['fallback']['name']:
                    if self.ai.api_keys.get('openai'):
                        model_type = Config.MODEL_CONFIG['fallback']['name']
                        logger.info(f"   切换为备用模型: {model_type}")
            
            if not ai_result:
                logger.error(f"❌ 批次 {batch_id} 所有重试均失败，跳过")
                continue
            
            # 处理结果
            try:
                self._process_batch_result(batch_data, ai_result, batch_num)
                self.processed_count += len(batch_data)
                
                # 每处理完一批显示进度
                if batch_num % 5 == 0:
                    stats = self.db.get_progress_stats()
                    self._print_progress(batch_num, stats)
                
                # 适当延迟
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"处理批次 {batch_id} 时出错: {e}")
                continue
    
    def _process_batch_result(self, batch_data: List[Dict], ai_result: Dict, batch_num: int):
        """处理批次结果"""
        content = ai_result['content']
        
        # 验证响应格式
        if 'classifications' not in content:
            raise ValueError("AI响应缺少classifications字段")
        
        # 处理每个仓库的分类结果
        for classification in content['classifications']:
            repo_full_name = classification['full_name']
            
            # 找到对应的仓库
            repo = next((r for r in batch_data if r['full_name'] == repo_full_name), None)
            if not repo:
                logger.warning(f"未找到仓库: {repo_full_name}")
                continue
            
            # 清洗README
            readme_clean = self.cleaner.clean_readme(repo.get('readme', ''))
            
            # 准备更新数据
            result_data = {
                'category': classification.get('category_id', 'unknown'),
                'reason': classification.get('reason', ''),
                'model_used': ai_result['model_used'],
                'raw_response': ai_result['raw_response'],
                'readme_clean': readme_clean
            }
            
            # 更新数据库
            self.db.update_classification_result(repo['id'], result_data)
        
        # 打印批次摘要
        categories = content.get('categories', [])
        classifications = content.get('classifications', [])
        
        # 统计分类分布
        from collections import Counter
        category_counts = Counter([c['category_id'] for c in classifications])
        
        logger.info(f"✅ 批次 #{batch_num} 完成")
        logger.info(f"   生成分类: {len(categories)}个")
        logger.info(f"   分类分布: {dict(category_counts)}")
        logger.info(f"   使用模型: {ai_result['model_used']}")
        logger.info(f"   处理耗时: {ai_result['response_time']:.2f}秒")
        logger.info(f"   Token使用: {ai_result.get('token_usage', {}).get('total_tokens', 0)}")
    
    def _print_stats(self, stats: Dict):
        """打印统计信息"""
        total = stats['total']
        completed = stats['completed']
        with_readme = stats['with_readme']
        categories = stats['categories']
        
        print(f"""
📊 数据库状态:
├── 总仓库数: {total}
├── 有README的: {with_readme} ({with_readme/total*100:.1f}%)
├── 已分类的: {completed} ({completed/total*100:.1f}%)
├── 待分类的: {total - completed}
└── 现有分类: {len(categories)}种
""")
        
        if categories:
            print("现有分类分布:")
            for category, count in categories.items():
                if category:  # 过滤掉None
                    print(f"  - {category}: {count}个")
    
    def _print_progress(self, batch_num: int, stats: Dict):
        """打印处理进度"""
        total = stats['total']
        completed = stats['completed']
        
        progress = completed / total * 100 if total > 0 else 0
        
        print(f"""
🔄 处理进度 (批次 #{batch_num}):
├── 进度: {completed}/{total} ({progress:.1f}%)
├── 已处理: {self.processed_count}个仓库
└── 分类数: {len(stats['categories'])}
""")
    
    def _print_final_summary(self):
        """打印最终摘要"""
        stats = self.db.get_progress_stats()
        
        print(f"""
🎉 L1分类处理完成！
========================================
📊 最终统计:
├── 总仓库数: {stats['total']}
├── 已分类数: {stats['completed']}
├── 分类覆盖率: {stats['completed']/stats['total']*100:.1f}%
└── 生成分类数: {len(stats['categories'])}
""")
        
        if stats['categories']:
            print("📈 分类分布:")
            sorted_categories = sorted(stats['categories'].items(), key=lambda x: x[1], reverse=True)
            
            for category, count in sorted_categories:
                if category:  # 过滤掉None
                    percentage = count / stats['completed'] * 100
                    print(f"  - {category}: {count}个 ({percentage:.1f}%)")
        
        # 估算成本
        # 假设平均每个批次使用4000 tokens
        estimated_tokens = (self.processed_count / Config.BATCH_SIZE) * 4000
        deepseek_cost = estimated_tokens * 0.14 / 1_000_000  # $0.14 per 1M tokens
        openai_cost = estimated_tokens * 1.5 / 1_000_000     # $1.5 per 1M tokens
        
        print(f"""
💰 成本估算:
├── 估算总Token: {estimated_tokens:,.0f}
├── DeepSeek成本: ${deepseek_cost:.4f}
└── OpenAI成本: ${openai_cost:.4f}
========================================
""")

# --- 主程序 ---
def main():
    """主函数"""
    print("""
🌐 浏览器生态分析系统 - L1分类处理器 (适配版)
================================================
基于你的数据库结构: github_repos_single_table.db
    """)
    
    # 检查环境变量
    if not Config.DEEPSEEK_API_KEY:
        print("⚠️  警告: DEEPSEEK_API_KEY 未设置")
        print("   请运行: export DEEPSEEK_API_KEY='你的API密钥'")
    if not Config.OPENAI_API_KEY:
        print("⚠️  警告: OPENAI_API_KEY 未设置（备用模型不可用）")
    
    # 检查数据库
    if not os.path.exists(Config.DB_PATH):
        print(f"❌ 错误: 数据库不存在 - {Config.DB_PATH}")
        return
    
    # 启动处理器
    processor = BatchProcessor()
    
    try:
        processor.run()
    except KeyboardInterrupt:
        print("\n\n👋 用户中断处理")
        print("下次运行将从断点继续。")
    except Exception as e:
        print(f"\n❌ 处理失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()