import sqlite3
import json
import os
import time
from datetime import datetime
from openai import OpenAI  # 确保已安装: pip install openai

# ==================== 配置 ====================
CONFIG = {
    # 数据库配置
    "db_path": "./data/github_repos_single_table.db",
    
    # 处理配置
    "batch_size": 15,
    "text_truncate_length": 1200,
    "pause_between_batches": 1,  # 秒
    "temperature": 0.2,
    
    # AI API 配置
    "api_key": "sk-KeaqnqGEo8nsj7jUrA1lk26XkVuZfjWCxyLUpYkgPLsUVwli",
    "base_url": "https://edge.tb.api.mkeai.com/v1",  # OpenAI 兼容端点
    "model": "deepseek-v3.2",
    
    # 输出配置
    "output_dir": "./batch_results",
    "checkpoint_file": "./checkpoint.json",
    
    # 数据库字段名 (只读取，不更新)
    "db_table_name": "repositories",
    "db_id_field": "id",
    "db_name_field": "full_name",
    "db_text_field": "enhanced_text",
    "db_stars_field": "stargazers_count",
    
    # AI 返回字段映射
    "ai_result_key": "classifications",
    "ai_id_key": "id",
    "ai_tag_key": "tag",
    
    # 默认值
    "unknown_category": "Unknown",
    
    # 检查点字段
    "checkpoint_last_id_field": "last_id",
    "checkpoint_processed_ids_field": "processed_ids"
}

# 初始化 OpenAI 客户端
client = OpenAI(api_key=CONFIG["api_key"], base_url=CONFIG["base_url"])

# ==================== 1. 数据库读取 (按星标排序) ====================
class DBHandler:
    def __init__(self, path):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row

    def get_batch(self, size, exclude_ids=None):
        """获取一批未处理的数据，排除已处理过的ID"""
        cursor = self.conn.cursor()
        
        # 构建SQL查询
        base_query = f"""
            SELECT {CONFIG['db_id_field']}, {CONFIG['db_name_field']}, 
                   {CONFIG['db_text_field']}, {CONFIG['db_stars_field']}
            FROM {CONFIG['db_table_name']}
            WHERE {CONFIG['db_text_field']} IS NOT NULL 
              AND LENGTH({CONFIG['db_text_field']}) > 100
        """
        
        params = []
        
        # 如果有要排除的ID，添加到查询条件
        if exclude_ids:
            placeholders = ','.join(['?'] * len(exclude_ids))
            base_query += f" AND {CONFIG['db_id_field']} NOT IN ({placeholders})"
            params.extend(exclude_ids)
        
        # 添加排序和限制
        base_query += f" ORDER BY {CONFIG['db_stars_field']} DESC LIMIT ?"
        params.append(size)
        
        cursor.execute(base_query, params)
        return cursor.fetchall()

# ==================== 2. AI 逻辑 (SDK 简化) ====================
def analyze_batch(batch):
    """调用AI分析批次数据"""
    # 构建 Prompt
    items = []
    for r in batch:
        text_preview = r[CONFIG['db_text_field']]
        if len(text_preview) > CONFIG['text_truncate_length']:
            text_preview = text_preview[:CONFIG['text_truncate_length']] + "..."
        
        items.append(f"ID: {r[CONFIG['db_id_field']]} | Name: {r[CONFIG['db_name_field']]}\nText: {text_preview}")
    
    item_separator = "\n---\n"
    prompt = f"""分析以下{len(batch)}个浏览器相关项目并给出具体的分类标签(Tag)。

要求：
1. 为每个项目创建一个简洁的分类标签（1-3个关键词）
2. 分类要具体，如"Chromium扩展工具"而不是"工具"
3. 考虑：技术架构、目标用户、核心功能
## 分类要求：
1. **专注技术本质**：基于项目功能、技术栈、用途分类
2. **具体而非宽泛**：如"浏览器自动化测试框架"而非"测试工具"
3. **统一标签格式**：使用简洁中文标签，2-8个汉字
4. **技术导向**：优先考虑实现技术而非应用场景

## 技术分类参考（可扩展）：
- 浏览器自动化工具
- 扩展开发框架  
- 渲染引擎/内核
- 开发者工具包
- 隐私安全扩展
- 性能优化工具
- 跨平台框架
- 调试测试工具
- 网络代理工具
- Web组件库
项目数据：
{item_separator.join(items)}

请严格按照以下JSON格式输出：
{{
  "classifications": [
    {{
      "id": 项目ID,
      "tag": "分类标签"
    }}
  ]
}}"""
    
    try:
        response = client.chat.completions.create(
            model=CONFIG["model"],
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},  # 强制 JSON 输出
            temperature=CONFIG["temperature"],
            max_tokens=2000
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"AI 调用失败: {e}")
        return None

# ==================== 3. 数据绑定与持久化 ====================
def save_bundle(batch_id, original_batch, ai_results):
    """将分析结果与原始数据绑定并保存到文件"""
    os.makedirs(CONFIG["output_dir"], exist_ok=True)
    
    # 建立 ID -> Tag 的快速映射
    tag_map = {}
    if ai_results and CONFIG['ai_result_key'] in ai_results:
        for classification in ai_results[CONFIG['ai_result_key']]:
            id_key = CONFIG['ai_id_key']
            tag_key = CONFIG['ai_tag_key']
            if id_key in classification and tag_key in classification:
                tag_map[str(classification[id_key])] = classification[tag_key]
    
    # 四字段牢牢绑定
    bundle = []
    for repo in original_batch:
        repo_id = repo[CONFIG['db_id_field']]
        tag = tag_map.get(str(repo_id), CONFIG["unknown_category"])
        
        bundle.append({
            "id": repo_id,
            "name": repo[CONFIG['db_name_field']],
            "stars": repo[CONFIG['db_stars_field']],
            "enhanced_text": repo[CONFIG['db_text_field']],  # 完整保留原始文本
            "tag": tag  # 绑定 AI 结论
        })
    
    filename = f"batch_{batch_id:03d}_bundle.json"
    path = os.path.join(CONFIG["output_dir"], filename)
    
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({
            "batch_id": batch_id,
            "timestamp": datetime.now().isoformat(),
            "config_used": {
                "model": CONFIG["model"],
                "batch_size": len(original_batch),
                "text_truncate_length": CONFIG["text_truncate_length"]
            },
            "data": bundle,
            "ai_raw_response": ai_results  # 保存原始AI响应
        }, f, indent=2, ensure_ascii=False)
    
    return path, bundle

# ==================== 4. 检查点管理 ====================
class CheckpointManager:
    def __init__(self, checkpoint_file):
        self.checkpoint_file = checkpoint_file
        self.data = self._load()
    
    def _load(self):
        """加载检查点数据"""
        if os.path.exists(self.checkpoint_file):
            try:
                with open(self.checkpoint_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                print("⚠️ 检查点文件损坏，创建新的检查点")
        
        return {
            CONFIG["checkpoint_last_id_field"]: 0,
            CONFIG["checkpoint_processed_ids_field"]: []
        }
    
    def save(self, batch_id, processed_ids):
        """保存检查点"""
        self.data[CONFIG["checkpoint_last_id_field"]] = batch_id
        
        # 更新已处理的ID列表
        existing_ids = set(self.data.get(CONFIG["checkpoint_processed_ids_field"], []))
        new_ids = [pid for pid in processed_ids if pid not in existing_ids]
        self.data[CONFIG["checkpoint_processed_ids_field"]].extend(new_ids)
        
        # 确保目录存在
        os.makedirs(os.path.dirname(self.checkpoint_file), exist_ok=True)
        
        with open(self.checkpoint_file, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
    
    def get_processed_ids(self):
        """获取已处理的ID列表"""
        return self.data.get(CONFIG["checkpoint_processed_ids_field"], [])

# ==================== 5. 主流程 ====================
def main():
    # 初始化组件
    db = DBHandler(CONFIG["db_path"])
    checkpoint = CheckpointManager(CONFIG["checkpoint_file"])
    
    # 从检查点恢复
    batch_id = checkpoint.data.get(CONFIG["checkpoint_last_id_field"], 0) + 1
    processed_ids = checkpoint.get_processed_ids()
    
    print(f"🚀 启动 AI 分类分析流水线")
    print(f"   模型: {CONFIG['model']}")
    print(f"   批次大小: {CONFIG['batch_size']}")
    print(f"   数据库: {CONFIG['db_path']}")
    print(f"   从批次 #{batch_id} 开始")
    print(f"   已处理项目数: {len(processed_ids)}")
    print("="*50)
    
    processed_count = 0
    failed_batches = []
    
    try:
        while True:
            # 获取一个批次的数据（排除已处理过的）
            print(f"\n📦 批次 #{batch_id}: 加载数据...")
            batch = db.get_batch(CONFIG["batch_size"], processed_ids)
            
            if not batch:
                print("✅ 所有数据已分析完毕。")
                break
            
            # 显示批次信息
            first_repo_stars = batch[0][CONFIG['db_stars_field']] if batch else 0
            print(f"   项目数: {len(batch)}, 起始星标: {first_repo_stars}")
            
            # AI 分析
            print(f"   🤖 调用AI进行分析...")
            ai_res = analyze_batch(batch)
            
            if not ai_res:
                print(f"   ❌ AI 分析失败，跳过本批次")
                failed_batches.append(batch_id)
                batch_id += 1
                continue
            
            # 数据绑定 & 保存文件
            print(f"   💾 保存分析结果...")
            file_path, results = save_bundle(batch_id, batch, ai_res)
            
            # 提取本次处理的ID
            current_batch_ids = [item["id"] for item in results]
            
            # 更新检查点
            checkpoint.save(batch_id, current_batch_ids)
            
            # 更新统计
            processed_count += len(results)
            
            # 显示进度
            print(f"   ✅ 批次 #{batch_id} 完成")
            print(f"      保存到: {file_path}")
            if results:
                tags = [item["tag"] for item in results[:3]]
                print(f"      标签示例: {', '.join(tags)}")
            print(f"      累计分析: {processed_count} 个项目")
            
            # 准备下一批
            batch_id += 1
            
            # 频率控制
            time.sleep(CONFIG["pause_between_batches"])
            
    except KeyboardInterrupt:
        print("\n\n⏸️ 处理被用户中断")
    except Exception as e:
        print(f"\n❌ 处理过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 保存处理摘要
        summary = {
            "processed_at": datetime.now().isoformat(),
            "total_processed": processed_count,
            "last_batch_id": batch_id - 1,
            "failed_batches": failed_batches,
            "processed_ids_count": len(checkpoint.get_processed_ids()),
            "config": {
                "model": CONFIG["model"],
                "batch_size": CONFIG["batch_size"],
                "db_path": CONFIG["db_path"]
            }
        }
        
        summary_path = os.path.join(CONFIG["output_dir"], "processing_summary.json")
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        print(f"\n📋 处理摘要已保存: {summary_path}")
        print(f"   总处理批次: {batch_id - 1}")
        print(f"   成功分析: {processed_count} 个项目")
        print(f"   失败批次: {len(failed_batches)} 个")
        print(f"   检查点文件: {CONFIG['checkpoint_file']}")
        
        if failed_batches:
            print(f"   失败批次ID: {failed_batches}")
        
        print("\n🎉 分析完成！所有结果保存在:", CONFIG["output_dir"])

# ==================== 启动脚本 ====================
if __name__ == "__main__":
    # 检查数据库是否存在
    if not os.path.exists(CONFIG["db_path"]):
        print(f"❌ 错误: 数据库文件不存在 - {CONFIG['db_path']}")
        print(f"   当前工作目录: {os.getcwd()}")
        exit(1)
    
    # 检查API密钥
    if not CONFIG["api_key"] or CONFIG["api_key"] == "sk-KeaqnqGEo8nsj7jUrA1lk26XkVuZfjWCxyLUpYkgPLsUVwli":
        print("⚠️ 注意: 使用的是示例API密钥")
        print("   如需使用自己的密钥，请修改CONFIG['api_key']")
        print("   继续处理吗？(y/n): ", end="")
        response = input().strip().lower()
        if response != 'y':
            print("❌ 用户取消处理")
            exit(0)
    
    # 创建输出目录
    os.makedirs(CONFIG["output_dir"], exist_ok=True)
    
    # 运行主流程
    main()