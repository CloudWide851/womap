# WOMAP

通用地图数据查看与图斑轻量编辑工具的基础工程。

## 技术栈

- 后端：uv + Python 3.12 + FastAPI + SQLAlchemy 2
- 前端：Vite + React + TypeScript + OpenLayers + Ant Design
- 缓存：Redis，通过本地 `.env.local` 配置
- 数据库：PostgreSQL，通过本地 `.env.local` 配置
- 测试数据库：SQLite `.db` 文件

## 本地启动

```powershell
uv sync
uv run uvicorn app.main:app --reload
```

```powershell
cd frontend
pnpm install
pnpm dev
```

复制 `.env.example` 为 `.env.local` 后按本机环境修改连接信息。
