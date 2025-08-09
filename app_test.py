import streamlit as st
import os
import tempfile
import json
from pathlib import Path
import time
from dotenv import load_dotenv

# 環境変数を読み込み
load_dotenv()

# 一時的に認証システムを無効化（テスト用）
PAYWALL_AVAILABLE = False

# utilsモジュールをインポート
from utils.transcription import transcribe_audio_file, transcribe_realtime, create_srt_content
from utils.video_processing import extract_audio, burn_subtitles, get_video_info, create_srt_file
from utils.translation import translate_text

# ページ設定
st.set_page_config(
    page_title="動画・音声文字起こしアプリ",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="collapsed"
)

def initialize_paywall():
    """認証システム無効化中（テスト用）"""
    st.info("🚧 **開発モード**: 認証システムは一時的に無効化されています。基本機能をテストできます。")
    # 認証をスキップ

# カスタムCSS（元のまま）
st.markdown("""
<style>
    .main {
        padding: 2rem 1rem;
    }
    
    /* タブのスタイル修正 */
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
    
    .stTabs [data-baseweb="tab"] span {
        color: inherit !important;
    }
    
    /* セレクトボックスの設定 */
    .stSelectbox > div > div {
        background-color: white !important;
        border: 1px solid #d1d5db !important;
        border-radius: 6px;
        min-height: 40px !important;
    }
    
    .stSelectbox label {
        color: #374151 !important;
        font-weight: 500;
        margin-bottom: 0.5rem;
        display: block !important;
    }
    
    /* ボタンのスタイル */
    .stButton > button {
        background: linear-gradient(45deg, #1f77b4, #4a90e2) !important;
        color: white !important;
        border: none !important;
        border-radius: 8px;
        padding: 0.5rem 1rem;
        font-weight: 600;
        transition: all 0.3s ease;
    }
    
    .stButton > button:hover {
        background: linear-gradient(45deg, #1565c0, #3d82d3) !important;
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.2);
    }
    
    /* ファイルアップローダー */
    .stFileUploader > div {
        border: 2px dashed #1f77b4 !important;
        border-radius: 10px;
        padding: 2rem;
        background: #f8f9fa !important;
        transition: all 0.3s ease;
    }
    
    .stFileUploader > div:hover {
        border-color: #4a90e2 !important;
        background: #e3f2fd !important;
    }
    
    /* テスト版バッジ */
    .test-badge {
        background: linear-gradient(45deg, #ff6b35, #ff8a00);
        color: white;
        padding: 0.25rem 0.75rem;
        border-radius: 15px;
        font-size: 0.8rem;
        font-weight: bold;
        display: inline-block;
        margin-left: 0.5rem;
    }
    
    /* 情報表示エリア */
    .result-section {
        background: #f8f9fa !important;
        border-radius: 10px;
        padding: 1.5rem;
        margin: 1rem 0;
        border-left: 4px solid #1f77b4;
        color: #1f2937 !important;
    }
    
    /* ステータスメッセージ */
    .status-success {
        color: #059669 !important;
        font-weight: bold;
    }
    
    .status-error {
        color: #dc2626 !important;
        font-weight: bold;
    }
    
    .status-processing {
        color: #d97706 !important;
        font-weight: bold;
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
    test_badge = '<span class="test-badge">🧪 Test Mode</span>'
    
    st.markdown(f"""
    <div style="text-align: center; padding: 1rem 0 2rem 0;">
        <h1 style="color: #1f77b4; margin-bottom: 0.5rem;">🎬 動画・音声文字起こしアプリ {test_badge}</h1>
        <p style="color: #666; font-size: 1.1rem;">プロフェッショナル向け文字起こし・字幕生成ツール</p>
    </div>
    """, unsafe_allow_html=True)

def video_subtitle_tab():
    """動画字幕生成タブ"""
    st.markdown("### 📹 動画字幕生成")
    st.markdown("動画ファイルをアップロードして、自動で字幕を生成し、動画に焼き込みます。")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # ファイルアップロード
        uploaded_file = st.file_uploader(
            "動画ファイルを選択してください",
            type=['mp4', 'avi', 'mov', 'mkv'],
            help="対応形式: MP4, AVI, MOV, MKV"
        )
        
        if uploaded_file:
            # ファイル情報表示
            file_size = len(uploaded_file.read()) / (1024 * 1024)  # MB
            uploaded_file.seek(0)  # リセット
            
            st.info(f"📁 ファイル名: {uploaded_file.name}")
            st.info(f"📊 ファイルサイズ: {file_size:.1f} MB")
            
            # 字幕設定
            st.markdown("#### ⚙️ 字幕設定")
            col_font, col_pos, col_color = st.columns(3)
            
            with col_font:
                font_size = st.selectbox("フォントサイズ", [16, 20, 24, 28, 32], index=2)
            
            with col_pos:
                position = st.selectbox("字幕位置", ["下部", "中央", "上部"], index=0)
            
            with col_color:
                text_color = st.selectbox("文字色", ["白", "黄", "青", "緑"], index=0)
            
            # 翻訳設定
            translate_option = st.selectbox(
                "翻訳オプション",
                ["翻訳なし", "日本語→英語", "英語→日本語", "日本語→中国語", "日本語→韓国語"]
            )
    
    with col2:
        # 処理開始ボタン
        if st.button("🚀 字幕生成開始", type="primary", disabled=st.session_state.processing):
            if uploaded_file:
                process_video_subtitle(uploaded_file, font_size, position, text_color, translate_option)
            else:
                st.error("動画ファイルを選択してください。")
    
    # 結果表示
    if 'video_result' in st.session_state.results:
        display_video_results()

def audio_transcription_tab():
    """音声文字起こしタブ"""
    st.markdown("### 🎵 音声・動画文字起こし")
    st.markdown("音声ファイルや動画ファイルをテキストに変換します。")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # ファイルアップロード
        uploaded_file = st.file_uploader(
            "音声・動画ファイルを選択してください",
            type=['mp3', 'wav', 'm4a', 'aac', 'flac', 'mp4', 'avi', 'mov', 'mkv'],
            help="対応形式: MP3, WAV, M4A, AAC, FLAC, MP4, AVI, MOV, MKV"
        )
        
        if uploaded_file:
            # ファイル情報表示
            file_size = len(uploaded_file.read()) / (1024 * 1024)  # MB
            uploaded_file.seek(0)  # リセット
            
            st.info(f"📁 ファイル名: {uploaded_file.name}")
            st.info(f"📊 ファイルサイズ: {file_size:.1f} MB")
            
            # 出力設定
            st.markdown("#### ⚙️ 出力設定")
            col_format, col_timestamp = st.columns(2)
            
            with col_format:
                output_format = st.selectbox("出力形式", ["プレーンテキスト", "タイムスタンプ付き", "JSON形式"])
            
            with col_timestamp:
                include_timestamps = st.checkbox("タイムスタンプを含める", value=True)
            
            # 翻訳設定
            translate_option = st.selectbox(
                "翻訳オプション",
                ["翻訳なし", "日本語→英語", "英語→日本語", "日本語→中国語", "日本語→韓国語"],
                key="audio_translate"
            )
    
    with col2:
        # 処理開始ボタン
        if st.button("🚀 文字起こし開始", type="primary", disabled=st.session_state.processing):
            if uploaded_file:
                process_audio_transcription(uploaded_file, output_format, include_timestamps, translate_option)
            else:
                st.error("音声・動画ファイルを選択してください。")
    
    # 結果表示
    if 'audio_result' in st.session_state.results:
        display_audio_results()

def realtime_recording_tab():
    """リアルタイム録音タブ"""
    st.markdown("### 🎤 リアルタイム録音・文字起こし")
    st.markdown("マイクから音声を録音して、リアルタイムで文字起こしを行います。")
    
    # セキュリティ要件の説明
    st.info("💡 **重要**: マイク機能を使用するには、ブラウザがセキュアな環境を要求します。")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # 録音設定
        st.markdown("#### ⚙️ 録音設定")
        col_quality, col_lang = st.columns(2)
        
        with col_quality:
            audio_quality = st.selectbox("音質", ["標準 (16kHz)", "高品質 (44.1kHz)"], index=0)
        
        with col_lang:
            source_language = st.selectbox("音声言語", ["日本語", "英語", "中国語", "韓国語"], index=0)
        
        # 翻訳設定
        translate_option = st.selectbox(
            "翻訳オプション",
            ["翻訳なし", "日本語→英語", "英語→日本語", "日本語→中国語", "日本語→韓国語"],
            key="realtime_translate"
        )
    
    with col2:
        # 録音制御
        st.markdown("#### 🎙️ 録音制御")
        
        # フォールバック: 手動録音ボタン（機能制限）
        st.warning("⚠️ マイク録音機能を使用するには、追加のコンポーネントが必要です。")
        st.code("pip install streamlit-mic-recorder")
        
        col_start, col_stop = st.columns(2)
        
        with col_start:
            if st.button("🔴 録音開始（模擬）", disabled=st.session_state.recording):
                start_recording_fallback(audio_quality, source_language, translate_option)
        
        with col_stop:
            if st.button("⏹️ 録音停止（模擬）", disabled=not st.session_state.recording):
                stop_recording_fallback()
        
        # 録音状態表示
        if st.session_state.recording:
            st.markdown('<p class="status-processing">🔴 録音中...（模擬モード）</p>', unsafe_allow_html=True)
        else:
            st.markdown('<p class="status-success">⏹️ 録音停止中</p>', unsafe_allow_html=True)
    
    # リアルタイム結果表示
    if 'realtime_result' in st.session_state.results:
        display_realtime_results()

# 処理関数はすべて元のまま（長いので省略）
def process_video_subtitle(uploaded_file, font_size, position, text_color, translate_option):
    """動画字幕生成処理"""
    st.session_state.processing = True
    
    with st.spinner('動画を処理中...'):
        try:
            # 一時ファイル保存
            with tempfile.NamedTemporaryFile(delete=False, suffix=Path(uploaded_file.name).suffix) as tmp_file:
                tmp_file.write(uploaded_file.read())
                video_path = tmp_file.name
            
            # 進行状況表示
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # ステップ1: 音声抽出
            status_text.text("🎵 音声を抽出中...")
            progress_bar.progress(20)
            audio_path = extract_audio(video_path)
            
            # ステップ2: 文字起こし
            status_text.text("📝 音声を文字起こし中...")
            progress_bar.progress(50)
            transcription_result = transcribe_audio_file(audio_path)
            
            # ステップ3: 翻訳（必要に応じて）
            srt_content_to_use = transcription_result  # デフォルトは元の文字起こし結果
            
            if translate_option != "翻訳なし":
                status_text.text("🌐 テキストを翻訳中...")
                progress_bar.progress(70)
                
                # テキスト全体を翻訳
                translated_text = translate_text(transcription_result['text'], translate_option)
                
                # セグメントも翻訳（セグメントがある場合）
                if 'segments' in transcription_result and transcription_result['segments']:
                    from utils.translation import translate_segments
                    translated_segments = translate_segments(transcription_result['segments'], translate_option)
                    
                    # 翻訳されたバージョンを作成
                    srt_content_to_use = {
                        'text': translated_text,
                        'segments': translated_segments,
                        'language': transcription_result.get('language', 'ja'),
                        'original_text': transcription_result['text'],  # 元のテキストも保持
                        'translation_option': translate_option
                    }
                else:
                    # セグメントがない場合はテキストのみ翻訳
                    srt_content_to_use = {
                        'text': translated_text,
                        'segments': [],
                        'language': transcription_result.get('language', 'ja'),
                        'original_text': transcription_result['text'],
                        'translation_option': translate_option
                    }
                
                # 翻訳結果を保存（表示用）
                transcription_result['translated'] = translated_text
                transcription_result['translation_option'] = translate_option
            
            # ステップ4: 字幕ファイル生成（翻訳後のコンテンツを使用）
            status_text.text("📄 字幕ファイルを生成中...")
            progress_bar.progress(80)
            srt_path = create_srt_file(srt_content_to_use)
            
            # ステップ5: 動画に字幕焼き込み
            status_text.text("🎬 動画に字幕を焼き込み中...")
            progress_bar.progress(90)
            
            # 位置パラメータを修正
            position_mapping = {"下部": "bottom", "中央": "center", "上部": "top"}
            color_mapping = {"白": "white", "黄": "yellow", "青": "blue", "緑": "green"}
            
            output_video_path = burn_subtitles(
                video_path,
                srt_path,
                font_size,
                position_mapping[position],
                color_mapping[text_color]
            )
            
            # 完了
            progress_bar.progress(100)
            status_text.text("✅ 処理完了!")
            
            # 結果保存
            st.session_state.results['video_result'] = {
                'transcription': transcription_result,
                'srt_path': srt_path,
                'video_path': output_video_path,
                'original_filename': uploaded_file.name,
                'translation_used': translate_option != "翻訳なし",
                'srt_content_used': srt_content_to_use  # どのコンテンツが使われたかも保存
            }
            
            # 一時ファイル削除
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
    
    with st.spinner('音声を処理中...'):
        try:
            # 一時ファイル保存
            with tempfile.NamedTemporaryFile(delete=False, suffix=Path(uploaded_file.name).suffix) as tmp_file:
                tmp_file.write(uploaded_file.read())
                audio_path = tmp_file.name
            
            # 進行状況表示
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # 動画ファイルの場合は音声抽出
            if Path(uploaded_file.name).suffix.lower() in ['.mp4', '.avi', '.mov', '.mkv']:
                status_text.text("🎵 音声を抽出中...")
                progress_bar.progress(25)
                audio_path = extract_audio(audio_path)
            
            # 文字起こし
            status_text.text("📝 音声を文字起こし中...")
            progress_bar.progress(60)
            transcription_result = transcribe_audio_file(audio_path)
            
            # 翻訳（必要に応じて）
            if translate_option != "翻訳なし":
                status_text.text("🌐 テキストを翻訳中...")
                progress_bar.progress(80)
                translated_text = translate_text(transcription_result['text'], translate_option)
                transcription_result['translated'] = translated_text
            
            # 完了
            progress_bar.progress(100)
            status_text.text("✅ 処理完了!")
            
            # 結果保存
            st.session_state.results['audio_result'] = {
                'transcription': transcription_result,
                'output_format': output_format,
                'include_timestamps': include_timestamps,
                'original_filename': uploaded_file.name
            }
            
            # 一時ファイル削除
            os.unlink(audio_path)
            
            st.success("音声文字起こしが完了しました！")
            
        except Exception as e:
            st.error(f"エラーが発生しました: {str(e)}")
        finally:
            st.session_state.processing = False

def start_recording_fallback(audio_quality, source_language, translate_option):
    """フォ
