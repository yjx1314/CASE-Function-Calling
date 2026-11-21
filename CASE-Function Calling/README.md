# CASE-Function Calling 项目介绍

基于 **Qwen-Agent（通义千问智能体框架）** 的 Function Calling 实战案例。项目通过自定义 `exc_sql` 工具，让大模型（Qwen 系列）根据用户自然语言问题自动生成 SQL 并查询 MySQL 数据库，再把查询结果以 Markdown 表格 + 柱状图的形式返回给用户，实现一个"Text2SQL + 数据可视化"的智能数据问答助手。

## 核心工作流程

```
用户提问（自然语言）
      │
      ▼
Qwen Assistant（大模型，system prompt 中包含表结构）
      │  Function Calling：生成 SQL
      ▼
exc_sql 自定义工具（@register_tool 注册）
      │  连接 MySQL 执行 SQL（pandas.read_sql）
      ▼
查询结果 DataFrame
      │
      ├──▶ Markdown 表格（df.head(10)）
      └──▶ matplotlib 柱状图（保存到 image_show/）
      │
      ▼
模型将表格 + 图片 Markdown 原样输出给用户
```

## 项目目录结构

```
CASE-Function Calling/
├── assistant_ticket_bot-1.py      # 门票助手 V1：基础版（SQL 查询，返回 Markdown 表格）
├── assistant_ticket_bot-2.py      # 门票助手 V2：增加自动可视化（每次查询附带柱状图）
├── assistant_ticket_bot-3.py      # 门票助手 V3：接入 MCP 工具（高德地图、Tavily）+ 堆积柱状图
├── assistant_ticket_bot_logic.html# assistant_ticket_bot-1.py 代码逻辑整理文档（Mermaid 流程图）
├── requirements.txt               # 项目依赖清单
├── image_show/                    # V2/V3 生成的柱状图 PNG 输出目录
├── test/
│   ├── assistant_order_bot.py     # 订单助手（本地 MySQL 版，Gradio 静态目录支持 WebUI 显示图片）
│   └── image_show/                # 订单助手生成的柱状图输出目录
├── workspace/
│   └── tools/                     # qwen-agent 运行时生成的工具工作区
│       ├── code_interpreter/      # 代码解释器内核连接文件（Jupyter kernel）
│       ├── simple_doc_parser/     # 文档解析工具目录（空）
│       └── doc_parser/            # 文档解析工具目录（空）
└── __pycache__/                   # Python 编译缓存
```

## 各文件功能说明

### 1. assistant_ticket_bot-1.py —— 基础版门票助手

- **模型**：`qwen-flash`（DashScope API，Key 从环境变量 `DASHSCOPE_API_KEY` 读取）
- **System Prompt**：内置门票订单表 `tkt_orders` 的完整建表语句（13 个字段）、SKU 分类规则（一日票 / 二日票）以及统计口径的 SQL 模板，引导模型正确生成 SQL
- **自定义工具 `exc_sql`**：通过 `@register_tool` 注册到 Qwen-Agent，接收模型生成的 SQL，连接阿里云 RDS MySQL 执行查询，返回前 10 行的 Markdown 表格
- **运行模式**：`app_tui()` 终端交互 / `app_gui()` Gradio WebUI（默认启动 WebUI，内置 3 个典型问题示例）
- **技术栈**：dashscope + qwen_agent + pandas + SQLAlchemy（mysqlconnector 驱动）

### 2. assistant_ticket_bot-2.py —— 增加自动可视化

在 V1 基础上新增：

- **自动绘图**：`exc_sql` 工具查询后自动推断 x 轴（object 列）/ y 轴（数值列），绘制分组柱状图并保存为 `image_show/bar_<时间戳>.png`，随表格一起以图片 Markdown 返回
- **Prompt 约束**：要求模型"必须原样输出工具返回的全部内容（包括图片 Markdown）"，保证用户能直接看到表格和图表
- **模型切换**：改用 `qwen-plus`（注释记录了 qwen-turbo 限流 429、快照模型 403 的实测结论）

### 3. assistant_ticket_bot-3.py —— 接入 MCP + 可视化增强（当前主版本）

在 V2 基础上新增：

- **MCP 工具接入**：`function_list` 中同时注册自定义工具与 MCP Server 配置：
  - `amap-maps`：高德地图 MCP 服务（`@amap/amap-maps-mcp-server`）
  - `tavily-mcp`：Tavily 联网搜索 MCP 服务（API Key 从环境变量 `TAVILY_API_KEY` 读取）
- **可视化重构**：抽出通用函数 `generate_chart_png()`，支持：
  - 有多个 object 列时自动 `pivot_table` 透视并绘制**堆积柱状图**
  - 全程对标签做 `%`、`{}`、`}` 等格式化字符安全转义，避免 matplotlib 渲染报错
- **中文支持**：配置 `SimHei / Microsoft YaHei` 等中文字体，解决图表中文乱码
- **驱动切换**：数据库驱动改为 `pymysql`，并用 `sqlalchemy.text()` 包装 SQL，避免特殊字符导致的格式化问题

### 4. test/assistant_order_bot.py —— 订单助手（本地版）

- 场景从"门票订单"换成通用电商**订单表 `orders`**（订单号、收货地址、支付方式、订单状态等 19 个字段），并内置订单状态码（0-4）的 CASE WHEN 映射说明
- 数据库连接改为**本地 MySQL**（localhost）
- 针对 WebUI 无法显示图片的问题，使用 `gr.set_static_paths()` 将 `image_show` 注册为 Gradio 静态目录，使 `/file=` 路由可以访问生成的图表
- 同样支持终端 / WebUI 两种运行模式

### 5. assistant_ticket_bot_logic.html —— 代码逻辑文档

使用 Mermaid 流程图整理 `assistant_ticket_bot-1.py` 的执行逻辑，浏览器打开即可查看。

## 环境依赖

`requirements.txt` 主要依赖：

| 依赖 | 版本 | 用途 |
|------|------|------|
| qwen_agent | 0.0.25 | 智能体框架（Assistant / WebUI / 自定义工具） |
| dashscope | 1.22.1 | 通义千问 API SDK |
| pandas / numpy | 2.3.0 | 数据查询结果处理 |
| matplotlib | 3.10.3 | 柱状图绘制 |
| SQLAlchemy | 2.0.23 | MySQL 连接与 ORM 引擎 |
| scikit_learn | 1.7.0 | 辅助依赖 |

## 运行方式

```bash
# 1. 安装依赖
pip install -r requirements.txt
# 另需安装数据库驱动：pip install pymysql（V3）或 mysql-connector-python

# 2. 配置环境变量
# Windows (PowerShell)
$env:DASHSCOPE_API_KEY = "你的 DashScope API Key"
$env:TAVILY_API_KEY = "你的 Tavily API Key"   # 仅 V3 需要

# 3. 运行（默认启动 Gradio WebUI，浏览器访问 http://127.0.0.1:7860）
python assistant_ticket_bot-3.py
```

## 版本演进总结

| 版本 | 文件 | 核心能力 |
|------|------|----------|
| V1 | assistant_ticket_bot-1.py | Text2SQL 查询 + Markdown 表格 |
| V2 | assistant_ticket_bot-2.py | + 自动柱状图可视化 |
| V3 | assistant_ticket_bot-3.py | + MCP 工具（地图/联网搜索）+ 堆积柱状图 + 中文图表支持 |
| 扩展 | test/assistant_order_bot.py | 本地 MySQL 订单数据场景 + Gradio 图片显示修复 |
