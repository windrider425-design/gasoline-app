import streamlit as st
import pandas as pd
from datetime import datetime
from PIL import Image
from google import genai
import os

# --- 設定 ---
st.set_page_config(page_title="ガソリン記録アプリ", layout="wide")

DATA_FILE = "gasoline_data.csv"

# APIキーをStreamlit Secretsから安全に取得
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except Exception:
    API_KEY = ""

COLUMN_ORDER = [
    "車両", "日付", "スタンド名", "総走行距離(ODO)", "ODO差分(km)", "区間距離(TRIP)",
    "給油量(L)", "支払金額(円)", "ガソリン単価(円/L)", "燃費(km/L)",
    "統計対象", "備考"
]

st.title("⛽ ガソリン記録アプリ")

# セッション状態の初期化
if "parsed_date" not in st.session_state:
    st.session_state.parsed_date = datetime.now()
if "parsed_ss_name" not in st.session_state:
    st.session_state.parsed_ss_name = ""
if "parsed_volume" not in st.session_state:
    st.session_state.parsed_volume = 0.0
if "parsed_unit_price" not in st.session_state:
    st.session_state.parsed_unit_price = 0.0
if "parsed_amount" not in st.session_state:
    st.session_state.parsed_amount = 0
if "parsed_hand_trip" not in st.session_state:
    st.session_state.parsed_hand_trip = None
if "parsed_hand_odo" not in st.session_state:
    st.session_state.parsed_hand_odo = None
if "is_parsed" not in st.session_state:
    st.session_state.is_parsed = False
if "bulk_df" not in st.session_state:
    st.session_state.bulk_df = None

# --- 車両選択 ---
st.sidebar.header("🚗 車両選択")
car_option = st.sidebar.selectbox("記録・表示する車両を選択", ["アウトバックBS9", "アウトバックBMR"])

st.subheader(f"車両: 【{car_option}】")

# 過去データの読み込み（前回データ・スタンド名の取得用）
last_odo = 0
last_ss_name = ""
avg_fe_historical = 0.0

if os.path.exists(DATA_FILE):
    try:
        df_exist = pd.read_csv(DATA_FILE)
        if "車両" in df_exist.columns:
            df_car_exist = df_exist[df_exist["車両"] == car_option].dropna(subset=["日付"]).copy()
            if not df_car_exist.empty:
                df_car_exist["dt"] = pd.to_datetime(df_car_exist["日付"], errors='coerce')
                df_car_sorted = df_car_exist.sort_values("dt")
                
                if "総走行距離(ODO)" in df_car_sorted.columns:
                    last_odo = df_car_sorted["総走行距離(ODO)"].iloc[-1]
                if "スタンド名" in df_car_sorted.columns and pd.notna(df_car_sorted["スタンド名"].iloc[-1]):
                    last_ss_name = str(df_car_sorted["スタンド名"].iloc[-1])
                    
                if "燃費(km/L)" in df_car_sorted.columns and "統計対象" in df_car_sorted.columns:
                    valid_fe = df_car_sorted[(df_car_sorted["統計対象"] == True) & (df_car_sorted["燃費(km/L)"] > 0)]
                    if not valid_fe.empty:
                        avg_fe_historical = valid_fe["燃費(km/L)"].mean()
    except Exception:
        pass

# --- タブによる機能切り替え（通常入力 / 大量一括読み取り） ---
tab_single, tab_bulk = st.tabs(["⛽ 都度記録（1枚）", "📸 レシート一括読み取り（複数枚）"])

# ==========================================
# タブ1: 通常の都度入力
# ==========================================
with tab_single:
    st.markdown("### 1. レシートと走行距離を入力")

    col_img, col_input = st.columns([1, 1])

    with col_img:
        input_method = st.radio("レシート画像の入力方法", ["ファイルから選択", "📷 スマホのカメラで撮影"], horizontal=True)
        
        image = None
        if input_method == "ファイルから選択":
            uploaded_file = st.file_uploader("レシート画像をアップロード", type=["jpg", "jpeg", "png"], key="single_file")
            if uploaded_file is not None:
                image = Image.open(uploaded_file)
        else:
            camera_file = st.camera_input("カメラで撮影")
            if camera_file is not None:
                image = Image.open(camera_file)

        if image is not None:
            st.image(image, caption="対象のレシート", width=300)
            if st.button("🤖 レシートから自動読み取り", key="btn_single_parse"):
                if not API_KEY:
                    st.error("APIキーが設定されていません。Streamlit Secretsを確認してください。")
                else:
                    with st.spinner("AI解析中（店舗名・手書きメモ含む）..."):
                        try:
                            client = genai.Client(api_key=API_KEY)
                            prompt = (
                                "このレシートから以下の項目を抽出してください。\n"
                                "1. 日付 (YYYY-MM-DD)\n"
                                "2. ガソリンスタンド名（店舗名・会社名。例: ENEOS〇〇SS, 出光 〇〇店など）\n"
                                "3. 給油量 (L)\n"
                                "4. 単価 (円/L)\n"
                                "5. 支払合計金額 (円)\n"
                                "6. レシート上部や余白に手書きされている『TRIP』または『トリップ』または『区間距離』の数値(km)\n"
                                "7. レシート上部や余白に手書きされている『ODO』または『オド』または『総走行距離』の数値(km)\n\n"
                                "該当がない項目や不明な場合は None としてください。\n"
                                "出力はカンマ区切りで『2026-09-01,ENEOS 百草SS,35.0,162.0,5670,450.2,123456』のように1行で返してください。"
                            )
                            
                            response = client.models.generate_content(
                                model='gemini-3.6-flash',
                                contents=[image, prompt]
                            )
                            
                            res_text = response.text.strip()
                            parts = res_text.split(",")
                            
                            if len(parts) >= 5:
                                st.session_state.parsed_date = datetime.strptime(parts[0].strip(), "%Y-%m-%d")
                                st.session_state.parsed_ss_name = parts[1].strip() if parts[1].strip() != "None" else last_ss_name
                                st.session_state.parsed_volume = float(parts[2].strip())
                                st.session_state.parsed_unit_price = float(parts[3].strip())
                                st.session_state.parsed_amount = int(float(parts[4].strip()))
                                
                                st.session_state.parsed_hand_trip = float(parts[5].strip()) if (len(parts) > 5 and parts[5].strip().replace('.', '', 1).isdigit()) else None
                                st.session_state.parsed_hand_odo = int(float(parts[6].strip())) if (len(parts) > 6 and parts[6].strip().replace('.', '', 1).isdigit()) else None

                                st.session_state.is_parsed = True
                                st.success("解析完了！スタンド名や手書きメモも読み取りました")
                            else:
                                st.warning(f"取得データ形式エラー: {res_text}")
                        except Exception as e:
                            st.error(f"解析エラー: {e}")

    with col_input:
        if last_odo > 0:
            st.info(f"💡 前回のODO（総走行距離）: **{int(last_odo):,} km**")

        trip_distance = st.number_input("今回リセットした区間距離 (TRIP km)", min_value=0.0, step=0.1, format="%.1f", help="ガソリンを入れた時にリセットしているトリップメーターの距離を入力")
        
        estimated_odo = int(last_odo + trip_distance) if (last_odo > 0 and trip_distance > 0) else int(last_odo)
        odo_help = f"前回のODO ({int(last_odo):,}km) + TRIP ({trip_distance}km) ＝ 想定ODO ({estimated_odo:,}km)" if (last_odo > 0 and trip_distance > 0) else ""

        current_odo = st.number_input(
            "現在の総走行距離 (ODO km)", 
            min_value=0, 
            value=estimated_odo if (last_odo > 0 and trip_distance > 0) else (int(last_odo) if last_odo > 0 else 0), 
            step=1,
            help=odo_help
        )

    odo_diff = current_odo - last_odo if (last_odo > 0 and current_odo > last_odo) else 0

    if st.session_state.is_parsed:
        st.markdown("---")
        st.markdown("### 📋 解析・計算結果の確認")
        
        calc_amount = int(round(st.session_state.parsed_unit_price * st.session_state.parsed_volume))
        amount_diff = st.session_state.parsed_amount - calc_amount
        calc_fe = round(trip_distance / st.session_state.parsed_volume, 2) if (trip_distance > 0 and st.session_state.parsed_volume > 0) else 0.0

        col_scan, col_calc = st.columns(2)
        
        with col_scan:
            st.markdown("#### 📄 スキャン値（レシート＆手書き記載）")
            c1, c2 = st.columns(2)
            c1.metric("📅 給油日", st.session_state.parsed_date.strftime("%Y/%m/%d"))
            c2.metric("⛽ ガソリンスタンド名", st.session_state.parsed_ss_name if st.session_state.parsed_ss_name else "未指定")
            
            c3, c4 = st.columns(2)
            c3.metric("💡 単価", f"{st.session_state.parsed_unit_price} 円/L")
            c4.metric("⛽ 給油量", f"{st.session_state.parsed_volume:.2f} L")

            c_p, c_t = st.columns(2)
            c_p.metric("💴 支払合計金額", f"{st.session_state.parsed_amount:,} 円")
            c_t.metric("📝 手書きTRIP (参考)", f"{st.session_state.parsed_hand_trip:.1f} km" if st.session_state.parsed_hand_trip is not None else "読み取り無し")

        with col_calc:
            st.markdown("#### 🧮 計算値（算出結果）")
            c5, c6 = st.columns(2)
            c5.metric("💰 計算合計金額", f"{calc_amount:,} 円", 
                      delta=f"差額: {amount_diff:+d}円" if amount_diff != 0 else "レシートと一致", 
                      delta_color="inverse" if amount_diff != 0 else "normal")
            c6.metric("🏎️ 概算燃費", f"{calc_fe:.2f} km/L" if calc_fe > 0 else "TRIP未入力")
            
            c7, c8 = st.columns(2)
            c7.metric("📏 ODO差分", f"{odo_diff:,} km" if odo_diff > 0 else "前回同値/未入力")
            c8.metric("📊 TRIPとの差", f"{round(trip_distance - odo_diff, 1):+g} km" if (odo_diff > 0 and trip_distance > 0) else "-")

        if calc_fe > 0 and avg_fe_historical > 0:
            if calc_fe < (avg_fe_historical * 0.8):
                st.warning(f"⚠️ **燃費注意アラート**: 今回の概算燃費（{calc_fe:.2f} km/L）は、過去の平均（{avg_fe_historical:.2f} km/L）より20%以上低めです。")

    st.markdown("---")
    with st.form("record_form"):
        st.markdown("### 2. 内容を確認して記録")
        
        default_ss = st.session_state.parsed_ss_name if st.session_state.parsed_ss_name else last_ss_name

        col1, col2, col3, col4, col5 = st.columns([1.2, 1.8, 1, 1, 1])
        with col1:
            input_date = st.date_input("給油日", st.session_state.parsed_date)
        with col2:
            input_ss_name = st.text_input("⛽ スタンド名", value=default_ss, placeholder="例: ENEOS 日野SS")
        with col3:
            input_volume = st.number_input("給油量 (L)", value=st.session_state.parsed_volume, format="%.2f")
        with col4:
            input_unit_price = st.number_input("単価 (円/L)", value=st.session_state.parsed_unit_price, format="%.1f")
        with col5:
            input_amount = st.number_input("支払金額 (円)", value=st.session_state.parsed_amount, step=1)
        
        col_m, col_c = st.columns([3, 1])
        with col_m:
            input_memo = st.text_input("📝 備考（任意メモ）", placeholder="例: 旅行で高速利用、エアコン多用など")
        with col_c:
            input_use_stat = st.checkbox("📊 統計・分析データに含める", value=True)
        
        submit_button = st.form_submit_button("データを記録する")

    if submit_button:
        if trip_distance == 0 or input_volume == 0:
            st.error("TRIP距離（区間距離）と給油量を入力してください。")
        else:
            final_unit_price = input_unit_price if input_unit_price > 0 else round(input_amount / input_volume, 1)
            fuel_efficiency = round(trip_distance / input_volume, 2) if trip_distance > 0 and input_volume > 0 else 0

            new_data = pd.DataFrame([{
                "車両": car_option,
                "日付": input_date.strftime("%Y-%m-%d"),
                "スタンド名": input_ss_name.strip(),
                "総走行距離(ODO)": current_odo,
                "ODO差分(km)": odo_diff if odo_diff > 0 else None,
                "区間距離(TRIP)": trip_distance,
                "給油量(L)": input_volume,
                "支払金額(円)": input_amount,
                "ガソリン単価(円/L)": final_unit_price,
                "燃費(km/L)": fuel_efficiency,
                "統計対象": input_use_stat,
                "備考": input_memo.strip()
            }])

            if os.path.exists(DATA_FILE):
                df_exist = pd.read_csv(DATA_FILE)
                df_combined = pd.concat([df_exist, new_data], ignore_index=True)
                for col in COLUMN_ORDER:
                    if col not in df_combined.columns:
                        df_combined[col] = None
                df_combined = df_combined[COLUMN_ORDER]
                df_combined.to_csv(DATA_FILE, index=False, encoding="utf-8-sig")
            else:
                new_data = new_data[COLUMN_ORDER]
                new_data.to_csv(DATA_FILE, index=False, encoding="utf-8-sig")

            st.balloons()
            st.success(f"記録しました！ 【{car_option}】 店舗: {input_ss_name} | 単価: {final_unit_price} 円/L | 燃費: {fuel_efficiency} km/L")
            st.session_state.is_parsed = False
            st.rerun()

# ==========================================
# タブ2: 複数枚レシートの一括読み取り＆データ化
# ==========================================
with tab_bulk:
    st.markdown("### 📸 複数レシートの一括読み取り ＆ 一括整理")
    st.info("過去のレシート写真をまとめてアップロードすると、AIがすべて自動解析して一覧表にします。手修正後に『日付順整理＆再計算』を押すと、ODO差分や燃費を全自動で再計算できます。")

    bulk_files = st.file_uploader("大量のレシート写真をまとめて選択・アップロード", type=["jpg", "jpeg", "png"], accept_multiple_files=True, key="bulk_files")

    if bulk_files:
        if st.button("🚀 まとめ読み取りを開始する"):
            if not API_KEY:
                st.error("APIキーが設定されていません。")
            else:
                client = genai.Client(api_key=API_KEY)
                parsed_list = []
                progress_bar = st.progress(0)
                status_text = st.empty()

                for i, file in enumerate(bulk_files):
                    status_text.text(f"解析中... ({i+1}/{len(bulk_files)} 枚目): {file.name}")
                    try:
                        img = Image.open(file)
                        prompt = (
                            "このレシートから以下の項目を抽出してください。\n"
                            "1. 日付 (YYYY-MM-DD)\n"
                            "2. ガソリンスタンド名（店舗名・会社名）\n"
                            "3. 給油量 (L)\n"
                            "4. 単価 (円/L)\n"
                            "5. 支払合計金額 (円)\n"
                            "6. レシート上部や余白に手書きされている『TRIP』または『区間距離』(km)\n"
                            "7. レシート上部や余白に手書きされている『ODO』または『総走行距離』(km)\n\n"
                            "該当がない場合は None としてください。\n"
                            "出力はカンマ区切りで『2026-09-01,ENEOS 百草SS,35.0,162.0,5670,450.2,123456』のように1行で返してください。"
                        )
                        response = client.models.generate_content(
                            model='gemini-3.6-flash',
                            contents=[img, prompt]
                        )
                        res_text = response.text.strip()
                        parts = res_text.split(",")

                        p_date = parts[0].strip() if parts[0].strip() != "None" else "2026-01-01"
                        p_ss = parts[1].strip() if parts[1].strip() != "None" else ""
                        p_vol = float(parts[2].strip()) if (len(parts)>2 and parts[2].strip().replace('.','',1).isdigit()) else 0.0
                        p_price = float(parts[3].strip()) if (len(parts)>3 and parts[3].strip().replace('.','',1).isdigit()) else 0.0
                        p_amt = int(float(parts[4].strip())) if (len(parts)>4 and parts[4].strip().replace('.','',1).isdigit()) else 0
                        p_trip = float(parts[5].strip()) if (len(parts)>5 and parts[5].strip().replace('.','',1).isdigit()) else 0.0
                        p_odo = int(float(parts[6].strip())) if (len(parts)>6 and parts[6].strip().replace('.','',1).isdigit()) else 0

                        parsed_list.append({
                            "車両": car_option,
                            "日付": p_date,
                            "スタンド名": p_ss,
                            "総走行距離(ODO)": p_odo,
                            "ODO差分(km)": None,
                            "区間距離(TRIP)": p_trip,
                            "給油量(L)": p_vol,
                            "支払金額(円)": p_amt,
                            "ガソリン単価(円/L)": p_price,
                            "燃費(km/L)": 0.0,
                            "統計対象": True,
                            "備考": f"一括取込 ({file.name})"
                        })
                    except Exception as e:
                        st.warning(f"{file.name} の解析に失敗しました: {e}")

                    progress_bar.progress((i + 1) / len(bulk_files))

                status_text.text("全枚数の読み取り完了！")
                st.session_state.bulk_df = pd.DataFrame(parsed_list)

    # 一括修正・計算テーブルエリア
    if st.session_state.bulk_df is not None and not st.session_state.bulk_df.empty:
        st.markdown("---")
        st.markdown("### ✏️ 一括解析結果のプレビュー ＆ 修正")
        st.caption("読み取りミスや不足している箇所の数値を直接編集してください。編集後『🔄 日付順に並べ替えて全自動再計算』を押してください。")

        edited_bulk = st.data_editor(
            st.session_state.bulk_df,
            num_rows="dynamic",
            use_container_width=True,
            key="bulk_editor"
        )

        col_b1, col_b2 = st.columns(2)

        with col_b1:
            if st.button("🔄 日付順に並べ替えて全自動再計算", use_container_width=True):
                df_calc = edited_bulk.copy()
                df_calc["dt"] = pd.to_datetime(df_calc["日付"], errors='coerce')
                df_calc = df_calc.sort_values("dt").reset_index(drop=True)
                df_calc["日付"] = df_calc["dt"].dt.strftime("%Y-%m-%d")
                df_calc = df_calc.drop(columns=["dt"])

                for idx in range(len(df_calc)):
                    vol = df_calc.loc[idx, "給油量(L)"]
                    trip = df_calc.loc[idx, "区間距離(TRIP)"]
                    amt = df_calc.loc[idx, "支払金額(円)"]
                    u_price = df_calc.loc[idx, "ガソリン単価(円/L)"]

                    # 単価補正
                    if u_price == 0 and vol > 0 and amt > 0:
                        df_calc.loc[idx, "ガソリン単価(円/L)"] = round(amt / vol, 1)

                    # 燃費計算
                    if vol > 0 and trip > 0:
                        df_calc.loc[idx, "燃費(km/L)"] = round(trip / vol, 2)

                    # ODO差分計算
                    if idx > 0:
                        prev_odo_v = df_calc.loc[idx-1, "総走行距離(ODO)"]
                        curr_odo_v = df_calc.loc[idx, "総走行距離(ODO)"]
                        if pd.notna(curr_odo_v) and pd.notna(prev_odo_v) and curr_odo_v > prev_odo_v:
                            df_calc.loc[idx, "ODO差分(km)"] = int(curr_odo_v - prev_odo_v)

                st.session_state.bulk_df = df_calc
                st.success("日付順にソートし、単価・燃費・ODO差分を自動再計算しました！")
                st.rerun()

        with col_b2:
            if st.button("💾 この内容を確定して保存する", use_container_width=True):
                save_df = st.session_state.bulk_df[COLUMN_ORDER]
                
                if os.path.exists(DATA_FILE):
                    df_ex = pd.read_csv(DATA_FILE)
                    df_final = pd.concat([df_ex, save_df], ignore_index=True)
                else:
                    df_final = save_df
                
                df_final.to_csv(DATA_FILE, index=False, encoding="utf-8-sig")
                st.balloons()
                st.success("一括データを既存の記録に登録しました！")
                st.session_state.bulk_df = None
                st.rerun()

# ==========================================
# 5. データ分析 ＆ 月別集計 ＆ グラフ ＆ 編集機能
# ==========================================
if os.path.exists(DATA_FILE):
    try:
        df_all = pd.read_csv(DATA_FILE)
        
        df_all = df_all.dropna(how="all")
        if "車両" not in df_all.columns:
            df_all["車両"] = "アウトバックBS9"
        if "スタンド名" not in df_all.columns:
            df_all["スタンド名"] = ""
        if "備考" not in df_all.columns:
            df_all["備考"] = ""
        if "統計対象" not in df_all.columns:
            df_all["統計対象"] = True
            
        for col in COLUMN_ORDER:
            if col not in df_all.columns:
                df_all[col] = None
                
        df_all = df_all[COLUMN_ORDER]
        df_car = df_all[df_all["車両"] == car_option].copy()
        
        st.markdown("---")
        
        if not df_car.empty:
            df_car["dt"] = pd.to_datetime(df_car["日付"], errors='coerce')
            df_car = df_car.sort_values("dt").reset_index(drop=True)
            df_car["日付"] = df_car["dt"].dt.strftime("%Y-%m-%d")
            
            st.subheader(f"📅 【{car_option}】 月別・利用コスト集計")
            
            df_car["年月"] = df_car["dt"].dt.strftime("%Y-%m")
            available_months = sorted(df_car["年月"].dropna().unique(), reverse=True)
            
            if available_months:
                selected_month = st.selectbox("集計対象の月を選択", available_months, index=0)
                df_month = df_car[df_car["年月"] == selected_month]
                
                m_trip = df_month["区間距離(TRIP)"].sum()
                m_volume = df_month["給油量(L)"].sum()
                m_amount = df_month["支払金額(円)"].sum()
                m_count = len(df_month)
                
                mc1, mc2, mc3, mc4 = st.columns(4)
                mc1.metric("💴 今月のガソリン代", f"{int(m_amount):,} 円", f"給油回数: {m_count}回")
                mc2.metric("⛽ 総給油量", f"{m_volume:.2f} L")
                mc3.metric("🗺️ 総走行距離", f"{m_trip:.1f} km")
                mc4.metric("💡 月間平均単価", f"{round(m_amount/m_volume, 1) if m_volume > 0 else 0} 円/L")

            st.markdown("---")
            df_car = df_car.drop(columns=["dt", "年月"])
            
            df_stat = df_car[df_car["統計対象"] == True]
            
            st.subheader(f"📊 【{car_option}】 の燃費・単価データ分析（全期間）")
            
            valid_fe = df_stat[df_stat["燃費(km/L)"] > 0]
            valid_price = df_stat[df_stat["ガソリン単価(円/L)"] > 0]
            
            if not valid_fe.empty and not valid_price.empty:
                avg_fe = valid_fe["燃費(km/L)"].mean()
                max_fe_row = valid_fe.loc[valid_fe["燃費(km/L)"].idxmax()]
                min_fe = valid_fe["燃費(km/L)"].min()
                max_fe = valid_fe["燃費(km/L)"].max()
                
                avg_price = valid_price["ガソリン単価(円/L)"].mean()
                min_price = valid_price["ガソリン単価(円/L)"].min()
                max_price = valid_price["ガソリン単価(円/L)"].max()
                latest_fe = valid_fe["燃費(km/L)"].iloc[-1]
                
                col_m1, col_m2, col_m3, col_m4 = st.columns(4)
                col_m1.metric("🏎️ 平均燃費", f"{avg_fe:.2f} km/L")
                col_m2.metric("🏆 最高燃費", f"{max_fe:.2f} km/L", f"記録日: {max_fe_row['日付']}")
                col_m3.metric("📉 燃費の振れ幅", f"{min_fe:.1f} ～ {max_fe:.1f} km/L")
                col_m4.metric("⛽ 単価レンジ", f"{min_price:.0f} ～ {max_price:.0f} 円/L", f"平均: {avg_price:.1f}円")
                
                comment = f"**【データ分析要約】**（※除外指定されたデータを除く {len(valid_fe)}件 を分析）\n"
                best_memo_str = f"（メモ: 『{max_fe_row['備考']}』）" if pd.notna(max_fe_row.get("備考")) and str(max_fe_row.get("備考")).strip() != "" else ""
                comment += f"- **燃費傾向**: 平均燃費は **{avg_fe:.2f} km/L** です。最高記録は **{max_fe_row['日付']}** の **{max_fe:.2f} km/L** {best_memo_str} でした！\n"
                comment += f"- **単価傾向**: これまでのガソリン単価は **{min_price:.1f}円〜{max_price:.1f}円/L**（平均 {avg_price:.1f}円/L）で推移しています。\n"
                
                if len(valid_fe) >= 2:
                    prev_fe = valid_fe["燃費(km/L)"].iloc[-2]
                    diff = round(latest_fe - prev_fe, 2)
                    if diff > 0:
                        comment += f"- **直近の動き**: 前回対象データ（{prev_fe} km/L）より **+{diff} km/L 燃費が向上** しています！"
                    elif diff < 0:
                        comment += f"- **直近の動き**: 前回対象データ（{prev_fe} km/L）より **{diff} km/L** 低下しています。"
                    else:
                        comment += f"- **直近の動き**: 前回対象データと全く同じ燃費（{latest_fe} km/L）をキープしています。"
                
                st.info(comment)
            else:
                st.warning("⚠️ 統計対象となるデータがありません。「統計対象」にチェックが入っているか確認してください。")
            
            st.markdown("### 📈 推移グラフ")
            col_g1, col_g2 = st.columns(2)
            with col_g1:
                st.markdown("**⛽ ガソリン単価 (円/L)**")
                if "ガソリン単価(円/L)" in df_stat.columns and not df_stat.empty:
                    st.line_chart(df_stat, x="日付", y="ガソリン単価(円/L)", color="#FF4B4B")
            with col_g2:
                st.markdown("**🏎️ 燃費 (km/L)**")
                if "燃費(km/L)" in df_stat.columns and not df_stat.empty:
                    st.line_chart(df_stat, x="日付", y="燃費(km/L)", color="#1E88E5")
            
            st.markdown("### 📊 記録一覧 ＆ 編集")
            
            col_tb1, col_tb2 = st.columns([3, 1])
            with col_tb1:
                st.caption("💡 「統計対象」のチェックを外すと、そのデータを平均値や推移グラフから外せます。")
            with col_tb2:
                if st.button("🔄 全データを日付順に並べ直して自動再計算", use_container_width=True):
                    df_car["dt"] = pd.to_datetime(df_car["日付"], errors='coerce')
                    df_car_sorted = df_car.sort_values("dt").reset_index(drop=True)
                    df_car_sorted["日付"] = df_car_sorted["dt"].dt.strftime("%Y-%m-%d")
                    df_car_sorted = df_car_sorted.drop(columns=["dt"])
                    
                    for i in range(len(df_car_sorted)):
                        vol = df_car_sorted.loc[i, "給油量(L)"]
                        trip = df_car_sorted.loc[i, "区間距離(TRIP)"]
                        
                        if vol > 0 and trip > 0:
                            df_car_sorted.loc[i, "燃費(km/L)"] = round(trip / vol, 2)

                        if i == 0:
                            df_car_sorted.loc[i, "ODO差分(km)"] = None
                        else:
                            prev_odo_val = df_car_sorted.loc[i-1, "総走行距離(ODO)"]
                            curr_odo_val = df_car_sorted.loc[i, "総走行距離(ODO)"]
                            if pd.notna(curr_odo_val) and pd.notna(prev_odo_val) and curr_odo_val > prev_odo_val:
                                df_car_sorted.loc[i, "ODO差分(km)"] = int(curr_odo_val - prev_odo_val)
                            else:
                                df_car_sorted.loc[i, "ODO差分(km)"] = None
                    
                    df_other = df_all[df_all["車両"] != car_option]
                    df_updated = pd.concat([df_other, df_car_sorted], ignore_index=True)
                    df_updated = df_updated[COLUMN_ORDER]
                    df_updated.to_csv(DATA_FILE, index=False, encoding="utf-8-sig")
                    
                    st.success("日付順に整列し、ODO差分と燃費を全自動再計算しました！")
                    st.rerun()

            edited_df = st.data_editor(
                df_car,
                num_rows="dynamic",
                use_container_width=True,
                key=f"editor_{car_option}"
            )
            
            if st.button("✏️ 変更を保存する"):
                df_other = df_all[df_all["車両"] != car_option]
                df_updated = pd.concat([df_other, edited_df], ignore_index=True)
                df_updated = df_updated[COLUMN_ORDER]
                df_updated.to_csv(DATA_FILE, index=False, encoding="utf-8-sig")
                st.success("データを更新しました！")
                st.rerun()

        else:
            st.info(f"【{car_option}】 の記録はまだありません。給油データを記録すると分析が表示されます。")
    except Exception as e:
        st.error(f"データ表示エラー: {e}")