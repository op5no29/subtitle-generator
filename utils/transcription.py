import os
import tempfile
import openai
import json
import time
from pathlib import Path
import streamlit as st
import subprocess
import io
import shutil

# OpenAI API設定
def get_openai_client():
    """OpenAI クライアントを取得"""
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        raise ValueError("OPENAI_API_KEY が設定されていません")
    return openai.OpenAI(api_key=api_key)

def check_ffmpeg():
    """FFmpegの存在確認（Streamlit Community Cloud対応）"""
    import os
    import subprocess
    
    # 環境変数で指定されたパスを優先
    ffmpeg_binary = os.environ.get('FFMPEG_BINARY', 'ffmpeg')
    ffprobe_binary = os.environ.get('FFPROBE_BINARY', 'ffprobe')
    
    # FFmpegとFFprobeの候補パス
    ffmpeg_candidates = [
        ffmpeg_binary,
        'ffmpeg',
        '/usr/bin/ffmpeg',
        '/usr/local/bin/ffmpeg',
        '/opt/conda/bin/ffmpeg',
        '/home/appuser/venv/bin/ffmpeg'
    ]
    
    ffprobe_candidates = [
        ffprobe_binary,
        'ffprobe',
        '/usr/bin/ffprobe',
        '/usr/local/bin/ffprobe',
        '/opt/conda/bin/ffprobe',
        '/home/appuser/venv/bin/ffprobe'
    ]
    
    # FFmpegチェック
    ffmpeg_found = False
    for candidate in ffmpeg_candidates:
        try:
            result = subprocess.run([candidate, '-version'],
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                os.environ['FFMPEG_BINARY'] = candidate
                ffmpeg_found = True
                break
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.CalledProcessError):
            continue
    
    # FFprobeチェック
    ffprobe_found = False
    for candidate in ffprobe_candidates:
        try:
            result = subprocess.run([candidate, '-version'],
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                os.environ['FFPROBE_BINARY'] = candidate
                ffprobe_found = True
                break
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.CalledProcessError):
            continue
    
    if not ffmpeg_found:
        raise RuntimeError("FFmpegが見つかりません。Streamlit Community Cloudでは通常利用可能です。")
    if not ffprobe_found:
        raise RuntimeError("FFprobeが見つかりません。Streamlit Community Cloudでは通常利用可能です。")

def get_audio_duration(file_path):
    """音声ファイルの長さを取得"""
    try:
        check_ffmpeg()
        result = subprocess.run([
            'ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
            '-of', 'csv=p=0', file_path
        ], capture_output=True, text=True, check=True)
        
        duration_str = result.stdout.strip()
        if not duration_str or duration_str == 'N/A' or duration_str == '':
            # FFprobeで取得できない場合は別の方法を試す
            st.warning(f"音声長取得: FFprobeで長さを取得できませんでした ({duration_str})")
            return estimate_duration_from_file_size(file_path)
        
        try:
            return float(duration_str)
        except ValueError:
            st.warning(f"音声長取得: 無効な形式 '{duration_str}'")
            return estimate_duration_from_file_size(file_path)
        
    except (subprocess.CalledProcessError, ValueError) as e:
        st.warning(f"音声長取得エラー: {str(e)}")
        return estimate_duration_from_file_size(file_path)

def estimate_duration_from_file_size(file_path):
    """ファイルサイズから音声長を推定"""
    try:
        file_size = os.path.getsize(file_path)
        # WAVファイルの場合の概算: 16kHz, 16bit, mono = 約32KB/秒
        estimated_duration = file_size / (16000 * 2)  # 大まかな推定
        estimated_duration = max(estimated_duration, 1.0)  # 最低1秒
        st.info(f"ファイルサイズから音声長を推定: 約{estimated_duration:.1f}秒")
        return estimated_duration
    except:
        return 10.0  # デフォルト10秒

def convert_audio_for_whisper(file_path):
    """Whisper用に音声を変換（16kHz, mono, WAV）"""
    try:
        check_ffmpeg()
        output_path = tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".wav",
            prefix="whisper_ready_"
        ).name
        
        # FFmpegで変換
        subprocess.run([
            'ffmpeg', '-i', file_path,
            '-acodec', 'pcm_s16le',  # WAV形式
            '-ar', '16000',          # 16kHzサンプリングレート
            '-ac', '1',              # モノラル
            '-y',                    # 上書き確認なし
            output_path
        ], capture_output=True, check=True)
        
        return output_path
        
    except subprocess.CalledProcessError as e:
        st.error(f"音声変換エラー: {str(e)}")
        return file_path
    except Exception as e:
        st.error(f"予期しないエラー: {str(e)}")
        return file_path

def split_audio_file(file_path, chunk_length_seconds=600):
    """大きな音声ファイルを分割（10分 = 600秒）"""
    try:
        duration = get_audio_duration(file_path)
        file_size = os.path.getsize(file_path)
        
        # ファイルサイズと長さの両方をチェック
        if file_size < 25 * 1024 * 1024 and duration < chunk_length_seconds:
            # 小さなファイルはそのまま変換のみ
            converted_file = convert_audio_for_whisper(file_path)
            return [converted_file]
        
        if duration <= 0:
            # 長さが不明の場合はファイルサイズで判断
            if file_size < 25 * 1024 * 1024:
                st.info("音声長が不明ですが、ファイルサイズが小さいため分割せずに処理します")
                converted_file = convert_audio_for_whisper(file_path)
                return [converted_file]
            else:
                st.warning("音声長が不明で大きなファイルです。時間ベースでなくサイズベースで分割します")
                return split_by_file_size(file_path)
        
        st.info(f"大きなファイル（{file_size/(1024*1024):.1f}MB, {duration/60:.1f}分）を分割処理します...")
        
        chunk_files = []
        num_chunks = int(duration // chunk_length_seconds) + 1
        
        for i in range(num_chunks):
            start_time = i * chunk_length_seconds
            if start_time >= duration:
                break
                
            output_path = tempfile.NamedTemporaryFile(
                delete=False,
                suffix=".wav",
                prefix=f"chunk_{i:03d}_"
            ).name
            
            # チャンクを抽出して変換
            subprocess.run([
                'ffmpeg', '-i', file_path,
                '-ss', str(start_time),
                '-t', str(chunk_length_seconds),
                '-acodec', 'pcm_s16le',
                '-ar', '16000',
                '-ac', '1',
                '-y',
                output_path
            ], capture_output=True, check=True)
            
            # ファイルが正常に作成されたかチェック
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                chunk_files.append(output_path)
            else:
                st.warning(f"チャンク {i+1} の作成に失敗しました")
        
        if not chunk_files:
            st.error("チャンク分割に失敗しました。元ファイルを使用します。")
            converted_file = convert_audio_for_whisper(file_path)
            return [converted_file]
        
        return chunk_files
        
    except Exception as e:
        st.error(f"音声ファイル分割エラー: {str(e)}")
        # エラー時は元ファイルを変換して返す
        converted_file = convert_audio_for_whisper(file_path)
        return [converted_file]

def split_by_file_size(file_path, max_chunk_size=20*1024*1024):
    """ファイルサイズベースで分割（フォールバック）"""
    try:
        st.info("時間情報が不明のため、ファイルサイズベースで分割します")
        file_size = os.path.getsize(file_path)
        
        if file_size <= max_chunk_size:
            converted_file = convert_audio_for_whisper(file_path)
            return [converted_file]
        
        # 簡単な実装：元ファイルのみ変換して返す
        # より複雑な分割は必要に応じて実装
        st.warning("大きなファイルですが、時間ベース分割ができません。そのまま処理を試行します。")
        converted_file = convert_audio_for_whisper(file_path)
        return [converted_file]
        
    except Exception as e:
        st.error(f"ファイルサイズベース分割エラー: {str(e)}")
        converted_file = convert_audio_for_whisper(file_path)
        return [converted_file]

def transcribe_audio_chunk(file_path, language=None):
    """音声チャンクを文字起こし"""
    try:
        client = get_openai_client()
        
        # ファイルサイズチェック（25MB制限）
        file_size = os.path.getsize(file_path)
        if file_size > 25 * 1024 * 1024:
            raise ValueError(f"ファイルサイズが大きすぎます: {file_size/(1024*1024):.1f}MB > 25MB")
        
        if file_size == 0:
            return {'text': '', 'segments': [], 'language': language or 'ja'}
        
        with open(file_path, 'rb') as audio_file:
            # Whisper APIで文字起こし
            response = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="verbose_json",
                language=language,
                temperature=0
            )
            
            # セグメント情報の取得
            segments = []
            if hasattr(response, 'segments') and response.segments:
                segments = [
                    {
                        'start': segment.start,
                        'end': segment.end,
                        'text': segment.text
                    }
                    for segment in response.segments
                ]
            
            return {
                'text': response.text or '',
                'segments': segments,
                'language': getattr(response, 'language', language or 'ja')
            }
            
    except Exception as e:
        st.error(f"文字起こしエラー: {str(e)}")
        return {'text': '', 'segments': [], 'language': language or 'ja'}

def transcribe_audio_file(file_path, language=None):
    """音声ファイル全体を文字起こし（大きなファイルは自動分割）"""
    try:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"ファイルが見つかりません: {file_path}")
        
        # 音声ファイルを分割
        chunk_files = split_audio_file(file_path)
        
        if len(chunk_files) == 1:
            # 単一ファイルの場合
            result = transcribe_audio_chunk(chunk_files[0], language)
            # 一時ファイルをクリーンアップ
            if chunk_files[0] != file_path:
                cleanup_temp_files(chunk_files[0])
            return result
        
        # 複数チャンクの処理
        all_text = []
        all_segments = []
        current_time_offset = 0
        
        progress_placeholder = st.empty()
        status_placeholder = st.empty()
        
        for i, chunk_file in enumerate(chunk_files):
            try:
                # 進行状況表示
                progress = (i + 1) / len(chunk_files)
                progress_placeholder.progress(progress, f"チャンク {i+1}/{len(chunk_files)} を処理中...")
                status_placeholder.info(f"処理中: チャンク {i+1}/{len(chunk_files)}")
                
                # チャンクを文字起こし
                chunk_result = transcribe_audio_chunk(chunk_file, language)
                
                if chunk_result['text']:
                    all_text.append(chunk_result['text'])
                
                # セグメントのタイムスタンプを調整
                if chunk_result['segments']:
                    for segment in chunk_result['segments']:
                        adjusted_segment = {
                            'start': segment['start'] + current_time_offset,
                            'end': segment['end'] + current_time_offset,
                            'text': segment['text']
                        }
                        all_segments.append(adjusted_segment)
                
                # 次のチャンクのためのオフセット計算（10分 = 600秒）
                current_time_offset += 600
                
            except Exception as e:
                st.warning(f"チャンク {i+1} の処理でエラー: {str(e)}")
                continue
            
            finally:
                # チャンクファイルを削除
                cleanup_temp_files(chunk_file)
        
        progress_placeholder.empty()
        status_placeholder.empty()
        
        if not all_text:
            st.warning("文字起こし結果が空です")
        
        return {
            'text': ' '.join(all_text),
            'segments': all_segments,
            'language': language or 'ja'
        }
        
    except Exception as e:
        st.error(f"音声ファイル文字起こしエラー: {str(e)}")
        return {'text': '', 'segments': [], 'language': language or 'ja'}

def format_timestamp(seconds):
    """秒をSRT形式のタイムスタンプに変換"""
    try:
        seconds = max(0, float(seconds))  # 負の値を防ぐ
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millisecs = int((seconds % 1) * 1000)
        
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millisecs:03d}"
    except (ValueError, TypeError):
        return "00:00:00,000"

def create_srt_content(segments):
    """セグメントからSRTファイル内容を生成"""
    if not segments:
        return ""
    
    srt_content = []
    
    for i, segment in enumerate(segments, 1):
        try:
            start_time = format_timestamp(segment.get('start', 0))
            end_time = format_timestamp(segment.get('end', 0))
            text = str(segment.get('text', '')).strip()
            
            if text:
                srt_content.append(f"{i}")
                srt_content.append(f"{start_time} --> {end_time}")
                srt_content.append(text)
                srt_content.append("")  # 空行
        except Exception as e:
            st.warning(f"セグメント {i} の処理エラー: {str(e)}")
            continue
    
    return '\n'.join(srt_content)

def transcribe_realtime(recording_config):
    """リアルタイム録音の文字起こし処理"""
    try:
        if not isinstance(recording_config, dict):
            raise ValueError("録音設定が無効です")
        
        start_time = recording_config.get('start_time', time.time())
        duration = time.time() - start_time
        
        # サンプルの文字起こし結果（実際の録音機能は別途実装が必要）
        sample_text = f"リアルタイム録音のテストです。録音時間は約{duration:.1f}秒でした。"
        
        return {
            'text': sample_text,
            'segments': [
                {
                    'start': 0.0,
                    'end': duration,
                    'text': sample_text
                }
            ],
            'language': 'ja',
            'duration': duration
        }
        
    except Exception as e:
        st.error(f"リアルタイム文字起こしエラー: {str(e)}")
        return {'text': '', 'segments': [], 'language': 'ja', 'duration': 0}

def cleanup_temp_files(*file_paths):
    """一時ファイルを安全に削除"""
    for file_path in file_paths:
        if file_path and os.path.exists(file_path):
            try:
                os.unlink(file_path)
            except Exception as e:
                st.warning(f"一時ファイル削除エラー: {file_path} - {str(e)}")

def validate_audio_file(file_path):
    """音声ファイルの妥当性チェック"""
    try:
        if not os.path.exists(file_path):
            return False, "ファイルが見つかりません"
        
        file_size = os.path.getsize(file_path)
        if file_size == 0:
            return False, "ファイルが空です"
        
        if file_size > 2 * 1024 * 1024 * 1024:  # 2GB
            return False, "ファイルサイズが大きすぎます（最大2GB）"
        
        # FFprobeで音声ファイルかチェック
        duration = get_audio_duration(file_path)
        if duration <= 0:
            return False, "有効な音声ファイルではありません"
        
        if duration < 1:
            return False, "音声が短すぎます（最低1秒必要）"
        
        if duration > 12 * 60 * 60:  # 12時間
            return False, "音声が長すぎます（最大12時間）"
        
        return True, "OK"
        
    except Exception as e:
        return False, f"音声ファイル検証エラー: {str(e)}"

def get_audio_info(file_path):
    """音声ファイルの詳細情報を取得"""
    try:
        check_ffmpeg()
        
        # 基本情報取得
        duration = get_audio_duration(file_path)
        file_size = os.path.getsize(file_path)
        
        # フォーマット情報取得
        result = subprocess.run([
            'ffprobe', '-v', 'quiet', '-show_entries',
            'stream=sample_rate,channels,codec_name',
            '-of', 'csv=p=0', file_path
        ], capture_output=True, text=True)
        
        format_info = result.stdout.strip().split(',')
        
        hours = int(duration // 3600)
        minutes = int((duration % 3600) // 60)
        seconds = int(duration % 60)
        
        return {
            'duration': duration,
            'duration_formatted': f"{hours:02d}:{minutes:02d}:{seconds:02d}",
            'sample_rate': int(format_info[0]) if len(format_info) > 0 and format_info[0].isdigit() else 0,
            'channels': int(format_info[1]) if len(format_info) > 1 and format_info[1].isdigit() else 0,
            'codec': format_info[2] if len(format_info) > 2 else 'unknown',
            'file_size': file_size,
            'file_size_mb': file_size / (1024 * 1024)
        }
        
    except Exception as e:
        return {
            'duration': 0,
            'duration_formatted': "00:00:00",
            'sample_rate': 0,
            'channels': 0,
            'codec': 'unknown',
            'file_size': os.path.getsize(file_path) if os.path.exists(file_path) else 0,
            'file_size_mb': 0,
            'error': str(e)
        }
