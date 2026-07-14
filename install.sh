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

# 检测包管理器（Kylin V11 默认 dnf，向下兼容 yum）
if command -v dnf &> /dev/null; then
    PKG_MGR="dnf"
elif command -v yum &> /dev/null; then
    PKG_MGR="yum"
else
    echo "[error] 未找到 yum/dnf 包管理器，脚本无法继续"
    exit 1
fi
echo "  使用包管理器: $PKG_MGR"

# ★ 系统依赖白名单（每一项都是踩过坑总结出来的，缺一不可）★
#   - git                : 克隆项目（评委机可能没预装）
#   - gcc / gcc-c++ / make: C/C++ 编译（chroma-hnswlib、numpy 需要）
#   - python3-devel       : Python.h 头文件（编译 C 扩展必需）
#   - libffi-devel        : cryptography/cffi 编译需要
#   - openssl-devel       : cryptography 编译需要
#   - pkg-config          : 各种 configure 脚本需要
#   - gcc-gfortran / libgfortran : numpy 编译需要
#   - openblas / openblas-devel  : numpy 线性代数（关键，避免 _gfortran_concat_string 符号错误）
#   - lapack / lapack-devel      : numpy 线性代数
#   - rust / cargo               : maturin / pydantic-core Rust 编译器（关键）
#   - sqlite-devel               : chromadb 用 sqlite 后端
#   - zlib-devel                 : Pillow / pypdf 需要
BASE_PKGS="git gcc gcc-c++ make python3-devel libffi-devel openssl-devel pkg-config \
           gcc-gfortran libgfortran openblas openblas-devel lapack lapack-devel \
           rust cargo sqlite-devel zlib-devel"

echo "  安装基础编译依赖: $BASE_PKGS"
sudo $PKG_MGR install -y $BASE_PKGS || {
    echo "[error] 基础系统依赖安装失败，请检查 $PKG_MGR 源配置"
    echo "  可尝试手动执行: sudo $PKG_MGR install -y $BASE_PKGS"
    exit 1
}

# ★ 装完立刻校验 —— 任何一个缺失都直接退出，别让后面莫名其妙崩 ★
MISSING=""
for cmd in git gcc g++ make python3 gfortran rustc cargo; do
    if ! command -v $cmd &> /dev/null; then
        MISSING="$MISSING $cmd"
    fi
done
if [ -n "$MISSING" ]; then
    echo "[error] 以下命令安装后仍不可用:$MISSING"
    echo "  请检查 $PKG_MGR 源是否配置正确，或手动补装对应包"
    exit 1
fi

echo "  ✓ gcc:      $(gcc --version | head -1)"
echo "  ✓ gfortran: $(gfortran --version | head -1)"
echo "  ✓ rustc:    $(rustc --version)"
echo "  ✓ cargo:    $(cargo --version)"
echo "  ✓ python3:  $(python3 --version)"
echo "  ✓ git:      $(git --version)"

# OCR 依赖（可选，失败不中断）
echo "  安装 OCR 依赖（可选）..."
sudo $PKG_MGR install -y tesseract tesseract-langpack-chi_sim poppler-utils 2>&1 | tail -3 || \
    echo "  [warn] OCR 依赖安装失败，扫描版 PDF 识别降级"

# Nginx（可选，失败自动切 Python 兜底）
if ! command -v nginx &> /dev/null; then
    echo "  安装 Nginx..."
    sudo $PKG_MGR install -y nginx 2>&1 | tail -3 || {
        echo "  默认源无 nginx，尝试 EPEL 源..."
        sudo $PKG_MGR install -y epel-release 2>/dev/null || true
        sudo $PKG_MGR install -y nginx 2>&1 | tail -3 || {
            echo "  [警告] Nginx 安装失败，将使用 Python 内置服务器托管前端"
        }
    }
fi

# ---------- 3. 创建 Python 虚拟环境 ----------
echo ""
echo "[3/9] 创建 Python 虚拟环境..."
if [ ! -d "$VENV_DIR" ]; then
    # 用真实用户身份创建，避免 root 属主导致后续无法清理
    sudo -u "$REAL_USER" python3 -m venv "$VENV_DIR"
fi
# 无论是否新建，都强制修正属主，防止历史残留权限错误
chown -R "$REAL_USER:$REAL_USER" "$VENV_DIR"
source "$VENV_DIR/bin/activate"
pip install --upgrade pip setuptools wheel

# ---------- 4. 编译安装 Python 依赖 ----------
echo ""
echo "[4/9] 编译安装 Python 依赖（LoongArch 兼容模式）..."
cd "$PROJECT_DIR"
bash deploy_loongarch.sh "$BACKEND_DIR" "$VENV_DIR"

# 编译安装后再次修正属主（编译过程会写入大量文件，防止属主偏移）
chown -R "$REAL_USER:$REAL_USER" "$VENV_DIR"

# 修正整个项目目录属主（关键：sudo git clone 会导致 backend/data/*.db 属主 root，
# 触发 SQLite "attempt to write a readonly database" 让后端启动失败）
chown -R "$REAL_USER:$REAL_USER" "$PROJECT_DIR"

# ---------- 5. 配置环境变量 ----------
echo ""
echo "[5/9] 配置环境变量..."
cd "$BACKEND_DIR"
if [ ! -f .env ]; then
    cp .env.example .env
    # 生成随机 JWT_SECRET，避免生产安全检查阻止启动
    JWT_SECRET_VAL=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    sed -i "s|^JWT_SECRET=.*|JWT_SECRET=$JWT_SECRET_VAL|" .env
    # 龙芯环境默认开启调试模式（评委演示场景）
    sed -i 's|ALLOW_INSECURE_JWT=.*|ALLOW_INSECURE_JWT=true|' .env
    sed -i 's|DEBUG=.*|DEBUG=true|' .env
    echo "  .env 已创建，JWT_SECRET 已自动生成随机值"
    echo "  需要手动填入 DASHSCOPE_API_KEY: vi $BACKEND_DIR/.env"
else
    echo "  .env 已存在"
fi
# 保证 .env 属主是真实用户
chown "$REAL_USER:$REAL_USER" .env 2>/dev/null || true

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

    # 关键：Kylin 默认 /etc/nginx/nginx.conf 里有个 default_server 会抢占 80 端口
    # 把它的 default_server 标记去掉，让咱们的 conf.d/loongchip.conf 生效
    if [ -f /etc/nginx/nginx.conf ]; then
        sudo cp /etc/nginx/nginx.conf /etc/nginx/nginx.conf.bak 2>/dev/null || true
        sudo sed -i 's/listen[[:space:]]*80[[:space:]]*default_server;/listen 80;/g' /etc/nginx/nginx.conf
        sudo sed -i 's/listen[[:space:]]*\[::\]:80[[:space:]]*default_server;/listen [::]:80;/g' /etc/nginx/nginx.conf
    fi
    # 备份并禁用可能存在的默认站点配置
    [ -f /etc/nginx/conf.d/default.conf ] && sudo mv /etc/nginx/conf.d/default.conf /etc/nginx/conf.d/default.conf.bak 2>/dev/null || true

    cat << 'NGINXEOF' | sudo tee "$NGINX_CONF" > /dev/null
server {
    listen       80 default_server;
    listen       [::]:80 default_server;
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
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
        client_max_body_size 50m;
    }

    location /uploads/ {
        proxy_pass http://127.0.0.1:8000;
    }
}
NGINXEOF
    sudo sed -i "s|FRONTEND_DIST_PLACEHOLDER|$FRONTEND_DIR/dist|" "$NGINX_CONF"

    # 保证 Nginx 能读到用户家目录下的 dist（nginx 用户需要 755 权限沿路径下钻）
    chmod 755 "$REAL_HOME" 2>/dev/null || true
    chmod -R 755 "$FRONTEND_DIR/dist" 2>/dev/null || true

    # SELinux 拦 Nginx 读用户家目录时会 403；Kylin 默认 Enforcing，临时放开
    if command -v setenforce &> /dev/null; then
        sudo setenforce 0 2>/dev/null || true
    fi
    if command -v sestatus &> /dev/null && [ -f /etc/selinux/config ]; then
        sudo sed -i 's/^SELINUX=enforcing/SELINUX=permissive/' /etc/selinux/config 2>/dev/null || true
    fi

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
ExecStart=VENV_BIN_PLACEHOLDER/python3 -m http.server 8080 --bind 0.0.0.0
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
