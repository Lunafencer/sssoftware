# 软件安装包及部署文档

## 赛题信息

- 赛题名称：基于多模态大模型技术的设备检修知识检索与作业系统
- 出题企业：龙芯中科技术股份有限公司
- 组类：A组

---

## 一、运行环境要求

| 项目 | 要求 |
|------|------|
| CPU 架构 | LoongArch（龙芯自主指令集） |
| CPU 核数 | 四核及以上 |
| 操作系统 | 银河麒麟高级服务器操作系统 V11/V10 |
| 内存 | 8GB 以上 |
| 硬盘 | 256GB 以上 |
| Python | 3.10+（系统自带） |
| Node.js | 18+（用于前端构建，可选） |
| 网络 | 需访问阿里云 DashScope API |

> **注意：赛题明确要求"软件需部署在自主指令系统LoongArch架构+银河麒麟高级服务器版上运行，不满足该要求视为0分"。**

---

## 二、安装包结构

```
software2026/
├── install.sh                ← 一键部署脚本
├── deploy_loongarch.sh       ← LoongArch 依赖编译脚本
├── DEPLOY.md                 ← 本文档
├── backend/                  ← 后端源码（FastAPI + Python）
│   ├── app/
│   │   ├── api/              路由模块（auth/chat/kb/kg/ticket/admin）
│   │   ├── core/             配置、数据库、安全、迁移
│   │   ├── models/           ORM 模型
│   │   ├── services/         LLM 调用、RAG 检索、文档解析
│   │   └── main.py           FastAPI 入口
│   ├── tests/                测试文件
│   ├── requirements.txt      Python 依赖清单
│   ├── .env.example          环境变量模板
│   └── Dockerfile
├── src/                      ← 前端源码（Vue 3 + TypeScript + Vite）
│   ├── api/                  后端接口调用
│   ├── assets/              样式资源
│   ├── components/          UI 组件（PC + Mobile）
│   ├── composables/        组合式函数
│   ├── layouts/             布局组件
│   ├── router/             路由
│   ├── stores/              Pinia 状态管理
│   ├── utils/              工具函数
│   └── views/              页面视图
├── public/                   静态资源
├── index.html                前端入口
├── package.json              前端依赖
├── vite.config.ts            Vite 构建配置
├── tsconfig.json             TypeScript 配置
├── tailwind.config.js        Tailwind CSS 配置
├── postcss.config.js         PostCSS 配置
└── README.md                 项目说明
```

---

## 三、一键部署

### 3.1 传输安装包

将安装包上传至龙芯虚拟机：

```bash
# 方式一：scp 上传
scp software2026.tar.gz vmuser@<虚拟机IP>:~/

# 方式二：通过共享文件夹或 U 盘拷贝
```

### 3.2 解压

```bash
cd ~
tar xzf software2026.tar.gz
cd software2026
```

### 3.3 执行一键部署

```bash
bash install.sh
```

部署脚本自动完成以下步骤：

1. 检查系统架构（loongarch64）
2. 安装系统依赖（gcc、nginx、tesseract 等）
3. 创建 Python 虚拟环境（~/venv）
4. 编译安装 Python 依赖（LoongArch 兼容模式，解决 Rust/pydantic-core 编译问题）
5. 生成 .env 配置文件
6. 构建前端静态资源（dist/）
7. 配置 Nginx 反向代理
8. 注册 systemd 服务（开机自启）
9. 启动后端服务

### 3.4 配置 API 密钥

部署完成后需配置大模型 API 密钥：

```bash
cd ~/software2026/backend
vi .env
```

修改以下内容：

```env
DASHSCOPE_API_KEY=你的阿里云百炼API密钥
ALLOW_INSECURE_JWT=true
DEBUG=true
```

保存后重启服务：

```bash
sudo systemctl restart loongchip
```

---

## 四、手动部署（如一键脚本失败）

### 4.1 安装系统依赖

```bash
sudo yum install -y libffi-devel pkg-config openssl-devel gcc gcc-c++ make python3-devel nginx
sudo yum install -y tesseract tesseract-langpack-chi_sim poppler-utils
```

### 4.2 创建 Python 虚拟环境

```bash
cd ~
python3 -m venv venv
source ~/venv/bin/activate
pip install --upgrade pip setuptools wheel
```

### 4.3 编译安装 Python 依赖

LoongArch 架构下部分包需要源码编译，执行专用脚本：

```bash
cd ~/software2026
bash deploy_loongarch.sh
```

该脚本解决了以下 LoongArch 兼容性问题：
- maturin 编译 pydantic-core
- bcrypt 纯 C 编译（不依赖 Rust）
- chromadb 跳过 onnxruntime
- 锁定 pydantic v2.7.4 版本

### 4.4 配置环境变量

```bash
cd ~/software2026/backend
cp .env.example .env
vi .env
```

填入：

```env
DASHSCOPE_API_KEY=sk-你的密钥
ALLOW_INSECURE_JWT=true
DEBUG=true
```

### 4.5 构建前端

```bash
cd ~/software2026
sudo yum install -y nodejs npm   # 如未安装
npm config set registry https://registry.npmmirror.com
npm install
npm run build
```

构建产物在 `dist/` 目录。

### 4.6 配置 Nginx

```bash
sudo vi /etc/nginx/conf.d/loongchip.conf
```

写入（替换路径中的 vmuser 为实际用户名）：

```nginx
server {
    listen       80;
    server_name  _;

    root   /home/vmuser/software2026/dist;
    index  index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        client_max_body_size 50m;
    }
}
```

```bash
sudo nginx -t
sudo systemctl enable nginx
sudo systemctl restart nginx
```

### 4.7 注册后端服务

```bash
sudo vi /etc/systemd/system/loongchip.service
```

写入：

```ini
[Unit]
Description=设备检修知识检索与作业系统-后端
After=network.target

[Service]
Type=simple
User=vmuser
WorkingDirectory=/home/vmuser/software2026/backend
EnvironmentFile=/home/vmuser/software2026/backend/.env
ExecStart=/home/vmuser/venv/bin/python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable loongchip
sudo systemctl start loongchip
```

### 4.8 防火墙放行

```bash
sudo firewall-cmd --add-port=80/tcp --permanent
sudo firewall-cmd --reload
```

---

## 五、验证部署

### 5.1 检查后端

```bash
curl http://127.0.0.1:8000/api/health
```

返回 `{"status":"ok"}` 即正常。

### 5.2 检查前端

浏览器访问 `http://<虚拟机IP>`，应看到登录页面。

### 5.3 登录系统

- 用户名：`admin`
- 密码：`123456`

### 5.4 测试知识检索

1. 登录后进入「知识库管理」→「上传文档」
2. 上传一份检修手册（PDF/DOCX）
3. 等待向量化完成
4. 进入「知识检索」提问测试

---

## 六、服务管理

| 操作 | 命令 |
|------|------|
| 启动后端 | `sudo systemctl start loongchip` |
| 停止后端 | `sudo systemctl stop loongchip` |
| 重启后端 | `sudo systemctl restart loongchip` |
| 查看状态 | `sudo systemctl status loongchip` |
| 查看日志 | `sudo journalctl -u loongchip -f` |
| 重启 Nginx | `sudo systemctl restart nginx` |
| 开机自启 | `sudo systemctl enable loongchip`（部署时已设置） |

---

## 七、故障排查

### 后端启动失败

```bash
# 查看详细日志
sudo journalctl -u loongchip -n 100

# 手动启动排查
cd ~/software2026/backend
source ~/venv/bin/activate
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

常见原因：
- `.env` 中 `DASHSCOPE_API_KEY` 未填写 → 补填后重启
- `ALLOW_INSECURE_JWT` 未设为 `true` → 修改 `.env`
- Python 依赖未装全 → 重新执行 `bash deploy_loongarch.sh`

### 前端页面空白

```bash
# 检查 Nginx 配置
sudo nginx -t

# 确认前端已构建
ls ~/software2026/dist/index.html

# 重启 Nginx
sudo systemctl restart nginx
```

### API 返回 500

```bash
# 检查后端日志
sudo journalctl -u loongchip -n 50

# 常见原因：DashScope 欠费或 API Key 无效
# 登录阿里云百炼控制台检查
```

### 向量检索无结果

```bash
# 检查向量库
ls ~/software2026/backend/chroma_db/

# 如果为空，需要上传知识文档后重建
```

---

## 八、默认账号

| 角色 | 用户名 | 密码 | 权限 |
|------|--------|------|------|
| 管理员 | admin | 123456 | 全部功能 |
| 审核员 | auditor | 123456 | 知识审核 + 检索 |
| 一线人员 | worker | 123456 | 检索 + 工单 |

> 首次部署后建议修改默认密码。

---

## 九、技术架构概览

| 层 | 技术选型 |
|------|------|
| 前端框架 | Vue 3 + Vite + TypeScript + Pinia |
| UI 组件 | Element Plus + Vant + Tailwind CSS |
| 后端框架 | FastAPI（Python） |
| ORM | SQLAlchemy |
| 数据库 | SQLite |
| 向量数据库 | ChromaDB |
| 大语言模型 | Qwen-plus（阿里云 DashScope） |
| 多模态模型 | Qwen-VL-Max |
| 嵌入模型 | text-embedding-v3 |
| 鉴权 | JWT |
| Web 服务器 | Nginx |
| 应用服务器 | Uvicorn |
| 进程管理 | systemd |
