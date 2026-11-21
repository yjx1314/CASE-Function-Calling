# -*- coding: utf-8 -*-
import os
import asyncio
from typing import Optional
import dashscope
from qwen_agent.agents import Assistant
from qwen_agent.gui import WebUI
import pandas as pd
from sqlalchemy import create_engine
from qwen_agent.tools.base import BaseTool, register_tool
import matplotlib.pyplot as plt
import io
import base64
import time

# 解决 matplotlib 图表中文乱码问题（使用 Windows 自带的中文字体）
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False  # 正常显示负号

import gradio as gr

# 图片保存目录（绝对路径）
IMAGE_SAVE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'image_show')
# 将图片目录注册为 gradio 静态目录，使 WebUI 的 /file= 路由可以访问生成的图表
gr.set_static_paths(paths=[IMAGE_SAVE_DIR])

# 配置 DashScope
dashscope.api_key = os.getenv('DASHSCOPE_API_KEY', '')  # 从环境变量获取 API Key
dashscope.timeout = 30  # 设置超时时间为 30 秒

# ====== 本地 MySQL 连接配置 ======
DB_HOST = 'localhost'
DB_PORT = 3306
DB_USER = 'root'
DB_PASSWORD = 'MyTDBpvydvJabz7tGCfk'
DB_NAME = 'mysql'  # 订单表所在的数据库

# ====== 订单助手 system prompt 和函数描述 ======
system_prompt = """我是订单助手，以下是关于订单表相关的字段，我可能会编写对应的SQL，对数据进行查询
-- 订单表（注意：表名 orders 建议用反引号包裹，如 `orders`，数据库名为 mysql）
CREATE TABLE `orders` (
    id BIGINT UNSIGNED,          -- 订单ID（自增主键）
    order_no VARCHAR(32),        -- 订单号，如 ORD20260618000001
    user_id INT UNSIGNED,        -- 用户ID
    user_name VARCHAR(50),       -- 收货人姓名
    user_phone VARCHAR(20),      -- 联系电话
    province VARCHAR(30),        -- 省
    city VARCHAR(30),            -- 市
    district VARCHAR(30),        -- 区
    address VARCHAR(200),        -- 详细地址
    product_id INT UNSIGNED,     -- 商品ID
    product_name VARCHAR(100),   -- 商品名称
    unit_price DECIMAL(10,2),    -- 成交单价
    quantity INT,                -- 数量
    total_amount DECIMAL(10,2),  -- 订单金额
    pay_type VARCHAR(20),        -- 支付方式，如：微信支付、支付宝、银行卡
    order_status TINYINT,        -- 订单状态：0待付款 1已付款 2已发货 3已完成 4已取消
    remark VARCHAR(200),         -- 备注
    created_at DATETIME          -- 下单时间
);
订单状态说明（需要显示状态名称时，可用 CASE WHEN 映射）：
0=待付款，1=已付款，2=已发货，3=已完成，4=已取消
我将回答用户关于订单相关的问题

每当 exc_sql 工具返回 markdown 表格和图片时，你必须原样输出工具返回的全部内容（包括图片 markdown），不要只总结表格，也不要省略图片。这样用户才能直接看到表格和图片。
"""

functions_desc = [
    {
        "name": "exc_sql",
        "description": "对于生成的SQL，进行SQL查询",
        "parameters": {
            "type": "object",
            "properties": {
                "sql_input": {
                    "type": "string",
                    "description": "生成的SQL语句",
                }
            },
            "required": ["sql_input"],
        },
    },
]

# ====== 会话隔离 DataFrame 存储 ======
# 用于存储每个会话的 DataFrame，避免多用户数据串扰
_last_df_dict = {}

def get_session_id(kwargs):
    """根据 kwargs 获取当前会话的唯一 session_id，这里用 messages 的 id"""
    messages = kwargs.get('messages')
    if messages is not None:
        return id(messages)
    return None

# ====== exc_sql 工具类实现 ======
@register_tool('exc_sql')
class ExcSQLTool(BaseTool):
    """
    SQL查询工具，执行传入的SQL语句并返回结果，并自动进行可视化。
    """
    description = '对于生成的SQL，进行SQL查询，并自动可视化'
    parameters = [{
        'name': 'sql_input',
        'type': 'string',
        'description': '生成的SQL语句',
        'required': True
    }]

    def call(self, params: str, **kwargs) -> str:
        import json
        import matplotlib.pyplot as plt
        import io, os, time
        args = json.loads(params)
        sql_input = args['sql_input']
        database = args.get('database', DB_NAME)
        engine = create_engine(
            f'mysql+mysqlconnector://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{database}?charset=utf8mb4',
            connect_args={'connect_timeout': 10}, pool_size=10, max_overflow=20
        )
        try:
            df = pd.read_sql(sql_input, engine)
            md = df.head(10).to_markdown(index=False)
            # 自动推断x/y字段
            x_candidates = df.select_dtypes(include=['object']).columns.tolist()
            if not x_candidates:
                x_candidates = df.columns.tolist()
            x = x_candidates[0]
            y_candidates = df.select_dtypes(include=['number']).columns.tolist()
            y_fields = y_candidates
            # 绘制柱状图
            plt.figure(figsize=(8, 5))
            bar_width = 0.35 if len(y_fields) > 1 else 0.6
            x_labels = df[x].astype(str)
            x_pos = range(len(df))
            for idx, y_col in enumerate(y_fields):
                plt.bar([p + idx*bar_width for p in x_pos], df[y_col], width=bar_width, label=y_col)
            plt.xlabel(x)
            plt.ylabel(','.join(y_fields))
            plt.title(f"{' & '.join(y_fields)} by {x}")
            plt.xticks([p + bar_width*(len(y_fields)-1)/2 for p in x_pos], x_labels, rotation=45, ha='right')
            plt.legend()
            plt.tight_layout()
            # 自动创建目录
            save_dir = IMAGE_SAVE_DIR
            os.makedirs(save_dir, exist_ok=True)
            # 生成唯一文件名
            filename = f'bar_{int(time.time()*1000)}.png'
            print("filename = ", filename)
            save_path = os.path.join(save_dir, filename)
            print("save_path = ", save_path)
            plt.savefig(save_path)
            plt.close()
            # 生成可通过 gradio /file= 路由访问的图片 URL，注意：
            # 1. 必须用正斜杠，反斜杠会被浏览器 URL 编码成 %5C 导致 404
            # 2. gradio 默认只通过 /file= 路由对外提供文件，相对路径无法访问
            # 3. 路径中的空格需编码为 %20（markdown 链接中不允许出现空格）
            img_url = '/file=' + os.path.abspath(save_path).replace(os.sep, '/').replace(' ', '%20')
            img_md = f'![柱状图]({img_url})'
            return f"{md}\n\n{img_md}"
        except Exception as e:
            return f"SQL执行或可视化出错: {str(e)}"

# ====== 初始化订单助手服务 ======
def init_agent_service():
    """初始化订单助手服务"""
    llm_cfg = {
        # 快照模型 qwen-turbo-2025-04-28 对当前账号返回 403 AccessDenied，
        # qwen-turbo 当前账号限流（429），实测 qwen-plus 可正常调用，故使用 qwen-plus
        'model': 'qwen-plus',
        'timeout': 30,
        'retry_count': 3,
    }
    try:
        bot = Assistant(
            llm=llm_cfg,
            name='订单助手',
            description='订单查询与订单分析',
            system_message=system_prompt,
            function_list=['exc_sql'],
        )
        print("助手初始化成功！")
        return bot
    except Exception as e:
        print(f"助手初始化失败: {str(e)}")
        raise

def app_tui():
    """终端交互模式
    
    提供命令行交互界面，支持：
    - 连续对话
    - 文件输入
    - 实时响应
    """
    try:
        # 初始化助手
        bot = init_agent_service()

        # 对话历史
        messages = []
        while True:
            try:
                # 获取用户输入
                query = input('user question: ')
                # 获取可选的文件输入
                file = input('file url (press enter if no file): ').strip()
                
                # 输入验证
                if not query:
                    print('user question cannot be empty！')
                    continue
                    
                # 构建消息
                if not file:
                    messages.append({'role': 'user', 'content': query})
                else:
                    messages.append({'role': 'user', 'content': [{'text': query}, {'file': file}]})

                print("正在处理您的请求...")
                # 运行助手并处理响应
                response = []
                for response in bot.run(messages):
                    print('bot response:', response)
                messages.extend(response)
            except Exception as e:
                print(f"处理请求时出错: {str(e)}")
                print("请重试或输入新的问题")
    except Exception as e:
        print(f"启动终端模式失败: {str(e)}")


def app_gui():
    """图形界面模式，提供 Web 图形界面"""
    try:
        print("正在启动 Web 界面...")
        # 初始化助手
        bot = init_agent_service()
        # 配置聊天界面，列举3个典型订单查询问题
        chatbot_config = {
            'prompt.suggestions': [
                '统计每个月的订单量和订单总金额，按月排序',
                '不同支付方式的订单金额和订单数量分布',
                '本月的销量是多少？',
                '相比于上个月，这个月的销量环比增长多少？',
            ]
        }
        print("Web 界面准备就绪，正在启动服务...")
        # 启动 Web 界面
        WebUI(
            bot,
            chatbot_config=chatbot_config
        ).run()
    except Exception as e:
        print(f"启动 Web 界面失败: {str(e)}")
        print("请检查网络连接和 API Key 配置")


if __name__ == '__main__':
    # 运行模式选择
    app_gui()          # 图形界面模式（默认）
{
    "mcpServers": {
        "amap-maps": {
            "command": "npx",
            "args": [
                "-y",
                "@amap/amap-maps-mcp-server"
            ],
            "env": {
                "AMAP_MAPS_API_KEY": "3c05ae99a8016eef752264da1cd7e39b"
            }
        }
    }
}