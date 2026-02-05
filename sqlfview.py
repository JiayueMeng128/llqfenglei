#!/usr/bin/env python3
"""
数据库结构探查工具
用于分析现有数据库的完整结构，为代码设计提供依据
"""

import sqlite3
import json
import os
from datetime import datetime
from typing import Dict, List, Any
import pandas as pd
from tabulate import tabulate

class DatabaseExplorer:
    """数据库探查器"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = None
        self.cursor = None
        self.structure = {}
        
    def connect(self):
        """连接到数据库"""
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"数据库文件不存在: {self.db_path}")
        
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()
        print(f"✅ 成功连接到数据库: {self.db_path}")
        print(f"📅 数据库最后修改时间: {datetime.fromtimestamp(os.path.getmtime(self.db_path))}")
        return self
    
    def disconnect(self):
        """断开数据库连接"""
        if self.conn:
            self.conn.close()
            print("🔌 数据库连接已关闭")
    
    def get_all_tables(self) -> List[str]:
        """获取所有表名"""
        self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
        tables = [row[0] for row in self.cursor.fetchall()]
        print(f"📋 发现 {len(tables)} 个表:")
        for i, table in enumerate(tables, 1):
            print(f"  {i:2d}. {table}")
        return tables
    
    def get_table_structure(self, table_name: str) -> Dict[str, Any]:
        """获取表的结构信息"""
        # 获取列信息
        self.cursor.execute(f"PRAGMA table_info({table_name});")
        columns = self.cursor.fetchall()
        
        # 获取索引信息
        self.cursor.execute(f"PRAGMA index_list({table_name});")
        indexes = self.cursor.fetchall()
        
        # 获取外键信息
        self.cursor.execute(f"PRAGMA foreign_key_list({table_name});")
        foreign_keys = self.cursor.fetchall()
        
        # 获取行数
        self.cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
        row_count = self.cursor.fetchone()[0]
        
        # 获取样本数据（前3行）
        sample_data = []
        if row_count > 0:
            try:
                self.cursor.execute(f"SELECT * FROM {table_name} LIMIT 3;")
                sample_data = self.cursor.fetchall()
                # 获取列名用于样本展示
                self.cursor.execute(f"SELECT * FROM {table_name} LIMIT 0;")
                column_names = [description[0] for description in self.cursor.description]
            except:
                column_names = []
                sample_data = []
        
        return {
            "table_name": table_name,
            "row_count": row_count,
            "columns": [
                {
                    "cid": col[0],
                    "name": col[1],
                    "type": col[2],
                    "notnull": bool(col[3]),
                    "default": col[4],
                    "pk": bool(col[5])
                } for col in columns
            ],
            "indexes": [
                {
                    "seq": idx[0],
                    "name": idx[1],
                    "unique": bool(idx[2]),
                    "origin": idx[3],
                    "partial": bool(idx[4])
                } for idx in indexes
            ],
            "foreign_keys": [
                {
                    "id": fk[0],
                    "seq": fk[1],
                    "table": fk[2],
                    "from": fk[3],
                    "to": fk[4],
                    "on_update": fk[5],
                    "on_delete": fk[6],
                    "match": fk[7]
                } for fk in foreign_keys
            ],
            "sample_data": sample_data,
            "column_names": column_names if 'column_names' in locals() else []
        }
    
    def analyze_column_statistics(self, table_name: str) -> Dict[str, Any]:
        """分析列的统计信息"""
        table_info = self.get_table_structure(table_name)
        stats = {}
        
        for column in table_info["columns"]:
            col_name = column["name"]
            col_type = column["type"].lower()
            
            # 跳过某些类型的统计
            if col_type in ['text', 'blob']:
                continue
                
            try:
                # 数值列统计
                if any(num_type in col_type for num_type in ['int', 'float', 'real', 'double', 'decimal']):
                    self.cursor.execute(f"""
                        SELECT 
                            MIN("{col_name}"), 
                            MAX("{col_name}"), 
                            AVG("{col_name}"),
                            COUNT(DISTINCT "{col_name}"),
                            COUNT("{col_name}") as non_null_count
                        FROM {table_name}
                    """)
                    min_val, max_val, avg_val, distinct_count, non_null_count = self.cursor.fetchone()
                    
                    stats[col_name] = {
                        "type": "numeric",
                        "min": min_val,
                        "max": max_val,
                        "avg": avg_val,
                        "distinct_values": distinct_count,
                        "null_count": table_info["row_count"] - non_null_count,
                        "null_percentage": round((table_info["row_count"] - non_null_count) / table_info["row_count"] * 100, 2) if table_info["row_count"] > 0 else 0
                    }
                
                # 文本列统计（只对较短的列进行）
                elif col_type == 'text':
                    # 检查文本长度分布
                    self.cursor.execute(f"""
                        SELECT 
                            AVG(LENGTH("{col_name}")) as avg_length,
                            MAX(LENGTH("{col_name}")) as max_length,
                            COUNT(DISTINCT "{col_name}") as distinct_count
                        FROM {table_name}
                    """)
                    avg_len, max_len, distinct_count = self.cursor.fetchone()
                    
                    # 获取最常见的值（如果文本不太长）
                    if max_len < 100:  # 只对短文本进行值分布分析
                        self.cursor.execute(f"""
                            SELECT "{col_name}", COUNT(*) as freq
                            FROM {table_name}
                            WHERE "{col_name}" IS NOT NULL
                            GROUP BY "{col_name}"
                            ORDER BY freq DESC
                            LIMIT 5
                        """)
                        top_values = self.cursor.fetchall()
                    else:
                        top_values = []
                    
                    stats[col_name] = {
                        "type": "text",
                        "avg_length": avg_len,
                        "max_length": max_len,
                        "distinct_values": distinct_count,
                        "top_values": top_values
                    }
                    
            except Exception as e:
                stats[col_name] = {"error": str(e)}
        
        return stats
    
    def get_database_schema_sql(self) -> str:
        """获取数据库的完整SQL模式"""
        self.cursor.execute("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type, name;")
        schema_lines = self.cursor.fetchall()
        schema_sql = "\n".join([line[0] + ";" for line in schema_lines if line[0]])
        return schema_sql
    
    def generate_erd_data(self) -> Dict[str, Any]:
        """生成实体关系图数据"""
        tables = self.get_all_tables()
        erd_data = {
            "tables": [],
            "relationships": []
        }
        
        for table in tables:
            table_info = self.get_table_structure(table)
            
            # 添加表信息
            erd_data["tables"].append({
                "name": table,
                "columns": [
                    {
                        "name": col["name"],
                        "type": col["type"],
                        "primary_key": col["pk"],
                        "nullable": not col["notnull"]
                    } for col in table_info["columns"]
                ],
                "row_count": table_info["row_count"]
            })
            
            # 添加关系信息
            for fk in table_info["foreign_keys"]:
                erd_data["relationships"].append({
                    "from_table": table,
                    "from_column": fk["from"],
                    "to_table": fk["table"],
                    "to_column": fk["to"],
                    "on_update": fk["on_update"],
                    "on_delete": fk["on_delete"]
                })
        
        return erd_data
    
    def export_structure_report(self, output_dir: str = "reports"):
        """导出完整的结构报告"""
        os.makedirs(output_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_data = {
            "database_info": {
                "path": self.db_path,
                "size_mb": round(os.path.getsize(self.db_path) / (1024 * 1024), 2),
                "last_modified": datetime.fromtimestamp(os.path.getmtime(self.db_path)).isoformat(),
                "timestamp": timestamp
            },
            "tables": {},
            "schema_sql": self.get_database_schema_sql(),
            "erd_data": self.generate_erd_data()
        }
        
        tables = self.get_all_tables()
        for table in tables:
            print(f"\n🔍 分析表: {table}")
            table_info = self.get_table_structure(table)
            column_stats = self.analyze_column_statistics(table)
            
            report_data["tables"][table] = {
                "structure": table_info,
                "statistics": column_stats
            }
            
            # 打印表结构摘要
            self.print_table_summary(table, table_info, column_stats)
        
        # 保存JSON报告
        json_path = os.path.join(output_dir, f"db_structure_{timestamp}.json")
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2, default=str)
        
        # 保存SQL模式
        sql_path = os.path.join(output_dir, f"db_schema_{timestamp}.sql")
        with open(sql_path, 'w', encoding='utf-8') as f:
            f.write(report_data["schema_sql"])
        
        # 生成HTML报告
        self.generate_html_report(report_data, output_dir, timestamp)
        
        print(f"\n📁 报告已保存到目录: {output_dir}/")
        print(f"  📄 JSON报告: db_structure_{timestamp}.json")
        print(f"  📄 SQL模式: db_schema_{timestamp}.sql")
        print(f"  📄 HTML报告: db_report_{timestamp}.html")
        
        return report_data
    
    def print_table_summary(self, table_name: str, table_info: Dict, column_stats: Dict):
        """打印表结构摘要"""
        print(f"\n{'='*60}")
        print(f"表名: {table_name}")
        print(f"行数: {table_info['row_count']:,}")
        print(f"列数: {len(table_info['columns'])}")
        print(f"索引数: {len(table_info['indexes'])}")
        print(f"外键数: {len(table_info['foreign_keys'])}")
        
        # 打印列信息表格
        columns_data = []
        for col in table_info["columns"]:
            # 获取列统计信息（如果有）
            stats = column_stats.get(col["name"], {})
            
            columns_data.append([
                col["name"],
                col["type"],
                "✓" if col["pk"] else "",
                "✓" if col["notnull"] else "NULL",
                col["default"] or "",
                stats.get("type", ""),
                f"{stats.get('null_percentage', 0)}%" if "null_percentage" in stats else ""
            ])
        
        if columns_data:
            print("\n📊 列信息:")
            print(tabulate(columns_data, 
                          headers=["列名", "类型", "PK", "非空", "默认值", "统计类型", "空值%"],
                          tablefmt="grid"))
        
        # 打印索引信息
        if table_info["indexes"]:
            print("\n📈 索引信息:")
            for idx in table_info["indexes"]:
                print(f"  - {idx['name']} {'(唯一)' if idx['unique'] else ''}")
        
        # 打印外键信息
        if table_info["foreign_keys"]:
            print("\n🔗 外键信息:")
            for fk in table_info["foreign_keys"]:
                print(f"  - {fk['from']} → {fk['table']}.{fk['to']}")
    
    def generate_html_report(self, report_data: Dict, output_dir: str, timestamp: str):
        """生成HTML格式的报告"""
        html_path = os.path.join(output_dir, f"db_report_{timestamp}.html")
        
        html_content = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>数据库结构报告 - {timestamp}</title>
    <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 40px; line-height: 1.6; color: #333; }}
        .header {{ background: linear-gradient(135deg, #6a11cb 0%, #2575fc 100%); color: white; padding: 30px; border-radius: 10px; margin-bottom: 30px; }}
        .section {{ background: white; padding: 25px; border-radius: 10px; box-shadow: 0 2px 15px rgba(0,0,0,0.1); margin-bottom: 25px; }}
        h1, h2, h3 {{ color: #2c3e50; }}
        h1 {{ margin: 0; }}
        .table-info {{ overflow-x: auto; }}
        table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
        th, td {{ padding: 12px 15px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background-color: #f8f9fa; font-weight: 600; }}
        tr:hover {{ background-color: #f5f5f5; }}
        .pk {{ background-color: #e8f5e9; color: #2e7d32; font-weight: bold; }}
        .fk {{ background-color: #e3f2fd; color: #1565c0; }}
        .numeric {{ color: #d81b60; }}
        .text {{ color: #00897b; }}
        .stats {{ background-color: #fff3e0; padding: 15px; border-radius: 5px; margin: 10px 0; }}
        .timestamp {{ color: #7f8c8d; font-size: 0.9em; }}
        .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; }}
        .summary-card {{ background: #f8f9fa; padding: 20px; border-radius: 8px; text-align: center; }}
        .summary-card h3 {{ margin-top: 0; color: #3498db; }}
        .summary-number {{ font-size: 2.5em; font-weight: bold; color: #2c3e50; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>📊 数据库结构分析报告</h1>
        <p>数据库: {report_data['database_info']['path']}</p>
        <p class="timestamp">生成时间: {report_data['database_info']['timestamp']} | 大小: {report_data['database_info']['size_mb']} MB</p>
    </div>
    
    <div class="section">
        <h2>📋 数据库概览</h2>
        <div class="summary">
            <div class="summary-card">
                <h3>表数量</h3>
                <div class="summary-number">{len(report_data['tables'])}</div>
            </div>
            <div class="summary-card">
                <h3>总行数</h3>
                <div class="summary-number">{sum(t['structure']['row_count'] for t in report_data['tables'].values()):,}</div>
            </div>
            <div class="summary-card">
                <h3>总列数</h3>
                <div class="summary-number">{sum(len(t['structure']['columns']) for t in report_data['tables'].values())}</div>
            </div>
        </div>
    </div>
"""
        
        # 为每个表生成详细内容
        for table_name, table_data in report_data["tables"].items():
            structure = table_data["structure"]
            stats = table_data["statistics"]
            
            html_content += f"""
    <div class="section">
        <h2>📁 表: {table_name}</h2>
        <p>行数: <strong>{structure['row_count']:,}</strong> | 列数: {len(structure['columns'])} | 索引: {len(structure['indexes'])} | 外键: {len(structure['foreign_keys'])}</p>
        
        <h3>列结构</h3>
        <div class="table-info">
            <table>
                <thead>
                    <tr>
                        <th>列名</th>
                        <th>类型</th>
                        <th>主键</th>
                        <th>非空</th>
                        <th>默认值</th>
                        <th>统计信息</th>
                    </tr>
                </thead>
                <tbody>
"""
            
            for col in structure["columns"]:
                col_stats = stats.get(col["name"], {})
                stat_text = ""
                
                if col_stats.get("type") == "numeric":
                    stat_text = f"范围: {col_stats.get('min')}~{col_stats.get('max')}, 空值: {col_stats.get('null_percentage', 0)}%"
                elif col_stats.get("type") == "text":
                    stat_text = f"平均长度: {col_stats.get('avg_length', 0):.1f}, 最大长度: {col_stats.get('max_length', 0)}"
                
                html_content += f"""
                    <tr>
                        <td class="{'pk' if col['pk'] else ''}">{col['name']}</td>
                        <td class="{col_stats.get('type', '')}">{col['type']}</td>
                        <td>{'✓' if col['pk'] else ''}</td>
                        <td>{'✓' if col['notnull'] else 'NULL'}</td>
                        <td>{col['default'] or ''}</td>
                        <td>{stat_text}</td>
                    </tr>
"""
            
            html_content += """
                </tbody>
            </table>
        </div>
"""
            
            # 添加样本数据
            if structure.get("sample_data") and len(structure["sample_data"]) > 0:
                html_content += f"""
        <h3>样本数据 (前{len(structure['sample_data'])}行)</h3>
        <div class="table-info">
            <table>
                <thead>
                    <tr>
"""
                for col_name in structure.get("column_names", []):
                    html_content += f"<th>{col_name}</th>"
                
                html_content += """
                    </tr>
                </thead>
                <tbody>
"""
                for row in structure["sample_data"]:
                    html_content += "<tr>"
                    for cell in row:
                        cell_str = str(cell)
                        if cell is None:
                            cell_str = "<em style='color:#999'>NULL</em>"
                        elif len(cell_str) > 100:
                            cell_str = cell_str[:100] + "..."
                        html_content += f"<td>{cell_str}</td>"
                    html_content += "</tr>"
                
                html_content += """
                </tbody>
            </table>
        </div>
"""
        
        html_content += """
    </div>
</body>
</html>
"""
        
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"📄 HTML报告已生成: {html_path}")

def main():
    """主函数"""
    # 配置数据库路径
    db_path = "./data/github_repos_single_table.db"  # 根据你的实际情况调整
    
    if not os.path.exists(db_path):
        print(f"❌ 数据库文件不存在: {db_path}")
        print("请提供正确的数据库路径:")
        db_path = input("数据库路径: ").strip()
        
        if not os.path.exists(db_path):
            print("❌ 指定的数据库文件也不存在，请检查路径")
            return
    
    print("🔍 数据库结构探查工具")
    print("=" * 60)
    
    # 创建探查器
    explorer = DatabaseExplorer(db_path)
    
    try:
        # 连接数据库
        explorer.connect()
        
        # 获取并打印表列表
        tables = explorer.get_all_tables()
        
        # 导出完整报告
        print("\n📊 正在生成完整数据库结构报告...")
        report = explorer.export_structure_report("reports/database_structure")
        
        # 生成实体关系图数据（供后续可视化）
        erd_data = explorer.generate_erd_data()
        erd_path = "reports/database_structure/erd_data.json"
        os.makedirs(os.path.dirname(erd_path), exist_ok=True)
        with open(erd_path, 'w', encoding='utf-8') as f:
            json.dump(erd_data, f, indent=2, ensure_ascii=False)
        
        print(f"\n📊 ERD数据已保存: {erd_path}")
        
        # 提供后续步骤建议
        print("\n🎯 基于数据库结构的代码设计建议:")
        print("=" * 60)
        
        for table_name in tables:
            table_info = explorer.get_table_structure(table_name)
            print(f"\n📌 表: {table_name}")
            
            # 分析表特点并提供建议
            if table_info["row_count"] > 1000:
                print(f"  ⚠️  数据量大 ({table_info['row_count']:,} 行)，建议:")
                print("    - 实现分页查询")
                print("    - 添加适当的索引")
                print("    - 考虑数据分区策略")
            
            if len(table_info["indexes"]) == 0 and table_info["row_count"] > 100:
                print("  ⚠️  缺乏索引，建议添加索引以提升查询性能")
            
            # 检查文本字段
            text_columns = [col for col in table_info["columns"] 
                          if col["type"].lower() == "text"]
            for col in text_columns:
                print(f"  📝 文本列: {col['name']} - 考虑:")
                print("    - 是否需要全文搜索")
                print("    - 是否需要设置最大长度")
                print("    - 是否需要文本清洗处理")
            
            # 检查外键关系
            if table_info["foreign_keys"]:
                print(f"  🔗 外键关系:")
                for fk in table_info["foreign_keys"]:
                    print(f"    - {fk['from']} → {fk['table']}.{fk['to']}")
                    print(f"      考虑实现级联操作或连接查询优化")
        
    except Exception as e:
        print(f"❌ 探查过程中出错: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        explorer.disconnect()

if __name__ == "__main__":
    main()