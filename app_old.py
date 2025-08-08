import os
import streamlit as st
import tempfile
import ffmpeg
import anthropic
from openai import OpenAI
from dotenv import load_dotenv
import pysrt
from datetime import timedelta
import json

# 環境変数読み込み
load_dotenv()

# API クライアント初期化
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
claude_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

def extract_audio_from_video(video_path, audio_path):
    """動画から音声を抽出"""
    try:
        (
            ffmpeg
            .input(video_path)
            .output(audio_path, acodec='pcm_s16le', ar=16000, ac=1)
            .overwrite_output()
            .run(quiet=True)
        )
        return True
    except Exception as e:
        st.error(f"音声抽出エラー: {e}")
        return False

def transcribe_with_whisper(audio_path, language="auto"):
    """Whisperで音声認識（タイムスタンプ付き）"""
    try:
        with open(audio_path, "rb") as audio_file:
            transcript = openai_client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="verbose_json",
                timestamp_granularities=["word"]
            )
        return transcript
    except Exception as e:
        st.error(f"音声認識エラー: {e}")
        return None

def translate_with_claude(text, source_lang="英語", target_lang="日本語"):
    """Claude APIで翻訳"""
    try:
        response = claude_client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=4000,
            messages=[{
                "role": "user",
                "content": f"""
以下の{source_lang}テキストを自然な{target_lang}に翻訳してください。
- 動画の字幕として使用するため、読みやすく短めに
- 専門用語は適切に翻訳
- 原文の意味とニュアンスを保持

原文：
{text}
"""
            }]
        )
        return response.content[0].text
    except Exception as e:
        st.error(f"翻訳エラー: {e}")
        return text

def create_srt_from_transcript(transcript, translation):
    """タイムスタンプ付きSRTファイル作成"""
    subs = pysrt.SubRipFile()
    
    # words属性を安全に取得
    words = getattr(transcript, 'words', []) if hasattr(transcript, 'words') else []
    if not words:
        # wordsがない場合は全体を1つの字幕に
        text_content = getattr(transcript, 'text', translation) if hasattr(transcript, 'text') else translation
        subs.append(pysrt.SubRipItem(
            index=1,
            start=pysrt.SubRipTime(0, 0, 0, 0),
            end=pysrt.SubRipTime(0, 0, 10, 0),
            text=text_content
        ))
        return subs
    
    # 10秒ごとに字幕を分割
    current_text = ""
    start_time = 0
    subtitle_index = 1
    
    for i, word in enumerate(words):
        word_text = getattr(word, 'word', '') if hasattr(word, 'word') else str(word)
        word_start = getattr(word, 'start', i) if hasattr(word, 'start') else i
        word_end = getattr(word, 'end', i+1) if hasattr(word, 'end') else i+1
        
        current_text += word_text + " "
        
        # 10秒経過または最後の単語の場合
        if word_end - start_time >= 10 or i == len(words) - 1:
            # この部分を翻訳
            translated_segment = translate_with_claude(current_text.strip())
            
            subs.append(pysrt.SubRipItem(
                index=subtitle_index,
                start=pysrt.SubRipTime.from_ordinal(int(start_time * 1000)),
                end=pysrt.SubRipTime.from_ordinal(int(word_end * 1000)),
                text=translated_segment
            ))
            
            current_text = ""
            start_time = word_end
            subtitle_index += 1
    
    return subs

def embed_subtitles_to_video(video_path, srt_path, output_path):
    """動画に字幕を埋め込み"""
    try:
        (
            ffmpeg
            .input(video_path)
            .output(
                output_path,
                vf=f"subtitles={srt_path}:force_style='FontSize=20,PrimaryColour=&Hffffff&,OutlineColour=&H000000&,Outline=2'",
                acodec='copy'
            )
            .overwrite_output()
            .run(quiet=True)
        )
        return True
    except Exception as e:
        st.error(f"字幕埋め込みエラー: {e}")
        return False

# Streamlit UI
st.title("🎬 自動字幕生成アプリ")
st.write("動画をアップロードして、自動で日本語字幕を生成します！")

# サイドバーで設定
st.sidebar.header("設定")
source_language = st.sidebar.selectbox(
    "元の言語",
    ["auto", "en", "zh", "ko", "es", "fr"],
    format_func=lambda x: {
        "auto": "自動検出",
        "en": "英語",
        "zh": "中国語",
        "ko": "韓国語",
        "es": "スペイン語",
        "fr": "フランス語"
    }[x]
)

# ファイルアップロード
uploaded_file = st.file_uploader(
    "動画ファイルをアップロード",
    type=['mp4', 'mov', 'avi', 'mkv'],
    help="対応形式: MP4, MOV, AVI, MKV"
)

if uploaded_file is not None:
    # 一時ファイル作成
    with tempfile.TemporaryDirectory() as temp_dir:
        # アップロードされた動画を保存
        video_path = os.path.join(temp_dir, "input_video.mp4")
        with open(video_path, "wb") as f:
            f.write(uploaded_file.read())
        
        # 動画情報表示
        st.video(uploaded_file)
        
        if st.button("🚀 字幕生成開始"):
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # Step 1: 音声抽出
            status_text.text("📄 動画から音声を抽出中...")
            progress_bar.progress(20)
            
            audio_path = os.path.join(temp_dir, "audio.wav")
            if not extract_audio_from_video(video_path, audio_path):
                st.stop()
            
            # Step 2: 音声認識
            status_text.text("🎤 音声認識中...")
            progress_bar.progress(40)
            
            transcript = transcribe_with_whisper(audio_path, source_language)
            if not transcript:
                st.stop()
            
            # Step 3: 翻訳
            status_text.text("🌐 翻訳中...")
            progress_bar.progress(60)
            
            original_text = transcript.text if hasattr(transcript, 'text') else ''
            translated_text = translate_with_claude(original_text)
            
            # Step 4: 字幕ファイル作成
            status_text.text("📝 字幕ファイル作成中...")
            progress_bar.progress(80)
            
            srt_content = create_srt_from_transcript(transcript, translated_text)
            srt_path = os.path.join(temp_dir, "subtitles.srt")
            srt_content.save(srt_path)
            
            # Step 5: 動画に字幕埋め込み
            status_text.text("🎬 動画に字幕を埋め込み中...")
            progress_bar.progress(90)
            
            output_path = os.path.join(temp_dir, "output_with_subtitles.mp4")
            if embed_subtitles_to_video(video_path, srt_path, output_path):
                progress_bar.progress(100)
                status_text.text("✅ 完了！")
                
                # 結果表示
                st.success("字幕付き動画が生成されました！")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader("📄 元のテキスト")
                    st.text_area("", original_text, height=200)
                
                with col2:
                    st.subheader("🌐 翻訳結果")
                    st.text_area("", translated_text, height=200)
                
                # ファイルダウンロード
                with open(output_path, "rb") as f:
                    st.download_button(
                        label="📥 字幕付き動画をダウンロード",
                        data=f.read(),
                        file_name="subtitled_video.mp4",
                        mime="video/mp4"
                    )
                
                # SRTファイルダウンロード
                with open(srt_path, "r", encoding="utf-8") as f:
                    st.download_button(
                        label="📄 字幕ファイル(SRT)をダウンロード",
                        data=f.read(),
                        file_name="subtitles.srt",
                        mime="text/plain"
                    )

# 使い方説明
with st.expander("📖 使い方"):
    st.markdown("""
    1. **APIキー設定**: `.env`ファイルにOpenAIとAnthropicのAPIキーを設定
    2. **動画アップロード**: 対応形式の動画ファイルを選択
    3. **言語選択**: 元の動画の言語を選択（自動検出も可能）
    4. **実行**: 「字幕生成開始」ボタンをクリック
    5. **ダウンロード**: 生成された字幕付き動画をダウンロード
    
    **対応形式**: MP4, MOV, AVI, MKV
    **処理時間**: 動画の長さに応じて数分〜数十分
    """)

# 注意事項
with st.expander("⚠️ 注意事項"):
    st.markdown("""
    - **APIコスト**: 長時間の動画は料金が高くなる可能性があります
    - **処理時間**: 動画の長さに比例して時間がかかります
    - **ファイルサイズ**: 大容量ファイルは処理に時間がかかります
    - **精度**: 音質や話し方により認識精度が変わります
    """)
