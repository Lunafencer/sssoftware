# =========================================================
# 后端：FastAPI + SQLAlchemy + Chroma + DashScope
# 镜像：python:3.11-slim
# =========================================================
FROM python:3.11-slim AS backend

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Shanghai

# 换清华源（容器构建时不走宿主机代理，直接走国内镜像更稳）
# python:3.11-slim 基于 debian trixie，sources 是 deb822 格式
RUN sed -i 's|http://deb.debian.org|https://mirrors.tuna.tsinghua.edu.cn|g; s|http://security.debian.org|https://mirrors.tuna.tsinghua.edu.cn|g' \
        /etc/apt/sources.list.d/debian.sources 2>/dev/null || true

# 系统依赖：
#  - build-essential / gcc：编译 chromadb / pydantic 等 native 扩展
#  - libmagic1：python-magic 探测文件类型时可能用到
#  - fonts-noto-cjk / fonts-wqy-microhei：PDF 导出 CJK 字体回退链 (FIX6 第 7 项)
#  - tzdata：时区
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        libmagic1 \
        fonts-noto-cjk \
        fonts-wqy-microhei \
        tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先装依赖，利用缓存层（pip 走清华镜像）
COPY requirements.txt /app/requirements.txt
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple \
 && pip install --upgrade pip \
 && pip install -r requirements.txt

# 拷贝应用代码
COPY app /app/app

# 运行时数据目录（与 settings 默认值对齐：相对 /app 工作目录）
RUN mkdir -p /app/uploads /app/chroma_db

EXPOSE 8000

# 生产模式：gunicorn + uvicorn worker
# 单 worker 是因为 SQLite + ChromaDB 本地存储不适合多进程并发写。
# 如需多 worker，请切换到 Postgres + 远端 Chroma。
CMD ["gunicorn", "app.main:app", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "-w", "1", \
     "-b", "0.0.0.0:8000", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
