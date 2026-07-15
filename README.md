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
database:
  host: 127.0.0.1
  ssl: false

server:
  host: 127.0.0.1
  port: 8000

frontend:
  dev_server:
    host: 127.0.0.1
    port: 5173
```

本地 PostgreSQL/PostGIS 默认使用 IPv4 `127.0.0.1` 且关闭 SSL；远程数据库需要时再显式设置 `database.ssl: true`。数据库 URL 由分离字段安全组装，不要把密码拼进连接字符串或日志。

示例配置默认前端端口为 `5173`；本地 `config/settings.local.yaml` 可以改为其他端口，例如与本机 CORS 配置对齐的 `9173`。启动器和 Vite dev server 都会优先读取本地 YAML 中的 `server.host/port` 和 `frontend.dev_server.host/port`。Vite 会严格绑定配置端口，端口被占用时需要先释放端口或调整 YAML。

`dev` 会先尝试 API、再尝试 Web，但两个启动动作彼此独立：API 启动失败时仍会继续启动 Web，全部尝试完成后统一返回失败状态；已经成功启动的服务不会因为另一项失败而被停止。就绪超时只清理本次 launcher 捕获并验证的进程树与记录。

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

## 工作空间与分享包

顶栏“工作空间”入口用于管理持久地图上下文。`本地工作台` 是不可删除的默认工作空间；也可以新建、另存为、重命名、切换和删除命名工作空间。工作空间保存底图、地图中心与缩放、图层顺序/显隐/透明度，以及每层“全部图斑”或“指定图斑”的选择。修改后需要显式保存；切换工作空间时会提供保存、放弃或取消。

工作空间只引用已经导入 PostGIS 的 GDB、SHP 和手工图层，不会直接扫描尚未导入的原始文件。导入图斑优先使用稳定的数据集/源图斑标识，手工图斑使用数据库 ID；删除工作空间定义不会删除可能被其他工作空间引用的数据。

工作空间可导出为 `*.womap.zip`，内容固定为：

- `manifest.json`：版本化工作空间定义和非敏感底图引用。
- `data.gpkg`：仅包含该工作空间实际选择的图层与图斑。
- `checksums.json`：包内容 SHA-256 校验。
- `README.txt`：简短使用说明。

分享包不包含 SMB 凭据、本地绝对路径、API key、会话信息、缓存目录或在线底图瓦片。导入会先展示名称、图层/图斑数量、版本、底图绑定和 UUID 冲突；默认创建副本，也可明确覆盖同 UUID 工作空间。覆盖先写 staging，全部成功后才替换。服务端同时拒绝路径穿越、绝对路径、符号链接、校验失败、未知新版清单和异常压缩包。

## 地图工具

地图右上角“工具”下拉集中提供四类工具，临时参数内容关闭后卸载，不再长期占用左右侧栏：

- 坐标转换：支持 `EPSG:4326`、`EPSG:3857`、`GCJ-02`、`BD-09`。Web Mercator 转换使用 OpenLayers `ol/proj`，GCJ-02/BD-09 为常用网页底图坐标换算。
- 两期影像卷帘：从已启用底图中选择前期和后期，使用 OpenLayers 图层渲染裁剪比较两期底图。当前能力比较配置底图，不伪造后端遥感影像成果。
- 空间分析：进入独立模式后拾取当前工作空间内可见的真实后端图斑，并执行缓冲相交分析。
- 性能：显示当前图层要素数、加载策略与告警；设置页“性能”开关控制该入口是否可用。

选择“两期卷帘”会立即退出编辑态并聚焦地图；关闭工具弹框不会关闭已启用的卷帘，可重新打开工具关闭卷帘，或切换顶部普通工作模式退出。

进入“图斑编辑”后，点击“绘制图斑”始终保持绘制态；重复点击会取消当前草图并等待新的首次双击。建层失败或目标图层受限时可在修正条件后再次点击重试，绘制态地图使用带 `crosshair` 回退的画笔光标。

## 空间分析

从地图右上角“工具 → 空间分析”进入分析模式。进入时会退出编辑、取消草图并关闭两期卷帘；地图右上角的“退出空间分析”按钮或 Escape 可回到浏览模式。点击当前工作空间中可见的真实图斑后，右侧详情可打开分析表单。

- 范围单位支持米、千米、英尺和英里；可分析工作空间全部参与图层或仅可见图层。
- 目标图斑自身会被排除，但同图层其他图斑仍参与。
- 结果按数据集、图层、图斑分级展示，也保留无命中分组；面图层显示直接/缓冲相交面积与覆盖比例，线图层显示相交长度，点图层显示点命中数。
- 分析使用 PostGIS geography 椭球距离、面积和长度，并先通过空间索引预筛选；只分析已经导入当前工作空间的数据，不处理未导入原文件或栅格。
- 任务支持进度、取消、历史重新打开、服务端分页和陈旧数据告警；结果可导出为包含 `summary.csv`、`hits.geojson` 与参数说明的 ZIP。
