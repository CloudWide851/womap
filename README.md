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

前端脚本使用 Vite/Vitest 的 `--configLoader native`，用于避开当前 Windows 受限环境中 `net use` realpath 探测导致的 `spawn EPERM`。手动运行 `pnpm dev` 时，Vite 会优先读取 `config/settings.local.yaml` 中的 `frontend.dev_server.host/port`；也可以显式覆盖：

```powershell
cd frontend
pnpm dev --host 127.0.0.1 --port 9173
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

示例配置默认前端端口为 `5173`；本地 `config/settings.local.yaml` 可以改为其他端口，例如与本机 CORS 配置对齐的 `9173`。启动器和 Vite dev server 都会优先读取本地 YAML 中的 `server.host/port` 和 `frontend.dev_server.host/port`。Vite 会严格绑定配置端口，端口被占用时需要先释放端口或调整 YAML。

启动器退出交互面板时会尽力关闭它启动的 API/Web 服务；外部占用同一端口的进程只会显示为 `listening`，不会被自动终止。

## 导出能力

后端提供 `POST /api/v1/exports`，支持将后端数据库中的真实图层导出为 `SHP` 或 `FileGDB` zip：

```json
{
  "format": "shp",
  "layer_ids": [1, 2]
}
```

- `format` 可选 `shp` 或 `gdb`。
- `SHP` 导出会为字段名生成 Shapefile 兼容短名，并在 zip 中写入 `field-map.json`。
- `GDB` 指 Esri File Geodatabase 目录，最终以 zip 下载。
- 导出依赖 `geopandas`、`pyogrio` 和底层 GDAL 驱动；驱动不可用时接口返回明确错误，不生成假文件。
- 当前前端示例图层不是后端真实数据，只有加载到后端数据库的图层才会被导出。

## 地图工具

工作台左侧“地图工具”面板提供两类前端工具：

- 坐标转换：支持 `EPSG:4326`、`EPSG:3857`、`GCJ-02`、`BD-09`。Web Mercator 转换使用 OpenLayers `ol/proj`，GCJ-02/BD-09 为常用网页底图坐标换算。
- 两期影像卷帘：从已启用底图中选择前期和后期，使用 OpenLayers 图层渲染裁剪比较两期底图。当前能力比较配置底图，不伪造后端遥感影像成果。
