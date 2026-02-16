from django.shortcuts import render
from django.contrib import messages
from .models import StockData
import json
import datetime
# 引入 dateutil 來處理月份加減會更方便，但在不增加依賴的情況下，我們用原生邏輯寫
from dateutil.relativedelta import relativedelta # 建議加裝 pip install python-dateutil

def home(request):
    context = {}
    now = datetime.datetime.now()
    
    # --- [新增] 自動判斷預設年月邏輯 ---
    if now.day > 10:
        # 超過10號 -> 預設為上個月
        target_date = now - relativedelta(months=1)
    else:
        # 10號(含)以前 -> 預設為上上個月
        target_date = now - relativedelta(months=2)
        
    default_year = target_date.year
    default_month = target_date.month
    # --------------------------------

    # 下拉選單範圍 (前後5年)
    context['years'] = range(now.year, now.year - 5, -1)
    context['months'] = range(1, 13)
    
    # 設定選單預設值：如果有 POST (使用者自己選的) 就用 POST，否則用自動判斷的 default
    try:
        context['selected_year'] = int(request.POST.get('year', default_year))
        context['selected_month'] = int(request.POST.get('month', default_month))
    except ValueError:
        context['selected_year'] = default_year
        context['selected_month'] = default_month

    if request.method == 'POST':
        # ... (中間的上傳邏輯保持不變) ...
        # ... (為了節省篇幅，這裡省略上傳部分的代碼，請保留原樣) ...

        # --- 處理查詢 ---
        # 這裡也要確保當使用者只是「上傳」而沒有按查詢時，選單不會跑掉
        if 'stock_id' in request.POST and 'upload_json' not in request.FILES:
            sid = request.POST.get('stock_id', '').strip()
            q_year = int(request.POST.get('year'))
            q_month = int(request.POST.get('month'))
            
            context['selected_id'] = sid
            
            try:
                db_obj = StockData.objects.get(
                    stock_id=sid, 
                    data_year=q_year, 
                    data_month=q_month
                )
                
                # ... (以下資料打包邏輯完全保持不變) ...
                raw = db_obj.raw_data
                per = raw['PER_Analysis']
                
                # 1. 歷史股價
                hist_rows = []
                loop_len = min(len(per['H']), len(per['L']), len(per['EPS']))
                for i in range(loop_len):
                    y_ad = per['Current_Year'] - 1 - i
                    y_roc = per['Current_Year_ROC'] - 1 - i
                    hist_rows.append({
                        'year_str': f"{y_ad}/{y_roc}",
                        'h': per['H'][i], 'l': per['L'][i], 'eps': per['EPS'][i],
                        'pe_h': per['PE_H'][i], 'pe_l': per['PE_L'][i]
                    })
                
                # 2. 營收
                rev_rows = []
                for i in range(len(per['Rev_Names'])):
                    rev_rows.append({'name': per['Rev_Names'][i], 'val': per['Rev_Vals'][i]})
                yoy_rows = []
                for i in range(len(per['YoY_Names'])):
                    yoy_rows.append({'name': per['YoY_Names'][i], 'yoy': per['YoY_Vals'][i]})

                # 3. 淨利
                net_rows = []
                for i in range(len(per['Net_Names'])):
                    net_rows.append({'name': per['Net_Names'][i], 'val': per['Net_Vals'][i]})

                # 4. Q4 檢查
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

                context['result'] = raw
                context['hist_rows'] = hist_rows
                context['rev_rows'] = rev_rows
                context['yoy_rows'] = yoy_rows
                context['net_rows'] = net_rows
                context['q4_rows'] = q4_data

            except StockData.DoesNotExist:
                messages.warning(request, f"找不到 {q_year}年 {q_month}月 的 {sid} 資料。")

    return render(request, 'home.html', context)