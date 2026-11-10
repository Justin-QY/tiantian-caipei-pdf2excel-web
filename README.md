# 天天采配清单 PDF 转 Excel · 网页版

把「天天采配」导出的商品清单 PDF，按原始分表结构转换成排好版的 Excel，通过浏览器访问，不需要安装客户端。

> 需要 Windows 桌面客户端？那是另一个独立项目：[tiantian-caipei-pdf2excel](https://github.com/Justin-QY/tiantian-caipei-pdf2excel)

![platform](https://img.shields.io/badge/platform-Docker%20%2F%20Linux-blue)
![python](https://img.shields.io/badge/python-3.12-3776AB)
![server](https://img.shields.io/badge/server-waitress-2C7FB8)

---

## 功能

- 浏览器上传 / 拖放 / 添加整个文件夹，勾选要转换的文件
- 表结构自动识别：中农/含费价（11 列）与品牌价（9 列）分别归位；跨页断行复原
- 两种输出：单工作表（多段连续排版，不冻结表头）/ 多工作表（每表独立冻结）
- 自定义文件名；多个结果自动打包成 zip
- 转换前确认框：列出勾选数量、输出方式、文件名，绿色「开始」/ 灰色「取消」
- 实时进度条 + 完整处理日志（解析、警告、失败明细）
- 右上角服务三态：**就绪**（绿，服务正常）/ **进行**（黄，处理中）/ **异常**（红，无法处理）
- 上传的 PDF 转换完即删除；结果文件保留 30 分钟，可重复下载
- 访问口令 + 按 IP 限流，适合挂到公网
- 支持子路径部署，例如 `https://your-domain.com/ttqd/`，可与已有主站共存

## 快速开始（Docker）

```bash
cp .env.example .env
# 编辑 .env，务必设置自己的 ACCESS_CODE
sudo docker compose up -d --build
```

容器只监听 `127.0.0.1:8765`，公网访问请用 nginx 反向代理，配置参考 `nginx.conf.example`。

不使用 Docker 时可执行 `sudo bash deploy.sh`：安装到 `/opt/pdf2xlsx`、建 venv、生成随机口令并注册 `pdf2xlsx.service`。

## 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `ACCESS_CODE` | 必填 | 访问口令；分享链接用 `#code=<口令>` |
| `PORT` | `8765` | 后端监听端口 |
| `HOST` | `0.0.0.0` | 容器内监听地址 |
| `THREADS` | `4` | waitress 工作线程数 |
| `MAX_UPLOAD_MB` | `50` | 单个请求上传上限 |
| `CHANNEL_TIMEOUT` | `300` | 任务事件通道超时（秒） |

口令只保存在服务器的 `.env`（权限 600），仓库里仅有 `.env.example` 占位符，不含任何真实口令。

## 反向代理与限流

- `nginx.conf.example`：子路径用 `location ^~ /ttqd/` → `proxy_pass http://127.0.0.1:8765/;`。上传接口缺少 `X-Access-Code` 请求头时，nginx 在 rewrite 阶段直接返回 403，不会接收请求体，避免浪费带宽和后端资源。
- `nginx-limits.conf.example`：按 IP 限流（上传 10r/m、burst 4；并发上传 4 / 其他 10），必须放在 nginx 的 **http 上下文**（宝塔面板对应 `/www/server/panel/vhost/nginx/*.conf`）。
- 前端从 `location.pathname` 自动推导接口前缀，子路径和根路径部署都无需改代码。
- 完整部署步骤、调参、429 排错与回滚见 `部署说明.txt`。

## 目录结构

```
app.py                     Flask 路由、任务队列、口令校验、结果清理
converter_core.py          PDF 解析 + Excel 排版（与桌面版共用）
static/index.html          单页前端（磨玻璃 UI、确认框、三态、日志）
requirements.txt           flask / pdfplumber / openpyxl / waitress
Dockerfile, docker-compose.yml
deploy.sh                  裸机 systemd 部署
init-env.sh                生成 .env 与随机口令
nginx.conf.example         反向代理片段
nginx-limits.conf.example  IP 限流 zone
部署说明.txt               运维手册
```

## 技术栈

- 后端：Flask + Waitress（生产 WSGI），Python 3.12
- 解析：pdfplumber；输出：openpyxl
- 前端：原生 HTML/CSS/JS，`backdrop-filter` 磨玻璃
- 部署：Docker Compose 或 systemd + nginx 反向代理
