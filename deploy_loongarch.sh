#!/bin/bash
# 龙芯 LoongArch64 + Kylin V11 部署脚本
# 解决 Rust 1.82 兼容性、numpy gfortran 符号、chromadb 依赖等一系列龙芯专属问题
# 本脚本经过 vmuser2 实机验证一键跑通
set -e

# 接收参数：$1=BACKEND_DIR, $2=VENV_DIR
BACKEND_DIR="${1:-$(pwd)/backend}"
VENV_DIR="${2:-$HOME/venv}"

# 激活已有的虚拟环境（install.sh 已创建）
if [ -f "$VENV_DIR/bin/activate" ]; then
    source "$VENV_DIR/bin/activate"
fi

# venv site-packages 目录（用于放置 stub 模块）
SITE_PACKAGES="$VENV_DIR/lib/python3.11/site-packages"
if [ ! -d "$SITE_PACKAGES" ]; then
    # 兼容 python3.10/3.12 等其它版本
    SITE_PACKAGES=$(python -c "import site; print(site.getsitepackages()[0])")
fi

echo "===== Phase 3: 安装 maturin + 构建依赖 ====="
pip install "maturin==1.7.8"
# typing-extensions 必须在编译 pydantic-core 前安装
# 因为 --no-build-isolation 模式下，构建脚本 generate_self_schema.py 需要 import typing_extensions
pip install typing-extensions
# pybind11 必须提前装，chroma-hnswlib 用 --no-build-isolation 编译时需要
pip install pybind11

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

echo "===== Phase 11: numpy 源码编译（关键：绕过 gfortran 符号版本问题）====="
# 龙芯上 PyPI 预编译的 numpy wheel 需要 _gfortran_concat_string 未版本化符号
# 但 Kylin V11 的 libgfortran.so.5 只提供 _gfortran_concat_string@@GFORTRAN_8 版本化符号
# 必须 --no-binary numpy 从源码编译，用本机 gfortran 12.3.1 重新链接
# 前置条件：Phase 2 已装 openblas-devel + lapack-devel
pip install --force-reinstall --no-deps --no-cache-dir --no-binary numpy "numpy==1.26.4"
# 验证 numpy 可用
python -c "import numpy; numpy.array([1,2,3]).sum()" || {
    echo "[error] numpy 编译失败或链接错误，请检查 openblas-devel/lapack-devel 是否已装"
    exit 1
}

echo "===== Phase 12: chroma-hnswlib（用已装的 numpy + pybind11 编译）====="
pip install --no-build-isolation "chroma-hnswlib==0.7.3" || echo "[warn] chroma-hnswlib 编译失败，向量检索性能降级"

echo "===== Phase 13: chromadb 0.4.24（--no-deps 避开 onnxruntime）====="
pip install "chromadb==0.4.24" --no-deps
# 手动装 chromadb 实际会 import 的运行时依赖（对照 vmuser 已验证 venv）
pip install pypika pyyaml tenacity tqdm importlib-resources httpx
pip install posthog overrides backoff typer rich click shellingham
pip install mmh3 || echo "[warn] mmh3 编译失败，chromadb 降级运行"

# opentelemetry：只装 http 版本，跳过需要 grpcio 的版本
pip install "opentelemetry-api>=1.20" "opentelemetry-sdk>=1.20" \
    opentelemetry-instrumentation opentelemetry-instrumentation-fastapi \
    "opentelemetry-exporter-otlp-proto-common>=1.20" \
    "opentelemetry-exporter-otlp-proto-http>=1.20" \
    opentelemetry-semantic-conventions || echo "[warn] opentelemetry 部分安装失败"

pip install kubernetes || echo "[warn] kubernetes 安装失败"

echo "===== Phase 14: 创建 stub 模块（绕过龙芯无法编译的包）====="
# 说明：这些包在龙芯 loongarch64 上无 PyPI wheel 或源码编译失败
# 项目使用 DashScope Embedding + SQLite 后端，实际不调用这些包的核心功能
# 只需要提供空壳类让 chromadb 的 import 语句通过即可

# 1. onnxruntime stub —— chromadb 类定义时会 import，但我们用 DashScope 不真调用
cat > "$SITE_PACKAGES/onnxruntime.py" << 'STUBEOF'
# 龙芯 loongarch64 无官方 onnxruntime wheel，此为空桩
# 项目使用 DashScope Embedding，不会执行真实推理
class InferenceSession:
    def __init__(self, *args, **kwargs):
        raise RuntimeError("onnxruntime stub: 项目使用 DashScope Embedding")

def get_available_providers():
    return []

class SessionOptions:
    def __init__(self):
        pass
    graph_optimization_level = None

class GraphOptimizationLevel:
    ORT_ENABLE_ALL = 0
STUBEOF

# 2. tokenizers stub —— chromadb 的 DefaultEmbeddingFunction 需要
cat > "$SITE_PACKAGES/tokenizers.py" << 'STUBEOF'
# 龙芯 loongarch64 无 tokenizers wheel（Rust edition2024 依赖）
class Tokenizer:
    @classmethod
    def from_file(cls, *args, **kwargs):
        raise RuntimeError("tokenizers stub: 项目使用 DashScope Embedding")
    def encode(self, *args, **kwargs):
        raise RuntimeError("tokenizers stub")
STUBEOF

# 3. orjson stub —— Rust 1.82 不支持 orjson 3.10+ 的 edition2024
cat > "$SITE_PACKAGES/orjson.py" << 'STUBEOF'
# 龙芯上 orjson 依赖 Rust edition2024（Rust 1.82 不支持），用标准 json 兜底
# chromadb 只在 telemetry 上用 orjson，性能影响可忽略
import json as _json

def dumps(obj, default=None, option=0):
    s = _json.dumps(obj, default=default, ensure_ascii=False)
    return s.encode('utf-8')

def loads(data):
    if isinstance(data, bytes):
        data = data.decode('utf-8')
    return _json.loads(data)

OPT_INDENT_2 = 1
OPT_NON_STR_KEYS = 2
OPT_SERIALIZE_NUMPY = 4
OPT_NAIVE_UTC = 8
JSONDecodeError = _json.JSONDecodeError
JSONEncodeError = ValueError
STUBEOF

# 4. pulsar stub —— chromadb 默认使用 SQLite 后端，不真调用 pulsar
cat > "$SITE_PACKAGES/pulsar.py" << 'STUBEOF'
# 龙芯无 pulsar-client wheel，项目使用 SQLite 后端
class Client:
    def __init__(self, *args, **kwargs):
        raise RuntimeError("pulsar stub: 项目使用 SQLite 后端")

class ConsumerType:
    Shared = 0
    Exclusive = 1

class InitialPosition:
    Latest = 0
    Earliest = 1

class ProducerCryptoFailureAction:
    FAIL = 0
    SEND = 1
STUBEOF

# 5. opentelemetry.exporter.otlp.proto.grpc 子包 stub
# chromadb/telemetry/opentelemetry/__init__.py 硬编码 import 这个 grpc 版
# 我们只装了 http 版，需要建假的 grpc 子包
STUB_GRPC_DIR="$SITE_PACKAGES/opentelemetry/exporter/otlp/proto/grpc"
mkdir -p "$STUB_GRPC_DIR"
cat > "$STUB_GRPC_DIR/__init__.py" << 'STUBEOF'
# 龙芯 grpcio 编译失败，此为空桩包
# chromadb 只是 import 名字，不会真正走 grpc 上报 telemetry
STUBEOF

cat > "$STUB_GRPC_DIR/trace_exporter.py" << 'STUBEOF'
class OTLPSpanExporter:
    def __init__(self, *args, **kwargs):
        pass
    def export(self, spans):
        return 0  # SUCCESS
    def shutdown(self):
        pass
STUBEOF

cat > "$STUB_GRPC_DIR/metric_exporter.py" << 'STUBEOF'
class OTLPMetricExporter:
    def __init__(self, *args, **kwargs):
        pass
    def export(self, metrics, *args, **kwargs):
        return 0
    def shutdown(self):
        pass
STUBEOF

echo "  已创建 5 个 stub：onnxruntime / tokenizers / orjson / pulsar / opentelemetry.grpc"

echo "===== Phase 15: 验证导入 ====="
cd "$BACKEND_DIR"
# 传 ALLOW_INSECURE_JWT=true 绕过项目内置生产安全检查
ALLOW_INSECURE_JWT=true python -c "
import onnxruntime, tokenizers, orjson, pulsar
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
import fastapi, uvicorn, pydantic, sqlalchemy, jose, bcrypt, dashscope, chromadb, pypdf, docx, reportlab, numpy
print('所有核心包导入成功')
print('numpy:', numpy.__version__, ' chromadb:', chromadb.__version__)
from app.main import app
print('FastAPI app 创建成功')
" 2>&1

echo ""
echo "===== 安装完成 ====="
echo "如果上面显示 'FastAPI app 创建成功'，说明环境就绪"
echo "下一步：填写 .env 中的 DASHSCOPE_API_KEY，然后启动服务"
