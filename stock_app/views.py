from django.shortcuts import render
from django.contrib import messages
from .models import StockData
import json
import datetime
import requests
from bs4 import BeautifulSoup
import random

# =========================================================
# 輔助函式：即時爬蟲 (與 GUI 邏輯相同)
# =========================================================
def fetch_live_price(stock_id):
    try:
        # 隨機 User-Agent 避免被擋
        agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36'
        ]
        headers = {'User-Agent': random.choice(agents)}
        url = f'https://stock.wearn.com/a{stock_id}.html'
        
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code != 200: return None
        
        soup = BeautifulSoup(r.content, 'html.parser')
        
        # 嘗試抓取成交價 (根據 Wearn 網頁結構)
        price = 0.0
        uls = soup.find_all('ul')
        for ul in uls:
            if "成交價" in str(ul):
                li = ul.find_all('li')[0]
                txt = li.text.replace(',', '').strip()
                price = float(txt)
                break
        
        # 備用抓取邏輯
        if price == 0 and len(uls) > 6:
            txt = uls[4].find_all('li')[0].text.replace(',', '').strip()
            price = float(txt)
            
        return price if price > 0 else None
    except:
        return None

# =========================================================
# 輔助函式：資料打包 (讓 search 和 calc 共用)
# =========================================================
def get_dashboard_data(db_obj):
    raw = db_obj.raw_data
    per = raw.get('PER_Analysis', {})
    
    # 1. 歷史股價
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
    
    # 2. 營收與 YoY
    rev_rows = []
    rev_names = per.get('Rev_Names', []); rev_vals = per.get('Rev_Vals', [])
    yoy_names = per.get('YoY_Names', []); yoy_vals = per.get('YoY_Vals', [])
    for i in range(len(rev_names)):
        rev_rows.append({'name': rev_names[i], 'val': rev_vals[i]})
    yoy_rows_list = []
    for i in range(len(yoy_names)):
        yoy_rows_list.append({'name': yoy_names[i], 'yoy': yoy_vals[i]})

    # 3. 淨利
    net_rows = []
    net_names = per.get('Net_Names', []); net_vals = per.get('Net_Vals', [])
    for i in range(len(net_names)):
        net_rows.append({'name': net_names[i], 'val': net_vals[i]})

    # 4. Q4 列表
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

    return {
        'result': raw,
        'hist_rows': hist_rows,
        'rev_rows': rev_rows,
        'yoy_rows': yoy_rows_list,
        'net_rows': net_rows,
        'q4_rows': q4_data
    }

# =========================================================
# 主視圖
# =========================================================
def home(request):
    context = {}
    now = datetime.datetime.now()
    
    # 自動判斷預設顯示的年月
    if now.day > 10:
        default_month = now.month - 1
        default_year = now.year
    else:
        default_month = now.month - 2
        default_year = now.year
        
    while default_month <= 0:
        default_month += 12
        default_year -= 1
        
    context['years'] = range(now.year, now.year - 5, -1)
    context['months'] = range(1, 13)
    
    try:
        req_y = request.POST.get('year')
        req_m = request.POST.get('month')
        context['selected_year'] = int(req_y) if req_y else default_year
        context['selected_month'] = int(req_m) if req_m else default_month
    except ValueError:
        context['selected_year'] = default_year
        context['selected_month'] = default_month

    if request.method == 'POST':
        # --- 上傳邏輯 (保持不變) ---
        if 'upload_json' in request.FILES:
            try:
                f = request.FILES['upload_json']
                data = json.load(f)
                count = 0
                debug_info = []
                for sid, content in data.items():
                    meta = content.get('Meta', {})
                    try: t_month = int(meta.get('TargetMonth', now.month))
                    except: t_month = now.month
                    q_date_str = meta.get('QueryDate', now.strftime('%Y-%m-%d'))
                    try: t_year = int(q_date_str.split('-')[0])
                    except: t_year = now.year
                    
                    StockData.objects.update_or_create(
                        stock_id=sid, data_year=t_year, data_month=t_month,
                        defaults={'stock_name': meta.get('StockName', str(sid)), 'raw_data': content}
                    )
                    count += 1
                    debug_info.append(f"{sid}存為{t_year}年{t_month}月")
                
                messages.success(request, f"成功匯入 {count} 筆資料！<br><small>詳細：{', '.join(debug_info[:3])}...</small>")
                context['selected_year'] = t_year
                context['selected_month'] = t_month
            except Exception as e:
                messages.error(request, f"上傳失敗：{e}")

        # --- 查詢與即時試算邏輯 ---
        target_sid = request.POST.get('stock_id', '').strip()
        
        # 自動填入上傳的第一筆
        if not target_sid and 'upload_json' in request.FILES:
             try: target_sid = list(data.keys())[0]
             except: pass

        if target_sid:
            context['selected_id'] = target_sid
            q_year = context['selected_year']
            q_month = context['selected_month']
            
            db_obj = None
            try:
                db_obj = StockData.objects.get(stock_id=target_sid, data_year=q_year, data_month=q_month)
            except StockData.DoesNotExist:
                # 智慧搜尋最近一筆
                fallback_obj = StockData.objects.filter(stock_id=target_sid).order_by('-data_year', '-data_month').first()
                if fallback_obj:
                    db_obj = fallback_obj
                    context['selected_year'] = db_obj.data_year
                    context['selected_month'] = db_obj.data_month
                    messages.warning(request, f"找不到 {q_year}/{q_month} 的資料，已自動顯示最近一筆 ({db_obj.data_year}/{db_obj.data_month})。")
                else:
                    messages.error(request, f"找不到代號 {target_sid} 的資料。")

            if db_obj:
                # 1. 先打包基礎數據供顯示
                base_data = get_dashboard_data(db_obj)
                context.update(base_data)
                
                # 2. 判斷是否為「即時試算」請求
                if 'calc_realtime' in request.POST:
                    per_data = db_obj.raw_data.get('PER_Analysis', {})
                    
                    # A. 抓取即時股價
                    live_price = fetch_live_price(target_sid)
                    
                    # B. 進行試算 (使用 JSON 內的 2026 預測值)
                    if live_price:
                        try:
                            # 讀取數據
                            predict_eps = float(per_data.get('Predict_EPS', 0)) # 這是 2026 預測值
                            pe_h = float(per_data.get('PE_Use_H', 0))
                            pe_l = float(per_data.get('PE_Use_L', 0))
                            
                            # 計算目標價
                            target_h = round(predict_eps * pe_h, 2)
                            target_l = round(predict_eps * pe_l, 2)
                            
                            # 計算空間
                            upside = (target_h - live_price) / live_price
                            downside = (target_l - live_price) / live_price
                            
                            # 風險報酬比
                            rr_ratio = abs(upside / downside) if downside != 0 else 0
                            
                            # 包裝結果
                            context['realtime_res'] = {
                                'price': live_price,
                                'eps_2026': predict_eps,
                                'pe_h': pe_h,
                                'pe_l': pe_l,
                                'target_h': target_h,
                                'target_l': target_l,
                                'upside': f"{upside*100:.2f}%",
                                'downside': f"{downside*100:.2f}%",
                                'rr': round(rr_ratio, 2)
                            }
                            messages.success(request, f"即時股價更新成功：{live_price}")
                        except Exception as calc_err:
                            messages.error(request, f"試算錯誤：數據不完整 ({calc_err})")
                    else:
                        messages.error(request, "無法獲取即時股價，請稍後再試。")

    return render(request, 'home.html', context)