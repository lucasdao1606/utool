#!/bin/bash
set -e

echo "=========================================================="
echo ">>> [1/6] CẬP NHẬT HỆ THỐNG VÀ CÀI CÁC THƯ VIỆN C++ / GRAPHICS"
echo "=========================================================="
sudo apt-get update -y
sudo apt-get install -y \
    python3-pip \
    python3-dev \
    python3-venv \
    build-essential \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libgomp1 \
    libspatialindex-dev \
    fonts-liberation \
    fonts-dejavu \
    wget \
    curl

echo "=========================================================="
echo ">>> [2/6] KHỞI TẠO MÔI TRƯỜNG ẢO PYTHON (VENV)"
echo "=========================================================="
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "Đã tạo thư mục môi trường ảo venv."
fi

# Kích hoạt venv
source venv/bin/activate

# Nâng cấp pip và wheel
pip install --upgrade pip setuptools wheel

echo "=========================================================="
echo ">>> [3/6] CÀI ĐẶT PYTORCH CPU & PADDLEPADDLE 2.6.2"
echo "=========================================================="
# 1. Cài PyTorch CPU (cho VietOCR)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu

# 2. Cài PaddlePaddle CPU 2.6.2
pip install paddlepaddle==2.6.2 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/

echo "=========================================================="
echo ">>> [4/6] CÀI ĐẶT STREAMLIT, PROTOBUF & CÁC DEPENDENCY CHUẨN"
echo "=========================================================="
# Cố định Protobuf cho Paddle & Streamlit tương thích
pip install "protobuf>=3.20.0,<=3.20.3"
pip install "streamlit==1.35.0"
pip install "pillow>=10.0.0,<11.0.0"
pip install "numpy<2.0.0"

# Cài PaddleOCR và VietOCR
pip install paddleocr==2.7.3 --no-deps
pip install shapely pyclipper attrdict visualdl
pip install vietocr
pip install pymupdf python-docx opencv-python-headless beautifulsoup4 pdfplumber

echo "=========================================================="
echo ">>> [5/6] KIỂM TRA ĐỘ TOÀN VẸN CỦA GÓI PHỤ THUỘC"
echo "=========================================================="
pip check

echo "=========================================================="
echo ">>> [6/6] TẢI TRƯỚC MODEL TRỌNG SỐ (WEIGHTS) VÀ TEST KHỞI CHẠY"
echo "=========================================================="
# Thiết lập cờ hệ thống ngăn xung đột OneDNN
export FLAGS_use_mkldnn=0
export PADDLE_ONEDNN=0

python3 -c "
import os
os.environ['FLAGS_use_mkldnn'] = '0'
os.environ['PADDLE_ONEDNN'] = '0'

print('Đang kiểm tra và tải trọng lượng PaddleOCR...')
from paddleocr import PaddleOCR
detector = PaddleOCR(use_angle_cls=True, det=True, rec=False, show_log=False, enable_mkldnn=False, ir_optim=False)

print('Đang kiểm tra và tải trọng lượng VietOCR Transformer...')
from vietocr.tool.predictor import Predictor
from vietocr.tool.config import Cfg
config = Cfg.load_config_from_name('vgg_transformer')
config['device'] = 'cpu'
predictor = Predictor(config)

print('>>> TẤT CẢ MODEL ĐÃ ĐƯỢC TẢI VÀ KHỞI TẠO THÀNH CÔNG 100%!')
"

echo "=========================================================="
echo ">>> HOÀN TẤT CÀI ĐẶT TOÀN BỘ MÔI TRƯỜNG!"
echo "Để chạy ứng dụng trên VPS Ubuntu:"
echo "  source venv/bin/activate"
echo "  export FLAGS_use_mkldnn=0"
echo "  export PADDLE_ONEDNN=0"
echo "  streamlit run app.py --server.port 8501 --server.address 0.0.0.0"
echo "=========================================================="