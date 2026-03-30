import streamlit as st
import google.generativeai as genai
from PIL import Image
import sqlite3
import pandas as pd
from datetime import date, datetime
import json

# --- إعدادات الصفحة ---
st.set_page_config(page_title="AI Nutrition", page_icon="✨", layout="centered", initial_sidebar_state="collapsed")

# CSS لإخفاء زر النشر وتحسين المظهر
st.markdown("""
<style>
    .stDeployButton {display:none;}
    .stProgress > div > div > div { background-color: #4CAF50; }
</style>
""", unsafe_allow_html=True)

# --- إعداد قاعدة البيانات (للمستخدم الواحد) ---
conn = sqlite3.connect('nutrition_data.db', check_same_thread=False)
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS daily_logs
             (date TEXT, time TEXT, food_name TEXT, calories REAL, protein REAL, carbs REAL, fat REAL, fiber REAL)''')
# إضافة خانة الوقت إذا لم تكن موجودة
c.execute("PRAGMA table_info(daily_logs)")
cols = [col[1] for col in c.fetchall()]
if 'time' not in cols:
    c.execute("ALTER TABLE daily_logs ADD COLUMN time TEXT DEFAULT '-'")

c.execute('''CREATE TABLE IF NOT EXISTS user_targets
             (id INTEGER PRIMARY KEY, calories REAL, protein REAL, carbs REAL, fat REAL, fiber REAL)''')
c.execute("SELECT * FROM user_targets WHERE id=1")
if not c.fetchone():
    c.execute("INSERT INTO user_targets (id, calories, protein, carbs, fat, fiber) VALUES (1, 2250, 142, 255, 75, 35)")
conn.commit()

c.execute("SELECT calories, protein, carbs, fat, fiber FROM user_targets WHERE id=1")
t_cal, t_pro, t_carbs, t_fat, t_fib = c.fetchone()

# الدالة الأصلية التي كانت تعمل معك بشكل ممتاز
def get_gemini_model(api_key):
    genai.configure(api_key=api_key)
    best_model = "gemini-pro-vision" 
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            if 'flash' in m.name.lower() or 'vision' in m.name.lower():
                best_model = m.name
                break
    return genai.GenerativeModel(best_model)

# --- القائمة الجانبية (الإعدادات البسيطة) ---
with st.sidebar:
    st.header("⚙️ الإعدادات والأهداف")
    # سحب المفتاح من الأسرار إذا كان موجوداً
    saved_key = st.secrets.get("GEMINI_API_KEY", "") if hasattr(st, "secrets") else ""
    api_key = st.text_input("🔑 API Key:", type="password", value=saved_key)
    
    st.divider()
    
    with st.expander("✏️ تعديل الأهداف يدوياً"):
        col1, col2 = st.columns(2)
        with col1:
            new_cal = st.number_input("🔥 السعرات", min_value=1000, max_value=5000, value=int(t_cal), step=50)
            new_carbs = st.number_input("🍚 الكارب (g)", min_value=0, max_value=500, value=int(t_carbs), step=5)
            new_fib = st.number_input("🥗 الألياف (g)", min_value=0, max_value=80, value=int(t_fib), step=1)
        with col2:
            new_pro = st.number_input("🥩 البروتين (g)", min_value=0, max_value=300, value=int(t_pro), step=5)
            new_fat = st.number_input("🥑 الدهون (g)", min_value=0, max_value=200, value=int(t_fat), step=5)
            
        if st.button("حفظ التعديلات 💾", use_container_width=True):
            c.execute("UPDATE user_targets SET calories=?, protein=?, carbs=?, fat=?, fiber=? WHERE id=1",
                      (new_cal, new_pro, new_carbs, new_fat, new_fib))
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
                    {{"calories": 0, "protein": 0, "carbs": 0, "fat": 0, "fiber": 0}}
                    """
                    with st.spinner("جاري الحساب..."):
                        res = model.generate_content(prompt)
                        clean_res = res.text.strip().replace('```json', '').replace('```', '')
                        new_targets = json.loads(clean_res)
                        
                        c.execute("UPDATE user_targets SET calories=?, protein=?, carbs=?, fat=?, fiber=? WHERE id=1",
                                  (new_targets['calories'], new_targets['protein'], new_targets['carbs'], new_targets['fat'], new_targets['fiber']))
                        conn.commit()
                        st.success("تم الحساب والتحديث!")
                        st.rerun()
                except Exception as e:
                    st.error(f"خطأ في الحساب. التفاصيل: {e}")

# --- الواجهة الرئيسية (مع ميزة مسح النص التلقائي) ---
st.markdown("<br><h2 style='text-align: center;'>✨ مساعد التغذية الشخصي</h2><br>", unsafe_allow_html=True)

if 'user_text' not in st.session_state:
    st.session_state.user_text = ""
if 'process_text' not in st.session_state:
    st.session_state.process_text = ""

def submit_action():
    if st.session_state.user_text:
        st.session_state.process_text = st.session_state.user_text
        st.session_state.user_text = "" 

with st.container(border=True):
    col_input, col_submit = st.columns([7, 1.5])
    with col_input:
        st.text_input("ماذا أكلت اليوم؟", key="user_text", placeholder="اكتب وجبتك هنا ثم اضغط Enter...", label_visibility="collapsed", on_change=submit_action)
    with col_submit:
        st.button("⏩", on_click=submit_action, use_container_width=True)

    tab_gallery, tab_camera = st.tabs(["🖼️ إرفاق من المعرض", "📷 التقاط مباشر"])
    with tab_gallery:
        uploaded_file = st.file_uploader("تصفح", type=["jpg", "jpeg", "png"], label_visibility="collapsed")
    with tab_camera:
        camera_photo = st.camera_input("تصوير", label_visibility="collapsed")

# --- معالجة الإدخال ---
text_to_process = st.session_state.process_text
if text_to_process or camera_photo or uploaded_file:
    if not api_key:
        st.error("يرجى إدخال API Key في القائمة الجانبية أو في الإعدادات السرية للموقع.")
        st.session_state.process_text = ""
    else:
        try:
            model = get_gemini_model(api_key)
            system_prompt = """
            أنت خبير تغذية. أعد فقط كائن JSON:
            {"food_name": "اسم الطعام", "calories": 0, "protein": 0, "carbs": 0, "fat": 0, "fiber": 0}
            """
            inputs = [system_prompt]
            if text_to_process: inputs.append(f"التفاصيل: {text_to_process}")
            
            photo_to_process = camera_photo if camera_photo else uploaded_file
            if photo_to_process: inputs.append(Image.open(photo_to_process))
            
            with st.spinner("✨ جاري التحليل..."):
                response = model.generate_content(inputs)
                clean_text = response.text.strip().replace('```json', '').replace('```', '')
                data = json.loads(clean_text)
                
                today = str(date.today())
                current_time = datetime.now().strftime("%H:%M") 
                
                # التعامل مع قاعدة البيانات لضمان عدم حدوث خطأ بسبب التحديثات السابقة
                c.execute("PRAGMA table_info(daily_logs)")
                log_cols = [col[1] for col in c.fetchall()]
                
                if 'username' in log_cols:
                    c.execute("INSERT INTO daily_logs (date, time, food_name, calories, protein, carbs, fat, fiber, username) VALUES (?,?,?,?,?,?,?,?,?)", 
                              (today, current_time, data["food_name"], data["calories"], data["protein"], data["carbs"], data["fat"], data["fiber"], "admin"))
                else:
                    c.execute("INSERT INTO daily_logs (date, time, food_name, calories, protein, carbs, fat, fiber) VALUES (?,?,?,?,?,?,?,?)", 
                              (today, current_time, data["food_name"], data["calories"], data["protein"], data["carbs"], data["fat"], data["fiber"]))
                conn.commit()
                
                st.session_state.process_text = ""
                st.rerun()
                
        except Exception as e:
            st.error(f"حدث خطأ. (التفاصيل: {e})")
            st.session_state.process_text = ""

# --- عرض السجل ---
st.divider()
today_str = str(date.today())

c.execute("PRAGMA table_info(daily_logs)")
if 'username' in [col[1] for col in c.fetchall()]:
    df = pd.read_sql_query(f"SELECT rowid, * FROM daily_logs WHERE date='{today_str}' AND username='admin'", conn)
else:
    df = pd.read_sql_query(f"SELECT rowid, * FROM daily_logs WHERE date='{today_str}'", conn)

total_cals = df['calories'].sum() if not df.empty else 0
prot_sum = df['protein'].sum() if not df.empty else 0
fat_sum = df['fat'].sum() if not df.empty else 0
carbs_sum = df['carbs'].sum() if not df.empty else 0
fiber_sum = df['fiber'].sum() if not df.empty else 0

st.markdown(f"<h4 style='text-align: center;'>📊 استهلاك اليوم: {total_cals:.0f} / {t_cal:.0f} kcal</h4>", unsafe_allow_html=True)
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
    st.markdown(make_bar("🍚 كارب", carbs_sum, t_carbs, "#4ECDC4"), unsafe_allow_html=True)
    st.markdown(make_bar("🥗 ألياف", fiber_sum, t_fib, "#95E1D3"), unsafe_allow_html=True)

st.write("")

if not df.empty:
    with st.expander("📝 عرض وتعديل سجل الوجبات"):
        for index, row in df.sort_values(by='time', ascending=False).iterrows():
            col_info, col_del = st.columns([8, 1])
            with col_info:
                st.write(f"🕒 **{row['time']}** | 🍽️ {row['food_name']} | 🔥 **{row['calories']} kcal**")
            with col_del:
                if st.button("❌", key=f"del_{row['rowid']}"):
                    c.execute("DELETE FROM daily_logs WHERE rowid=?", (row['rowid'],))
                    conn.commit()
                    st.rerun()
