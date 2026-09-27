import streamlit as st
import pandas as pd
from datetime import datetime
from PIL import Image
import google.generativeai as genai

# --- 設定 ---
st.set_page_config(page_title="ガソリン記録アプリ", layout="centered")

# Gemini APIの設定（取得したAPIキーを入力）
API_KEY = "...CZxw"
if API_KEY != "YOUR_API_KEY":
    genai.configure(api_key=API_KEY)

st.title("⛽ ガソリン記録アプリ")

# --- 1. レシート画像アップロード ＆ 手入力 ---
st.subheader("1. レシートと走行距離を入力")

uploaded_file = st.file_uploader("レシート画像をアップロード", type=["jpg", "jpeg", "png"])
current_mileage = st.number_input("現在の総走行距離 (km)", min_value=0, step=1)

# 初期値
date_val = datetime.now()
volume_val = 0.0
amount_val = 0

# --- 2. OCR解析処理 ---
if uploaded_file is not None:
    image = Image.open(uploaded_file)
    st.image(image, caption="アップロードしたレシート", use_container_width=True)
    
    if API_KEY != "YOUR_API_KEY":
        if st.button("レシートから自動読み取り"):
            with st.spinner("AI解析中..."):
                try:
                    model = genai.GenerativeModel('gemini-1.5-flash')
                    prompt = "このレシートから「日付(YYYY-MM-DD)」「給油量(L)」「支払合計金額(円)」を抽出し、カンマ区切りで『2026-09-01,35.0,6125』のように数値のみ返してください。"
                    response = model.generate_content([prompt, image])
                    st.success(f"解析結果: {response.text}")
                except Exception as e:
                    st.error(f"解析エラー: {e}")
    else:
        st.warning("※APIキーを設定すると、レシートの自動読み取り機能が使えます。")

# --- 3. 確認・保存フォーム ---
with st.form("record_form"):
    st.subheader("2. 内容を確認して記録")
    
    input_date = st.date_input("給油日", date_val)
    input_volume = st.number_input("給油量 (L)", value=volume_val, format="%.2f")
    input_amount = st.number_input("支払金額 (円)", value=amount_val, step=1)
    
    submit_button = st.form_submit_button("データを記録する")

if submit_button:
    if current_mileage == 0 or input_volume == 0:
        st.error("走行距離と給油量を入力してください。")
    else:
        unit_price = round(input_amount / input_volume, 1) if input_volume > 0 else 0
        st.balloons()
        st.success(f"記録しました！ ガソリン単価: {unit_price} 円/L")