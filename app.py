import streamlit as st
import os
import tempfile
import json
from pathlib import Path
import time
from dotenv import load_dotenv

# 環境変数を読み込み
load_dotenv()

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

# カスタムCSS
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
    
    /* セレクトボックス内の選択された値の表示 */
    .stSelectbox [data-baseweb="select"] {
        background-color: white !important;
        min-height: 40px !important;
    }
    
    .stSelectbox [data-baseweb="select"] > div {
        background-color: white !important;
        color: #1f2937 !important;
        border: 1px solid #d1d5db !important;
        border-radius: 6px;
        padding: 8px 12px !important;
        min-height: 40px !important;
        display: flex !important;
        align-items: center !important;
        font-size: 14px !important;
        line-height: 1.5 !important;
    }
    
    /* セレクトボックス内のテキスト要素 */
    .stSelectbox [data-baseweb="select"] [data-baseweb="input"] {
        color: #1f2937 !important;
        font-size: 14px !important;
    }
    
    .stSelectbox [data-baseweb="select"] [data-baseweb="input"] input {
        color: #1f2937 !important;
        background-color: transparent !important;
        border: none !important;
        font-size: 14px !important;
    }
    
    /* 選択されたオプションの表示 */
    .stSelectbox [data-baseweb="select"] [data-baseweb="single-select"] {
        color: #1f2937 !important;
        font-size: 14px !important;
        padding: 0 !important;
    }
    
    /* ドロップダウンの矢印アイコン */
    .stSelectbox [data-baseweb="select"] svg {
        color: #6b7280 !important;
        width: 16px !important;
        height: 16px !important;
    }
    
    /* より具体的なセレクトボックス修正 */
    [data-testid="stSelectbox"] {
        color: #374151 !important;
    }
    
    [data-testid="stSelectbox"] label {
        color: #374151 !important;
        font-weight: 500;
        margin-bottom: 8px;
        font-size: 14px;
    }
    
    [data-testid="stSelectbox"] > div > div {
        background-color: white !important;
        border: 1px solid #d1d5db !important;
        border-radius: 6px;
        min-height: 42px !important;
    }
    
    [data-testid="stSelectbox"] [data-baseweb="select"] {
        background-color: white !important;
        color: #1f2937 !important;
        min-height: 42px !important;
        font-size: 14px !important;
    }
    
    [data-testid="stSelectbox"] [data-baseweb="select"] > div {
        background-color: white !important;
        color: #1f2937 !important;
        padding: 10px 12px !important;
        border: none !important;
        min-height: 42px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: space-between !important;
    }
    
    /* ドロップダウンメニューの背景と選択肢 */
    .stSelectbox [data-baseweb="popover"] {
        background-color: white !important;
        border: 1px solid #d1d5db !important;
        border-radius: 6px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        z-index: 1000;
    }
    
    .stSelectbox [role="option"] {
        background-color: white !important;
        color: #1f2937 !important;
        padding: 10px 12px !important;
        font-size: 14px !important;
        border: none !important;
        cursor: pointer;
    }
    
    .stSelectbox [role="option"]:hover {
        background-color: #f3f4f6 !important;
        color: #111827 !important;
    }
    
    .stSelectbox [role="option"][aria-selected="true"] {
        background-color: #1f77b4 !important;
        color: white !important;
    }
    
    .stSelectbox [role="option"] {
        background-color: white !important;
        color: #1f2937 !important;
        padding: 0.5rem 0.75rem;
    }
    
    .stSelectbox [role="option"]:hover {
        background-color: #f3f4f6 !important;
        color: #111827 !important;
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
    
    .stFileUploader label {
        color: #374151 !important;
        font-weight: 500;
    }
    
    /* アップロードされたファイルの情報表示 */
    .stFileUploader [data-testid="fileUploaderFileData"] {
        background-color: white !important;
        color: #1f2937 !important;
        border: 1px solid #d1d5db !important;
        border-radius: 6px;
        padding: 0.75rem;
    }
    
    /* テキストエリア */
    .stTextArea > div > div > textarea {
        border: 1px solid #d1d5db !important;
        border-radius: 6px;
        background-color: white !important;
        color: #1f2937 !important;
        padding: 0.75rem;
    }
    
    .stTextArea label {
        color: #374151 !important;
        font-weight: 500;
    }
    
    /* チェックボックス */
    .stCheckbox label {
        color: #374151 !important;
    }
    
    /* プログレスバー */
    .stProgress > div > div {
        background: linear-gradient(90deg, #1f77b4, #4a90e2) !important;
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
    
    /* 一般的なテキスト */
    .stMarkdown, .stMarkdown p {
        color: #374151 !important;
    }
    
    /* メトリクス */
    .stMetric {
        background: white !important;
        padding: 1rem;
        border-radius: 8px;
        border: 1px solid #e5e7eb !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    
    .stMetric [data-testid="metric-container"] {
        color: #1f2937 !important;
    }
    
    /* サイドバー（もしあれば） */
    .css-1d391kg {
        background-color: #f9fafb !important;
    }
    
    /* 列レイアウト */
    .stColumn {
        padding: 0.5rem;
    }
    
    /* 入力フィールド全般 */
    input[type="text"], input[type="number"] {
        background-color: white !important;
        color: #1f2937 !important;
        border: 1px solid #d1d5db !important;
        border-radius: 6px;
        padding: 0.5rem 0.75rem;
    }
    
    /* ラベル全般 */
    label {
        color: #374151 !important;
        font-weight: 500;
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
    st.markdown("""
    <div style="text-align: center; padding: 1rem 0 2rem 0;">
        <h1 style="color: #1f77b4; margin-bottom: 0.5rem;">🎬 動画・音声文字起こしアプリ</h1>
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
    st.info("💡 **重要**: マイク機能を使用するには、ブラウザがセキュアな環境を要求します。現在 `http://localhost:8501` で動作中です。")
    
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
        
        # 実際のマイク録音機能を実装（要: streamlit-mic-recorder）
        try:
            # streamlit-mic-recorderがインストールされている場合
            from streamlit_mic_recorder import mic_recorder
            
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
                
        except ImportError:
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

def process_realtime_audio(audio_data, source_language, translate_option):
    """実際のマイク録音データを処理"""
    try:
        with st.spinner('音声を文字起こし中...'):
            # 録音データを一時ファイルに保存
            import tempfile
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
                tmp_file.write(audio_data['bytes'])
                audio_path = tmp_file.name
            
            # 音声認識実行
            transcription_result = transcribe_audio_file(audio_path)
            
            # 翻訳（必要に応じて）
            if translate_option != "翻訳なし":
                translated_text = translate_text(transcription_result['text'], translate_option)
                transcription_result['translated'] = translated_text
            
            # 結果保存
            st.session_state.results['realtime_result'] = {
                'status': 'completed',
                'transcription': transcription_result,
                'audio_duration': len(audio_data['bytes']) / (audio_data['sample_rate'] * audio_data['sample_width']),
                'source_language': source_language,
                'translate_option': translate_option,
                'timestamp': time.time()
            }
            
            # 一時ファイル削除
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
        
        # 模擬の文字起こし結果
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
            output_video_path = burn_subtitles(video_path, srt_path, font_size, position, text_color)
            
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

def start_recording(audio_quality, source_language, translate_option):
    """録音開始"""
    st.session_state.recording = True
    st.session_state.results['realtime_result'] = {
        'status': 'recording',
        'audio_quality': audio_quality,
        'source_language': source_language,
        'translate_option': translate_option,
        'start_time': time.time()
    }
    st.rerun()

def stop_recording():
    """録音停止・処理"""
    st.session_state.recording = False
    
    with st.spinner('録音を処理中...'):
        try:
            # 録音データを処理（実装は utils/transcription.py で）
            result = transcribe_realtime(st.session_state.results['realtime_result'])
            
            st.session_state.results['realtime_result'].update({
                'status': 'completed',
                'transcription': result,
                'end_time': time.time()
            })
            
            st.success("録音の文字起こしが完了しました！")
            
        except Exception as e:
            st.error(f"エラーが発生しました: {str(e)}")
            st.session_state.results['realtime_result']['status'] = 'error'

def create_srt_file(transcription_result):
    """SRTファイル生成"""
    try:
        # 一時ファイル作成
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".srt")
        srt_path = temp_file.name
        temp_file.close()
        
        # 翻訳されたセグメントがあるかチェック
        segments_to_use = None
        text_to_use = ""
        
        if 'segments' in transcription_result and transcription_result['segments']:
            segments_to_use = transcription_result['segments']
        
        if 'text' in transcription_result:
            text_to_use = transcription_result['text']
        
        # SRT内容生成
        if segments_to_use:
            srt_content = create_srt_content(segments_to_use)
        else:
            # セグメント情報がない場合は全体テキストで単一エントリ作成
            if text_to_use:
                srt_content = "1\n00:00:00,000 --> 00:10:00,000\n" + text_to_use
            else:
                srt_content = "1\n00:00:00,000 --> 00:10:00,000\n字幕なし"
        
        # ファイル書き込み
        with open(srt_path, 'w', encoding='utf-8') as f:
            f.write(srt_content)
        
        # デバッグ情報（翻訳が適用されているかチェック）
        if 'translation_option' in transcription_result:
            st.info(f"字幕ファイル作成: {transcription_result['translation_option']}を適用")
            # 最初の100文字を表示してデバッグ
            preview_text = (text_to_use[:100] + "...") if len(text_to_use) > 100 else text_to_use
            st.write(f"字幕プレビュー: {preview_text}")
        
        return srt_path
        
    except Exception as e:
        st.error(f"SRTファイル作成エラー: {str(e)}")
        return None

def display_video_results():
    """動画結果表示"""
    result = st.session_state.results['video_result']
    
    st.markdown('<div class="result-section">', unsafe_allow_html=True)
    st.markdown("### 📹 動画字幕生成結果")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # 文字起こし結果
        st.markdown("#### 📝 文字起こし結果")
        st.text_area("テキスト", result['transcription']['text'], height=200, key="video_transcript")
        
        # 翻訳結果（あれば）
        if 'translated' in result['transcription']:
            st.markdown("#### 🌐 翻訳結果")
            st.text_area("翻訳テキスト", result['transcription']['translated'], height=100, key="video_translated")
    
    with col2:
        # ダウンロードオプション
        st.markdown("#### 💾 ダウンロード")
        
        # SRTファイルダウンロード
        if os.path.exists(result['srt_path']):
            with open(result['srt_path'], 'rb') as file:
                st.download_button(
                    "📄 字幕ファイル (.srt)",
                    file.read(),
                    file_name=f"{Path(result['original_filename']).stem}.srt",
                    mime="text/plain"
                )
        
        # 動画ファイルダウンロード
        if os.path.exists(result['video_path']):
            with open(result['video_path'], 'rb') as file:
                st.download_button(
                    "🎬 字幕付き動画",
                    file.read(),
                    file_name=f"{Path(result['original_filename']).stem}_subtitled.mp4",
                    mime="video/mp4"
                )
        
        # テキストファイルダウンロード
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
        # 文字起こし結果
        st.markdown("#### 📝 文字起こし結果")
        st.text_area("テキスト", result['transcription']['text'], height=300, key="audio_transcript")
        
        # 翻訳結果（あれば）
        if 'translated' in result['transcription']:
            st.markdown("#### 🌐 翻訳結果")
            st.text_area("翻訳テキスト", result['transcription']['translated'], height=150, key="audio_translated")
    
    with col2:
        # コピーボタン
        st.markdown("#### 📋 コピー")
        if st.button("📝 テキストをコピー", key="copy_audio_text"):
            st.write("テキストがコピーされました（ブラウザのコピー機能を使用してください）")
        
        # ダウンロードオプション
        st.markdown("#### 💾 ダウンロード")
        
        # テキストファイル
        st.download_button(
            "📝 テキストファイル (.txt)",
            result['transcription']['text'],
            file_name=f"{Path(result['original_filename']).stem}_transcript.txt",
            mime="text/plain"
        )
        
        # JSONファイル
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
        st.markdown('<p class="status-processing">🔴 録音中...</p>', unsafe_allow_html=True)
        
        # 録音時間表示
        if 'start_time' in result:
            elapsed_time = time.time() - result['start_time']
            st.metric("録音時間", f"{elapsed_time:.1f}秒")
    
    elif result['status'] == 'completed' and 'transcription' in result:
        col1, col2 = st.columns([2, 1])
        
        with col1:
            # 文字起こし結果
            st.markdown("#### 📝 文字起こし結果")
            transcription_text = result['transcription'].get('text', '')
            st.text_area("テキスト", transcription_text, height=200, key="realtime_transcript")
            
            # 翻訳結果（あれば）
            if 'translated' in result['transcription']:
                st.markdown("#### 🌐 翻訳結果")
                translated_text = result['transcription']['translated']
                st.text_area("翻訳テキスト", translated_text, height=100, key="realtime_translated")
        
        with col2:
            # 録音情報
            st.markdown("#### ℹ️ 録音情報")
            
            # 録音時間の計算（複数のソースから）
            duration = None
            if 'audio_duration' in result:
                duration = result['audio_duration']
            elif 'end_time' in result and 'start_time' in result:
                duration = result['end_time'] - result['start_time']
            elif 'start_time' in result and 'timestamp' in result:
                duration = result['timestamp'] - result['start_time']
            elif 'transcription' in result and 'duration' in result['transcription']:
                duration = result['transcription']['duration']
            
            if duration:
                st.metric("録音時間", f"{duration:.1f}秒")
            else:
                st.metric("録音時間", "不明")
            
            # その他の情報
            if 'source_language' in result:
                st.info(f"言語: {result['source_language']}")
            if 'translate_option' in result:
                st.info(f"翻訳: {result['translate_option']}")
            
            # ダウンロード
            st.markdown("#### 💾 ダウンロード")
            if transcription_text:
                timestamp_str = int(result.get('timestamp', time.time()))
                st.download_button(
                    "📝 テキストファイル",
                    transcription_text,
                    file_name=f"realtime_transcript_{timestamp_str}.txt",
                    mime="text/plain"
                )
    
    elif result['status'] == 'error':
        st.markdown('<p class="status-error">❌ 録音処理でエラーが発生しました</p>', unsafe_allow_html=True)
        if 'error_message' in result:
            st.error(result['error_message'])
    
    st.markdown('</div>', unsafe_allow_html=True)

def main():
    """メイン関数"""
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
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
