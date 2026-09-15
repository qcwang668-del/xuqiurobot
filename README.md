# 需求搜集智能工作台

基于企业微信智能机器人 + AI 大模型的产品需求搜集管理系统。成员在机器人会话窗口提交文字需求，AI 自动整理提炼并在会话内推送确认卡片，确认后进入统一需求池管理。

## 目录结构

```text
app/
  server/            后端（FastAPI + SQLite）
    app/
      main.py        应用入口（含前端静态资源托管与 SPA 回退）
      pipeline.py    核心业务管线（上报缓冲、提炼、确认/修改/忽略、相似归并、催办）
      llm.py         方舟大模型客户端（OpenAI 兼容协议）与本地模拟提炼
      bot.py         机器人适配层（mock 模拟 + 企微 SDK 长连接适配器骨架）
      broadcast.py   每日/每周播报与定时调度
      routers_core.py    登录、概览、待确认收件箱、需求池接口
      routers_admin.py   系统管理、播报、统计、模拟器接口
    run.py           启动脚本（127.0.0.1:8000）
    data/            运行时数据（app.db，首次启动自动建表）
  web/               前端（React + Vite + Ant Design）
PRD/                 需求文档与方案文档
```

## 快速启动

1. 安装后端依赖（Python 3.12+）：

```bash
pip install -r app/server/requirements.txt
```

2. 构建前端（Node 18+，已构建可跳过）：

```bash
cd app/web
npm install
npm run build
```

3. 启动服务：

```bash
cd app/server
python run.py
```

4. 浏览器访问 http://127.0.0.1:8000 ，初始账号：

| 账号 | 密码 | 角色 |
| --- | --- | --- |
| admin | admin123 | 系统管理员 |
| leader | leader123 | 产品负责人 |
| member | member123 | 成员（王雁） |

## 配置说明

### 大模型（系统管理 → 模型配置）

- Base URL：`https://ark.cn-beijing.volces.com/api/coding/v3`（OpenAI 兼容协议）
- 模型名称：`ark-code-latest`
- API Key：在配置页输入，加密存储不回显；未配置时系统使用本地模拟提炼（仅用于联调）
- 相似度阈值：默认 0.85；配置 API Key 后相似需求由大模型语义判定，未配置时使用本地文本比对（阈值自动放宽至 0.5 便于演示）

### 机器人（系统管理 → 机器人配置）

- 默认 `本地模拟` 模式：通过网页「机器人模拟器」收发消息，流程与真实企微机器人一致
- 群聊 @机器人 收集需求时，消息中的提出人为机器人作用域 OpenID（wo 开头），系统通过「系统管理 → 成员管理」中维护的 企微 UserID/群聊 OpenID 映射解析为成员姓名；群消息会记录群上下文，确认卡片与回复发往所在群；@提及前缀会自动剥离
- 接入真实机器人：在企业微信管理后台获取智能机器人 Bot ID 与 Secret，填入配置并切换 `企微长连接` 模式；长连接按后台「API 配置 - 配置指引」使用官方 SDK 完成对接（`app/server/app/bot.py` 中 `WeComBotAdapter` 为接入点）
- 也可通过环境变量注入：`WECOM_BOT_ID`、`WECOM_BOT_SECRET`、`ARK_API_KEY`、`ARK_BASE_URL`、`ARK_MODEL`

### 播报（系统管理 → 播报配置）

- 配置每日/每周播报时间与目标群 Webhook 后，系统自动定时推送
- 未配置 Webhook 时播报仅生成记录不推送；「汇总播报」页支持手动生成与补发

## 机器人会话指令

| 指令 | 说明 |
| --- | --- |
| 直接发送文字 | 上报需求，5 分钟内连续消息自动合并为一条 |
| 确认 | 确认入池，回执需求编号 |
| 修改：你的意见 | AI 结合意见重新提炼（每条最多 3 轮） |
| 忽略 | 归档卡片，网页端已忽略列表可恢复 |
| 合并 / 新建 | 检测到相似需求时选择合并（提出次数+1）或仍新建 |
| 帮助 | 查看使用说明 |

## 接口文档

启动后访问 http://127.0.0.1:8000/docs 查看 Swagger 接口文档。
