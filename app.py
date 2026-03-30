import streamlit as st
import google.generativeai as genai
from PIL import Image
import sqlite3
import pandas as pd
from datetime import date, datetime
import json
import uuid

# --- إعدادات الصفحة ---
st.set_page_config(page_title="AI Nutrition", page_icon="✨", layout="centered", initial_sidebar_state="collapsed")

# CSS
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
             (date TEXT, time TEXT, food_name TEXT, calories REAL, protein REAL, carbs REAL, fat REAL, fiber REAL, username TEXT)''')
c.execute("PRAGMA table_info(daily_logs)")
log_cols = [col[1] for col in c.fetchall()]
if 'username' not in log_cols:
    c.execute("ALTER TABLE daily_logs ADD COLUMN username TEXT DEFAULT 'admin'")

c.execute('''CREATE TABLE IF NOT EXISTS user_targets
             (username TEXT PRIMARY KEY, calories REAL, protein REAL, carbs REAL, fat REAL, fiber REAL)''')
c.execute("PRAGMA table_info(user_targets)")
target_cols = [col[1] for col in c.fetchall()]
if 'username' not in target_cols:
    c.execute("DROP TABLE user_targets")
    c.execute('''CREATE TABLE user_targets
                 (username TEXT PRIMARY KEY, calories REAL, protein REAL, carbs REAL, fat REAL, fiber REAL)''')

# جدول الأمان الجديد لحفظ جلسات (تذكرني)
c.execute('''CREATE TABLE IF NOT EXISTS user_auth
             (username TEXT PRIMARY KEY, api_key TEXT, session_token TEXT)''')
conn.commit()

def get_gemini_model(api_key):
    genai.configure(api_key=api_key)
    best_model = "gemini-pro-vision" 
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            if 'flash' in m.name.lower() or 'vision' in m.name.lower():
                best_model = m.name
                break
    return genai.GenerativeModel(best_model)

# --- نظام الذاكرة وتذكرني (Session & Auto-Login) ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.api_key = ""

# الدخول التلقائي السري إذا كان المتصفح يحتفظ بالرابط (تذكرني)
if not st.session_state.logged_in:
    url_params = st.query_params
    if "token" in url_params:
        token = url_params["token"]
        c.execute("SELECT username, api_key FROM user_auth WHERE session_token=?", (token,))
        auth_data = c.fetchone()
        if auth_data:
            st.session_state.username = auth_data[0]
            st.session_state.api_key = auth_data[1]
            st.session_state.logged_in = True

# شاشة الدخول (تظهر فقط إذا لم تكن مسجلاً)
if not st.session_state.logged_in:
    st.markdown("<br><h2 style='text-align: center;'>👋 أهلاً بك في مساعد التغذية</h2>", unsafe_allow_html=True)
    with st.container(border=True):
        st.info("سجل دخولك أو أنشئ حسابك للبدء:")
        
        user_input = st.text_input("👤 اسم المستخدم:", placeholder="اكتب اسمك هنا")
        key_input = st.text_input("🔑 مفتاح API الخاص بك:", type="password")
        remember_me = st.checkbox("☑️ تذكرني (عدم الخروج عند عمل Refresh)", value=True)
        
        if st.button("دخول 🚀", use_container_width=True, type="primary"):
            if user_input and key_input:
                username_val = user_input.strip()
                api_key_val = key_input.strip()
                
                st.session_state.username = username_val
                st.session_state.api_key = api_key_val
                st.session_state.logged_in = True
                
                if remember_me:
                    # برمجة ميزة تذكرني بوضع توكن سري في الرابط
                    token = str(uuid.uuid4())
                    c.execute("INSERT OR REPLACE INTO user_auth (username, api_key, session_token) VALUES (?, ?, ?)", (username_val, api_key_val, token))
                    conn.commit()
                    st.query_params["token"] = token
                else:
                    c.execute("INSERT OR REPLACE INTO user_auth (username, api_key, session_token) VALUES (?, ?, ?)", (username_val, api_key_val, ""))
                    conn.commit()
                    if "token" in st.query_params:
                        del st.query_params["token"]
                        
                st.rerun()
            else:
                st.error("يرجى إدخال الاسم والمفتاح للبدء.")
    st.stop()

# --- المتغيرات الحالية للمستخدم ---
username = st.session_state.username
api_key = st.session_state.api_key

# --- القائمة الجانبية ---
with st.sidebar:
    st.header(f"👤 مرحباً، {username}")
    if st.button("🚪 تسجيل الخروج"):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.session_state.api_key = ""
        if "token" in st.query_params:
            del st.query_params["token"]
        st.rerun()
        
    st.divider()

    c.execute("SELECT calories, protein, carbs, fat, fiber FROM user_targets WHERE username=?", (username,))
    user_data = c.fetchone()
    if not user_data:
        c.execute("INSERT INTO user_targets VALUES (?, 2250, 142, 255, 75, 35)", (username,))
        conn.commit()
        t_cal, t_pro, t_carbs, t_fat, t_fib = 2250, 142, 255, 75, 35
    else:
        t_cal, t_pro, t_carbs, t_fat, t_fib = user_data

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
            c.execute("UPDATE user_targets SET calories=?, protein=?, carbs=?, fat=?, fiber=? WHERE username=?",
                      (new_cal, new_pro, new_carbs, new_fat, new_fib, username))
            conn.commit()
            st.success("تم التحديث!")
            st.rerun()

    with st.expander("🤖 حساب الأهداف بالذكاء الاصطناعي"):
        profile_info = st.text_area("معلوماتك:", placeholder="العمر، الطول، الوزن، النشاط، الهدف...", height=100)
        if st.button("احسب أهدافي 🎯", use_container_width=True):
            if not profile_info:
                st.warning("أدخل معلوماتك أولاً.")
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
                        
                        c.execute("UPDATE user_targets SET calories=?, protein=?, carbs=?, fat=?, fiber=? WHERE username=?",
                                  (new_targets['calories'], new_targets['protein'], new_targets['carbs'], new_targets['fat'], new_targets['fiber'], username))
                        conn.commit()
                        st.success("تم الحساب والتحديث!")
                        st.rerun()
                except Exception as e:
                    st.error("خطأ في الحساب.")

# --- الواجهة الرئيسية وتفريغ مربع النص تلقائياً ---
st.markdown("<br><h2 style='text-align: center;'>✨ مساعد التغذية الشخصي</h2><br>", unsafe_allow_html=True)

# دوال التفريغ التلقائي للنص
if 'user_text' not in st.session_state:
    st.session_state.user_text = ""
if 'process_text' not in st.session_state:
    st.session_state.process_text = ""

def submit_action():
    if st.session_state.user_text:
        st.session_state.process_text = st.session_state.user_text
        st.session_state.user_text = "" # تفريغ النص من الشاشة

with st.container(border=True):
    col_input, col_submit = st.columns([7, 1.5])
    with col_input:
        # on_change يسمح لك بالإرسال بمجرد الضغط على Enter في الكيبورد
        st.text_input("ماذا أكلت اليوم؟", key="user_text", placeholder="اكتب وجبتك هنا ثم اضغط Enter...", label_visibility="collapsed", on_change=submit_action)
    with col_submit:
        st.button("⏩", on_click=submit_action, use_container_width=True)

    tab_gallery, tab_camera = st.tabs(["🖼️ إرفاق من المعرض", "📷 التقاط مباشر"])
    with tab_gallery:
        uploaded_file = st.file_uploader("تصفح", type=["jpg", "jpeg", "png"], label_visibility="collapsed")
    with tab_camera:
        camera_photo = st.camera_input("تصوير", label_visibility="collapsed")

# --- معالجة الوجبة المرسلة ---
text_to_process = st.session_state.process_text
if text_to_process or camera_photo or uploaded_file:
    try:
        model = get_gemini_model(api_key)
        system_prompt = """
        أنت خبير تغذية. أعد فقط كائن JSON:
        {"food_name": "اسم الطعام", "calories": 0, "protein": 0, "carbs": 0, "fat": 0, "fiber": 0}
        """
        inputs = [system_prompt]
        if text_to_process: 
            inputs.append(f"التفاصيل: {text_to_process}")
        
        photo_to_process = camera_photo if camera_photo else uploaded_file
        if photo_to_process: 
            inputs.append(Image.open(photo_to_process))
        
        with st.spinner("✨ جاري التحليل..."):
            response = model.generate_content(inputs)
            data = json.loads(response.text.strip().replace('```json', '').replace('```', ''))
            
            today = str(date.today())
            current_time = datetime.now().strftime("%H:%M") 
            
            c.execute("INSERT INTO daily_logs (date, time, food_name, calories, protein, carbs, fat, fiber, username) VALUES (?,?,?,?,?,?,?,?,?)", 
                      (today, current_time, data["food_name"], data["calories"], data["protein"], data["carbs"], data["fat"], data["fiber"], username))
            conn.commit()
            
            st.session_state.process_text = "" # تنظيف الذاكرة بعد الإرسال الناجح
            st.rerun()
            
    except Exception as e:
        st.error(f"حدث خطأ في قراءة الوجبة: أعد المحاولة بشكل أوضح.")
        st.session_state.process_text = "" # تنظيف الذاكرة حتى لو حدث خطأ

# --- عرض السجل ---
st.divider()
today_str = str(date.today())
df = pd.read_sql_query(f"SELECT rowid, * FROM daily_logs WHERE date='{today_str}' AND username='{username}'", conn)

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
