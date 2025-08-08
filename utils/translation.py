import os
import anthropic
import streamlit as st
import time
from typing import Dict, List, Optional, Union
import re

def get_anthropic_client():
    """Anthropic クライアントを取得"""
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY が設定されていません")
    return anthropic.Anthropic(api_key=api_key)

def translate_text(text: str, translation_option: str) -> str:
    """
    テキストを翻訳
    
    Args:
        text (str): 翻訳するテキスト
        translation_option (str): 翻訳オプション
    
    Returns:
        str: 翻訳されたテキスト
    """
    try:
        if not text or not text.strip():
            return text
        
        # 翻訳オプションの解析
        translation_map = {
            "日本語→英語": {"source": "日本語", "target": "英語"},
            "英語→日本語": {"source": "英語", "target": "日本語"},
            "日本語→中国語": {"source": "日本語", "target": "中国語"},
            "日本語→韓国語": {"source": "日本語", "target": "韓国語"},
            "翻訳なし": None
        }
        
        if translation_option not in translation_map or translation_map[translation_option] is None:
            return text
        
        config = translation_map[translation_option]
        source_lang = config["source"]
        target_lang = config["target"]
        
        # テキストの前処理
        cleaned_text = clean_transcription_text(text)
        
        # 長いテキストの場合は分割して処理
        if len(cleaned_text) > 4000:
            return translate_long_text(cleaned_text, source_lang, target_lang)
        
        # Claude APIで翻訳
        translated_text = translate_chunk(cleaned_text, source_lang, target_lang)
        
        return translated_text
        
    except Exception as e:
        st.error(f"翻訳エラー: {str(e)}")
        return text  # エラー時は原文を返す

def translate_long_text(text: str, source_lang: str, target_lang: str) -> str:
    """
    長いテキストを分割して翻訳
    
    Args:
        text (str): 翻訳するテキスト
        source_lang (str): 元言語
        target_lang (str): 対象言語
    
    Returns:
        str: 翻訳されたテキスト
    """
    try:
        # テキストを文単位で分割
        sentences = split_text_into_sentences(text)
        translated_sentences = []
        
        current_chunk = ""
        chunk_size = 3000  # 安全なチャンクサイズ
        
        progress_placeholder = st.empty()
        total_sentences = len(sentences)
        processed_sentences = 0
        
        for sentence in sentences:
            # チャンクサイズチェック
            if len(current_chunk) + len(sentence) < chunk_size:
                current_chunk += sentence
            else:
                # 現在のチャンクを翻訳
                if current_chunk.strip():
                    translated_chunk = translate_chunk(current_chunk.strip(), source_lang, target_lang)
                    translated_sentences.append(translated_chunk)
                
                # 進行状況表示
                processed_sentences += current_chunk.count('。') + current_chunk.count('.') + 1
                progress = min(processed_sentences / total_sentences, 1.0)
                progress_placeholder.progress(progress, f"翻訳中... {processed_sentences}/{total_sentences}")
                
                # 新しいチャンク開始
                current_chunk = sentence
        
        # 残りのチャンクを翻訳
        if current_chunk.strip():
            translated_chunk = translate_chunk(current_chunk.strip(), source_lang, target_lang)
            translated_sentences.append(translated_chunk)
        
        progress_placeholder.empty()
        
        return ''.join(translated_sentences)
        
    except Exception as e:
        st.error(f"長文翻訳エラー: {str(e)}")
        return text

def translate_chunk(chunk: str, source_lang: str, target_lang: str) -> str:
    """
    テキストチャンクを翻訳
    
    Args:
        chunk (str): 翻訳するテキストチャンク
        source_lang (str): 元言語
        target_lang (str): 対象言語
    
    Returns:
        str: 翻訳されたテキスト
    """
    try:
        if not chunk or not chunk.strip():
            return chunk
        
        client = get_anthropic_client()
        prompt = create_translation_prompt(chunk, source_lang, target_lang)
        
        response = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=4000,
            temperature=0,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        if not response.content:
            return chunk
        
        translated_text = response.content[0].text.strip()
        
        # 不要な前置きを除去
        translated_text = clean_translation_output(translated_text)
        
        # API制限を考慮した待機
        time.sleep(0.5)
        
        return translated_text
        
    except Exception as e:
        st.warning(f"チャンク翻訳エラー: {str(e)}")
        return chunk

def create_translation_prompt(text: str, source_lang: str, target_lang: str) -> str:
    """
    翻訳用プロンプトを作成
    
    Args:
        text (str): 翻訳するテキスト
        source_lang (str): 元言語
        target_lang (str): 対象言語
    
    Returns:
        str: 翻訳プロンプト
    """
    prompt_templates = {
        ("日本語", "英語"): f"""
以下の日本語テキストを自然な英語に翻訳してください。
音声認識の結果なので、文脈を考慮して適切に翻訳してください。
専門用語や固有名詞は適切に処理し、読みやすい英語にしてください。

翻訳するテキスト:
{text}

翻訳結果のみを出力してください。前置きや説明は不要です。
""",
        ("英語", "日本語"): f"""
以下の英語テキストを自然な日本語に翻訳してください。
音声認識の結果なので、文脈を考慮して適切に翻訳してください。
敬語や丁寧語を適切に使用し、読みやすい日本語にしてください。

翻訳するテキスト:
{text}

翻訳結果のみを出力してください。前置きや説明は不要です。
""",
        ("日本語", "中国語"): f"""
以下の日本語テキストを自然な中国語（簡体字）に翻訳してください。
音声認識の結果なので、文脈を考慮して適切に翻訳してください。
中国語として自然で読みやすい表現にしてください。

翻訳するテキスト:
{text}

翻訳結果のみを出力してください。前置きや説明は不要です。
""",
        ("日本語", "韓国語"): f"""
以下の日本語テキストを自然な韓国語に翻訳してください。
音声認識の結果なので、文脈を考慮して適切に翻訳してください。
韓国語として自然で読みやすい表現にしてください。

翻訳するテキスト:
{text}

翻訳結果のみを出力してください。前置きや説明は不要です。
"""
    }
    
    return prompt_templates.get((source_lang, target_lang), f"""
Translate the following {source_lang} text to {target_lang}. 
This is a result of speech recognition, so please consider the context and translate appropriately.

Text to translate:
{text}

Please provide only the translation without any explanations or preambles.
""")

def translate_segments(segments: List[Dict], translation_option: str) -> List[Dict]:
    """
    セグメントリストを翻訳
    
    Args:
        segments (List[Dict]): 文字起こしセグメント
        translation_option (str): 翻訳オプション
    
    Returns:
        List[Dict]: 翻訳されたセグメント
    """
    try:
        if translation_option == "翻訳なし" or not segments:
            return segments
        
        translated_segments = []
        
        # 各セグメントを個別に翻訳
        progress_placeholder = st.empty()
        total_segments = len(segments)
        
        for i, segment in enumerate(segments):
            try:
                # 進行状況表示
                progress = (i + 1) / total_segments
                progress_placeholder.progress(progress, f"セグメント翻訳中... {i+1}/{total_segments}")
                
                original_text = segment.get('text', '')
                if original_text.strip():
                    translated_text = translate_text(original_text, translation_option)
                else:
                    translated_text = original_text
                
                # 新しいセグメントを作成
                new_segment = segment.copy()
                new_segment['text'] = translated_text
                new_segment['original_text'] = original_text  # 元のテキストも保持
                translated_segments.append(new_segment)
                
            except Exception as e:
                st.warning(f"セグメント {i+1} の翻訳エラー: {str(e)}")
                # エラー時は元のセグメントを保持
                translated_segments.append(segment)
        
        progress_placeholder.empty()
        
        return translated_segments
        
    except Exception as e:
        st.error(f"セグメント翻訳エラー: {str(e)}")
        return segments

def detect_source_language(text: str) -> str:
    """
    テキストの言語を検出
    
    Args:
        text (str): 検出するテキスト
    
    Returns:
        str: 検出された言語
    """
    try:
        if not text or not text.strip():
            return "unknown"
        
        # 各言語の文字数をカウント
        japanese_chars = count_japanese_chars(text)
        chinese_chars = count_chinese_chars(text)
        korean_chars = count_korean_chars(text)
        english_chars = count_english_chars(text)
        
        total_chars = len(re.sub(r'\s+', '', text))
        
        if total_chars == 0:
            return "unknown"
        
        # 比率計算
        ratios = {
            "日本語": japanese_chars / total_chars,
            "中国語": (chinese_chars / total_chars) * 0.8,  # 日本語と区別するため重みを下げる
            "韓国語": korean_chars / total_chars,
            "英語": english_chars / total_chars
        }
        
        # 最も高い比率の言語を返す
        detected_lang = max(ratios, key=ratios.get)
        
        # 閾値チェック
        if ratios[detected_lang] < 0.1:
            return "unknown"
        
        return detected_lang
        
    except Exception as e:
        st.warning(f"言語検出エラー: {str(e)}")
        return "unknown"

def count_japanese_chars(text: str) -> int:
    """日本語文字数をカウント"""
    return sum(1 for char in text if
               '\u3040' <= char <= '\u309F' or  # ひらがな
               '\u30A0' <= char <= '\u30FF' or  # カタカナ
               '\u4E00' <= char <= '\u9FAF')    # 漢字

def count_chinese_chars(text: str) -> int:
    """中国語文字数をカウント（漢字のみ、日本語と重複あり）"""
    return sum(1 for char in text if '\u4E00' <= char <= '\u9FAF')

def count_korean_chars(text: str) -> int:
    """韓国語文字数をカウント"""
    return sum(1 for char in text if '\uAC00' <= char <= '\uD7AF')

def count_english_chars(text: str) -> int:
    """英語文字数をカウント"""
    return sum(1 for char in text if char.isalpha() and ord(char) < 128)

def get_supported_translation_pairs():
    """
    サポートされている翻訳ペアを取得
    
    Returns:
        List[str]: 翻訳オプションのリスト
    """
    return [
        "翻訳なし",
        "日本語→英語",
        "英語→日本語",
        "日本語→中国語",
        "日本語→韓国語"
    ]

def estimate_translation_time(text: str) -> float:
    """
    翻訳時間を推定
    
    Args:
        text (str): 翻訳するテキスト
    
    Returns:
        float: 推定時間（秒）
    """
    try:
        if not text:
            return 5
        
        # 文字数ベースの推定
        char_count = len(text)
        
        # 基本時間：1000文字あたり10秒
        base_time = (char_count / 1000) * 10
        
        # チャンク数による補正
        num_chunks = max(1, char_count // 3000)
        chunk_overhead = num_chunks * 2  # チャンクあたり2秒のオーバーヘッド
        
        # 最終推定時間
        estimated_time = base_time + chunk_overhead
        
        # 最低時間：5秒、最大時間：600秒（10分）
        estimated_time = max(min(estimated_time, 600), 5)
        
        return estimated_time
        
    except:
        return 30  # デフォルト30秒

def format_translation_result(original_text: str, translated_text: str, source_lang: str, target_lang: str) -> Dict:
    """
    翻訳結果をフォーマット
    
    Args:
        original_text (str): 元のテキスト
        translated_text (str): 翻訳されたテキスト
        source_lang (str): 元言語
        target_lang (str): 対象言語
    
    Returns:
        Dict: フォーマットされた翻訳結果
    """
    return {
        'original': {
            'text': original_text,
            'language': source_lang,
            'char_count': len(original_text)
        },
        'translated': {
            'text': translated_text,
            'language': target_lang,
            'char_count': len(translated_text)
        },
        'metadata': {
            'translation_pair': f"{source_lang}→{target_lang}",
            'timestamp': time.time(),
            'success': True
        }
    }

def validate_translation_request(text: str, translation_option: str) -> tuple:
    """
    翻訳リクエストの妥当性をチェック
    
    Args:
        text (str): 翻訳するテキスト
        translation_option (str): 翻訳オプション
    
    Returns:
        tuple: (is_valid, error_message)
    """
    try:
        # テキストの長さチェック
        if not text or not text.strip():
            return False, "翻訳するテキストが空です"
        
        if len(text) > 100000:  # 100,000文字制限
            return False, "テキストが長すぎます（最大100,000文字）"
        
        # 翻訳オプションチェック
        supported_options = get_supported_translation_pairs()
        if translation_option not in supported_options:
            return False, f"サポートされていない翻訳オプションです: {translation_option}"
        
        # API キーチェック
        if translation_option != "翻訳なし":
            if not os.getenv('ANTHROPIC_API_KEY'):
                return False, "Anthropic API キーが設定されていません"
        
        return True, "OK"
        
    except Exception as e:
        return False, f"翻訳リクエスト検証エラー: {str(e)}"

def clean_transcription_text(text: str) -> str:
    """
    文字起こしテキストをクリーニング
    
    Args:
        text (str): クリーニングするテキスト
    
    Returns:
        str: クリーニングされたテキスト
    """
    try:
        if not text:
            return text
        
        # 余分な空白を削除
        cleaned_text = re.sub(r'\s+', ' ', text)
        
        # 重複する句読点を削除
        cleaned_text = re.sub(r'[。]{2,}', '。', cleaned_text)
        cleaned_text = re.sub(r'[、]{2,}', '、', cleaned_text)
        cleaned_text = re.sub(r'[？]{2,}', '？', cleaned_text)
        cleaned_text = re.sub(r'[！]{2,}', '！', cleaned_text)
        cleaned_text = re.sub(r'[\.]{2,}', '.', cleaned_text)
        cleaned_text = re.sub(r'[,]{2,}', ',', cleaned_text)
        cleaned_text = re.sub(r'[\?]{2,}', '?', cleaned_text)
        cleaned_text = re.sub(r'[!]{2,}', '!', cleaned_text)
        
        # 改行の正規化
        cleaned_text = re.sub(r'\n+', '\n', cleaned_text)
        
        # 先頭と末尾の空白を削除
        cleaned_text = cleaned_text.strip()
        
        return cleaned_text
        
    except Exception as e:
        st.warning(f"テキストクリーニングエラー: {str(e)}")
        return text

def clean_translation_output(translated_text: str) -> str:
    """
    翻訳出力をクリーニング
    
    Args:
        translated_text (str): 翻訳された生テキスト
    
    Returns:
        str: クリーニングされた翻訳テキスト
    """
    try:
        if not translated_text:
            return translated_text
        
        # 一般的な前置きパターンを除去
        prefixes_to_remove = [
            r'^翻訳[:：]\s*',
            r'^Translation[:：]\s*',
            r'^翻訳結果[:：]\s*',
            r'^結果[:：]\s*',
            r'^訳[:：]\s*',
            r'^以下が翻訳です[:：]\s*',
            r'^翻訳は以下の通りです[:：]\s*'
        ]
        
        for prefix in prefixes_to_remove:
            translated_text = re.sub(prefix, '', translated_text, flags=re.IGNORECASE)
        
        # 引用符の除去
        if translated_text.startswith('"') and translated_text.endswith('"'):
            translated_text = translated_text[1:-1]
        if translated_text.startswith('「') and translated_text.endswith('」'):
            translated_text = translated_text[1:-1]
        
        # 余分な空白を削除
        translated_text = translated_text.strip()
        
        return translated_text
        
    except Exception as e:
        st.warning(f"翻訳出力クリーニングエラー: {str(e)}")
        return translated_text

def split_text_into_sentences(text: str) -> List[str]:
    """
    テキストを文単位に分割
    
    Args:
        text (str): 分割するテキスト
    
    Returns:
        List[str]: 分割された文のリスト
    """
    try:
        if not text:
            return []
        
        # 日本語の句読点で分割
        sentences = re.split(r'[。！？\.\!\?]', text)
        
        # 空の文を除去し、句読点を復元
        result = []
        original_sentences = re.findall(r'[^。！？\.\!\?]*[。！？\.\!\?]?', text)
        
        for sentence in original_sentences:
            if sentence.strip():
                result.append(sentence)
        
        return result if result else [text]
        
    except Exception as e:
        st.warning(f"文分割エラー: {str(e)}")
        return [text]

def get_translation_quality_score(original_text: str, translated_text: str) -> Dict:
    """
    翻訳品質のスコアを計算（簡易版）
    
    Args:
        original_text (str): 元のテキスト
        translated_text (str): 翻訳されたテキスト
    
    Returns:
        Dict: 品質スコア情報
    """
    try:
        if not original_text or not translated_text:
            return {
                'score': 0,
                'details': {
                    'length_ratio': 0,
                    'content_preserved': False,
                    'structure_preserved': False
                }
            }
        
        # 長さの比率チェック（適切な翻訳は長さが大きく変わらない）
        length_ratio = len(translated_text) / len(original_text)
        length_score = 1.0 if 0.5 <= length_ratio <= 2.0 else 0.5
        
        # 内容の保持チェック（数字や固有名詞の保持）
        original_numbers = re.findall(r'\d+', original_text)
        translated_numbers = re.findall(r'\d+', translated_text)
        content_score = 1.0 if len(original_numbers) == len(translated_numbers) else 0.7
        
        # 構造の保持チェック（句読点の数の比較）
        original_punct = len(re.findall(r'[。！？\.\!\?]', original_text))
        translated_punct = len(re.findall(r'[。！？\.\!\?]', translated_text))
        structure_score = 1.0 if abs(original_punct - translated_punct) <= 2 else 0.8
        
        # 総合スコア
        total_score = (length_score + content_score + structure_score) / 3
        
        return {
            'score': round(total_score * 100),
            'details': {
                'length_ratio': round(length_ratio, 2),
                'content_preserved': len(original_numbers) == len(translated_numbers),
                'structure_preserved': abs(original_punct - translated_punct) <= 2,
                'length_score': round(length_score * 100),
                'content_score': round(content_score * 100),
                'structure_score': round(structure_score * 100)
            }
        }
        
    except Exception as e:
        return {
            'score': 50,
            'details': {
                'length_ratio': 1.0,
                'content_preserved': True,
                'structure_preserved': True,
                'error': str(e)
            }
        }

def batch_translate_texts(texts: List[str], translation_option: str) -> List[str]:
    """
    複数のテキストを一括翻訳
    
    Args:
        texts (List[str]): 翻訳するテキストのリスト
        translation_option (str): 翻訳オプション
    
    Returns:
        List[str]: 翻訳されたテキストのリスト
    """
    try:
        if not texts or translation_option == "翻訳なし":
            return texts
        
        translated_texts = []
        
        progress_placeholder = st.empty()
        total_texts = len(texts)
        
        for i, text in enumerate(texts):
            try:
                # 進行状況表示
                progress = (i + 1) / total_texts
                progress_placeholder.progress(progress, f"一括翻訳中... {i+1}/{total_texts}")
                
                if text.strip():
                    translated_text = translate_text(text, translation_option)
                    translated_texts.append(translated_text)
                else:
                    translated_texts.append(text)
                
            except Exception as e:
                st.warning(f"テキスト {i+1} の翻訳エラー: {str(e)}")
                translated_texts.append(text)  # エラー時は元のテキストを保持
        
        progress_placeholder.empty()
        
        return translated_texts
        
    except Exception as e:
        st.error(f"一括翻訳エラー: {str(e)}")
        return texts

def save_translation_cache(original_text: str, translated_text: str, translation_option: str):
    """
    翻訳キャッシュを保存（セッション内のみ）
    
    Args:
        original_text (str): 元のテキスト
        translated_text (str): 翻訳されたテキスト
        translation_option (str): 翻訳オプション
    """
    try:
        if 'translation_cache' not in st.session_state:
            st.session_state.translation_cache = {}
        
        cache_key = f"{hash(original_text)}_{translation_option}"
        st.session_state.translation_cache[cache_key] = {
            'translated_text': translated_text,
            'timestamp': time.time()
        }
        
        # キャッシュサイズ制限（最大100エントリ）
        if len(st.session_state.translation_cache) > 100:
            # 古いエントリを削除
            oldest_key = min(
                st.session_state.translation_cache.keys(),
                key=lambda k: st.session_state.translation_cache[k]['timestamp']
            )
            del st.session_state.translation_cache[oldest_key]
        
    except Exception as e:
        st.warning(f"翻訳キャッシュ保存エラー: {str(e)}")

def get_translation_cache(original_text: str, translation_option: str) -> Optional[str]:
    """
    翻訳キャッシュを取得
    
    Args:
        original_text (str): 元のテキスト
        translation_option (str): 翻訳オプション
    
    Returns:
        Optional[str]: キャッシュされた翻訳テキスト（なければNone）
    """
    try:
        if 'translation_cache' not in st.session_state:
            return None
        
        cache_key = f"{hash(original_text)}_{translation_option}"
        cache_entry = st.session_state.translation_cache.get(cache_key)
        
        if cache_entry:
            # 1時間以内のキャッシュのみ有効
            if time.time() - cache_entry['timestamp'] < 3600:
                return cache_entry['translated_text']
            else:
                # 期限切れのキャッシュを削除
                del st.session_state.translation_cache[cache_key]
        
        return None
        
    except Exception as e:
        st.warning(f"翻訳キャッシュ取得エラー: {str(e)}")
        return None

def clear_translation_cache():
    """翻訳キャッシュをクリア"""
    try:
        if 'translation_cache' in st.session_state:
            st.session_state.translation_cache.clear()
            st.success("翻訳キャッシュをクリアしました")
    except Exception as e:
        st.warning(f"翻訳キャッシュクリアエラー: {str(e)}")

def get_cache_statistics() -> Dict:
    """翻訳キャッシュの統計情報を取得"""
    try:
        if 'translation_cache' not in st.session_state:
            return {'cache_size': 0, 'oldest_entry': None, 'newest_entry': None}
        
        cache = st.session_state.translation_cache
        
        if not cache:
            return {'cache_size': 0, 'oldest_entry': None, 'newest_entry': None}
        
        timestamps = [entry['timestamp'] for entry in cache.values()]
        
        return {
            'cache_size': len(cache),
            'oldest_entry': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(min(timestamps))),
            'newest_entry': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(max(timestamps)))
        }
        
    except Exception as e:
        return {'cache_size': 0, 'oldest_entry': None, 'newest_entry': None, 'error': str(e)}
