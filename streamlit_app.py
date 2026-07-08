import streamlit as st
from garmin_fit_sdk import Decoder, Stream
import datetime

# --- 輔助函式區 ---
def format_time(seconds):
    if seconds is None: return "00:00:00"
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

def m_per_s_to_pace(m_per_s):
    if not m_per_s or m_per_s <= 0: return "--:--/km"
    sec_per_km = 1000 / m_per_s
    m = int(sec_per_km // 60)
    s = int(sec_per_km % 60)
    return f"{m}:{s:02d}/km"

def generate_sub_laps(lap_recs):
    """用於長距離分段（大於1km）自動拆分每一公里小圈"""
    if not lap_recs: return ""
    total_lap_dist = lap_recs[-1].get('distance', 0) - lap_recs[0].get('distance', 0)
    if total_lap_dist <= 1005: 
        return ""

    splits = []
    split_start_ts = lap_recs[0]['timestamp']
    split_start_dist = lap_recs[0].get('distance', 0)
    target_dist = split_start_dist + 1000
    hrs = []

    for i, r in enumerate(lap_recs):
        dist = r.get('distance')
        if dist is None: continue
        if r.get('heart_rate'): hrs.append(r['heart_rate'])

        is_last = (i == len(lap_recs) - 1)
        if dist >= target_dist or is_last:
            chunk_dist = dist - split_start_dist
            if chunk_dist > 50: 
                dt = (r['timestamp'] - split_start_ts).total_seconds() if isinstance(split_start_ts, datetime.datetime) else (r['timestamp'] - split_start_ts)
                if dt > 0:
                    pace = m_per_s_to_pace(chunk_dist / dt)
                    avg_hr = int(sum(hrs)/len(hrs)) if hrs else '--'
                    time_str = format_time(dt)
                    splits.append(f"{chunk_dist/1000:.2f}km {time_str}({pace}) HR{avg_hr}")

            split_start_ts = r['timestamp']
            split_start_dist = dist
            target_dist += 1000
            hrs = []

    if splits:
        return " (" + ", ".join(splits) + ")"
    return ""

def get_hr_min_max(lap_hrs, hr_avg, hr_max):
    """簡化版：只抓最低與最高心率"""
    if not lap_hrs:
        val_min = hr_avg if hr_avg != '--' else '--'
        val_max = hr_max if hr_max != '--' else '--'
        return val_min, val_max
        
    hr_min = min(lap_hrs)
    hr_max_calc = max(lap_hrs)
    
    final_max = hr_max if (hr_max != '--' and hr_max > hr_max_calc) else hr_max_calc
    return hr_min, final_max

# --- 核心解析區 ---
def parse_fit_bytes_to_text(file_bytes):
    stream = Stream.from_byte_array(bytearray(file_bytes))
    decoder = Decoder(stream)
    messages, errors = decoder.read()

    session_mesgs = messages.get('session_mesgs', [])
    lap_mesgs = messages.get('lap_mesgs', [])
    record_mesgs = messages.get('record_mesgs', []) 
    workout_step_mesgs = messages.get('workout_step_mesgs', [])
    
    if not session_mesgs:
        return "找不到摘要數據。"
        
    session = session_mesgs[0]
    activity_start = session.get('start_time')
    
    # 課表名稱對照
    wkt_dict = {}
    for step in workout_step_mesgs:
        idx = step.get('message_index')
        name = step.get('wkt_step_name')
        if not name:
            intensity = step.get('intensity')
            if intensity is not None:
                int_str = str(intensity).lower()
                if int_str in ['2', 'warmup', 'warm_up']: name = "暖身"
                elif int_str in ['3', 'cooldown', 'cool_down']: name = "緩和"
                elif int_str in ['1', 'rest']: name = "休息"
                elif int_str in ['4', 'recovery']: name = "恢復"
                elif int_str in ['0', 'active']: name = "訓練"
                elif int_str in ['5', 'interval']: name = "間歇"
        if name and idx is not None:
            wkt_dict[idx] = name

    sport = session.get('sport', 'unknown')
    dt = activity_start if activity_start else 'Unknown'
    
    # 【時區修正】在這裡將 UTC 時間加上 8 小時轉換為台灣時間
    if isinstance(dt, datetime.datetime):
        dt_taiwan = dt + datetime.timedelta(hours=8)
        date_str = dt_taiwan.strftime("%Y/%m/%d %p%I:%M:%S").replace("AM", "上午").replace("PM", "下午")
    else:
        date_str = str(dt)
        
    duration_str = format_time(session.get('total_timer_time', 0))
    total_dist_km = session.get('total_distance', 0) / 1000
    avg_pace = m_per_s_to_pace(session.get('enhanced_avg_speed', 0))
    max_speed_kph = session.get('enhanced_max_speed', 0) * 3.6
    
    avg_hr = session.get('avg_heart_rate', '--')
    max_hr = session.get('max_heart_rate', '--')
    ascent = session.get('total_ascent', 0)
    descent = session.get('total_descent', 0)
    calories = session.get('total_calories', '--')
    avg_pwr = session.get('avg_power', '--')
    max_pwr = session.get('max_power', '--')
    
    avg_cad = session.get('avg_running_cadence', session.get('avg_cadence', '--'))
    if isinstance(avg_cad, (int, float)): avg_cad = int(avg_cad * 2)

    te = session.get('total_training_effect', '--')
    if isinstance(te, (int, float)): te = f"{float(te):.1f}"
    
    device = "Unknown Garmin Device"
    file_id_mesgs = messages.get('file_id_mesgs', [])
    if file_id_mesgs:
        device = file_id_mesgs[0].get('garmin_product', device)
        
    out = []
    # 圖例重新補上 Temp(溫度)
    out.append("[圖例] HR=平均(最小/最大) Pwr=功率(W) Cad=步頻(spm) VO=垂直振幅(mm) GCT=觸地時間(ms) Temp=溫度(°C) Elev=海拔變化(m)\n")
    out.append("[概要]")
    out.append(f"運動: {sport}\n日期: {date_str}\n時間: {duration_str} | 距離: {total_dist_km:.2f}km")
    out.append(f"平均配速: {avg_pace} | 最大速度: {max_speed_kph:.1f}kph")
    out.append(f"HR: 平均 {avg_hr} / 最大 {max_hr}\n海拔: +{ascent}m / -{descent}m\n卡路里: {calories}")
    out.append(f"額外數據: 平均 Pwr: {avg_pwr}W (最大 {max_pwr}W) | 平均 Cad: {avg_cad} | TE: {te}")
    
    # 概要區補上單純的手錶內建「平均氣溫」
    avg_temp = session.get('avg_temperature')
    if avg_temp is not None:
        out.append(f"平均氣溫: {avg_temp}°C")
        
    out.append(f"裝置: {device}\n\n[分段]")

    # 漏斗分裝法
    lap_buckets = [[] for _ in range(len(lap_mesgs))]
    current_lap_idx = 0
    
    for r in record_mesgs:
        ts = r.get('timestamp')
        if not ts: continue
        if activity_start and ts < activity_start: continue
            
        while current_lap_idx < len(lap_mesgs):
            lap_end = lap_mesgs[current_lap_idx].get('timestamp')
            if not lap_end:
                current_lap_idx += 1
                continue
            if ts <= lap_end:
                lap_buckets[current_lap_idx].append(r)
                break
            else:
                current_lap_idx += 1
    
    cumulative_dist = 0
    
    for i, lap in enumerate(lap_mesgs, 1):
        lap_recs = lap_buckets[i-1]
        
        lap_name = lap.get('name', '')
        wkt_idx = lap.get('wkt_step_index')
        if wkt_idx is not None and wkt_idx in wkt_dict:
            lap_name = wkt_dict[wkt_idx]
        name_str = f"({lap_name})" if lap_name else ""
        
        cumulative_dist += lap.get('total_distance', 0)
        lap_time_str = format_time(lap.get('total_timer_time', 0))
        lap_pace = m_per_s_to_pace(lap.get('enhanced_avg_speed', 0))
        
        hr_avg = lap.get('avg_heart_rate', '--')
        hr_max = lap.get('max_heart_rate', '--')
        lap_hrs = [r['heart_rate'] for r in lap_recs if r.get('heart_rate')]
        hr_min, hr_max_final = get_hr_min_max(lap_hrs, hr_avg, hr_max)
        
        pwr = lap.get('avg_power', '--')
        cad = lap.get('avg_running_cadence', lap.get('avg_cadence', '--'))
        if isinstance(cad, (int, float)): cad = int(cad * 2)
        
        vo = lap.get('avg_vertical_oscillation', '--')
        if isinstance(vo, (int, float)): vo = f"{float(vo):.1f}"
        
        gct = lap.get('avg_stance_time', '--')
        if isinstance(gct, (int, float)): gct = f"{float(gct):.1f}"
        
        # 分段數據重新補上手錶記錄的單圈平均溫度
        temp = lap.get('avg_temperature', '--')
        lap_ascent = lap.get('total_ascent', 0)
        lap_descent = lap.get('total_descent', 0)
        
        parts = [f"L{i}{name_str}: {cumulative_dist/1000:.2f}km", lap_time_str, lap_pace]
        
        if hr_avg != '--':
            parts.append(f"HR{hr_avg}({hr_min}/{hr_max_final})")
                
        if pwr != '--': parts.append(f"Pwr{pwr}")
        if cad != '--': parts.append(f"Cad{cad}")
        if vo != '--': parts.append(f"VO{vo}")
        if gct != '--': parts.append(f"GCT{gct}")
        if temp != '--': parts.append(f"Temp{temp}") # 補回分段溫度
        parts.append(f"Elev+{lap_ascent}/-{lap_descent}")
        
        lap_str = " | ".join(parts)
        sub_laps_str = generate_sub_laps(lap_recs)
        out.append(lap_str + sub_laps_str)
        
    return "\n".join(out)

# --- 網頁介面設計 ---
st.set_page_config(page_title="Garmin 數據解碼器", page_icon="🏃‍♂️")
st.title("🏃‍♂️ Garmin FIT 原始數據解碼器")
st.write("上傳您的 `.fit` 檔案，自動生成可複製的純文字分段報告。")

uploaded_file = st.file_uploader("請選擇 FIT 檔案", type=["fit"])

if uploaded_file is not None:
    try:
        with st.spinner("正在解析您的跑步數據..."):
            file_bytes = uploaded_file.read()
            result = parse_fit_bytes_to_text(file_bytes)
            
        st.success("解析成功！")
        st.text_area("請在下方全選複製您的數據：", value=result, height=500)
    except Exception as e:
        st.error(f"解析失敗，請確認檔案格式是否正確。錯誤訊息：{e}")
