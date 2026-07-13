#!/bin/bash
# ========================================================
# 设备检修知识检索与作业系统
# LoongArch + 银河麒麟高级服务器版 V11 一键部署脚本
# ========================================================
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR"
REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME=$(getent passwd "$REAL_USER" | cut -d: -f6)
VENV_DIR="$REAL_HOME/venv"

echo "================================================"
echo "  设备检修知识检索与作业系统"
echo "  部署环境：LoongArch64 + 银河麒麟 V11"
echo "================================================"

# ---------- 1. 检查架构 ----------
echo ""
echo "[1/9] 检查系统架构..."
ARCH=$(uname -m)
echo "  当前架构: $ARCH"
if [[ "$ARCH" != "loongarch64" ]]; then
    echo "  [警告] 当前架构非 loongarch64，赛题要求 LoongArch 架构"
    echo "  继续部署（仅测试用）..."
fi

# ---------- 2. 安装系统依赖 ----------
echo ""
echo "[2/9] 安装系统依赖..."

# 先装基础编译工具
sudo yum install -y libffi-devel pkg-config openssl-devel gcc gcc-c++ make python3-devel 2>/dev/null || \
sudo dnf install -y libffi-devel pkg-config openssl-devel gcc gcc-c++ make python3-devel 2>/dev/null || \
echo "[warn] 部分系统包可能需要手动安装"

# OCR 依赖（可选）
sudo yum install -y tesseract tesseract-langpack-chi_sim poppler-utils 2>/dev/null || \
sudo dnf install -y tesseract tesseract-langpack-chi_sim poppler-utils 2>/dev/null || \
echo "[warn] OCR 依赖安装失败，不影响核心功能"

# Nginx：Kylin V11 默认源可能没有，尝试 EPEL 源
if ! command -v nginx &> /dev/null; then
    echo "  尝试安装 Nginx..."
    sudo yum install -y nginx 2>/dev/null || {
        echo "  默认源无 nginx，尝试 EPEL 源..."
        sudo yum install -y epel-release 2>/dev/null
        sudo yum install -y nginx 2>/dev/null || {
            echo "  [警告] Nginx 安装失败"
            echo "  将使用 Python 内置服务器托管前端静态资源"
        }
    }
fi

# ---------- 3. 创建 Python 虚拟环境 ----------
echo ""
echo "[3/9] 创建 Python 虚拟环境..."
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"
pip install --upgrade pip setuptools wheel

# ---------- 4. 编译安装 Python 依赖 ----------
echo ""
echo "[4/9] 编译安装 Python 依赖（LoongArch 兼容模式）..."
cd "$PROJECT_DIR"
bash deploy_loongarch.sh "$BACKEND_DIR" "$VENV_DIR"

# ---------- 5. 配置环境变量 ----------
echo ""
echo "[5/9] 配置环境变量..."
cd "$BACKEND_DIR"
if [ ! -f .env ]; then
    cp .env.example .env
    # 龙芯环境默认开启调试模式
    sed -i 's|ALLOW_INSECURE_JWT=.*|ALLOW_INSECURE_JWT=true|' .env
    sed -i 's|DEBUG=.*|DEBUG=true|' .env
    echo "  .env 已创建，需要填入 DASHSCOPE_API_KEY"
    echo "  编辑: vi $BACKEND_DIR/.env"
else
    echo "  .env 已存在"
fi

# ---------- 6. 前端 ----------
echo ""
echo "[6/9] 检查前端..."
cd "$FRONTEND_DIR"
if [ -d "$FRONTEND_DIR/dist" ] && [ -f "$FRONTEND_DIR/dist/index.html" ]; then
    echo "  dist/ 已存在（预构建），跳过"
elif command -v node &> /dev/null; then
    echo "  dist/ 不存在，用 Node.js 构建..."
    npm config set registry https://registry.npmmirror.com
    npm install
    npm run build
    echo "  前端构建完成"
else
    echo "  [错误] 无 Node.js 且无预构建 dist/，前端无法部署"
    exit 1
fi

# ---------- 7. 配置 Web 服务器 ----------
echo ""
echo "[7/9] 配置 Web 服务器..."

if command -v nginx &> /dev/null; then
    # 有 Nginx：用 Nginx 托管前端 + 反向代理 API
    echo "  使用 Nginx 托管前端"
    NGINX_CONF="/etc/nginx/conf.d/loongchip.conf"
    sudo mkdir -p /etc/nginx/conf.d
    cat << 'NGINXEOF' | sudo tee "$NGINX_CONF" > /dev/null
server {
    listen       80;
    server_name  _;

    root   FRONTEND_DIST_PLACEHOLDER;
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
NGINXEOF
    sudo sed -i "s|FRONTEND_DIST_PLACEHOLDER|$FRONTEND_DIR/dist|" "$NGINX_CONF"
    sudo nginx -t 2>/dev/null && sudo systemctl enable nginx && sudo systemctl restart nginx || echo "[warn] Nginx 配置需检查"
    WEB_MODE="nginx"
else
    # 无 Nginx：用 Python http.server 托管前端（后台运行）
    echo "  Nginx 不可用，使用 Python 静态服务器托管前端"
    WEB_MODE="python"
fi

# ---------- 8. 注册 systemd 服务 ----------
echo ""
echo "[8/9] 注册 systemd 服务..."

# 8.1 后端服务
cat << SVCEOF | sudo tee /etc/systemd/system/loongchip-backend.service > /dev/null
[Unit]
Description=设备检修知识检索与作业系统-后端
After=network.target

[Service]
Type=simple
User=CURR_USER_PLACEHOLDER
WorkingDirectory=BACKEND_DIR_PLACEHOLDER
EnvironmentFile=BACKEND_DIR_PLACEHOLDER/.env
ExecStart=VENV_BIN_PLACEHOLDER/python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SVCEOF

sudo sed -i "s|CURR_USER_PLACEHOLDER|$REAL_USER|" /etc/systemd/system/loongchip-backend.service
sudo sed -i "s|BACKEND_DIR_PLACEHOLDER|$BACKEND_DIR|g" /etc/systemd/system/loongchip-backend.service
sudo sed -i "s|VENV_BIN_PLACEHOLDER|$VENV_DIR/bin|" /etc/systemd/system/loongchip-backend.service

# 8.2 如果没有 Nginx，注册前端静态服务器
if [ "$WEB_MODE" = "python" ]; then
    cat << FEOF | sudo tee /etc/systemd/system/loongchip-frontend.service > /dev/null
[Unit]
Description=设备检修知识检索与作业系统-前端静态服务
After=network.target

[Service]
Type=simple
User=CURR_USER_PLACEHOLDER
WorkingDirectory=FRONTEND_DIST_PLACEHOLDER
ExecStart=VENV_BIN_PLACEHOLDER/python3 -m http.server 80 --bind 0.0.0.0
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
FEOF
    sudo sed -i "s|CURR_USER_PLACEHOLDER|$REAL_USER|" /etc/systemd/system/loongchip-frontend.service
    sudo sed -i "s|FRONTEND_DIST_PLACEHOLDER|$FRONTEND_DIR/dist|" /etc/systemd/system/loongchip-frontend.service
    sudo sed -i "s|VENV_BIN_PLACEHOLDER|$VENV_DIR/bin|" /etc/systemd/system/loongchip-frontend.service
fi

sudo systemctl daemon-reload
sudo systemctl enable loongchip-backend
if [ "$WEB_MODE" = "python" ]; then
    sudo systemctl enable loongchip-frontend
fi

# ---------- 8.5 防火墙 ----------
echo ""
echo "[8.5/9] 配置防火墙..."
if command -v firewall-cmd &> /dev/null; then
    sudo firewall-cmd --permanent --add-port=8000/tcp 2>/dev/null || true
    if [ "$WEB_MODE" = "nginx" ]; then
        sudo firewall-cmd --permanent --add-service=http 2>/dev/null || true
    else
        sudo firewall-cmd --permanent --add-port=8080/tcp 2>/dev/null || true
    fi
    sudo firewall-cmd --reload 2>/dev/null || true
    echo "  防火墙已配置"
else
    echo "  firewalld 不可用，跳过（可能未启用防火墙）"
fi

# ---------- 9. 启动 ----------
echo ""
echo "[9/9] 启动服务..."
sudo systemctl start loongchip-backend
if [ "$WEB_MODE" = "python" ]; then
    sudo systemctl start loongchip-frontend
fi
sleep 3

if sudo systemctl is-active --quiet loongchip-backend; then
    echo ""
    echo "================================================"
    echo "  部署成功！"
    echo "================================================"
    if [ "$WEB_MODE" = "nginx" ]; then
        echo "  前端访问: http://<本机IP>"
    else
        echo "  前端访问: http://<本机IP>:8080"
        echo "  （使用 Python 静态服务器，建议后续安装 Nginx）"
    fi
    echo "  后端API:  http://<本机IP>:8000"
    echo "  管理员:   admin / 123456"
    echo ""
    echo "  服务管理:"
    echo "    启动: sudo systemctl start loongchip-backend"
    echo "    停止: sudo systemctl stop loongchip-backend"
    echo "    重启: sudo systemctl restart loongchip-backend"
    echo "    日志: sudo journalctl -u loongchip-backend -f"
    if [ "$WEB_MODE" = "python" ]; then
        echo "    前端: sudo systemctl restart loongchip-frontend"
    fi
    echo ""
    echo "  首次使用需配置 .env:"
    echo "    vi $BACKEND_DIR/.env"
    echo "    填入 DASHSCOPE_API_KEY"
    echo "    sudo systemctl restart loongchip-backend"
    echo "================================================"
else
    echo ""
    echo "[错误] 后端服务启动失败，请检查日志:"
    echo "  sudo journalctl -u loongchip-backend -n 50"
fi
