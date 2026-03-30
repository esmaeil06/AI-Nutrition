import streamlit as st
import google.generativeai as genai
from PIL import Image
import sqlite3
import pandas as pd
from datetime import date, datetime
import json

# --- إعدادات الصفحة ---
st.set_page_config(page_title="AI Nutrition", page_icon="✨", layout="centered", initial_sidebar_state="collapsed")

# CSS لإخفاء زر Deploy فقط وتحسين شريط التحميل
st.markdown("""
<style>
    .stDeployButton {display:none;}
    .stProgress > div > div > div { background-color: #4CAF50; }
</style>
""", unsafe_allow_html=True)

# --- إعداد قاعدة البيانات ---
conn = sqlite3.connect('nutrition_data.db', check_same_thread=False)
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS daily_logs
             (date TEXT, food_name TEXT, calories REAL, protein REAL, carbs REAL, fat REAL, fiber REAL)''')
c.execute("PRAGMA table_info(daily_logs)")
cols = [col[1] for col in c.fetchall()]
if 'time' not in cols:
    c.execute("ALTER TABLE daily_logs ADD COLUMN time TEXT DEFAULT '-'")
if 'water' not in cols:
    c.execute("ALTER TABLE daily_logs ADD COLUMN water REAL DEFAULT 0")

c.execute('''CREATE TABLE IF NOT EXISTS user_targets
             (id INTEGER PRIMARY KEY, calories REAL, protein REAL, carbs REAL, fat REAL, fiber REAL)''')
c.execute("PRAGMA table_info(user_targets)")
t_cols = [col[1] for col in c.fetchall()]
if 'water' not in t_cols:
    c.execute("ALTER TABLE user_targets ADD COLUMN water REAL DEFAULT 2500")

c.execute("SELECT * FROM user_targets WHERE id=1")
if not c.fetchone():
    c.execute("INSERT INTO user_targets (id, calories, protein, carbs, fat, fiber, water) VALUES (1, 2250, 142, 255, 75, 35, 2500)")
conn.commit()

c.execute("SELECT calories, protein, carbs, fat, fiber, water FROM user_targets WHERE id=1")
t_cal, t_pro, t_carbs, t_fat, t_fib, t_water = c.fetchone()

def get_gemini_model(api_key):
    genai.configure(api_key=api_key)
    best_model = "gemini-pro-vision" 
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            if 'flash' in m.name.lower() or 'vision' in m.name.lower():
                best_model = m.name
                break
    return genai.GenerativeModel(best_model)

# --- القائمة الجانبية (الإعدادات) ---
with st.sidebar:
    st.header("⚙️ الإعدادات والأهداف")
    
    saved_key = st.secrets.get("GEMINI_API_KEY", "") if hasattr(st, "secrets") else ""
    api_key = st.text_input("🔑 API Key:", type="password", value=saved_key)
    
    st.divider()
    
    with st.expander("✏️ تعديل الأهداف يدوياً"):
        col1, col2 = st.columns(2)
        with col1:
            new_cal = st.number_input("🔥 السعرات", min_value=1000, max_value=5000, value=int(t_cal), step=50)
            new_carbs = st.number_input("🍚 الكارب (g)", min_value=0, max_value=500, value=int(t_carbs), step=5)
            new_fib = st.number_input("🥗 الألياف (g)", min_value=0, max_value=80, value=int(t_fib), step=1)
            new_water = st.number_input("💧 الماء (ml)", min_value=500, max_value=8000, value=int(t_water), step=250)
        with col2:
            new_pro = st.number_input("🥩 البروتين (g)", min_value=0, max_value=300, value=int(t_pro), step=5)
            new_fat = st.number_input("🥑 الدهون (g)", min_value=0, max_value=200, value=int(t_fat), step=5)
            
        if st.button("حفظ التعديلات 💾", use_container_width=True):
            c.execute("UPDATE user_targets SET calories=?, protein=?, carbs=?, fat=?, fiber=?, water=? WHERE id=1",
                      (new_cal, new_pro, new_carbs, new_fat, new_fib, new_water))
            conn.commit()
            st.success("تم التحديث!")
            st.rerun()

    with st.expander("🤖 حساب الأهداف بالذكاء الاصطناعي"):
        profile_info = st.text_area("معلوماتك:", placeholder="العمر، الطول، الوزن، النشاط، الهدف...", height=100)
        if st.button("احسب أهدافي 🎯", use_container_width=True):
            if not api_key or not profile_info:
                st.warning("أدخل المفتاح والمعلومات أولاً.")
            else:
                try:
                    model = get_gemini_model(api_key)
                    prompt = f"""
                    أنت خبير تغذية. احسب الاحتياجات اليومية بناءً على: {profile_info}.
                    أعد كائن JSON فقط:
                    {{"calories": 0, "protein": 0, "carbs": 0, "fat": 0, "fiber": 0, "water": 0}}
                    """
                    with st.spinner("جاري الحساب..."):
                        res = model.generate_content(prompt)
                        clean_res = res.text.strip().replace('```json', '').replace('```', '')
                        new_targets = json.loads(clean_res)
                        
                        c.execute("UPDATE user_targets SET calories=?, protein=?, carbs=?, fat=?, fiber=?, water=? WHERE id=1",
                                  (new_targets.get('calories',0), new_targets.get('protein',0), new_targets.get('carbs',0), new_targets.get('fat',0), new_targets.get('fiber',0), new_targets.get('water',2500)))
                        conn.commit()
                        st.success("تم الحساب والتحديث!")
                        st.rerun()
                except Exception as e:
                    st.error("خطأ في الحساب.")

# --- الواجهة الرئيسية ---
st.markdown("<br><h2 style='text-align: center;'>✨ مساعد التغذية الشخصي</h2><br>", unsafe_allow_html=True)

with st.container(border=True):
    col_input, col_submit = st.columns([7, 1.5])
    with col_input:
        user_details = st.text_input("ماذا أكلت اليوم؟", placeholder="اكتب هنا...", label_visibility="collapsed")
    with col_submit:
        submit_btn = st.button("أرسل", use_container_width=True)

    # تم حذف الكاميرا وإبقاء خيار إرفاق الصور من المعرض فقط
    uploaded_file = st.file_uploader("إرفاق صورة من المعرض", type=["jpg", "jpeg", "png"])

# --- معالجة الإدخال ---
if submit_btn and (user_details or uploaded_file):
    if not api_key:
        st.error("يرجى إدخال API Key في القائمة الجانبية.")
    else:
        try:
            model = get_gemini_model(api_key)
            system_prompt = """
            أنت خبير تغذية. أعد فقط كائن JSON. وإذا كان الطعام يحتوي على سوائل أو ماء، ضع الكمية بالملليلتر في حقل water:
            {"food_name": "اسم الطعام", "calories": 0, "protein": 0, "carbs": 0, "fat": 0, "fiber": 0, "water": 0}
            """
            inputs = [system_prompt]
            if user_details: inputs.append(f"التفاصيل: {user_details}")
            
            if uploaded_file: inputs.append(Image.open(uploaded_file))
            
            with st.spinner("✨ جاري التحليل..."):
                response = model.generate_content(inputs)
                data = json.loads(response.text.strip().replace('```json', '').replace('```', ''))
                
                today = str(date.today())
                current_time = datetime.now().strftime("%H:%M") 
                
                c.execute("INSERT INTO daily_logs (date, time, food_name, calories, protein, carbs, fat, fiber, water) VALUES (?,?,?,?,?,?,?,?,?)", 
                          (today, current_time, data.get("food_name","غير معروف"), data.get("calories",0), data.get("protein",0), data.get("carbs",0), data.get("fat",0), data.get("fiber",0), data.get("water",0)))
                conn.commit()
                st.rerun()
                
        except Exception as e:
            st.error("حدث خطأ في قراءة الوجبة.")

# --- عرض السجل ---
st.divider()
today_str = str(date.today())
df = pd.read_sql_query(f"SELECT rowid, * FROM daily_logs WHERE date='{today_str}'", conn)

total_cals = df['calories'].sum() if not df.empty else 0
prot_sum = df['protein'].sum() if not df.empty else 0
fat_sum = df['fat'].sum() if not df.empty else 0
carbs_sum = df['carbs'].sum() if not df.empty else 0
fiber_sum = df['fiber'].sum() if not df.empty else 0
water_sum = df['water'].sum() if not df.empty else 0

st.markdown(f"<h4 style='text-align: center;'>استهلاك اليوم: {total_cals:.0f} / {t_cal:.0f} كالوريز</h4>", unsafe_allow_html=True)
st.progress(min(total_cals / t_cal, 1.0) if t_cal > 0 else 0)
st.write("") 

def make_bar(title, consumed, target, color):
    percent = min((consumed / target) * 100, 100) if target > 0 else 0
    return f"""
    <div style="margin-bottom: 15px;">
        <div style="display: flex; justify-content: space-between; font-size: 14px; margin-bottom: 5px; color: #ddd;">
            <strong>{title}</strong>
            <span>{consumed:.1f} / {target}g</span>
        </div>
        <div style="background-color: #2b2b36; border-radius: 8px; height: 10px; width: 100%; overflow: hidden;">
            <div style="background-color: {color}; width: {percent}%; height: 100%; border-radius: 8px;"></div>
        </div>
    </div>
    """

c1, c2 = st.columns(2)
with c1:
    st.markdown(make_bar("🥩 بروتين", prot_sum, t_pro, "#FF6B6B"), unsafe_allow_html=True)
    st.markdown(make_bar("🥑 دهون", fat_sum, t_fat, "#FFE66D"), unsafe_allow_html=True)
with c2:
    # تم تغيير لون الكارب إلى الأزرق لتمييزه عن الألياف
    st.markdown(make_bar("🍚 كارب", carbs_sum, t_carbs, "#4EA8DE"), unsafe_allow_html=True)
    st.markdown(make_bar("🥗 ألياف", fiber_sum, t_fib, "#95E1D3"), unsafe_allow_html=True)

st.write("")

if not df.empty:
    with st.expander("📝 عرض وتعديل سجل الوجبات (بالتفصيل)"):
        for index, row in df.sort_values(by='time', ascending=False).iterrows():
            col_info, col_del = st.columns([8, 1])
            with col_info:
                st.markdown(f"""
                <div style="background-color: #212121; padding: 10px; border-radius: 8px; margin-bottom: 5px;">
                    <strong>🕒 {row['time']} | 🍽️ {row['food_name']}</strong><br>
                    <span style="font-size: 13px; color: #bbb;">
                    🔥 السعرات: {row['calories']} | 🥩 بروتين: {row['protein']}g | 🍚 كارب: {row['carbs']}g | 🥑 دهون: {row['fat']}g | 🥗 ألياف: {row['fiber']}g | 💧 ماء: {row['water']}ml
                    </span>
                </div>
                """, unsafe_allow_html=True)
            with col_del:
                if st.button("❌", key=f"del_{row['rowid']}"):
                    c.execute("DELETE FROM daily_logs WHERE rowid=?", (row['rowid'],))
                    conn.commit()
                    st.rerun()

# --- قسم تتبع الماء اليدوي ---
st.divider()
st.markdown("<h4 style='text-align: center;'>💧 تتبع شرب الماء</h4>", unsafe_allow_html=True)
st.progress(min(water_sum / t_water, 1.0) if t_water > 0 else 0)
st.markdown(f"<p style='text-align: center; color: #4ECDC4;'><strong>{water_sum:.0f} / {t_water:.0f} ml</strong></p>", unsafe_allow_html=True)

def add_manual_water(amount):
    t = str(date.today())
    ct = datetime.now().strftime("%H:%M") 
    c.execute("INSERT INTO daily_logs (date, time, food_name, calories, protein, carbs, fat, fiber, water) VALUES (?,?,?,?,?,?,?,?,?)", 
              (t, ct, f"ماء ({amount}ml)", 0, 0, 0, 0, 0, amount))
    conn.commit()
    st.rerun()

w1, w2, w3, w4 = st.columns(4)
if w1.button("🥤 +250ml", use_container_width=True): add_manual_water(250)
if w2.button("💧 +500ml", use_container_width=True): add_manual_water(500)
if w3.button("🚰 +1000ml", use_container_width=True): add_manual_water(1000)
with w4:
    custom_water = st.number_input("مخصص", min_value=0, step=100, label_visibility="collapsed", placeholder="أضف رقم")
    if st.button("إضافة", use_container_width=True) and custom_water > 0:
        add_manual_water(custom_water)
