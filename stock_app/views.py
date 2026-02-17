from django.shortcuts import render
from django.contrib import messages
from .models import StockData
import json
import datetime
import requests
from bs4 import BeautifulSoup
import random

# =========================================================
# 輔助函式：解析百分比字串
# =========================================================
def parse_pct(val):
    try:
        return float(str(val).replace('%', '').replace(',', '').strip()) / 100
    except:
        return 0.0

# =========================================================
# 輔助函式：即時爬蟲
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
                
                # --- [功能 C] 模擬試算邏輯 (含算式紀錄) ---
                if 'calc_simulation' in request.POST:
                    live_price = fetch_live_price(target_sid)
                    
                    try:
                        # 1. 取得原始參數
                        orig_yoy = parse_pct(per_data.get('YoY_Use', '0%'))
                        orig_net = parse_pct(per_data.get('Net_Avg', '0%'))
                        capital = float(per_data.get('Capital', 1))
                        orig_rev_predict = float(per_data.get('Predict_Rev', 0))
                        
                        calc_details = [] # 算式紀錄清單

                        # 2. 反推基期營收
                        if (1 + orig_yoy) != 0:
                            base_rev = orig_rev_predict / (1 + orig_yoy)
                        else:
                            base_rev = orig_rev_predict
                        
                        calc_details.append({
                            "step": "1. 反推基期營收",
                            "formula": f"原始預估營收 {orig_rev_predict} ÷ (1 + 原始YoY {orig_yoy:.2%})",
                            "result": f"{base_rev:.2f} 億"
                        })

                        # 3. 接收使用者輸入
                        user_yoy_val = request.POST.get('sim_yoy', '').strip()
                        user_net_val = request.POST.get('sim_net', '').strip()
                        
                        if user_yoy_val: sim_yoy = float(user_yoy_val) / 100
                        else: sim_yoy = orig_yoy
                            
                        if user_net_val: sim_net = float(user_net_val) / 100
                        else: sim_net = orig_net

                        sim_pe_h = float(request.POST.get('sim_pe_h', per_data.get('PE_Use_H', 0)))
                        sim_pe_l = float(request.POST.get('sim_pe_l', per_data.get('PE_Use_L', 0)))
                        
                        # 4. 連動計算
                        # A. 新營收
                        sim_rev = base_rev * (1 + sim_yoy)
                        calc_details.append({
                            "step": "2. 計算模擬營收",
                            "formula": f"基期營收 {base_rev:.2f} × (1 + 設定YoY {sim_yoy:.2%})",
                            "result": f"{sim_rev:.2f} 億"
                        })

                        # B. 新淨利
                        sim_net_income = sim_rev * sim_net
                        calc_details.append({
                            "step": "3. 計算模擬淨利",
                            "formula": f"模擬營收 {sim_rev:.2f} × 設定淨利率 {sim_net:.2%}",
                            "result": f"{sim_net_income:.2f} 億"
                        })

                        # C. 新EPS
                        sim_eps = round(sim_net_income / capital * 10, 2)
                        calc_details.append({
                            "step": "4. 計算模擬 EPS",
                            "formula": f"(模擬淨利 {sim_net_income:.2f} ÷ 股本 {capital}) × 10",
                            "result": f"{sim_eps} 元"
                        })
                        
                        # D. 目標價
                        target_h = round(sim_eps * sim_pe_h, 2)
                        target_l = round(sim_eps * sim_pe_l, 2)
                        calc_details.append({
                            "step": "5. 計算目標價",
                            "formula": f"高: EPS {sim_eps} × PE {sim_pe_h} | 低: EPS {sim_eps} × PE {sim_pe_l}",
                            "result": f"高 {target_h} / 低 {target_l}"
                        })
                        
                        # E. 報酬率
                        upside = 0; downside = 0; rr = 0
                        if live_price:
                            upside = (target_h - live_price) / live_price
                            downside = (target_l - live_price) / live_price
                            rr = abs(upside / downside) if downside != 0 else 0
                            
                            calc_details.append({
                                "step": "6. 報酬與風險",
                                "formula": f"即時價 {live_price} vs 目標價 {target_h} / {target_l}",
                                "result": f"上 {upside*100:.2f}% / 下 {downside*100:.2f}%"
                            })
                        
                        context['sim_res'] = {
                            'live_price': live_price if live_price else "抓取失敗",
                            'display_yoy': round(sim_yoy * 100, 2),
                            'display_net': round(sim_net * 100, 2),
                            'pe_h': sim_pe_h, 'pe_l': sim_pe_l,
                            'calc_eps': sim_eps, 'calc_rev': round(sim_rev, 2),
                            'target_h': target_h, 'target_l': target_l,
                            'upside': f"{upside*100:.2f}%" if live_price else "-",
                            'downside': f"{downside*100:.2f}%" if live_price else "-",
                            'rr': round(rr, 2) if live_price else "-",
                            'details': calc_details # 傳遞詳細算式
                        }
                        
                        if live_price: messages.success(request, f"試算成功！EPS 已更新。")
                        else: messages.warning(request, "試算完成，但無法抓取即時股價。")
                        
                    except ValueError:
                        messages.error(request, "輸入格式錯誤。")

    return render(request, 'home.html', context)