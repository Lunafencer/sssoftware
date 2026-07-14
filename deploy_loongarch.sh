#!/bin/bash
# 龙芯 LoongArch64 + Kylin V11 部署脚本
# 解决 Rust 1.82 兼容性、onnxruntime 缺失等问题
set -e

# 接收参数：$1=BACKEND_DIR, $2=VENV_DIR
BACKEND_DIR="${1:-$(pwd)/backend}"
VENV_DIR="${2:-$HOME/venv}"

# 激活已有的虚拟环境（install.sh 已创建）
if [ -f "$VENV_DIR/bin/activate" ]; then
    source "$VENV_DIR/bin/activate"
fi

echo "===== Phase 3: 安装 maturin + 构建依赖 ====="
pip install "maturin==1.7.8"
# typing-extensions 必须在编译 pydantic-core 前安装
# 因为 --no-build-isolation 模式下，构建脚本 generate_self_schema.py 需要 import typing_extensions
pip install typing-extensions

echo "===== Phase 4: 编译 pydantic-core（复用已装 maturin，跳过隔离构建）====="
pip install --no-build-isolation "pydantic-core==2.18.4"

echo "===== Phase 5: pydantic v2（不拉依赖，core 已手动装好）====="
pip install "pydantic==2.7.4" --no-deps
pip install annotated-types "typing-inspection>=0.4.2"

echo "===== Phase 6: cffi + cryptography（42 版用 cffi，不需要 maturin）====="
pip install cffi
pip install "cryptography==42.0.8"

echo "===== Phase 7: bcrypt 4.0（纯 C，不需要 Rust）====="
pip install "bcrypt==4.0.1"

echo "===== Phase 8: FastAPI 生态（锁版本，不拉最新 pydantic）====="
pip install "starlette==0.37.2"
pip install "fastapi==0.111.0" --no-deps
pip install "uvicorn==0.30.6"
pip install gunicorn
pip install python-multipart
pip install Jinja2

echo "===== Phase 9: 数据库 + 鉴权 ====="
pip install pydantic-settings
pip install sqlalchemy
pip install python-jose ecdsa rsa pyasn1

echo "===== Phase 10: DashScope + 文档处理 ====="
pip install dashscope
pip install pypdf python-docx reportlab
# Pillow: parser.py 的 _ocr_image_file 用 PIL.Image 打开图片（可选，失败降级到 Qwen-VL）
pip install pillow || echo "[warn] Pillow 安装失败，图片 OCR 降级到 Qwen-VL"
# 多模态问题修复第3项：OCR Python 依赖（扫描版 PDF 识别，失败不中断）
pip install pdf2image pytesseract || echo "[warn] OCR Python 包安装失败，扫描版 PDF 无法 OCR"

echo "===== Phase 11: chromadb（LoongArch 兼容安装）====="
# numpy 必须在 chroma-hnswlib 之前装，因为编译 chroma-hnswlib 需要 numpy
pip install numpy
pip install chroma-hnswlib || echo "[warn] chroma-hnswlib 编译失败，向量检索不可用"
# chromadb 0.4.24 用 --no-deps 避免 onnxruntime 等不兼容包
pip install "chromadb==0.4.24" --no-deps
# 手动安装 chromadb 0.4.24 的所有依赖（对照 vmuser 已验证 venv）
pip install pypika pyyaml tenacity tqdm importlib-resources httpx
pip install posthog overrides backoff typer rich click shellingham
# 以下包编译可能慢，逐个装，失败不影响核心功能
pip install mmh3 || echo "[warn] mmh3 编译失败，chromadb 降级运行"
pip install grpcio || echo "[warn] grpcio 编译失败，chromadb 降级运行"
pip install opentelemetry-api opentelemetry-sdk opentelemetry-proto opentelemetry-semantic-conventions opentelemetry-exporter-otlp-proto-common opentelemetry-exporter-otlp-proto-grpc || echo "[warn] opentelemetry 安装失败"
pip install kubernetes || echo "[warn] kubernetes 安装失败"

echo "===== Phase 12: 验证导入 ====="
BACKEND_DIR="${1:-$(pwd)/backend}"
cd "$BACKEND_DIR"
python -c "
import fastapi, uvicorn, pydantic, sqlalchemy, jose, bcrypt, dashscope, chromadb, pypdf, docx, reportlab
print('所有核心包导入成功')
from app.main import app
print('FastAPI app 创建成功')
" 2>&1

echo ""
echo "===== 安装完成 ====="
echo "如果上面显示'FastAPI app 创建成功'，说明环境就绪"
echo "下一步：配置 .env 并启动服务"
