#!/bin/bash
# FocusFlow 一鍵啟動腳本

echo "=========================================="
echo "  🚀 啟動 FocusFlow 智慧工作追蹤與代辦排程系統"
echo "=========================================="

# 載入 .env 環境變數 (若存在)
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

# 確保資料庫已初始化
python3 -c "import database; database.init_db()"

echo "正在啟動伺服器於 http://localhost:8080 ..."
echo "按下 Ctrl + C 即可停止服務"
echo "=========================================="

python3 app.py
