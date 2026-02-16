#!/usr/bin/env bash
# exit on error
set -o errexit

pip install -r requirements.txt

# 收集靜態檔案
python manage.py collectstatic --no-input

# 更新資料庫結構
python manage.py makemigrations
python manage.py migrate

#清除資料庫資料
#python manage.py flush --no-input
#python manage.py migrate stock_app zero
#python manage.py migrate