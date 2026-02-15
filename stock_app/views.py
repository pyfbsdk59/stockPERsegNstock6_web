from django.shortcuts import render
from django.contrib import messages
from .models import StockData
import json
import datetime

def home(request):
    context = {}
    current_year = datetime.datetime.now().year
    context['years'] = range(current_year, current_year - 5, -1)
    context['months'] = range(1, 13)
    
    # 預設接收 GET 或 POST
    if request.method == 'POST':
        # --- 處理上傳 JSON ---
        if 'upload_json' in request.FILES:
            try:
                f = request.FILES['upload_json']
                data = json.load(f)
                count = 0
                for sid, content in data.items():
                    StockData.objects.update_or_create(
                        stock_id=sid,
                        defaults={
                            'stock_name': content.get('Meta', {}).get('StockName', ''),
                            'raw_data': content
                        }
                    )
                    count += 1
                messages.success(request, f"成功上傳 {count} 筆資料！")
            except Exception as e:
                messages.error(request, f"上傳失敗：{e}")

        # --- 處理查詢 ---
        if 'stock_id' in request.POST: # 只要有送出 stock_id 就算查詢
            sid = request.POST.get('stock_id', '').strip()
            context['selected_id'] = sid
            try:
                db_obj = StockData.objects.get(stock_id=sid)
                raw = db_obj.raw_data
                per = raw['PER_Analysis']
                
                # [關鍵修改] 資料前處理：將分散的 List 打包成 Rows 以便 Template 渲染
                
                # 1. 歷史股價打包
                hist_rows = []
                # 確保不會超出範圍 (預設 5 年)
                loop_len = min(len(per['H']), len(per['L']), len(per['EPS']))
                for i in range(loop_len):
                    # 年份計算：Current_Year - 1 - i
                    y_ad = per['Current_Year'] - 1 - i
                    y_roc = per['Current_Year_ROC'] - 1 - i
                    hist_rows.append({
                        'year_str': f"{y_ad}/{y_roc}",
                        'h': per['H'][i],
                        'l': per['L'][i],
                        'eps': per['EPS'][i],
                        'pe_h': per['PE_H'][i],
                        'pe_l': per['PE_L'][i]
                    })
                
                # 2. 營收打包 (合併營收數值與年增率)
                # GUI 是分兩段顯示，這裡我們模仿 GUI 邏輯
                rev_rows = []
                for i in range(len(per['Rev_Names'])):
                    # 營收數值
                    rev_rows.append({
                        'name': per['Rev_Names'][i],
                        'val': per['Rev_Vals'][i],
                        'yoy': '-' 
                    })
                # 補上年增率 (通常比較短)
                yoy_rows = []
                for i in range(len(per['YoY_Names'])):
                    yoy_rows.append({
                        'name': per['YoY_Names'][i],
                        'val': '-',
                        'yoy': per['YoY_Vals'][i]
                    })

                # 3. 淨利打包
                net_rows = []
                for i in range(len(per['Net_Names'])):
                    net_rows.append({
                        'name': per['Net_Names'][i],
                        'val': per['Net_Vals'][i]
                    })

                # 4. Q4 預測檢查表 (轉換成列表以便迴圈)
                # 對應 GUI 的 Treeview 順序
                q4_data = [
                    ("狀態", per['Detect_Reason']),
                    ("網頁最新季別", per['Latest_Quarter_Str']),
                    ("Q1 EPS (實際)", per['EPS_Q1']),
                    ("Q2 EPS (實際)", per['EPS_Q2']),
                    ("Q3 EPS (實際)", per['EPS_Q3']),
                    ("Q1-Q3 總和", round(per['EPS_Q1']+per['EPS_Q2']+per['EPS_Q3'], 2)),
                    ("---", "---"),
                    ("去年 Q4 營收", per['Q4_Rev_Actual']),
                    ("平均淨利率", per['Net_Avg']),
                    ("股本(億)", per['Capital']),
                    ("Q4 EPS (估算)", per['Q4_EPS_Est']),
                    ("---", "---"),
                    ("全年 EPS (估/實)", per['Total_EPS_Est']),
                ]

                # 將整理好的資料塞回 context
                context['result'] = raw
                context['hist_rows'] = hist_rows
                context['rev_rows'] = rev_rows
                context['yoy_rows'] = yoy_rows
                context['net_rows'] = net_rows
                context['q4_rows'] = q4_data

            except StockData.DoesNotExist:
                messages.error(request, f"找不到代號 {sid}，請確認是否已上傳 JSON。")

    return render(request, 'home.html', context)