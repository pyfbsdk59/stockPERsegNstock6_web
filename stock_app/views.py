from django.shortcuts import render
from django.contrib import messages
from .models import StockData
import json
import datetime
import requests
from bs4 import BeautifulSoup
import random

# =========================================================
# 輔助函式：解析百分比字串 (例如 "15.5%" -> 0.155)
# =========================================================
def parse_pct(val):
    try:
        return float(str(val).replace('%', '').replace(',', '').strip()) / 100
    except:
        return 0.0

# =========================================================
# 輔助函式：即時爬蟲 (抓取最新成交價)
# =========================================================
def fetch_live_price(stock_id):
    try:
        agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36'
        ]
        headers = {'User-Agent': random.choice(agents)}
        url = f'https://stock.wearn.com/a{stock_id}.html'
        
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code != 200: return None
        
        soup = BeautifulSoup(r.content, 'html.parser')
        price = 0.0
        uls = soup.find_all('ul')
        for ul in uls:
            if "成交價" in str(ul):
                li = ul.find_all('li')[0]
                txt = li.text.replace(',', '').strip()
                try: price = float(txt)
                except: pass
                break
        
        if price == 0 and len(uls) > 6:
            try:
                txt = uls[4].find_all('li')[0].text.replace(',', '').strip()
                price = float(txt)
            except: pass
            
        return price if price > 0 else None
    except:
        return None

# =========================================================
# 輔助函式：資料打包
# =========================================================
def get_dashboard_data(db_obj):
    raw = db_obj.raw_data
    per = raw.get('PER_Analysis', {})
    
    # 歷史股價
    hist_rows = []
    H = per.get('H', []); L = per.get('L', []); EPS = per.get('EPS', [])
    PE_H = per.get('PE_H', []); PE_L = per.get('PE_L', [])
    loop_len = min(len(H), len(L), len(EPS))
    
    current_year = per.get('Current_Year', datetime.datetime.now().year)
    current_year_roc = per.get('Current_Year_ROC', current_year - 1911)

    for i in range(loop_len):
        y_ad = current_year - 1 - i
        y_roc = current_year_roc - 1 - i
        hist_rows.append({
            'year_str': f"{y_ad}/{y_roc}",
            'h': H[i], 'l': L[i], 'eps': EPS[i],
            'pe_h': PE_H[i] if i < len(PE_H) else '-', 
            'pe_l': PE_L[i] if i < len(PE_L) else '-'
        })
    
    # 營收
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

    # Q4
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
    
    # 10號規則
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
        # --- [功能 A] 上傳 JSON ---
        if 'upload_json' in request.FILES:
            try:
                f = request.FILES['upload_json']
                data = json.load(f)
                count = 0
                debug_info = []
                
                upload_year = context['selected_year']
                upload_month = context['selected_month']

                for sid, content in data.items():
                    meta = content.get('Meta', {})
                    try: t_month = int(meta.get('TargetMonth', now.month))
                    except: t_month = now.month
                    q_date_str = meta.get('QueryDate', now.strftime('%Y-%m-%d'))
                    try: t_year = int(q_date_str.split('-')[0])
                    except: t_year = now.year
                    
                    upload_year = t_year
                    upload_month = t_month

                    StockData.objects.update_or_create(
                        stock_id=sid, data_year=t_year, data_month=t_month,
                        defaults={'stock_name': meta.get('StockName', str(sid)), 'raw_data': content}
                    )
                    count += 1
                    debug_info.append(f"{sid}({t_year}/{t_month})")
                
                messages.success(request, f"成功匯入 {count} 筆資料！<br><small>{', '.join(debug_info[:2])}...</small>")
                context['selected_year'] = upload_year
                context['selected_month'] = upload_month
                
            except Exception as e:
                messages.error(request, f"上傳失敗：{e}")

        # --- [功能 B] 查詢與模擬 ---
        target_sid = request.POST.get('stock_id', '').strip()
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
                fallback_obj = StockData.objects.filter(stock_id=target_sid).order_by('-data_year', '-data_month').first()
                if fallback_obj:
                    db_obj = fallback_obj
                    context['selected_year'] = db_obj.data_year
                    context['selected_month'] = db_obj.data_month
                    messages.warning(request, f"找不到 {q_year}/{q_month}，已自動顯示 ({db_obj.data_year}/{db_obj.data_month}) 資料。")
                else:
                    messages.error(request, f"找不到代號 {target_sid} 的資料。")

            if db_obj:
                base_data = get_dashboard_data(db_obj)
                context.update(base_data)
                
                per_data = db_obj.raw_data.get('PER_Analysis', {})
                
                # --- [功能 C] 模擬試算邏輯 (大幅升級) ---
                if 'calc_simulation' in request.POST:
                    live_price = fetch_live_price(target_sid)
                    
                    try:
                        # 1. 取得原始基礎參數
                        orig_yoy = parse_pct(per_data.get('YoY_Use', '0%'))
                        orig_net = parse_pct(per_data.get('Net_Avg', '0%'))
                        capital = float(per_data.get('Capital', 1))
                        # 這是 JSON 中計算好的預估營收，我們先還原回「基期營收」(去年的概念)
                        orig_rev_predict = float(per_data.get('Predict_Rev', 0))
                        
                        # 反推基期營收：如果預估營收是成長後的，那除以 (1+YoY) 就是基期
                        if (1 + orig_yoy) != 0:
                            base_rev = orig_rev_predict / (1 + orig_yoy)
                        else:
                            base_rev = orig_rev_predict

                        # 2. 接收使用者輸入 (若空則使用原始值)
                        # 注意：前端傳來的是 "15" 代表 15%，所以要除以 100
                        user_yoy_val = request.POST.get('sim_yoy', '').strip()
                        user_net_val = request.POST.get('sim_net', '').strip()
                        
                        # 處理 YOY 輸入
                        if user_yoy_val:
                            sim_yoy = float(user_yoy_val) / 100
                        else:
                            sim_yoy = orig_yoy
                            
                        # 處理 淨利率 輸入
                        if user_net_val:
                            sim_net = float(user_net_val) / 100
                        else:
                            sim_net = orig_net

                        # 處理 PE 區間輸入
                        sim_pe_h = float(request.POST.get('sim_pe_h', per_data.get('PE_Use_H', 0)))
                        sim_pe_l = float(request.POST.get('sim_pe_l', per_data.get('PE_Use_L', 0)))
                        
                        # 3. 連動計算核心公式
                        # 新營收 = 基期營收 * (1 + 新YoY)
                        sim_rev = base_rev * (1 + sim_yoy)
                        # 新淨利 = 新營收 * 新淨利率
                        sim_net_income = sim_rev * sim_net
                        # 新EPS = 新淨利 / 股本 * 10
                        sim_eps = round(sim_net_income / capital * 10, 2)
                        
                        # 計算目標價
                        target_h = round(sim_eps * sim_pe_h, 2)
                        target_l = round(sim_eps * sim_pe_l, 2)
                        
                        upside = 0; downside = 0; rr = 0
                        if live_price:
                            upside = (target_h - live_price) / live_price
                            downside = (target_l - live_price) / live_price
                            rr = abs(upside / downside) if downside != 0 else 0
                        
                        context['sim_res'] = {
                            'live_price': live_price if live_price else "抓取失敗",
                            # 回傳給前端顯示的值 (轉回百分比顯示)
                            'display_yoy': round(sim_yoy * 100, 2),
                            'display_net': round(sim_net * 100, 2),
                            'pe_h': sim_pe_h,
                            'pe_l': sim_pe_l,
                            'calc_eps': sim_eps, # 這是計算出來的新 EPS
                            'calc_rev': round(sim_rev, 2),
                            'target_h': target_h,
                            'target_l': target_l,
                            'upside': f"{upside*100:.2f}%" if live_price else "-",
                            'downside': f"{downside*100:.2f}%" if live_price else "-",
                            'rr': round(rr, 2) if live_price else "-"
                        }
                        
                        if live_price: messages.success(request, f"試算成功！EPS 已根據參數重新計算。")
                        else: messages.warning(request, "試算完成，但無法抓取即時股價。")
                        
                    except ValueError:
                        messages.error(request, "輸入格式錯誤，請檢查數值。")

    return render(request, 'home.html', context)