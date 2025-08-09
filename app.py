import streamlit as st
import os
import tempfile
import json
from pathlib import Path
import time
from dotenv import load_dotenv

# 環境変数を読み込み
load_dotenv()

# st-paywall課金システムのインポート
try:
    from st_paywall import add_auth
    PAYWALL_AVAILABLE = True
except ImportError:
    PAYWALL_AVAILABLE = False
    st.warning("st-paywall未インストール: 認証機能は無効です（開発モード）")

# utilsモジュールをインポート
try:
    from utils.transcription import transcribe_audio_file, transcribe_realtime, create_srt_content
    from utils.video_processing import extract_audio, burn_subtitles, get_video_info, create_srt_file
    from utils.translation import translate_text
except ImportError as e:
    st.error(f"utilsモジュールのインポートエラー: {str(e)}")
    st.stop()

# ページ設定
st.set_page_config(
    page_title="動画・音声文字起こしアプリ",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="collapsed"
)

def initialize_paywall():
    """st-paywall課金システムを初期化"""
    if not PAYWALL_AVAILABLE:
        st.warning("⚠️ 課金システム未設定 - 開発モードで動作中")
        return
    
    try:
        # st-paywall 1.0.2の正しいAPI使用
        # secrets.tomlから設定を自動読み込み
        add_auth(
            required=False,  # 開発中はFalseに設定
            show_redirect_button=True,
            subscription_button_text="🔐 プレミアム機能を利用（月額500円）",
            button_color="#1f77b4",
            use_sidebar=True
        )
        
        # 認証成功後のメッセージ
        if st.session_state.get("user_subscribed", False):
            user_email = st.session_state.get("email", "ユーザー")
            st.success(f"✅ ようこそ、{user_email}さん！プレミアム機能をお楽しみください。")
        
    except Exception as e:
        st.warning(f"認証システムエラー（開発中は無視）: {str(e)}")

def check_paywall_config():
    """課金システムの設定確認（開発用）"""
    try:
        if not PAYWALL_AVAILABLE:
            return True  # 開発モードでは常にTrue
            
        # secrets.tomlの基本設定をチェック
        config_ok = True
        
        if "payment_provider" not in st.secrets:
            st.info("💡 payment_provider が未設定です")
            config_ok = False
            
        if "testing_mode" not in st.secrets:
            st.info("💡 testing_mode が未設定です")
            config_ok = False
        
        return config_ok
        
    except Exception as e:
        st.warning(f"設定確認エラー: {str(e)}")
        return True  # エラー時も継続

# カスタムCSS
st.markdown("""
<style>
    .main {
        padding: 2rem 1rem;
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
    
    .premium-badge {
        background: linear-gradient(45deg, #ffd700, #ffed4e);
        color: #1f2937;
        padding: 0.25rem 0.75rem;
        border-radius: 15px;
        font-size: 0.8rem;
        font-weight: bold;
        display: inline-block;
        margin-left: 0.5rem;
    }
    
    .result-section {
        background: #f8f9fa !important;
        border-radius: 10px;
        padding: 1.5rem;
        margin: 1rem 0;
        border-left: 4px solid #1f77b4;
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

def display_header():
    """ヘッダー表示"""
    premium_badge = ""
    if st.session_state.get("user_subscribed", False):
        premium_badge = '<span class="premium-badge">👑 Premium</span>'
    
    st.markdown(f"""
    <div style="text-align: center; padding: 1rem 0 2rem 0;">
        <h1 style="color: #1f77b4; margin-bottom: 0.5rem;">🎬 動画・音声文字起こしアプリ {premium_badge}</h1>
        <p style="color: #666; font-size: 1.1rem;">プロフェッショナル向け文字起こし・字幕生成ツール</p>
    </div>
    """, unsafe_allow_html=True)

def video_subtitle_tab():
    """動画字幕生成タブ"""
    st.markdown("### 📹 動画字幕生成")
    st.markdown("動画ファイルをアップロードして、自動で字幕を生成し、動画に焼き込みます。")
    
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
            if uploaded_file:
                process_video_subtitle(uploaded_file, font_size, position, text_color, translate_option)
            else:
                st.error("動画ファイルを選択してください。")
    
    if 'video_result' in st.session_state.results:
        display_video_results()

def audio_transcription_tab():
    """音声文字起こしタブ"""
    st.markdown("### 🎵 音声・動画文字起こし")
    st.markdown("音声ファイルや動画ファイルをテキストに変換します。")
    
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
            if uploaded_file:
                process_audio_transcription(uploaded_file, output_format, include_timestamps, translate_option)
            else:
                st.error("音声・動画ファイルを選択してください。")
    
    if 'audio_result' in st.session_state.results:
        display_audio_results()

def realtime_recording_tab():
    """リアルタイム録音タブ"""
    st.markdown("### 🎤 リアルタイム録音・文字起こし")
    st.markdown("マイクから音声を録音して、リアルタイムで文字起こしを行います。")
    
    # HTTPS環境チェック
    is_https = st.context.headers.get("X-Forwarded-Proto") == "https"
    is_localhost = "localhost" in str(st.context.headers.get("Host", ""))
    
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
            
            # セキュア環境またはローカル環境でのみマイク機能を表示
            if is_https or is_localhost:
                audio_data = mic_recorder(
                    start_prompt="🔴 録音開始",
                    stop_prompt="⏹️ 録音停止",
                    just_once=True,
                    use_container_width=True,
                    key='realtime_recorder'
                )
                
                if audio_data:
                    st.success("録音完了！文字起こしを実行中...")
                    process_realtime_audio(audio_data, source_language, translate_option)
            else:
                st.error("🔒 マイク機能はHTTPS環境でのみ利用可能です")
                
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
            
            if uploaded_audio:
                st.success("ファイルアップロード完了！文字起こしを実行中...")
                # ファイルを一時的に保存して処理
                with tempfile.NamedTemporaryFile(delete=False, suffix=Path(uploaded_audio.name).suffix) as tmp_file:
                    tmp_file.write(uploaded_audio.read())
                    audio_path = tmp_file.name
                
                try:
                    transcription_result = transcribe_audio_file(audio_path)
                    
                    if translate_option != "翻訳なし":
                        translated_text = translate_text(transcription_result['text'], translate_option)
                        transcription_result['translated'] = translated_text
                    
                    st.session_state.results['realtime_result'] = {
                        'status': 'completed',
                        'transcription': transcription_result,
                        'source_language': source_language,
                        'translate_option': translate_option,
                        'timestamp': time.time(),
                        'audio_duration': 0  # ファイルから取得困難なのでダミー
                    }
                    
                    os.unlink(audio_path)
                    st.success("音声ファイル文字起こしが完了しました！")
                    
                except Exception as e:
                    st.error(f"音声ファイル処理エラー: {str(e)}")
                    if os.path.exists(audio_path):
                        os.unlink(audio_path)
    
    if 'realtime_result' in st.session_state.results:
        display_realtime_results()

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

def start_recording_fallback(audio_quality, source_language, translate_option):
    """フォールバック録音開始（模擬）"""
    st.session_state.recording = True
    st.session_state.results['realtime_result'] = {
        'status': 'recording',
        'audio_quality': audio_quality,
        'source_language': source_language,
        'translate_option': translate_option,
        'start_time': time.time()
    }
    st.rerun()

def stop_recording_fallback():
    """フォールバック録音停止（模擬）"""
    st.session_state.recording = False
    
    if 'realtime_result' in st.session_state.results:
        result = st.session_state.results['realtime_result']
        duration = time.time() - result['start_time']
        
        sample_text = f"模擬録音のテストです。録音時間は約{duration:.1f}秒でした。実際の録音機能を使用するには 'pip install streamlit-mic-recorder' を実行してください。"
        
        st.session_state.results['realtime_result'].update({
            'status': 'completed',
            'transcription': {
                'text': sample_text,
                'segments': [{'start': 0.0, 'end': duration, 'text': sample_text}],
                'language': 'ja'
            },
            'end_time': time.time(),
            'audio_duration': duration
        })
        
        st.info("模擬録音完了！実際のマイク録音機能を使用するには追加コンポーネントが必要です。")

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
    
    if result['status'] == 'recording':
        st.markdown('<p style="color: orange;">🔴 録音中...</p>', unsafe_allow_html=True)
        
        if 'start_time' in result:
            elapsed_time = time.time() - result['start_time']
            st.metric("録音時間", f"{elapsed_time:.1f}秒")
    
    elif result['status'] == 'completed' and 'transcription' in result:
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
    # 設定チェック
    check_paywall_config()
    
    # 認証・課金チェック（開発モードでは緩い制限）
    initialize_paywall()
    
    # メイン処理
    initialize_session_state()
    display_header()
    
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
        <p><small>月額500円でプレミアム機能をご利用いただきありがとうございます</small></p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
