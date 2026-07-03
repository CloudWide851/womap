# WOMAP

通用地图数据查看与图斑轻量编辑工具的基础工程。

## 技术栈

- 后端：uv + Python 3.12 + FastAPI + SQLAlchemy 2
- 前端：Vite + React + TypeScript + OpenLayers + Ant Design
- 缓存：Redis，通过本地 `config/settings.local.yaml` 配置
- 数据库：PostgreSQL，通过本地 `config/settings.local.yaml` 配置
- 测试数据库：SQLite `.db` 文件

## 本地启动

Windows 下优先使用根目录启动器：

```powershell
.\start-womap.bat
```

常用命令：

```powershell
.\start-womap.bat status
.\start-womap.bat doctor
.\start-womap.bat dev
.\start-womap.bat open
.\start-womap.bat stop
.\start-womap.bat test
```

也可以手动启动后端和前端：

```powershell
uv sync
uv run uvicorn app.main:app --reload
```

```powershell
cd frontend
pnpm install
pnpm dev
```

复制 `config/settings.example.yaml` 为忽略的 `config/settings.local.yaml` 后按本机环境修改连接信息。

启动端口也在同一个 YAML 中配置：

```yaml
server:
  host: 127.0.0.1
  port: 8000

frontend:
  dev_server:
    host: 127.0.0.1
    port: 5173
```

示例配置默认前端端口为 `5173`；本地 `config/settings.local.yaml` 可以改为其他端口，例如与本机 CORS 配置对齐的 `9173`。启动器会优先读取本地 YAML 中的 `server.host/port` 和 `frontend.dev_server.host/port`。

启动器退出交互面板时会尽力关闭它启动的 API/Web 服务；外部占用同一端口的进程只会显示为 `listening`，不会被自动终止。
