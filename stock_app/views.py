
# Create your views here.
from django.shortcuts import render, redirect
from django.contrib import messages
from .models import StockData
import json
import datetime

def home(request):
    context = {}
    current_year = datetime.datetime.now().year
    
    # 準備下拉選單的資料
    context['years'] = range(current_year, current_year - 5, -1)
    context['months'] = range(1, 13)

    if request.method == 'POST':
        # --- 功能 A: 查詢股票 ---
        if 'search_stock' in request.POST:
            stock_id = request.POST.get('stock_id').strip()
            try:
                # 從資料庫撈取資料
                db_obj = StockData.objects.get(stock_id=stock_id)
                context['result'] = db_obj.raw_data # 傳遞 JSON 內容給前端
                context['selected_id'] = stock_id
            except StockData.DoesNotExist:
                messages.error(request, f"資料庫中找不到代號 {stock_id}，請先上傳 JSON。")

        # --- 功能 B: 上傳 JSON ---
        elif 'upload_json' in request.FILES:
            json_file = request.FILES['upload_json']
            try:
                data = json.load(json_file)
                # 解析並儲存
                # 假設 JSON 結構為: {"2330": {"Meta":{...}, ...}}
                count = 0
                for sid, content in data.items():
                    StockData.objects.update_or_create(
                        stock_id=sid,
                        defaults={
                            'stock_name': content.get('Meta', {}).get('StockName', '未知'),
                            'raw_data': content
                        }
                    )
                    count += 1
                messages.success(request, f"成功匯入 {count} 筆股票資料！")
            except Exception as e:
                messages.error(request, f"匯入失敗: {e}")

    return render(request, 'home.html', context)