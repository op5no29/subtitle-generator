import streamlit as st
import os
import tempfile
import json
from pathlib import Path
import time
from dotenv import load_dotenv

# 環境変数を読み込み
load_dotenv()

# ユーザー管理システムをインポート
from user_management import (
    UserManager, initialize_user_management, login_form, signup_form,
    logout, render_admin_dashboard, render_user_dashboard
)

# st-paywall課金システムのインポート（フォールバック用）
try:
    from st_paywall import add_auth
    PAYWALL_AVAILABLE = True
except ImportError:
    PAYWALL_AVAILABLE = False

# utilsモジュールをインポート
try:
    from utils.transcription import transcribe_audio_file, transcribe_realtime, create_srt_content
    from utils.video_processing import extract_audio, burn_subtitles, get_video_info, create_srt_file
    from utils.translation import translate_text
    UTILS_AVAILABLE = True
except ImportError as e:
    st.error(f"utilsモジュールのインポートエラー: {str(e)}")
    UTILS_AVAILABLE = False

# ページ設定
st.set_page_config(
    page_title="動画・音声文字起こしアプリ",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded"
)

def check_user_access():
    """ユーザーアクセス権限チェック"""
    if not st.session_state.current_user:
        return False, "ログインが必要です"
    
    user = st.session_state.current_user
    
    # 管理者は常にアクセス可能
    if user.get("is_admin", False):
        return True, "管理者アクセス"
    
    # 有料ユーザーはアクセス可能
    if user.get("subscription_status") == "active":
        return True, "プレミアムユーザー"
    
    # 無料ユーザーは制限あり
    return False, "プレミアムプラン登録が必要です"

def log_user_usage(feature_type: str, **kwargs):
    """ユーザー使用ログ記録"""
    if st.session_state.current_user:
        user_manager = UserManager()
        user_manager.log_usage(
            st.session_state.current_user["id"],
            feature_type,
            **kwargs
        )

# カスタムCSS
st.markdown("""
<style>
    .main {
        padding: 2rem 1rem;
    }
    
    .user-info {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 1rem;
        border-radius: 10px;
        margin-bottom: 1rem;
    }
    
    .admin-badge {
        background: linear-gradient(45deg, #ff6b6b, #feca57);
        color: white;
        padding: 0.25rem 0.75rem;
        border-radius: 15px;
        font-size: 0.8rem;
        font-weight: bold;
        display: inline-block;
    }
    
    .premium-badge {
        background: linear-gradient(45deg, #ffd700, #ffed4e);
        color: #1f2937;
        padding: 0.25rem 0.75rem;
        border-radius: 15px;
        font-size: 0.8rem;
        font-weight: bold;
        display: inline-block;
    }
    
    .free-badge {
        background: linear-gradient(45deg, #95a5a6, #bdc3c7);
        color: white;
        padding: 0.25rem 0.75rem;
        border-radius: 15px;
        font-size: 0.8rem;
        font-weight: bold;
        display: inline-block;
    }
    
    .stTabs [data-baseweb="tab-list"] {
        gap: 2rem;
        background: transparent;
    }
    
    .stTabs [data-baseweb="tab"] {
        height: 3rem;
        padding: 0.5rem 1.5rem;
        background: #f0f2f6 !important;
        border-radius: 0.5rem;
        border: none;
        color: #1f2937 !important;
        font-weight: 500;
        transition: all 0.3s ease;
    }
    
    .stTabs [data-baseweb="tab"]:hover {
        background: #e6e9ef !important;
        color: #111827 !important;
    }
    
    .stTabs [aria-selected="true"] {
        background: #1f77b4 !important;
        color: white !important;
        font-weight: 600;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    .result-section {
        background: #f8f9fa !important;
        border-radius: 10px;
        padding: 1.5rem;
        margin: 1rem 0;
        border-left: 4px solid #1f77b4;
    }
    
    .access-denied {
        background: linear-gradient(135deg, #ff6b6b, #ee5a24);
        color: white;
        padding: 2rem;
        border-radius: 10px;
        text-align: center;
        margin: 2rem 0;
    }
</style>
""", unsafe_allow_html=True)

def initialize_session_state():
    """セッション状態の初期化"""
    if 'processing' not in st.session_state:
        st.session_state.processing = False
    if 'results' not in st.session_state:
        st.session_state.results = {}
    if 'recording' not in st.session_state:
        st.session_state.recording = False

def render_sidebar():
    """サイドバー表示"""
    with st.sidebar:
        st.markdown("## 🎬 メニュー")
        
        if st.session_state.current_user:
            user = st.session_state.current_user
            
            # ユーザー情報表示
            st.markdown(f"""
            <div class="user-info">
                <h3>👤 {user['name']}</h3>
                <p>📧 {user['email']}</p>
            """, unsafe_allow_html=True)
            
            # バッジ表示
            if user.get("is_admin", False):
                st.markdown('<span class="admin-badge">🔧 管理者</span>', unsafe_allow_html=True)
            elif user.get("subscription_status") == "active":
                st.markdown('<span class="premium-badge">👑 Premium</span>', unsafe_allow_html=True)
            else:
                st.markdown('<span class="free-badge">🆓 Free</span>', unsafe_allow_html=True)
            
            st.markdown("</div>", unsafe_allow_html=True)
            
            # メインアプリに戻るボタン（ダッシュボード画面時のみ表示）
            if st.session_state.get('page') != 'main':
                if st.button("🏠 メインアプリに戻る", use_container_width=True):
                    st.session_state.page = "main"
                    st.rerun()
                st.markdown("---")
            
            # メニュー
            st.markdown("### 📊 ダッシュボード")
            if st.button("📈 使用統計", use_container_width=True, key="sidebar_user_dashboard"):
                st.session_state.page = "user_dashboard"
                st.rerun()
            
            if user.get("is_admin", False):
                st.markdown("### 🔧 管理者機能")
                if st.button("👥 ユーザー管理", use_container_width=True, key="sidebar_admin_dashboard"):
                    st.session_state.page = "admin_dashboard"
                    st.rerun()
            
            st.markdown("### ⚙️ アカウント")
            if st.button("🔓 ログアウト", use_container_width=True, key="sidebar_logout"):
                logout()
        
        else:
            st.markdown("### 🔐 認証")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("📝 新規登録", use_container_width=True, key="sidebar_signup"):
                    st.session_state.auth_mode = "signup"
                    st.rerun()
            with col2:
                if st.button("🔑 ログイン", use_container_width=True, key="sidebar_login"):
                    st.session_state.auth_mode = "login"
                    st.rerun()

def display_header():
    """ヘッダー表示"""
    user_badge = ""
    if st.session_state.current_user:
        user = st.session_state.current_user
        if user.get("is_admin", False):
            user_badge = '<span class="admin-badge">🔧 Admin</span>'
        elif user.get("subscription_status") == "active":
            user_badge = '<span class="premium-badge">👑 Premium</span>'
        else:
            user_badge = '<span class="free-badge">🆓 Free</span>'
    
    st.markdown(f"""
    <div style="text-align: center; padding: 1rem 0 2rem 0;">
        <h1 style="color: #1f77b4; margin-bottom: 0.5rem;">🎬 動画・音声文字起こしアプリ {user_badge}</h1>
        <p style="color: #666; font-size: 1.1rem;">プロフェッショナル向け文字起こし・字幕生成ツール</p>
    </div>
    """, unsafe_allow_html=True)

def render_access_denied():
    """アクセス拒否画面"""
    st.markdown("""
    <div class="access-denied">
        <h2>🔒 プレミアム機能</h2>
        <p>この機能をご利用いただくには、プレミアムプラン（月額500円）への登録が必要です。</p>
        <br>
        <h3>プレミアムプランの特典：</h3>
        <ul style="text-align: left; display: inline-block;">
            <li>✅ 無制限の動画・音声文字起こし</li>
            <li>✅ リアルタイム録音機能</li>
            <li>✅ 多言語翻訳機能</li>
            <li>✅ 字幕動画生成</li>
            <li>✅ 優先サポート</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        # 現在のページに基づいてユニークなキーを生成
        current_tab = st.session_state.get('current_tab', 'unknown')
        button_key = f"premium_signup_{current_tab}_{hash(str(time.time()))}"
        
        if st.button("💳 プレミアムプランに登録", type="primary", use_container_width=True, key=button_key):
            # TODO: 実際のStripe決済リンクに移動
            stripe_link = st.secrets.get("stripe_link_test", "")
            if stripe_link and stripe_link != "disabled":
                st.markdown(f'<meta http-equiv="refresh" content="0; url={stripe_link}">', unsafe_allow_html=True)
                st.success("Stripe決済ページに移動中...")
            else:
                st.info("💡 Stripe Payment Link設定後に決済機能が有効になります")
                with st.expander("管理者向け：手動でプレミアム化"):
                    if st.session_state.current_user.get("is_admin", False):
                        # 管理者向け手動プレミアム化
                        if st.button("🔓 このアカウントをプレミアム化", key=f"manual_premium_{button_key}"):
                            try:
                                import sqlite3
                                conn = sqlite3.connect('users.db')
                                cursor = conn.cursor()
                                cursor.execute(
                                    "UPDATE users SET subscription_status = 'active' WHERE id = ?",
                                    (st.session_state.current_user["id"],)
                                )
                                conn.commit()
                                conn.close()
                                
                                # セッション状態更新
                                st.session_state.current_user["subscription_status"] = "active"
                                st.success("プレミアムアカウントに変更しました！")
                                st.rerun()
                            except Exception as e:
                                st.error(f"エラー: {str(e)}")
                    else:
                        st.info("管理者権限が必要です")

def video_subtitle_tab():
    """動画字幕生成タブ"""
    st.session_state.current_tab = "video"  # タブ識別用
    
    st.markdown("### 📹 動画字幕生成")
    st.markdown("動画ファイルをアップロードして、自動で字幕を生成し、動画に焼き込みます。")
    
    # アクセス権限チェック
    has_access, message = check_user_access()
    if not has_access:
        render_access_denied()
        return
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        uploaded_file = st.file_uploader(
            "動画ファイルを選択してください",
            type=['mp4', 'avi', 'mov', 'mkv'],
            help="対応形式: MP4, AVI, MOV, MKV"
        )
        
        if uploaded_file:
            file_size = len(uploaded_file.read()) / (1024 * 1024)
            uploaded_file.seek(0)
            
            st.info(f"📁 ファイル名: {uploaded_file.name}")
            st.info(f"📊 ファイルサイズ: {file_size:.1f} MB")
            
            st.markdown("#### ⚙️ 字幕設定")
            col_font, col_pos, col_color = st.columns(3)
            
            with col_font:
                font_size = st.selectbox("フォントサイズ", [16, 20, 24, 28, 32], index=2)
            with col_pos:
                position = st.selectbox("字幕位置", ["下部", "中央", "上部"], index=0)
            with col_color:
                text_color = st.selectbox("文字色", ["白", "黄", "青", "緑"], index=0)
            
            translate_option = st.selectbox(
                "翻訳オプション",
                ["翻訳なし", "日本語→英語", "英語→日本語", "日本語→中国語", "日本語→韓国語"]
            )
    
    with col2:
        if st.button("🚀 字幕生成開始", type="primary", disabled=st.session_state.processing):
            if uploaded_file and UTILS_AVAILABLE:
                start_time = time.time()
                process_video_subtitle(uploaded_file, font_size, position, text_color, translate_option)
                processing_time = time.time() - start_time
                
                # 使用ログ記録
                log_user_usage(
                    "video",
                    file_name=uploaded_file.name,
                    file_size_mb=file_size,
                    processing_time_seconds=processing_time,
                    translation_used=translate_option != "翻訳なし"
                )
            elif not uploaded_file:
                st.error("動画ファイルを選択してください。")
            else:
                st.error("utilsモジュールが利用できません。")
    
    if 'video_result' in st.session_state.results:
        display_video_results()

def audio_transcription_tab():
    """音声文字起こしタブ"""
    st.session_state.current_tab = "audio"  # タブ識別用
    
    st.markdown("### 🎵 音声・動画文字起こし")
    st.markdown("音声ファイルや動画ファイルをテキストに変換します。")
    
    # アクセス権限チェック
    has_access, message = check_user_access()
    if not has_access:
        render_access_denied()
        return
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        uploaded_file = st.file_uploader(
            "音声・動画ファイルを選択してください",
            type=['mp3', 'wav', 'm4a', 'aac', 'flac', 'mp4', 'avi', 'mov', 'mkv'],
            help="対応形式: MP3, WAV, M4A, AAC, FLAC, MP4, AVI, MOV, MKV"
        )
        
        if uploaded_file:
            file_size = len(uploaded_file.read()) / (1024 * 1024)
            uploaded_file.seek(0)
            
            st.info(f"📁 ファイル名: {uploaded_file.name}")
            st.info(f"📊 ファイルサイズ: {file_size:.1f} MB")
            
            st.markdown("#### ⚙️ 出力設定")
            col_format, col_timestamp = st.columns(2)
            
            with col_format:
                output_format = st.selectbox("出力形式", ["プレーンテキスト", "タイムスタンプ付き", "JSON形式"])
            with col_timestamp:
                include_timestamps = st.checkbox("タイムスタンプを含める", value=True)
            
            translate_option = st.selectbox(
                "翻訳オプション",
                ["翻訳なし", "日本語→英語", "英語→日本語", "日本語→中国語", "日本語→韓国語"],
                key="audio_translate"
            )
    
    with col2:
        if st.button("🚀 文字起こし開始", type="primary", disabled=st.session_state.processing):
            if uploaded_file and UTILS_AVAILABLE:
                start_time = time.time()
                process_audio_transcription(uploaded_file, output_format, include_timestamps, translate_option)
                processing_time = time.time() - start_time
                
                # 使用ログ記録
                log_user_usage(
                    "audio",
                    file_name=uploaded_file.name,
                    file_size_mb=file_size,
                    processing_time_seconds=processing_time,
                    translation_used=translate_option != "翻訳なし"
                )
            elif not uploaded_file:
                st.error("音声・動画ファイルを選択してください。")
            else:
                st.error("utilsモジュールが利用できません。")
    
    if 'audio_result' in st.session_state.results:
        display_audio_results()

def realtime_recording_tab():
    """リアルタイム録音タブ"""
    st.session_state.current_tab = "realtime"  # タブ識別用
    
    st.markdown("### 🎤 リアルタイム録音・文字起こし")
    st.markdown("マイクから音声を録音して、リアルタイムで文字起こしを行います。")
    
    # アクセス権限チェック
    has_access, message = check_user_access()
    if not has_access:
        render_access_denied()
        return
    
    # HTTPS環境チェック（Streamlit Community Cloud対応）
    try:
        # Streamlit Community Cloudの場合
        host = str(st.context.headers.get("Host", ""))
        referer = str(st.context.headers.get("Referer", ""))
        origin = str(st.context.headers.get("Origin", ""))
        
        is_streamlit_cloud = ".streamlit.app" in host or ".streamlitapp.com" in host
        is_https = (
            st.context.headers.get("X-Forwarded-Proto") == "https" or
            "https://" in referer or
            "https://" in origin or
            is_streamlit_cloud
        )
        is_localhost = "localhost" in host or "127.0.0.1" in host
        
        # デバッグ情報（開発時のみ表示）
        if st.secrets.get("testing_mode", False):
            with st.expander("🔍 デバッグ情報"):
                st.write(f"Host: {host}")
                st.write(f"HTTPS判定: {is_https}")
                st.write(f"Streamlit Cloud: {is_streamlit_cloud}")
                st.write(f"Localhost: {is_localhost}")
        
    except Exception as e:
        # フォールバック：環境判定エラー時はHTTPS想定
        is_https = True
        is_localhost = False
        st.info(f"環境判定エラー（HTTPS想定で継続）: {str(e)}")
    
    if not is_https and not is_localhost:
        st.warning("🔒 **マイク機能にはHTTPS環境が必要です**")
        st.info("Streamlit Community Cloudにデプロイするか、ローカルでは以下を試してください：")
        st.code("streamlit run app.py --server.enableCORS=false --server.enableXsrfProtection=false")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("#### ⚙️ 録音設定")
        col_quality, col_lang = st.columns(2)
        
        with col_quality:
            audio_quality = st.selectbox("音質", ["標準 (16kHz)", "高品質 (44.1kHz)"], index=0)
        with col_lang:
            source_language = st.selectbox("音声言語", ["日本語", "英語", "中国語", "韓国語"], index=0)
        
        translate_option = st.selectbox(
            "翻訳オプション",
            ["翻訳なし", "日本語→英語", "英語→日本語", "日本語→中国語", "日本語→韓国語"],
            key="realtime_translate"
        )
    
    with col2:
        st.markdown("#### 🎙️ 録音制御")
        
        try:
            from streamlit_mic_recorder import mic_recorder
            
            # マイク機能を常に表示（環境判定に関係なく）
            st.info("🎤 マイクアクセス許可が必要です")
            
            audio_data = mic_recorder(
                start_prompt="🔴 録音開始",
                stop_prompt="⏹️ 録音停止",
                just_once=True,
                use_container_width=True,
                key='realtime_recorder'
            )
            
            if audio_data:
                st.success("録音完了！文字起こしを実行中...")
                start_time = time.time()
                process_realtime_audio(audio_data, source_language, translate_option)
                processing_time = time.time() - start_time
                
                # 使用ログ記録
                log_user_usage(
                    "realtime",
                    processing_time_seconds=processing_time,
                    translation_used=translate_option != "翻訳なし"
                )
                
        except ImportError:
            st.warning("⚠️ マイク録音機能をインストール中...")
            if st.button("📦 streamlit-mic-recorderをインストール"):
                st.code("pip install streamlit-mic-recorder")
                st.info("インストール後、アプリを再起動してください")
            
            # フォールバック：ファイルアップロード録音
            st.markdown("#### 📁 代替案：音声ファイルアップロード")
            uploaded_audio = st.file_uploader(
                "録音済み音声ファイルをアップロード",
                type=['wav', 'mp3', 'm4a'],
                help="マイク録音の代わりに音声ファイルをアップロードできます"
            )
            
            if uploaded_audio and UTILS_AVAILABLE:
                st.success("ファイルアップロード完了！文字起こしを実行中...")
                with tempfile.NamedTemporaryFile(delete=False, suffix=Path(uploaded_audio.name).suffix) as tmp_file:
                    tmp_file.write(uploaded_audio.read())
                    audio_path = tmp_file.name
                
                try:
                    start_time = time.time()
                    transcription_result = transcribe_audio_file(audio_path)
                    
                    if translate_option != "翻訳なし":
                        translated_text = translate_text(transcription_result['text'], translate_option)
                        transcription_result['translated'] = translated_text
                    
                    processing_time = time.time() - start_time
                    
                    st.session_state.results['realtime_result'] = {
                        'status': 'completed',
                        'transcription': transcription_result,
                        'source_language': source_language,
                        'translate_option': translate_option,
                        'timestamp': time.time(),
                        'audio_duration': 0
                    }
                    
                    # 使用ログ記録
                    log_user_usage(
                        "realtime",
                        file_name=uploaded_audio.name,
                        processing_time_seconds=processing_time,
                        translation_used=translate_option != "翻訳なし"
                    )
                    
                    os.unlink(audio_path)
                    st.success("音声ファイル文字起こしが完了しました！")
                    
                except Exception as e:
                    st.error(f"音声ファイル処理エラー: {str(e)}")
                    if os.path.exists(audio_path):
                        os.unlink(audio_path)
    
    if 'realtime_result' in st.session_state.results:
        display_realtime_results()

# 既存の処理関数（簡略版 - 元のapp.pyから移植）
def process_video_subtitle(uploaded_file, font_size, position, text_color, translate_option):
    """動画字幕生成処理"""
    st.session_state.processing = True
    
    try:
        with st.spinner('動画を処理中...'):
            with tempfile.NamedTemporaryFile(delete=False, suffix=Path(uploaded_file.name).suffix) as tmp_file:
                tmp_file.write(uploaded_file.read())
                video_path = tmp_file.name
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            status_text.text("🎵 音声を抽出中...")
            progress_bar.progress(20)
            audio_path = extract_audio(video_path)
            
            status_text.text("📝 音声を文字起こし中...")
            progress_bar.progress(50)
            transcription_result = transcribe_audio_file(audio_path)
            
            srt_content_to_use = transcription_result
            
            if translate_option != "翻訳なし":
                status_text.text("🌐 テキストを翻訳中...")
                progress_bar.progress(70)
                translated_text = translate_text(transcription_result['text'], translate_option)
                transcription_result['translated'] = translated_text
                
                if 'segments' in transcription_result and transcription_result['segments']:
                    from utils.translation import translate_segments
                    translated_segments = translate_segments(transcription_result['segments'], translate_option)
                    srt_content_to_use = {
                        'text': translated_text,
                        'segments': translated_segments,
                        'language': transcription_result.get('language', 'ja'),
                        'original_text': transcription_result['text'],
                        'translation_option': translate_option
                    }
            
            status_text.text("📄 字幕ファイルを生成中...")
            progress_bar.progress(80)
            srt_path = create_srt_file(srt_content_to_use)
            
            status_text.text("🎬 動画に字幕を焼き込み中...")
            progress_bar.progress(90)
            
            position_mapping = {"下部": "bottom", "中央": "center", "上部": "top"}
            color_mapping = {"白": "white", "黄": "yellow", "青": "blue", "緑": "green"}
            
            output_video_path = burn_subtitles(
                video_path,
                srt_path,
                font_size,
                position_mapping[position],
                color_mapping[text_color]
            )
            
            progress_bar.progress(100)
            status_text.text("✅ 処理完了!")
            
            st.session_state.results['video_result'] = {
                'transcription': transcription_result,
                'srt_path': srt_path,
                'video_path': output_video_path,
                'original_filename': uploaded_file.name,
                'translation_used': translate_option != "翻訳なし",
                'srt_content_used': srt_content_to_use
            }
            
            os.unlink(video_path)
            os.unlink(audio_path)
            
            success_msg = "動画字幕生成が完了しました！"
            if translate_option != "翻訳なし":
                success_msg += f" （{translate_option}で翻訳済み）"
            st.success(success_msg)
            
    except Exception as e:
        st.error(f"エラーが発生しました: {str(e)}")
    finally:
        st.session_state.processing = False

def process_audio_transcription(uploaded_file, output_format, include_timestamps, translate_option):
    """音声文字起こし処理"""
    st.session_state.processing = True
    
    try:
        with st.spinner('音声を処理中...'):
            with tempfile.NamedTemporaryFile(delete=False, suffix=Path(uploaded_file.name).suffix) as tmp_file:
                tmp_file.write(uploaded_file.read())
                audio_path = tmp_file.name
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            if Path(uploaded_file.name).suffix.lower() in ['.mp4', '.avi', '.mov', '.mkv']:
                status_text.text("🎵 音声を抽出中...")
                progress_bar.progress(25)
                audio_path = extract_audio(audio_path)
            
            status_text.text("📝 音声を文字起こし中...")
            progress_bar.progress(60)
            transcription_result = transcribe_audio_file(audio_path)
            
            if translate_option != "翻訳なし":
                status_text.text("🌐 テキストを翻訳中...")
                progress_bar.progress(80)
                translated_text = translate_text(transcription_result['text'], translate_option)
                transcription_result['translated'] = translated_text
            
            progress_bar.progress(100)
            status_text.text("✅ 処理完了!")
            
            st.session_state.results['audio_result'] = {
                'transcription': transcription_result,
                'output_format': output_format,
                'include_timestamps': include_timestamps,
                'original_filename': uploaded_file.name
            }
            
            os.unlink(audio_path)
            st.success("音声文字起こしが完了しました！")
            
    except Exception as e:
        st.error(f"エラーが発生しました: {str(e)}")
    finally:
        st.session_state.processing = False

def process_realtime_audio(audio_data, source_language, translate_option):
    """実際のマイク録音データを処理"""
    try:
        with st.spinner('音声を文字起こし中...'):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
                tmp_file.write(audio_data['bytes'])
                audio_path = tmp_file.name
            
            transcription_result = transcribe_audio_file(audio_path)
            
            if translate_option != "翻訳なし":
                translated_text = translate_text(transcription_result['text'], translate_option)
                transcription_result['translated'] = translated_text
            
            st.session_state.results['realtime_result'] = {
                'status': 'completed',
                'transcription': transcription_result,
                'audio_duration': len(audio_data['bytes']) / (audio_data['sample_rate'] * audio_data['sample_width']),
                'source_language': source_language,
                'translate_option': translate_option,
                'timestamp': time.time()
            }
            
            os.unlink(audio_path)
            st.success("リアルタイム録音の文字起こしが完了しました！")
            
    except Exception as e:
        st.error(f"録音処理エラー: {str(e)}")

# 結果表示関数（簡略版）
def display_video_results():
    """動画結果表示"""
    result = st.session_state.results['video_result']
    
    st.markdown('<div class="result-section">', unsafe_allow_html=True)
    st.markdown("### 📹 動画字幕生成結果")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("#### 📝 文字起こし結果")
        st.text_area("テキスト", result['transcription']['text'], height=200, key="video_transcript")
        
        if 'translated' in result['transcription']:
            st.markdown("#### 🌐 翻訳結果")
            st.text_area("翻訳テキスト", result['transcription']['translated'], height=100, key="video_translated")
    
    with col2:
        st.markdown("#### 💾 ダウンロード")
        
        if os.path.exists(result['srt_path']):
            with open(result['srt_path'], 'rb') as file:
                st.download_button(
                    "📄 字幕ファイル (.srt)",
                    file.read(),
                    file_name=f"{Path(result['original_filename']).stem}.srt",
                    mime="text/plain"
                )
        
        if os.path.exists(result['video_path']):
            with open(result['video_path'], 'rb') as file:
                st.download_button(
                    "🎬 字幕付き動画",
                    file.read(),
                    file_name=f"{Path(result['original_filename']).stem}_subtitled.mp4",
                    mime="video/mp4"
                )
        
        st.download_button(
            "📝 テキストファイル",
            result['transcription']['text'],
            file_name=f"{Path(result['original_filename']).stem}_transcript.txt",
            mime="text/plain"
        )
    
    st.markdown('</div>', unsafe_allow_html=True)

def display_audio_results():
    """音声結果表示"""
    result = st.session_state.results['audio_result']
    
    st.markdown('<div class="result-section">', unsafe_allow_html=True)
    st.markdown("### 🎵 音声文字起こし結果")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("#### 📝 文字起こし結果")
        st.text_area("テキスト", result['transcription']['text'], height=300, key="audio_transcript")
        
        if 'translated' in result['transcription']:
            st.markdown("#### 🌐 翻訳結果")
            st.text_area("翻訳テキスト", result['transcription']['translated'], height=150, key="audio_translated")
    
    with col2:
        st.markdown("#### 💾 ダウンロード")
        
        st.download_button(
            "📝 テキストファイル (.txt)",
            result['transcription']['text'],
            file_name=f"{Path(result['original_filename']).stem}_transcript.txt",
            mime="text/plain"
        )
        
        json_data = json.dumps(result['transcription'], ensure_ascii=False, indent=2)
        st.download_button(
            "📊 JSON形式 (.json)",
            json_data,
            file_name=f"{Path(result['original_filename']).stem}_transcript.json",
            mime="application/json"
        )
    
    st.markdown('</div>', unsafe_allow_html=True)

def display_realtime_results():
    """リアルタイム結果表示"""
    result = st.session_state.results['realtime_result']
    
    st.markdown('<div class="result-section">', unsafe_allow_html=True)
    st.markdown("### 🎤 リアルタイム録音結果")
    
    if result['status'] == 'completed' and 'transcription' in result:
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.markdown("#### 📝 文字起こし結果")
            transcription_text = result['transcription'].get('text', '')
            st.text_area("テキスト", transcription_text, height=200, key="realtime_transcript")
            
            if 'translated' in result['transcription']:
                st.markdown("#### 🌐 翻訳結果")
                translated_text = result['transcription']['translated']
                st.text_area("翻訳テキスト", translated_text, height=100, key="realtime_translated")
        
        with col2:
            st.markdown("#### ℹ️ 録音情報")
            
            duration = result.get('audio_duration', 0)
            if duration:
                st.metric("録音時間", f"{duration:.1f}秒")
            
            if 'source_language' in result:
                st.info(f"言語: {result['source_language']}")
            if 'translate_option' in result:
                st.info(f"翻訳: {result['translate_option']}")
            
            st.markdown("#### 💾 ダウンロード")
            if transcription_text:
                timestamp_str = int(result.get('timestamp', time.time()))
                st.download_button(
                    "📝 テキストファイル",
                    transcription_text,
                    file_name=f"realtime_transcript_{timestamp_str}.txt",
                    mime="text/plain"
                )
    
    st.markdown('</div>', unsafe_allow_html=True)

def main():
    """メイン関数"""
    # ユーザー管理システム初期化
    initialize_user_management()
    initialize_session_state()
    
    # ページ状態管理
    if 'page' not in st.session_state:
        st.session_state.page = "main"
    if 'auth_mode' not in st.session_state:
        st.session_state.auth_mode = None
    
    # サイドバー表示
    render_sidebar()
    
    # メインコンテンツ
    if not st.session_state.current_user:
        # 未ログイン状態
        display_header()
        
        if st.session_state.auth_mode == "login":
            login_form()
        elif st.session_state.auth_mode == "signup":
            signup_form()
        else:
            # ランディングページ
            st.markdown("""
            ## 🎬 動画・音声文字起こしアプリへようこそ
            
            プロフェッショナル向けの高精度文字起こし・翻訳・字幕生成ツールです。
            
            ### ✨ 主な機能
            
            - **📹 動画字幕生成**: 動画ファイルから自動で字幕を生成し、動画に焼き込み
            - **🎵 音声文字起こし**: 高精度でリアルタイム音声認識
            - **🌐 多言語翻訳**: 日本語↔英語、日本語→中国語・韓国語
            - **🎤 リアルタイム録音**: マイクからの直接録音・文字起こし
            
            ### 💰 料金プラン
            
            **プレミアムプラン**: 月額500円
            - ✅ 全機能無制限利用
            - ✅ 優先サポート
            - ✅ 高品質処理
            
            **友人特別価格**: 5名様限定でご提供中！
            
            ---
            
            まずは左サイドバーから **新規登録** または **ログイン** してください。
            """)
    
    else:
        # ログイン済み状態
        if st.session_state.page == "admin_dashboard":
            render_admin_dashboard()
        elif st.session_state.page == "user_dashboard":
            render_user_dashboard(st.session_state.current_user)
        else:
            # メインアプリ
            display_header()
            
            if not UTILS_AVAILABLE:
                st.error("⚠️ utilsモジュールが利用できません。アプリの機能が制限されます。")
                return
            
            # メインタブ
            tab1, tab2, tab3 = st.tabs(["📹 動画字幕生成", "🎵 音声文字起こし", "🎤 リアルタイム録音"])
            
            with tab1:
                video_subtitle_tab()
            
            with tab2:
                audio_transcription_tab()
            
            with tab3:
                realtime_recording_tab()
    
    # フッター
    st.markdown("---")
    st.markdown("""
    <div style="text-align: center; color: #666; padding: 1rem 0;">
        <p>🎬 動画・音声文字起こしアプリ - プロフェッショナル版</p>
        <p><small>OpenAI Whisper API & Anthropic Claude API 搭載</small></p>
        <p><small>島田紫音 - 友人限定サービス</small></p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
