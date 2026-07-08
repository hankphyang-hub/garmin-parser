import streamlit as st
from garmin_fit_sdk import Decoder, Stream
import datetime

def format_time(seconds):
    if seconds is None: return "00:00:00"
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

def m_per_s_to_pace(m_per_s):
    if not m_per_s or m_per_s <= 0: return "--:--/km"
    sec_per_km = 1000 / m_per_s
    m = int(sec_per_km // 60)
    s = int(sec_per_km % 60)
    return f"{m}:{s:02d}/km"

def parse_fit_bytes_to_text(file_bytes):
    # 這裡改成直接從記憶體(Bytes)讀取上傳的檔案，而不是從硬碟路徑讀取
    stream = Stream.from_byte_array(bytearray(file_bytes))
    decoder = Decoder(stream)
    messages, errors = decoder.read()

    session_mesgs = messages.get('session_mesgs', [])
    lap_mesgs = messages.get('lap_mesgs', [])
    
    if not session_mesgs:
        return "找不到摘要數據。"
        
    session = session_mesgs[0]
    
    # 處理概要數據
    sport = session.get('sport', 'unknown')
    dt = session.get('start_time', 'Unknown')
    if isinstance(dt, datetime.datetime):
        date_str = dt.strftime("%Y/%m/%d %p%I:%M:%S").replace("AM", "上午").replace("PM", "下午")
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
    te = session.get('total_training_effect', '--')
    
    device = "Unknown Garmin Device"
    file_id_mesgs = messages.get('file_id_mesgs', [])
    if file_id_mesgs:
        device = file_id_mesgs[0].get('garmin_product', device)
        
    out = []
    out.append("[图例] HR=心率(bpm) Pwr=功率(W) Cad=踏频(rpm/spm) GCT=触地时间(ms) VO=垂直振幅(mm) Elev=海拔(m)\n")
    out.append("[概要]")
    out.append(f"运动: {sport}\n日期: {date_str}\n用时: {duration_str} | 距离: {total_dist_km:.2f}km")
    out.append(f"平均配速: {avg_pace} | 最大速度: {max_speed_kph:.1f}kph")
    out.append(f"HR: 平均 {avg_hr} / 最大 {max_hr}\n海拔: +{ascent}m / -{descent}m\n卡路里: {calories}")
    out.append(f"额外数据: 平均 Pwr: {avg_pwr}W (最大 {max_pwr}W) | 平均 Cad: {avg_cad} | TE: {te}")
    out.append(f"设备: {device}\n\n[分段]")
    
    cumulative_dist = 0
    for i, lap in enumerate(lap_mesgs, 1):
        cumulative_dist += lap.get('total_distance', 0)
        lap_time_str = format_time(lap.get('total_timer_time', 0))
        lap_pace = m_per_s_to_pace(lap.get('enhanced_avg_speed', 0))
        
        hr = lap.get('avg_heart_rate', '--')
        pwr = lap.get('avg_power', '--')
        cad = lap.get('avg_running_cadence', lap.get('avg_cadence', '--'))
        
        vo = lap.get('avg_vertical_oscillation', '--')
        if isinstance(vo, (int, float)): vo = round(vo / 10)
        
        gct = lap.get('avg_stance_time', '--')
        if isinstance(gct, (int, float)): gct = round(gct / 10)
        
        parts = [f"L{i}: {cumulative_dist/1000:.2f}km", lap_time_str, lap_pace]
        if hr != '--': parts.append(f"HR{hr}")
        if pwr != '--': parts.append(f"Pwr{pwr}")
        if cad != '--': parts.append(f"Cad{cad}")
        if vo != '--': parts.append(f"VO{vo}")
        if gct != '--': parts.append(f"GCT{gct}")
        
        out.append(" | ".join(parts))
        
    return "\n".join(out)

# --- 網頁介面設計 ---
st.set_page_config(page_title="Garmin 數據解碼器", page_icon="🏃‍♂️")
st.title("🏃‍♂️ Garmin FIT 原始數據解碼器")
st.write("上傳你的 `.fit` 檔案，自動生成可複製的純文字分段報告。")

uploaded_file = st.file_uploader("請選擇 FIT 檔案", type=["fit"])

if uploaded_file is not None:
    try:
        with st.spinner("正在解析數據中..."):
            file_bytes = uploaded_file.read()
            result = parse_fit_bytes_to_text(file_bytes)
            
        st.success("解析成功！")
        # 用 text_area 顯示，讓使用者點擊就能直接全選複製
        st.text_area("請在下方全選複製你的數據：", value=result, height=450)
    except Exception as e:
        st.error(f"解析失敗，請確認檔案格式是否正確。錯誤訊息：{e}")
