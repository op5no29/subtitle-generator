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
import pyaudio
import wave
import time

# 環境変数読み込み
load_dotenv()

# API クライアント初期化
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
claude_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# 言語設定
LANGUAGES = {
    "auto": "自動検出",
    "ja": "日本語",
    "en": "英語",
    "zh": "中国語",
    "ko": "韓国語",
    "es": "スペイン語",
    "fr": "フランス語",
    "de": "ドイツ語",
    "it": "イタリア語",
    "pt": "ポルトガル語",
    "ru": "ロシア語",
    "unknown": "言語不明"
}

TARGET_LANGUAGES = {
    "ja": "日本語",
    "en": "英語",
    "zh": "中国語",
    "ko": "韓国語",
    "es": "スペイン語",
    "fr": "フランス語"
}

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
    """Whisperで音声認識（タイムスタンプ付き・言語検出情報付き）"""
    try:
        with open(audio_path, "rb") as audio_file:
            # languageが"auto"または"unknown"の場合はlanguageパラメータを省略
            if language in ["auto", "unknown"]:
                transcript = openai_client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="verbose_json",
                    timestamp_granularities=["word"]
                )
            else:
                transcript = openai_client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language=language,
                    response_format="verbose_json",
                    timestamp_granularities=["word"]
                )
        return transcript
    except Exception as e:
        st.error(f"音声認識エラー: {e}")
        return None

def translate_with_claude(text, source_lang="auto", target_lang="ja"):
    """Claude APIで翻訳（文脈重視・改良版）"""
    try:
        # 同じ言語の場合は翻訳せずそのまま返す
        if source_lang == target_lang:
            return text
        
        # より簡潔で文脈を重視するプロンプト
        if target_lang == "ja":
            target_name = "日本語"
        elif target_lang == "en":
            target_name = "英語"
        elif target_lang == "zh":
            target_name = "中国語"
        else:
            target_name = TARGET_LANGUAGES.get(target_lang, "日本語")
        
        response = claude_client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=4000,
            messages=[{
                "role": "user",
                "content": f"""以下のテキストを自然な{target_name}に翻訳してください。

重要な指示：
- 文脈とニュアンスを重視し、全体の流れを考慮してください
- 直訳ではなく、{target_name}として自然な表現にしてください
- 専門用語や固有名詞は適切に翻訳してください
- 話し言葉の場合は{target_name}の話し言葉として自然にしてください
- 元の意味とトーンを保持してください
- 翻訳結果のみを返してください（説明や前置きは不要）

翻訳対象テキスト：
{text}"""
            }]
        )
        return response.content[0].text.strip()
    except Exception as e:
        st.error(f"翻訳エラー: {e}")
        return text

def split_text_for_subtitles(text, max_chars_per_line=20, max_lines=2):
    """字幕用にテキストを適切に分割"""
    # 句読点で分割
    sentences = []
    current_sentence = ""
    
    for char in text:
        current_sentence += char
        if char in '。！？、.:!?':
            sentences.append(current_sentence.strip())
            current_sentence = ""
    
    if current_sentence.strip():
        sentences.append(current_sentence.strip())
    
    # 短いチャンクに分割
    chunks = []
    current_chunk = ""
    
    for sentence in sentences:
        if len(current_chunk + sentence) <= max_chars_per_line * max_lines:
            current_chunk += sentence
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = sentence
    
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    # 行分割
    final_chunks = []
    for chunk in chunks:
        if len(chunk) <= max_chars_per_line:
            final_chunks.append(chunk)
        else:
            # 長い場合は改行で分割
            words = chunk.split()
            lines = []
            current_line = ""
            
            for word in words:
                if len(current_line + word) <= max_chars_per_line:
                    current_line += word + " "
                else:
                    if current_line:
                        lines.append(current_line.strip())
                    current_line = word + " "
            
            if current_line:
                lines.append(current_line.strip())
            
            # 最大2行まで
            if len(lines) <= max_lines:
                final_chunks.append('\n'.join(lines))
            else:
                # 2行ずつに分割
                for i in range(0, len(lines), max_lines):
                    final_chunks.append('\n'.join(lines[i:i+max_lines]))
    
    return final_chunks

def create_srt_from_transcript(transcript, translation, source_lang, target_lang):
    """タイムスタンプ付きSRTファイル作成（改良版）"""
    subs = pysrt.SubRipFile()
    
    # words属性を安全に取得
    words = getattr(transcript, 'words', []) if hasattr(transcript, 'words') else []
    if not words:
        # wordsがない場合は翻訳を適切に分割
        if source_lang != target_lang:
            text_content = translate_with_claude(transcript.text if hasattr(transcript, 'text') else '', source_lang, target_lang)
        else:
            text_content = transcript.text if hasattr(transcript, 'text') else translation
        
        chunks = split_text_for_subtitles(text_content)
        duration_per_chunk = 10 / len(chunks) if chunks else 10
        
        for i, chunk in enumerate(chunks):
            subs.append(pysrt.SubRipItem(
                index=i+1,
                start=pysrt.SubRipTime.from_ordinal(int(i * duration_per_chunk * 1000)),
                end=pysrt.SubRipTime.from_ordinal(int((i + 1) * duration_per_chunk * 1000)),
                text=chunk
            ))
        return subs
    
    # 3-5秒ごとに字幕を分割（短縮）
    current_text = ""
    start_time = 0
    subtitle_index = 1
    
    for i, word in enumerate(words):
        word_text = getattr(word, 'word', '') if hasattr(word, 'word') else str(word)
        word_start = getattr(word, 'start', i) if hasattr(word, 'start') else i
        word_end = getattr(word, 'end', i+1) if hasattr(word, 'end') else i+1
        
        current_text += word_text + " "
        
        # 3-5秒経過、句読点、または最後の単語の場合
        duration = word_end - start_time
        is_sentence_end = word_text.strip().endswith(('。', '！', '？', '.', '!', '?', '、'))
        is_time_limit = duration >= 3
        is_last_word = i == len(words) - 1
        
        if is_time_limit or is_sentence_end or is_last_word:
            # この部分を翻訳
            if source_lang != target_lang:
                translated_segment = translate_with_claude(current_text.strip(), source_lang, target_lang)
            else:
                translated_segment = current_text.strip()
            
            # 長い場合は分割
            subtitle_chunks = split_text_for_subtitles(translated_segment)
            chunk_duration = (word_end - start_time) / len(subtitle_chunks) if subtitle_chunks else 3
            
            for j, chunk in enumerate(subtitle_chunks):
                chunk_start = start_time + (j * chunk_duration)
                chunk_end = start_time + ((j + 1) * chunk_duration)
                
                subs.append(pysrt.SubRipItem(
                    index=subtitle_index,
                    start=pysrt.SubRipTime.from_ordinal(int(chunk_start * 1000)),
                    end=pysrt.SubRipTime.from_ordinal(int(chunk_end * 1000)),
                    text=chunk
                ))
                subtitle_index += 1
            
            current_text = ""
            start_time = word_end
    
def create_srt_from_transcript_custom(transcript, translation, source_lang, target_lang, max_chars_per_line=20, max_lines=2):
    """タイムスタンプ付きSRTファイル作成（自然な区切り重視）"""
    subs = pysrt.SubRipFile()
    
    # Whisperが実際に検出した言語を取得
    detected_language = getattr(transcript, 'language', source_lang)
    actual_source_lang = detected_language if source_lang == "auto" else source_lang
    
    # 翻訳の必要性を判定（実際の検出言語ベース）
    need_translation = not (
        actual_source_lang == target_lang or
        (actual_source_lang == "ja" and target_lang == "ja") or
        (actual_source_lang == "japanese" and target_lang == "ja")  # Whisperは"japanese"を返すことがある
    )
    
    # 全体テキストを取得
    full_text = transcript.text if hasattr(transcript, 'text') else ''
    
    # 翻訳が必要な場合は、全体を一度に翻訳（文脈保持）
    if need_translation and full_text.strip():
        st.info("🌐 全体テキストを文脈を考慮して翻訳中...")
        full_translated_text = translate_with_claude(full_text, actual_source_lang, target_lang)
    else:
        full_translated_text = full_text
    
    # words属性を安全に取得
    words = getattr(transcript, 'words', []) if hasattr(transcript, 'words') else []
    
    if not words:
        # wordsがない場合は翻訳済みテキストを自然に分割
        chunks = split_text_for_subtitles(full_translated_text, max_chars_per_line, max_lines)
        # 適切な表示時間を計算（読む時間を考慮）
        total_duration = 30  # デフォルト30秒
        duration_per_chunk = max(2, total_duration / len(chunks)) if chunks else 3
        
        for i, chunk in enumerate(chunks):
            subs.append(pysrt.SubRipItem(
                index=i+1,
                start=pysrt.SubRipTime.from_ordinal(int(i * duration_per_chunk * 1000)),
                end=pysrt.SubRipTime.from_ordinal(int((i + 1) * duration_per_chunk * 1000)),
                text=chunk
            ))
        return subs
    
    # 単語レベルの情報がある場合：自然な区切りで字幕分割
    st.info("📝 音声の自然な区切りに合わせて字幕を作成中...")
    
    # 自然な区切りポイントを見つける
    natural_segments = find_natural_segments(words, full_translated_text)
    
    # 字幕アイテムを作成
    subtitle_index = 1
    for segment in natural_segments:
        # 長い場合はさらに分割
        subtitle_chunks = split_text_for_subtitles(segment['translated_text'], max_chars_per_line, max_lines)
        
        if len(subtitle_chunks) == 1:
            # 1つのチャンクの場合
            subs.append(pysrt.SubRipItem(
                index=subtitle_index,
                start=pysrt.SubRipTime.from_ordinal(int(segment['start'] * 1000)),
                end=pysrt.SubRipTime.from_ordinal(int(segment['end'] * 1000)),
                text=subtitle_chunks[0]
            ))
            subtitle_index += 1
        else:
            # 複数チャンクの場合は時間を分割
            chunk_duration = (segment['end'] - segment['start']) / len(subtitle_chunks)
            for j, chunk in enumerate(subtitle_chunks):
                chunk_start = segment['start'] + (j * chunk_duration)
                chunk_end = segment['start'] + ((j + 1) * chunk_duration)
                
                subs.append(pysrt.SubRipItem(
                    index=subtitle_index,
                    start=pysrt.SubRipTime.from_ordinal(int(chunk_start * 1000)),
                    end=pysrt.SubRipTime.from_ordinal(int(chunk_end * 1000)),
                    text=chunk
                ))
                subtitle_index += 1
    
    return subs

def find_natural_segments(words, translated_text):
    """音声の自然な区切りでセグメントを作成"""
    segments = []
    current_words = []
    current_original_text = ""
    segment_start = 0
    
    for i, word in enumerate(words):
        word_text = getattr(word, 'word', '') if hasattr(word, 'word') else str(word)
        word_start = getattr(word, 'start', i) if hasattr(word, 'start') else i
        word_end = getattr(word, 'end', i+1) if hasattr(word, 'end') else i+1
        
        if i == 0:
            segment_start = word_start
        
        current_words.append(word)
        current_original_text += word_text + " "
        
        # 自然な区切りポイントを判定
        is_sentence_end = word_text.strip().endswith(('。', '！', '？', '.', '!', '?'))
        is_pause_after = False
        
        # 次の単語との間に長いポーズがあるかチェック
        if i < len(words) - 1:
            next_word = words[i + 1]
            next_start = getattr(next_word, 'start', i+1)
            pause_duration = next_start - word_end
            is_pause_after = pause_duration > 1.0  # 1秒以上のポーズ
        
        # セグメント長さをチェック
        segment_duration = word_end - segment_start
        is_long_segment = segment_duration > 6.0  # 6秒以上の長いセグメント
        
        # 最後の単語
        is_last_word = i == len(words) - 1
        
        # 区切り条件
        should_break = (
            (is_sentence_end and segment_duration >= 1.5) or  # 文終了かつ最低1.5秒
            (is_pause_after and segment_duration >= 2.0) or   # 長いポーズかつ最低2秒
            is_long_segment or                                # 長すぎるセグメント
            is_last_word                                      # 最後の単語
        )
        
        if should_break:
            # セグメントを作成
            original_segment_text = current_original_text.strip()
            
            # 翻訳テキストから対応する部分を推定
            translated_segment = estimate_translated_segment(
                original_segment_text,
                translated_text,
                len(segments),
                len([w for w in words if getattr(w, 'start', 0) <= word_end])
            )
            
            segments.append({
                'start': segment_start,
                'end': word_end,
                'original_text': original_segment_text,
                'translated_text': translated_segment
            })
            
            # 次のセグメントの準備
            current_words = []
            current_original_text = ""
            if not is_last_word:
                segment_start = word_end
    
    return segments

def estimate_translated_segment(original_text, full_translated_text, segment_index, total_segments):
    """翻訳テキストから対応する部分を推定"""
    # 簡単な実装：翻訳テキストを句読点で分割
    import re
    
    sentences = re.split(r'[。！？\.\!\?]+', full_translated_text)
    sentences = [s.strip() for s in sentences if s.strip()]
    
    if not sentences:
        return original_text
    
    # セグメントインデックスに対応する文を選択
    if segment_index < len(sentences):
        result = sentences[segment_index]
        # 句読点を復元
        if segment_index < len(sentences) - 1:
            result += "。"
        return result
    else:
        # セグメントが文より多い場合は比例配分
        proportion = segment_index / max(total_segments, 1)
        char_position = int(len(full_translated_text) * proportion)
        
        # 適切な分割点を探す
        start_pos = max(0, char_position - 50)
        end_pos = min(len(full_translated_text), char_position + 50)
        
        # 句読点で区切る
        for i in range(char_position, end_pos):
            if full_translated_text[i] in '。！？':
                return full_translated_text[start_pos:i+1].strip()
        
        # 見つからない場合は文字数で切る
        return full_translated_text[start_pos:end_pos].strip()

def embed_subtitles_to_video_custom(video_path, srt_path, output_path, font_size=16, margin_bottom=20, outline_width=2):
    """動画に字幕を埋め込み（カスタム設定対応）"""
    try:
        # 字幕スタイルをカスタマイズ
        subtitle_style = (
            f"subtitles={srt_path}:"
            "force_style='"
            "FontName=Arial,"
            f"FontSize={font_size},"
            "PrimaryColour=&Hffffff&,"  # 白文字
            "OutlineColour=&H000000&,"  # 黒縁取り
            f"Outline={outline_width},"
            "Shadow=1,"  # 影
            "Alignment=2,"  # 下部中央揃え
            f"MarginV={margin_bottom},"  # 下端からの余白
            "MarginL=20,"  # 左余白
            "MarginR=20,"  # 右余白
            "BorderStyle=1"  # 縁取りスタイル
            "'"
        )
        
        (
            ffmpeg
            .input(video_path)
            .output(
                output_path,
                vf=subtitle_style,
                acodec='copy'
            )
            .overwrite_output()
            .run(quiet=True)
        )
        return True
    except Exception as e:
        st.error(f"字幕埋め込みエラー: {e}")
        return False

# リアルタイム音声認識用の関数
def test_realtime_audio():
    """リアルタイム音声レベル表示テスト（修正版）"""
    try:
        import pyaudio
        import struct
        import time
        
        # 音声設定（バッファを大きくしてオーバーフロー対策）
        FORMAT = pyaudio.paInt16
        CHANNELS = 1
        RATE = 16000
        CHUNK = 4096  # バッファサイズを大きく（1024→4096）
        
        audio = pyaudio.PyAudio()
        
        # 録音開始
        stream = audio.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            frames_per_buffer=CHUNK,
            input_device_index=None,  # デフォルトデバイス使用
        )
        
        st.info("🎤 リアルタイム音声テスト開始！話してみてください...")
        
        # リアルタイム表示用のプレースホルダー
        level_placeholder = st.empty()
        progress_placeholder = st.empty()
        
        max_level = 0
        test_duration = 10  # 10秒間テスト
        update_interval = 0.2  # 更新間隔を長く（0.1→0.2秒）
        
        total_chunks = int(RATE / CHUNK * test_duration)
        
        for i in range(total_chunks):
            try:
                # 非ブロッキング読み込み
                if stream.get_read_available() >= CHUNK:
                    data = stream.read(CHUNK, exception_on_overflow=False)
                    
                    # 音声レベルを計算
                    try:
                        samples = struct.unpack('<' + ('h' * (len(data) // 2)), data)
                        amplitude = max(abs(sample) for sample in samples)
                        current_level = amplitude
                        max_level = max(max_level, current_level)
                        
                        # 5回に1回だけ表示更新（負荷軽減）
                        if i % 5 == 0:
                            # プログレスバーで音声レベルを表示
                            progress = min(current_level / 30000, 1.0)  # 30000を最大値として正規化
                            progress_placeholder.progress(progress)
                            
                            # 数値でも表示
                            level_placeholder.metric(
                                "🎤 現在の音声レベル",
                                f"{current_level:,}",
                                f"最大: {max_level:,}"
                            )
                    except struct.error:
                        # データサイズ不整合の場合はスキップ
                        continue
                        
                else:
                    # データがない場合は少し待つ
                    time.sleep(0.01)
                
                # 更新間隔を調整
                time.sleep(update_interval)
                
            except IOError as e:
                if e.errno == -9981:  # Input overflowed
                    st.warning("⚠️ 音声バッファオーバーフロー。続行中...")
                    continue
                else:
                    raise e
        
        stream.stop_stream()
        stream.close()
        audio.terminate()
        
        # 最終表示をクリア
        level_placeholder.empty()
        progress_placeholder.empty()
        
        # 結果評価
        if max_level > 10000:
            st.success(f"✅ 音声キャプチャ成功！最大レベル: {max_level:,}")
            st.info("💡 この値なら音声認識に十分です")
        elif max_level > 1000:
            st.warning(f"⚠️ 音声レベルが低めです: {max_level:,}")
            st.info("💡 もう少し大きな声で話すか、マイクに近づいてください")
        else:
            st.error(f"❌ 音声がほとんど検出されません: {max_level:,}")
            st.error("💡 マイクの設定を確認してください")
            
        return max_level > 1000
        
    except Exception as e:
        st.error(f"❌ リアルタイム音声テストエラー: {e}")
        st.info("💡 Macの場合、以下を試してください：")
        st.info("- システム環境設定 > セキュリティとプライバシー > マイク で権限確認")
        st.info("- 他のアプリがマイクを使用していないか確認")
        st.info("- 内蔵マイクの音量を上げる")
        return False

def capture_audio_chunk(source_language="ja", target_language="ja"):
    """音声チャンクをキャプチャして処理（言語設定対応版）"""
    try:
        import pyaudio
        import wave
        import tempfile
        import time
        import os
        import struct
        
        st.info("🔧 デバッグ: 音声キャプチャを開始します...")
        st.info(f"🌐 設定: {LANGUAGES.get(source_language, source_language)} → {TARGET_LANGUAGES.get(target_language, target_language)}")
        
        # 音声設定（バッファオーバーフロー対策）
        FORMAT = pyaudio.paInt16
        CHANNELS = 1
        RATE = 16000
        CHUNK = 4096  # バッファサイズを大きく
        RECORD_SECONDS = 5  # 5秒間録音
        
        audio = pyaudio.PyAudio()
        
        # デバイス情報をチェック
        device_count = audio.get_device_count()
        default_input = audio.get_default_input_device_info()
        st.info(f"🔧 デバッグ: オーディオデバイス数: {device_count}")
        st.info(f"🔧 デバッグ: デフォルト入力デバイス: {default_input['name']}")
        
        # 録音開始（オーバーフロー対策）
        stream = audio.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            frames_per_buffer=CHUNK,
            input_device_index=None,  # デフォルトデバイス
        )
        
        st.info("🎤 5秒間音声をキャプチャします... **大きな声で話してください！**")
        
        # リアルタイム表示用
        level_placeholder = st.empty()
        progress_placeholder = st.empty()
        
        frames = []
        max_amplitude = 0
        
        # 録音ループ（エラーハンドリング強化）
        total_chunks = int(RATE / CHUNK * RECORD_SECONDS)
        
        for i in range(total_chunks):
            try:
                # オーバーフローを無視して録音
                data = stream.read(CHUNK, exception_on_overflow=False)
                frames.append(data)
                
                # 音声レベルをリアルタイム表示（軽量化）
                if i % 3 == 0:  # 3回に1回だけ更新
                    try:
                        samples = struct.unpack('<' + ('h' * (len(data) // 2)), data)
                        current_level = max(abs(sample) for sample in samples)
                        max_amplitude = max(max_amplitude, current_level)
                        
                        # プログレスバーで表示
                        progress = min(current_level / 30000, 1.0)
                        progress_placeholder.progress(progress)
                        level_placeholder.write(f"🎤 現在: {current_level:,} | 最大: {max_amplitude:,}")
                    except (struct.error, ValueError):
                        # データ処理エラーはスキップ
                        continue
                        
            except IOError as e:
                if e.errno == -9981:  # Input overflowed
                    # オーバーフローの場合は無音データを追加
                    silence = b'\x00' * (CHUNK * 2)  # 16bit = 2bytes
                    frames.append(silence)
                    continue
                else:
                    raise e
        
        stream.stop_stream()
        stream.close()
        audio.terminate()
        
        # 最終的なレベル表示をクリア
        level_placeholder.empty()
        progress_placeholder.empty()
        
        st.info(f"🔧 デバッグ: 最大音声レベル: {max_amplitude:,} (10000以上が理想)")
        
        if max_amplitude < 1000:
            st.warning("⚠️ 音声レベルが低すぎます。マイクに近づいて大きな声で話してください")
        
        st.info("🔄 音声ファイルを作成中...")
        
        # 一時ファイルに保存
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_audio:
            temp_path = temp_audio.name
            
            wf = wave.open(temp_path, 'wb')
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(audio.get_sample_size(FORMAT))
            wf.setframerate(RATE)
            wf.writeframes(b''.join(frames))
            wf.close()
            
            # ファイルサイズをチェック
            file_size = os.path.getsize(temp_path)
            st.info(f"🔧 デバッグ: 音声ファイルサイズ: {file_size:,} bytes")
            
            # ファイルサイズの閾値を調整（CHUNKが大きくなったため）
            min_file_size = RATE * 2 * RECORD_SECONDS * 0.5  # 期待サイズの50%以上
            
            if file_size < min_file_size:
                st.warning(f"⚠️ 音声ファイルが小さめです（{file_size:,} bytes < {min_file_size:,} bytes）")
                st.info("💡 音声が小さかった可能性がありますが、処理を続行します")
            
            st.info("🤖 Whisper APIで文字起こし中...")
            
            try:
                # Whisperで文字起こし（言語指定）
                with open(temp_path, "rb") as audio_file:
                    if source_language in ["auto", "unknown"]:
                        # 言語自動検出
                        transcript = openai_client.audio.transcriptions.create(
                            model="whisper-1",
                            file=audio_file,
                            response_format="text"
                        )
                    else:
                        # 言語指定
                        transcript = openai_client.audio.transcriptions.create(
                            model="whisper-1",
                            file=audio_file,
                            language=source_language,
                            response_format="text"
                        )
                
                st.info(f"🔧 デバッグ: Whisper生の結果: '{transcript}'")
                st.info(f"🔧 デバッグ: 文字数: {len(transcript)} 文字")
                
                if transcript.strip():
                    st.success(f"🎯 認識されたテキスト: '{transcript.strip()}'")
                    
                    # 翻訳判定：同じ言語または日本語→日本語の場合はスキップ
                    need_translation = not (
                        source_language == target_language or
                        (source_language == "ja" and target_language == "ja") or
                        (source_language == "auto" and target_language == "ja")
                    )
                    
                    if need_translation:
                        st.info("🌐 Claude APIで翻訳中...")
                        translated = translate_with_claude(transcript.strip(), source_language, target_language)
                        st.info(f"🔧 デバッグ: 翻訳結果: '{translated}'")
                    else:
                        st.info("✨ 翻訳をスキップして元の品質を保持します")
                        translated = transcript.strip()
                    
                    # 履歴に追加（確実に更新）
                    new_entry = {
                        "timestamp": time.strftime("%H:%M:%S"),
                        "original": transcript_text.strip(),
                        "translated": translated,
                        "source_lang": LANGUAGES.get(actual_source_lang, actual_source_lang),
                        "target_lang": TARGET_LANGUAGES.get(target_language, target_language),
                        "was_translated": need_translation,
                        "detected_lang": detected_language  # 実際の検出言語も保存
                    }
                    
                    # セッション状態の初期化（念のため）
                    if 'transcription_history' not in st.session_state:
                        st.session_state.transcription_history = []
                    
                    # 履歴に追加
                    st.session_state.transcription_history.append(new_entry)
                    
                    st.success(f"✅ 音声認識完了！履歴に追加されました（総数: {len(st.session_state.transcription_history)}）")
                    
                    # 結果を即座に表示（デバッグ用）
                    st.write("**追加された結果:**")
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write(f"元の音声: {new_entry['original']}")
                        if source_language == "auto":
                            st.caption(f"検出言語: {new_entry['source_lang']} ({detected_language})")
                        else:
                            st.caption(f"言語: {new_entry['source_lang']}")
                    with col2:
                        if need_translation:
                            st.write(f"翻訳結果: {new_entry['translated']}")
                            st.caption(f"翻訳先: {new_entry['target_lang']}")
                        else:
                            st.write(f"結果: {new_entry['translated']}")
                            st.caption("翻訳なし（品質保持）")
                    
                else:
                    st.warning("⚠️ Whisper APIから空の結果が返されました")
                    st.info("💡 以下を試してください：")
                    st.info("- より大きな声で話す")
                    st.info("- マイクに近づく")
                    st.info("- 背景ノイズを減らす")
                    return False
                
            except Exception as whisper_error:
                st.error(f"❌ Whisper API エラー: {whisper_error}")
                import traceback
                st.error(f"詳細: {traceback.format_exc()}")
                return False
            
            # 一時ファイルを削除
            os.unlink(temp_path)
            return True
            
    except Exception as e:
        st.error(f"❌ 音声キャプチャエラー: {e}")
        
        # エラーの種類に応じたアドバイス
        if "Input overflowed" in str(e):
            st.error("💡 音声バッファオーバーフロー対策：")
            st.info("- 他のアプリ（Zoom、Teams等）を終了してマイクを解放")
            st.info("- システム環境設定でマイク音量を下げる")
            st.info("- しばらく待ってから再試行")
        elif "Invalid device" in str(e):
            st.error("💡 マイクデバイス問題：")
            st.info("- システム環境設定 > サウンド で正しいマイクを選択")
            st.info("- 外部マイクの接続を確認")
        else:
            st.error("💡 一般的な対処法：")
            st.info("- アプリを再起動")
            st.info("- ブラウザを再起動")
            st.info("- システム環境設定 > セキュリティとプライバシー > マイク で権限確認")
        
        import traceback
        st.error(f"詳細エラー: {traceback.format_exc()}")
        return False

# Streamlit UI
st.title("🎬 多機能自動字幕生成アプリ")

# タブで機能を分割
tab1, tab2 = st.tabs(["📹 動画字幕生成", "🎤 リアルタイム音声認識"])

with tab1:
    st.write("動画をアップロードして、自動で字幕を生成します！")
    
    # 設定セクション
    st.subheader("⚙️ 基本設定")
    col1, col2 = st.columns(2)
    
    with col1:
        source_language = st.selectbox(
            "元の言語",
            list(LANGUAGES.keys()),
            format_func=lambda x: LANGUAGES[x],
            index=0
        )
    
    with col2:
        target_language = st.selectbox(
            "翻訳先言語",
            list(TARGET_LANGUAGES.keys()),
            format_func=lambda x: TARGET_LANGUAGES[x],
            index=0
        )
    
    # 翻訳の必要性を表示（事前判定）
    if source_language == target_language:
        st.success("✨ 翻訳をスキップして元の品質を保ちます（同じ言語）")
    elif source_language == "auto":
        st.info("🔍 自動検出モード：検出された言語によって翻訳を判定します")
        st.caption(f"→ 日本語が検出された場合：翻訳スキップ（品質保持）")
        st.caption(f"→ 他の言語が検出された場合：{TARGET_LANGUAGES[target_language]}に翻訳")
    elif source_language == "unknown":
        st.info("❓ 言語不明モード：検出された言語によって翻訳を判定します")
    else:
        source_name = LANGUAGES.get(source_language, "不明")
        target_name = TARGET_LANGUAGES.get(target_language, "不明")
        if source_language == "ja" and target_language == "ja":
            st.success("✨ 翻訳をスキップして元の品質を保ちます（日本語→日本語）")
        else:
            st.info(f"🌐 {source_name} → {target_name} に翻訳します")
    
    # 字幕設定（シンプル化）
    with st.expander("🎨 字幕スタイル設定"):
        col1, col2 = st.columns(2)
        
        with col1:
            font_size = st.slider("フォントサイズ", 12, 24, 16)
            max_chars_per_line = st.slider("1行あたりの最大文字数", 15, 30, 20)
        
        with col2:
            margin_bottom = st.slider("下端からの余白", 10, 50, 20)
            max_lines = st.selectbox("最大行数", [1, 2], index=1)
            outline_width = st.slider("縁取り太さ", 1, 4, 2)
    
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
                
                # Step 3: 翻訳判定と実行
                status_text.text("🌐 翻訳判定中...")
                progress_bar.progress(60)
                
                original_text = transcript.text if hasattr(transcript, 'text') else ''
                
                # Whisperが実際に検出した言語を取得
                detected_language = getattr(transcript, 'language', source_language)
                
                # 自動検出の場合は、実際に検出された言語を使用
                actual_source_lang = detected_language if source_language == "auto" else source_language
                
                # 翻訳の必要性を判定（実際の検出言語ベース）
                need_translation = not (
                    actual_source_lang == target_language or
                    (actual_source_lang == "ja" and target_language == "ja") or
                    (actual_source_lang == "japanese" and target_language == "ja")  # Whisperは"japanese"を返すことがある
                )
                
                # 検出された言語を表示
                if source_language == "auto":
                    detected_lang_name = LANGUAGES.get(detected_language, detected_language)
                    st.info(f"🔍 検出された言語: {detected_lang_name} ({detected_language})")
                
                if need_translation:
                    status_text.text("🌐 翻訳中...")
                    translated_text = translate_with_claude(original_text, actual_source_lang, target_language)
                    source_display = LANGUAGES.get(actual_source_lang, actual_source_lang)
                    target_display = TARGET_LANGUAGES.get(target_language, target_language)
                    st.info(f"✨ {source_display} → {target_display} に翻訳しました")
                else:
                    status_text.text("✨ 翻訳をスキップして品質を保持...")
                    translated_text = original_text
                    st.info(f"✨ 検出言語と翻訳先が同じ（{LANGUAGES.get(actual_source_lang, actual_source_lang)}）のため翻訳をスキップして、元の品質を保持しました")
                
                # Step 4: 字幕ファイル作成
                status_text.text("📝 字幕ファイル作成中...")
                progress_bar.progress(80)
                
                # カスタム設定を適用
                srt_content = create_srt_from_transcript_custom(
                    transcript, translated_text, source_language, target_language,
                    max_chars_per_line, max_lines
                )
                srt_path = os.path.join(temp_dir, "subtitles.srt")
                srt_content.save(srt_path)
                
                # Step 5: 動画に字幕埋め込み
                status_text.text("🎬 動画に字幕を埋め込み中...")
                progress_bar.progress(90)
                
                output_path = os.path.join(temp_dir, "output_with_subtitles.mp4")
                if embed_subtitles_to_video_custom(video_path, srt_path, output_path, font_size, margin_bottom, outline_width):
                    progress_bar.progress(100)
                    status_text.text("✅ 完了！")
                    
                    # 結果表示
                    st.success("字幕付き動画が生成されました！")
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        if source_language == "auto":
                            detected_lang_name = LANGUAGES.get(detected_language, detected_language)
                            st.subheader(f"📄 元のテキスト (検出: {detected_lang_name})")
                        else:
                            st.subheader(f"📄 元のテキスト ({LANGUAGES[source_language]})")
                        st.text_area("", original_text, height=200, key="original")
                    
                    with col2:
                        if need_translation:
                            st.subheader(f"🌐 翻訳結果 ({TARGET_LANGUAGES[target_language]})")
                            st.text_area("", translated_text, height=200, key="translated")
                        else:
                            st.subheader(f"✨ 結果 ({TARGET_LANGUAGES[target_language]})")
                            st.text_area("", translated_text, height=200, key="translated")
                            st.caption("翻訳スキップ（品質保持）")
                    
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

with tab2:
    st.write("マイクを使ってリアルタイム音声認識・翻訳を行います")
    
    # 言語設定セクション
    st.subheader("⚙️ 言語設定")
    col1, col2 = st.columns(2)
    
    with col1:
        rt_source_language = st.selectbox(
            "元の言語（リアルタイム）",
            list(LANGUAGES.keys()),
            format_func=lambda x: LANGUAGES[x],
            index=1,  # デフォルトで日本語
            key="rt_source"
        )
    
    with col2:
        rt_target_language = st.selectbox(
            "翻訳先言語（リアルタイム）",
            list(TARGET_LANGUAGES.keys()),
            format_func=lambda x: TARGET_LANGUAGES[x],
            index=0,  # デフォルトで日本語
            key="rt_target"
        )
    
    # 翻訳の必要性を表示
    if rt_source_language == rt_target_language:
        st.success("✨ 翻訳をスキップして元の品質を保ちます（同じ言語）")
    elif rt_source_language == "auto":
        st.info("🔍 自動検出モード：検出された言語によって翻訳を判定します")
        st.caption(f"→ 日本語が検出された場合：翻訳スキップ（品質保持）")
        st.caption(f"→ 他の言語が検出された場合：{TARGET_LANGUAGES[rt_target_language]}に翻訳")
    elif rt_source_language == "unknown":
        st.info("❓ 言語不明モード：検出された言語によって翻訳を判定します")
    else:
        source_name = LANGUAGES.get(rt_source_language, "不明")
        target_name = TARGET_LANGUAGES.get(rt_target_language, "不明")
        if rt_source_language == "ja" and rt_target_language == "ja":
            st.success("✨ 翻訳をスキップして元の品質を保ちます（日本語→日本語）")
        else:
            st.info(f"🌐 {source_name} → {target_name} に翻訳します")
    
    # セッション状態の初期化を明確に行う
    if 'recording_active' not in st.session_state:
        st.session_state.recording_active = False
    
    if 'transcription_history' not in st.session_state:
        st.session_state.transcription_history = []
    
    # マイクアクセステスト
    st.subheader("🎤 マイクテスト")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🔧 マイクアクセステスト"):
            try:
                import pyaudio
                audio = pyaudio.PyAudio()
                
                # 利用可能なデバイスをチェック
                device_count = audio.get_device_count()
                st.success(f"✅ PyAudio正常動作: {device_count}個のオーディオデバイスが見つかりました")
                
                # デフォルトマイクをテスト
                try:
                    stream = audio.open(
                        format=pyaudio.paInt16,
                        channels=1,
                        rate=16000,
                        input=True,
                        frames_per_buffer=1024
                    )
                    stream.close()
                    st.success("✅ マイクアクセス成功！録音機能が利用可能です")
                except Exception as mic_error:
                    st.error(f"❌ マイクアクセスエラー: {mic_error}")
                    st.info("💡 Macの場合: システム環境設定 > セキュリティとプライバシー > マイク でアクセス許可を確認してください")
                
                audio.terminate()
                
            except ImportError:
                st.error("❌ pyaudioがインストールされていません")
                st.code("pip install pyaudio")
            except Exception as e:
                st.error(f"❌ オーディオシステムエラー: {e}")
    
    with col2:
        if st.button("📊 リアルタイム音声テスト"):
            test_realtime_audio()
    
    st.subheader("🎙️ リアルタイム録音")
    
    # 簡単な録音制御
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("🎤 録音開始", disabled=st.session_state.recording_active, key="start_recording"):
            try:
                st.session_state.recording_active = True
                st.success("録音を開始しました")
                # st.rerun() を削除して履歴を保持
            except Exception as e:
                st.error(f"録音開始エラー: {e}")
                st.session_state.recording_active = False
    
    with col2:
        if st.button("⏹️ 録音停止", disabled=not st.session_state.recording_active, key="stop_recording"):
            st.session_state.recording_active = False
            st.success("録音を停止しました")
            # 履歴を保持したまま画面更新
            # st.rerun() を削除して履歴を保持
    
    with col3:
        if st.button("🗑️ 履歴クリア"):
            st.session_state.transcription_history = []
            st.success("履歴をクリアしました")
            # st.rerun() を削除
    
    # 録音状態の表示
    if st.session_state.recording_active:
        st.info("🎤 録音中... 音声をキャプチャしています")
        
        # 現在の履歴数を表示（デバッグ用）
        st.write(f"現在の履歴数: {len(st.session_state.transcription_history)}")
    
    # 音声処理ボタン（録音状態に関係なく常に表示）
    st.subheader("🎙️ 音声キャプチャ")
    
    if st.button("📝 手動で音声処理", key="manual_process"):
        try:
            with st.spinner("音声を処理中..."):
                # 5秒間の音声をキャプチャ（言語設定を渡す）
                success = capture_audio_chunk(rt_source_language, rt_target_language)
                if success:
                    st.success("音声処理が完了しました")
                    # 処理後にセッション状態を強制更新
                    st.session_state._last_update = time.time()
                else:
                    st.error("音声処理に失敗しました")
        except Exception as e:
            st.error(f"音声処理エラー: {e}")
    
    st.caption("💡 このボタンを押すと5秒間音声をキャプチャして文字起こしします")
    
    # 履歴数の表示（デバッグ情報として詳細表示）
    history_count = len(st.session_state.transcription_history)
    st.metric("📊 総履歴数", history_count)
    
    # セッション状態のデバッグ情報
    with st.expander("🔧 デバッグ情報"):
        st.write("セッション状態:")
        st.write(f"- recording_active: {st.session_state.recording_active}")
        st.write(f"- transcription_history length: {len(st.session_state.transcription_history)}")
        if st.session_state.transcription_history:
            st.write("最新の履歴:")
            st.json(st.session_state.transcription_history[-1])
    
    # 音声認識結果の表示（条件を緩和）
    if history_count > 0:
        st.subheader("📝 音声認識結果")
        
        # 最新の結果を最初に表示（最新を自動展開）
        for i, entry in enumerate(reversed(st.session_state.transcription_history[-10:])):  # 最新10件
            result_number = history_count - i
            is_latest = (i == 0)  # 最新の結果
            
            # 翻訳情報の表示
            translation_info = ""
            if entry.get('was_translated', True):  # 古いデータは翻訳ありとして扱う
                source_lang = entry.get('source_lang', '不明')
                target_lang = entry.get('target_lang', TARGET_LANGUAGES[rt_target_language])
                translation_info = f" ({source_lang}→{target_lang})"
            else:
                translation_info = " (翻訳なし)"
            
            with st.expander(
                f"[{entry['timestamp']}] 結果 #{result_number}{translation_info} {'(最新)' if is_latest else ''}",
                expanded=is_latest  # 最新の結果のみ展開
            ):
                col1, col2 = st.columns(2)
                with col1:
                    st.write("**元の音声:**")
                    st.write(entry['original'])
                    if 'detected_lang' in entry and entry.get('detected_lang'):
                        st.caption(f"検出言語: {entry.get('source_lang', '不明')} ({entry['detected_lang']})")
                    elif 'source_lang' in entry:
                        st.caption(f"認識言語: {entry['source_lang']}")
                with col2:
                    if entry.get('was_translated', True):
                        st.write("**翻訳結果:**")
                        st.write(entry['translated'])
                        if 'target_lang' in entry:
                            st.caption(f"翻訳先: {entry['target_lang']}")
                    else:
                        st.write("**結果:**")
                        st.write(entry['translated'])
                        st.caption("翻訳スキップ（品質保持）")
        
        # 全履歴をダウンロード
        col1, col2 = st.columns(2)
        with col1:
            if st.button("📥 全履歴をダウンロード"):
                history_text = f"音声認識履歴 (総数: {history_count})\n"
                history_text += f"生成日時: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                
                for i, entry in enumerate(st.session_state.transcription_history, 1):
                    history_text += f"=== 結果 #{i} ===\n"
                    history_text += f"時刻: {entry['timestamp']}\n"
                    history_text += f"元の音声: {entry['original']}\n"
                    
                    # 言語情報がある場合は追加
                    if 'detected_lang' in entry and entry.get('detected_lang'):
                        history_text += f"検出言語: {entry.get('source_lang', '不明')} ({entry['detected_lang']})\n"
                    elif 'source_lang' in entry:
                        history_text += f"認識言語: {entry['source_lang']}\n"
                    
                    # 翻訳情報
                    if entry.get('was_translated', True):
                        history_text += f"翻訳結果: {entry['translated']}\n"
                        if 'target_lang' in entry:
                            history_text += f"翻訳先言語: {entry['target_lang']}\n"
                    else:
                        history_text += f"結果: {entry['translated']}\n"
                        history_text += f"翻訳: スキップ（品質保持）\n"
                    
                    history_text += "\n"
                
                st.download_button(
                    label="📄 履歴をテキストファイルでダウンロード",
                    data=history_text,
                    file_name=f"transcription_history_{history_count}件.txt",
                    mime="text/plain"
                )
        
        with col2:
            if st.button("🔄 履歴を更新"):
                st.success("履歴を更新しました")
    else:
        st.info("まだ音声認識結果がありません。「📝 手動で音声処理」ボタンを押して音声をキャプチャしてください。")
        st.write("💡 **手順:**")
        st.write("1. 🎤 録音開始をクリック")
        st.write("2. 📝 手動で音声処理をクリック")
        st.write("3. 5秒間話す")
        st.write("4. 結果が表示される")

# 使い方説明
with st.expander("📖 使い方"):
    st.markdown("""
    ## 🎬 動画字幕生成
    1. **言語設定**: 元の言語と翻訳先言語を選択
    2. **動画アップロード**: 対応形式の動画ファイルを選択
    3. **実行**: 「字幕生成開始」ボタンをクリック
    4. **ダウンロード**: 生成された字幕付き動画をダウンロード
    
    ## 🎤 リアルタイム音声認識
    1. **翻訳先言語選択**: 翻訳したい言語を選択
    2. **録音開始**: マイクで音声をキャプチャ開始
    3. **録音停止**: 必要に応じて停止
    4. **結果確認**: リアルタイムで文字起こし・翻訳結果を表示
    
    **対応形式**: MP4, MOV, AVI, MKV
    **処理時間**: 動画の長さに応じて数分〜数十分
    """)

# 注意事項
with st.expander("⚠️ 注意事項"):
    st.markdown("""
    - **APIコスト**: 長時間の動画・音声は料金が高くなる可能性があります
    - **処理時間**: 動画の長さに比例して時間がかかります
    - **マイク許可**: リアルタイム音声認識にはマイクアクセス許可が必要です
    - **精度**: 音質や話し方により認識精度が変わります
    - **ネットワーク**: インターネット接続が必要です
    """)
