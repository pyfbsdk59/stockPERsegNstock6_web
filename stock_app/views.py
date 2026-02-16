from django.shortcuts import render
from django.contrib import messages
from .models import StockData
import json
import datetime
# 為了避免 Render 部署問題，我們用原生 datetime 處理月份加減
# from dateutil.relativedelta import relativedelta 

def home(request):
    context = {}
    now = datetime.datetime.now()
    
    # --- 1. 自動判斷預設顯示的年月 ---
    # 邏輯：每月10號前，預設看上上個月；10號後，看上個月
    if now.day > 10:
        # 上個月
        default_month = now.month - 1
        default_year = now.year
    else:
        # 上上個月
        default_month = now.month - 2
        default_year = now.year
        
    # 處理跨年 (例如 1月-1 = 0月 -> 去年12月)
    while default_month <= 0:
        default_month += 12
        default_year -= 1
        
    # 下拉選單範圍 (前後5年)
    context['years'] = range(now.year, now.year - 5, -1)
    context['months'] = range(1, 13)
    
    # 設定選單預設值
    try:
        req_y = request.POST.get('year')
        req_m = request.POST.get('month')
        context['selected_year'] = int(req_y) if req_y else default_year
        context['selected_month'] = int(req_m) if req_m else default_month
    except ValueError:
        context['selected_year'] = default_year
        context['selected_month'] = default_month

    if request.method == 'POST':
        
        # =========================================================
        # 功能 A: 上傳 JSON
        # =========================================================
        if 'upload_json' in request.FILES:
            try:
                f = request.FILES['upload_json']
                data = json.load(f)
                count = 0
                debug_info = []

                for sid, content in data.items():
                    meta = content.get('Meta', {})
                    
                    # 強制解析年份與月份，避免存錯
                    # 1. 嘗試讀取 GUI 傳來的 TargetMonth
                    try:
                        t_month = int(meta.get('TargetMonth', now.month))
                    except:
                        t_month = now.month
                        
                    # 2. 嘗試讀取 QueryDate 的年份
                    q_date_str = meta.get('QueryDate', now.strftime('%Y-%m-%d'))
                    try:
                        t_year = int(q_date_str.split('-')[0])
                    except:
                        t_year = now.year

                    # 3. 寫入資料庫
                    StockData.objects.update_or_create(
                        stock_id=sid,
                        data_year=t_year,
                        data_month=t_month,
                        defaults={
                            'stock_name': meta.get('StockName', str(sid)),
                            'raw_data': content
                        }
                    )
                    count += 1
                    debug_info.append(f"{sid}存為{t_year}年{t_month}月")

                # 顯示成功訊息 (包含除錯資訊)
                msg = f"成功匯入 {count} 筆資料！<br><small>詳細：{', '.join(debug_info[:3])}...</small>"
                messages.success(request, msg) # 注意：這裡用了 HTML，前端要支援 safe
                
                # 上傳後自動將選單切換到上傳資料的月份，方便使用者直接查詢
                context['selected_year'] = t_year
                context['selected_month'] = t_month

            except Exception as e:
                messages.error(request, f"上傳失敗：{e}")

        # =========================================================
        # 功能 B: 查詢股票 (含智慧搜尋)
        # =========================================================
        # 只要 POST 裡有 stock_id，即使是上傳動作後的刷新，也嘗試顯示數據
        target_sid = request.POST.get('stock_id', '').strip()
        
        # 如果是剛上傳完，可能還沒按查詢，但我們嘗試直接顯示上傳的那一筆
        if not target_sid and 'upload_json' in request.FILES:
             # 嘗試從剛上傳的 data 裡抓第一個 key 當作預設查詢
             try:
                 target_sid = list(data.keys())[0]
             except: pass

        if target_sid:
            context['selected_id'] = target_sid
            q_year = context['selected_year']
            q_month = context['selected_month']
            
            db_obj = None
            search_msg = ""

            # 1. 嘗試精準搜尋
            try:
                db_obj = StockData.objects.get(stock_id=target_sid, data_year=q_year, data_month=q_month)
            except StockData.DoesNotExist:
                # 2. 精準搜尋失敗，嘗試「智慧搜尋」：找該股票最近的一筆資料
                fallback_obj = StockData.objects.filter(stock_id=target_sid).order_by('-data_year', '-data_month').first()
                
                if fallback_obj:
                    db_obj = fallback_obj
                    # 更新選單顯示，讓使用者知道現在看的是哪個月
                    context['selected_year'] = db_obj.data_year
                    context['selected_month'] = db_obj.data_month
                    messages.warning(request, f"找不到 {q_year}/{q_month} 的資料，已自動為您顯示最近一筆 ({db_obj.data_year}/{db_obj.data_month}) 的數據。")
                else:
                    messages.error(request, f"資料庫中完全找不到代號 {target_sid} 的任何資料，請先上傳。")

            # 3. 如果有找到資料 (不論是精準還是智慧搜尋)，準備顯示
            if db_obj:
                raw = db_obj.raw_data
                per = raw.get('PER_Analysis', {})
                
                # --- 資料打包給 Template 用 (維持原樣) ---
                if per:
                    # 歷史股價
                    hist_rows = []
                    H = per.get('H', []); L = per.get('L', []); EPS = per.get('EPS', [])
                    PE_H = per.get('PE_H', []); PE_L = per.get('PE_L', [])
                    
                    loop_len = min(len(H), len(L), len(EPS))
                    for i in range(loop_len):
                        y_ad = per.get('Current_Year', 2026) - 1 - i
                        y_roc = per.get('Current_Year_ROC', 115) - 1 - i
                        hist_rows.append({
                            'year_str': f"{y_ad}/{y_roc}",
                            'h': H[i], 'l': L[i], 'eps': EPS[i],
                            'pe_h': PE_H[i] if i < len(PE_H) else '-', 
                            'pe_l': PE_L[i] if i < len(PE_L) else '-'
                        })
                    
                    # 營收與 YoY
                    rev_rows = []
                    rev_names = per.get('Rev_Names', []); rev_vals = per.get('Rev_Vals', [])
                    yoy_names = per.get('YoY_Names', []); yoy_vals = per.get('YoY_Vals', [])
                    
                    for i in range(len(rev_names)):
                        rev_rows.append({'name': rev_names[i], 'val': rev_vals[i]})
                    
                    yoy_rows_list = []
                    for i in range(len(yoy_names)):
                        yoy_rows_list.append({'name': yoy_names[i], 'yoy': yoy_vals[i]})

                    # 淨利
                    net_rows = []
                    net_names = per.get('Net_Names', []); net_vals = per.get('Net_Vals', [])
                    for i in range(len(net_names)):
                        net_rows.append({'name': net_names[i], 'val': net_vals[i]})

                    # Q4 列表
                    q4_data = [
                        ("狀態", per.get('Detect_Reason','-')),
                        ("網頁最新季別", per.get('Latest_Quarter_Str','-')),
                        ("Q1 EPS (實際)", per.get('EPS_Q1',0)),
                        ("Q2 EPS (實際)", per.get('EPS_Q2',0)),
                        ("Q3 EPS (實際)", per.get('EPS_Q3',0)),
                        ("Q1-Q3 總和", round(per.get('EPS_Q1',0)+per.get('EPS_Q2',0)+per.get('EPS_Q3',0), 2)),
                        ("---", "---"),
                        ("去年 Q4 營收", per.get('Q4_Rev_Actual',0)),
                        ("平均淨利率", per.get('Net_Avg','0%')),
                        ("股本(億)", per.get('Capital',0)),
                        ("Q4 EPS (估算)", per.get('Q4_EPS_Est',0)),
                        ("---", "---"),
                        ("全年 EPS (估/實)", per.get('Total_EPS_Est',0)),
                    ]

                    context['result'] = raw
                    context['hist_rows'] = hist_rows
                    context['rev_rows'] = rev_rows
                    context['yoy_rows'] = yoy_rows_list
                    context['net_rows'] = net_rows
                    context['q4_rows'] = q4_data

    return render(request, 'home.html', context)