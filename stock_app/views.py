from django.shortcuts import render
from django.contrib import messages
from .models import StockData
import json
import datetime

def home(request):
    context = {}
    now = datetime.datetime.now()
    current_year = now.year
    
    # 下拉選單範圍
    context['years'] = range(current_year, current_year - 5, -1)
    context['months'] = range(1, 13)
    
    # 預設選單停留在當下時間，或使用者上次選的時間
    context['selected_year'] = int(request.POST.get('year', current_year))
    context['selected_month'] = int(request.POST.get('month', now.month))

    if request.method == 'POST':
        # --- 處理上傳 JSON ---
        if 'upload_json' in request.FILES:
            try:
                f = request.FILES['upload_json']
                data = json.load(f)
                count = 0
                for sid, content in data.items():
                    meta = content.get('Meta', {})
                    
                    # 1. 解析月份 (從 GUI 紀錄的 TargetMonth)
                    try:
                        t_month = int(meta.get('TargetMonth', now.month))
                    except:
                        t_month = now.month
                        
                    # 2. 解析年份 (從 QueryDate 抓取，例如 "2026-02-15")
                    # 邏輯：通常查詢日期的年份就是資料年份
                    q_date_str = meta.get('QueryDate', now.strftime('%Y-%m-%d'))
                    try:
                        t_year = int(q_date_str.split('-')[0])
                    except:
                        t_year = now.year

                    # 3. 儲存或更新 (以 代碼+年+月 為基準)
                    StockData.objects.update_or_create(
                        stock_id=sid,
                        data_year=t_year,
                        data_month=t_month,
                        defaults={
                            'stock_name': meta.get('StockName', ''),
                            'raw_data': content
                        }
                    )
                    count += 1
                messages.success(request, f"成功匯入 {count} 筆資料 (年份:{t_year}, 月份:{t_month})！")
            except Exception as e:
                messages.error(request, f"上傳失敗：{e}")

        # --- 處理查詢 ---
        if 'stock_id' in request.POST and 'upload_json' not in request.FILES:
            sid = request.POST.get('stock_id', '').strip()
            # 取得使用者選單的年、月
            q_year = int(request.POST.get('year'))
            q_month = int(request.POST.get('month'))
            
            context['selected_id'] = sid
            
            try:
                # [關鍵修改] 增加年份與月份的過濾條件
                db_obj = StockData.objects.get(
                    stock_id=sid, 
                    data_year=q_year, 
                    data_month=q_month
                )
                
                # --- 以下為資料打包邏輯 (與之前相同) ---
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
                messages.warning(request, f"找不到 {q_year}年 {q_month}月 的 {sid} 資料。請確認是否已上傳該月份數據。")

    return render(request, 'home.html', context)