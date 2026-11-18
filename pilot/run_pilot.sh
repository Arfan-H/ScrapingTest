#!/usr/bin/env bash
# Menjalankan seluruh pilot dari nol. Butuh: pdfplumber pandas networkx scikit-learn onnxruntime tokenizers huggingface_hub
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p raw_pdf out
curl -sSL -o raw_pdf/rembang16_2023.pdf "$(awk -F, 'NR==2{print $7}' sumber.csv)"
curl -sSL -o raw_pdf/cianjur_cimacan_3_2025.pdf "$(awk -F, 'NR==3{print $7}' sumber.csv)"
python3 -I src/extract.py raw_pdf/rembang16_2023.pdf RSUD_REMBANG 9 out/items_rembang.csv
python3 -I src/extract.py raw_pdf/cianjur_cimacan_3_2025.pdf RSUD_CIMACAN 7 out/items_cimacan.csv
python3 -I src/golongan_rembang.py raw_pdf/rembang16_2023.pdf out/rembang
export HF_HUB_DISABLE_XET=1
export E5_DIR="$(python3 -I -c 'from huggingface_hub import snapshot_download as s; print(s("intfloat/multilingual-e5-small", allow_patterns=["onnx/model.onnx","tokenizer.json"]))')"
python3 -I src/align.py
python3 -I src/evaluate.py
python3 -I src/to_standard.py
python3 -I src/compare_v2.py
python3 -I src/build_graph.py
