import os
import subprocess
import tempfile
import streamlit as st
from pathlib import Path
import json
import shutil
from utils.transcription import create_srt_content, format_timestamp, cleanup_temp_files

def check_ffmpeg():
    """FFmpegの存在確認"""
    if not shutil.which('ffmpeg'):
        raise RuntimeError("FFmpegがインストールされていません。'brew install ffmpeg'でインストールしてください。")
    if not shutil.which('ffprobe'):
        raise RuntimeError("FFprobeがインストールされていません。'brew install ffmpeg'でインストールしてください。")

def extract_audio(video_path, output_format='wav'):
    """動画ファイルから音声を抽出"""
    try:
        check_ffmpeg()
        
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"動画ファイルが見つかりません: {video_path}")
        
        # 出力ファイル名生成
        output_path = tempfile.NamedTemporaryFile(
            delete=False,
            suffix=f".{output_format}",
            prefix="extracted_audio_"
        ).name
        
        # FFmpegで音声抽出
        cmd = [
            'ffmpeg', '-i', video_path,
            '-acodec', 'pcm_s16le',  # WAV形式
            '-ar', '16000',          # 16kHzサンプリングレート
            '-ac', '1',              # モノラル
            '-y',                    # 上書き確認なし
            output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode, cmd, result.stderr
            )
        
        # 出力ファイルの確認
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise RuntimeError("音声抽出に失敗しました（出力ファイルが空または存在しません）")
        
        return output_path
        
    except subprocess.CalledProcessError as e:
        error_msg = f"FFmpeg音声抽出エラー: {e.stderr if e.stderr else str(e)}"
        st.error(error_msg)
        raise RuntimeError(error_msg)
    except Exception as e:
        st.error(f"音声抽出エラー: {str(e)}")
        raise

def get_video_info(video_path):
    """動画ファイルの詳細情報を取得"""
    try:
        check_ffmpeg()
        
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"動画ファイルが見つかりません: {video_path}")
        
        # FFprobeで動画情報取得
        cmd = [
            'ffprobe', '-v', 'quiet', '-print_format', 'json',
            '-show_format', '-show_streams', video_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        probe_data = json.loads(result.stdout)
        
        # 動画ストリーム情報
        video_streams = [s for s in probe_data.get('streams', []) if s.get('codec_type') == 'video']
        audio_streams = [s for s in probe_data.get('streams', []) if s.get('codec_type') == 'audio']
        
        video_info = {
            'file_size': os.path.getsize(video_path),
            'file_size_mb': os.path.getsize(video_path) / (1024 * 1024)
        }
        
        # フォーマット情報
        format_info = probe_data.get('format', {})
        duration = float(format_info.get('duration', 0))
        
        video_info.update({
            'duration': duration,
            'format_name': format_info.get('format_name', 'unknown'),
            'bit_rate': int(format_info.get('bit_rate', 0))
        })
        
        # 動画ストリーム情報
        if video_streams:
            video_stream = video_streams[0]
            video_info.update({
                'width': int(video_stream.get('width', 0)),
                'height': int(video_stream.get('height', 0)),
                'video_codec': video_stream.get('codec_name', 'unknown'),
                'pixel_format': video_stream.get('pix_fmt', 'unknown')
            })
            
            # フレームレート計算
            r_frame_rate = video_stream.get('r_frame_rate', '0/1')
            if '/' in r_frame_rate:
                num, den = map(int, r_frame_rate.split('/'))
                fps = num / den if den != 0 else 0
            else:
                fps = float(r_frame_rate)
            video_info['fps'] = fps
        
        # 音声ストリーム情報
        if audio_streams:
            audio_stream = audio_streams[0]
            video_info.update({
                'audio_codec': audio_stream.get('codec_name', 'unknown'),
                'sample_rate': int(audio_stream.get('sample_rate', 0)),
                'channels': int(audio_stream.get('channels', 0))
            })
        
        # 総時間をフォーマット
        if duration > 0:
            hours = int(duration // 3600)
            minutes = int((duration % 3600) // 60)
            seconds = int(duration % 60)
            video_info['duration_formatted'] = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            video_info['duration_formatted'] = "00:00:00"
        
        return video_info
        
    except subprocess.CalledProcessError as e:
        st.error(f"動画情報取得エラー: {e.stderr if e.stderr else str(e)}")
        return {}
    except json.JSONDecodeError as e:
        st.error(f"動画情報解析エラー: {str(e)}")
        return {}
    except Exception as e:
        st.error(f"動画情報取得エラー: {str(e)}")
        return {}

def create_srt_file(transcription_result, output_path=None):
    """文字起こし結果からSRTファイルを作成"""
    try:
        if output_path is None:
            output_path = tempfile.NamedTemporaryFile(
                delete=False,
                suffix=".srt",
                prefix="subtitles_"
            ).name
        
        # SRT内容生成
        if 'segments' in transcription_result and transcription_result['segments']:
            srt_content = create_srt_content(transcription_result['segments'])
        else:
            # セグメント情報がない場合は全体テキストで単一エントリ作成
            text = transcription_result.get('text', '')
            if text:
                srt_content = "1\n00:00:00,000 --> 00:10:00,000\n" + text
            else:
                srt_content = ""
        
        if not srt_content:
            raise ValueError("SRT内容が空です")
        
        # ファイル書き込み
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(srt_content)
        
        # ファイルが正常に作成されたかチェック
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise RuntimeError("SRTファイルの作成に失敗しました")
        
        return output_path
        
    except Exception as e:
        st.error(f"SRTファイル作成エラー: {str(e)}")
        raise

def burn_subtitles(video_path, srt_path, font_size=24, position="bottom", color="white"):
    """動画に字幕を焼き込み"""
    try:
        check_ffmpeg()
        
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"動画ファイルが見つかりません: {video_path}")
        
        if not os.path.exists(srt_path):
            raise FileNotFoundError(f"SRTファイルが見つかりません: {srt_path}")
        
        # 出力ファイル名生成
        output_path = tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".mp4",
            prefix="subtitled_"
        ).name
        
        # 字幕位置設定
        position_map = {
            "bottom": "Alignment=2",  # 下部中央
            "center": "Alignment=5",  # 中央
            "top": "Alignment=8"      # 上部中央
        }
        alignment = position_map.get(position, "Alignment=2")
        
        # 文字色設定
        color_map = {
            "white": "&Hffffff",
            "yellow": "&H00ffff",
            "blue": "&Hff0000",
            "green": "&H00ff00"
        }
        subtitle_color = color_map.get(color, "&Hffffff")
        
        # 字幕スタイル設定
        subtitle_style = (
            f"FontSize={font_size},"
            f"PrimaryColour={subtitle_color},"
            f"OutlineColour=&H000000,"
            f"BackColour=&H80000000,"
            f"Outline=2,"
            f"Shadow=1,"
            f"{alignment}"
        )
        
        # SRTファイルのパスをエスケープ
        escaped_srt_path = srt_path.replace(':', '\\:').replace(',', '\\,')
        
        # FFmpegで字幕焼き込み
        cmd = [
            'ffmpeg', '-i', video_path,
            '-vf', f"subtitles={escaped_srt_path}:force_style='{subtitle_style}'",
            '-c:v', 'libx264',
            '-c:a', 'aac',
            '-crf', '23',        # 品質設定
            '-preset', 'medium', # エンコード速度
            '-y',                # 上書き確認なし
            output_path
        ]
        
        # 進行状況表示用
        progress_placeholder = st.empty()
        status_placeholder = st.empty()
        
        status_placeholder.info("字幕を動画に焼き込み中...")
        
        # FFmpegプロセス実行
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # プロセス完了まで待機
        stdout, stderr = process.communicate()
        
        if process.returncode != 0:
            raise subprocess.CalledProcessError(
                process.returncode, cmd, stderr
            )
        
        # 出力ファイルの確認
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise RuntimeError("字幕焼き込みに失敗しました（出力ファイルが空または存在しません）")
        
        progress_placeholder.empty()
        status_placeholder.empty()
        
        return output_path
        
    except subprocess.CalledProcessError as e:
        error_msg = f"FFmpeg字幕焼き込みエラー: {e.stderr if e.stderr else str(e)}"
        st.error(error_msg)
        raise RuntimeError(error_msg)
    except Exception as e:
        st.error(f"字幕焼き込みエラー: {str(e)}")
        raise

def compress_video(video_path, quality='medium'):
    """動画を圧縮"""
    try:
        check_ffmpeg()
        
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"動画ファイルが見つかりません: {video_path}")
        
        # 出力ファイル名生成
        output_path = tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".mp4",
            prefix="compressed_"
        ).name
        
        # 品質設定
        quality_map = {
            'high': {'crf': 18, 'preset': 'slow'},
            'medium': {'crf': 23, 'preset': 'medium'},
            'low': {'crf': 28, 'preset': 'fast'}
        }
        settings = quality_map.get(quality, quality_map['medium'])
        
        # FFmpegで圧縮
        cmd = [
            'ffmpeg', '-i', video_path,
            '-c:v', 'libx264',
            '-c:a', 'aac',
            '-crf', str(settings['crf']),
            '-preset', settings['preset'],
            '-y',
            output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        
        # 出力ファイルの確認
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise RuntimeError("動画圧縮に失敗しました")
        
        return output_path
        
    except subprocess.CalledProcessError as e:
        st.error(f"動画圧縮エラー: {e.stderr if e.stderr else str(e)}")
        raise
    except Exception as e:
        st.error(f"動画圧縮エラー: {str(e)}")
        raise

def convert_video_format(video_path, output_format='mp4'):
    """動画形式を変換"""
    try:
        check_ffmpeg()
        
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"動画ファイルが見つかりません: {video_path}")
        
        # 出力ファイル名生成
        output_path = tempfile.NamedTemporaryFile(
            delete=False,
            suffix=f".{output_format}",
            prefix="converted_"
        ).name
        
        # FFmpegで形式変換
        cmd = [
            'ffmpeg', '-i', video_path,
            '-c:v', 'libx264',
            '-c:a', 'aac',
            '-y',
            output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        
        # 出力ファイルの確認
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise RuntimeError("動画形式変換に失敗しました")
        
        return output_path
        
    except subprocess.CalledProcessError as e:
        st.error(f"動画形式変換エラー: {e.stderr if e.stderr else str(e)}")
        raise
    except Exception as e:
        st.error(f"動画形式変換エラー: {str(e)}")
        raise

def validate_video_file(video_path):
    """動画ファイルの妥当性チェック"""
    try:
        if not os.path.exists(video_path):
            return False, "ファイルが見つかりません"
        
        file_size = os.path.getsize(video_path)
        if file_size == 0:
            return False, "ファイルが空です"
        
        if file_size > 5 * 1024 * 1024 * 1024:  # 5GB
            return False, "ファイルサイズが大きすぎます（最大5GB）"
        
        # 動画ファイル情報を取得してチェック
        video_info = get_video_info(video_path)
        
        if not video_info:
            return False, "動画ファイルの読み込みに失敗しました"
        
        duration = video_info.get('duration', 0)
        
        if duration <= 0:
            return False, "有効な動画ファイルではありません"
        
        if duration < 1:
            return False, "動画が短すぎます（最低1秒必要）"
        
        if duration > 24 * 60 * 60:  # 24時間
            return False, "動画が長すぎます（最大24時間）"
        
        return True, "OK"
        
    except Exception as e:
        return False, f"動画ファイル検証エラー: {str(e)}"

def extract_video_thumbnail(video_path, time_offset=10):
    """動画からサムネイル画像を抽出"""
    try:
        check_ffmpeg()
        
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"動画ファイルが見つかりません: {video_path}")
        
        # 動画の長さを取得
        video_info = get_video_info(video_path)
        duration = video_info.get('duration', 0)
        
        # オフセット時間を調整（動画の長さより短く）
        actual_offset = min(time_offset, duration / 2) if duration > 0 else 0
        
        # 出力ファイル名生成
        output_path = tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".jpg",
            prefix="thumbnail_"
        ).name
        
        # FFmpegでサムネイル抽出
        cmd = [
            'ffmpeg', '-i', video_path,
            '-ss', str(actual_offset),
            '-vframes', '1',
            '-f', 'image2',
            '-c:v', 'mjpeg',
            '-y',
            output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        
        # 出力ファイルの確認
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            st.warning("サムネイル抽出に失敗しました")
            return None
        
        return output_path
        
    except subprocess.CalledProcessError as e:
        st.warning(f"サムネイル抽出エラー: {e.stderr if e.stderr else str(e)}")
        return None
    except Exception as e:
        st.warning(f"サムネイル抽出エラー: {str(e)}")
        return None

def estimate_processing_time(video_path):
    """動画処理時間を推定"""
    try:
        video_info = get_video_info(video_path)
        duration = video_info.get('duration', 0)
        file_size_mb = video_info.get('file_size_mb', 0)
        
        if duration == 0:
            return {
                'audio_extraction': 30,
                'transcription': 60,
                'subtitle_burn': 120,
                'total': 210,
                'total_formatted': "3分30秒",
                'error': "動画情報を取得できませんでした"
            }
        
        # 推定計算（経験的な値）
        audio_extraction_time = max(duration * 0.1, 10)    # 動画長の10%、最低10秒
        transcription_time = max(duration * 0.25, 30)      # 動画長の25%、最低30秒
        subtitle_burn_time = max(duration * 0.5, 60)       # 動画長の50%、最低60秒
        
        # ファイルサイズによる補正
        size_factor = min(file_size_mb / 100, 3)  # 最大3倍
        size_factor = max(size_factor, 0.5)       # 最低0.5倍
        
        total_estimated_time = (audio_extraction_time + transcription_time + subtitle_burn_time) * size_factor
        
        # フォーマット
        minutes = int(total_estimated_time // 60)
        seconds = int(total_estimated_time % 60)
        
        return {
            'audio_extraction': audio_extraction_time * size_factor,
            'transcription': transcription_time,
            'subtitle_burn': subtitle_burn_time * size_factor,
            'total': total_estimated_time,
            'total_formatted': f"{minutes}分{seconds}秒"
        }
        
    except Exception as e:
        return {
            'audio_extraction': 30,
            'transcription': 60,
            'subtitle_burn': 120,
            'total': 210,
            'total_formatted': "3分30秒",
            'error': str(e)
        }

def check_video_codecs(video_path):
    """動画のコーデック情報をチェック"""
    try:
        video_info = get_video_info(video_path)
        
        video_codec = video_info.get('video_codec', 'unknown')
        audio_codec = video_info.get('audio_codec', 'unknown')
        
        # サポートされているコーデックかチェック
        supported_video_codecs = ['h264', 'libx264', 'mpeg4', 'xvid', 'avi']
        supported_audio_codecs = ['aac', 'mp3', 'pcm_s16le', 'ac3']
        
        codec_status = {
            'video_supported': video_codec.lower() in supported_video_codecs,
            'audio_supported': audio_codec.lower() in supported_audio_codecs,
            'video_codec': video_codec,
            'audio_codec': audio_codec,
            'needs_conversion': False
        }
        
        # 変換が必要かどうか判定
        if not codec_status['video_supported'] or not codec_status['audio_supported']:
            codec_status['needs_conversion'] = True
        
        return codec_status
        
    except Exception as e:
        return {
            'video_supported': False,
            'audio_supported': False,
            'video_codec': 'unknown',
            'audio_codec': 'unknown',
            'needs_conversion': True,
            'error': str(e)
        }

def get_video_resolution_info(video_path):
    """動画の解像度情報を取得"""
    try:
        video_info = get_video_info(video_path)
        
        width = video_info.get('width', 0)
        height = video_info.get('height', 0)
        
        if width == 0 or height == 0:
            return {
                'width': 0,
                'height': 0,
                'resolution_name': 'unknown',
                'aspect_ratio': 'unknown'
            }
        
        # 一般的な解像度名を判定
        resolution_names = {
            (1920, 1080): 'Full HD (1080p)',
            (1280, 720): 'HD (720p)',
            (854, 480): 'SD (480p)',
            (640, 360): '360p',
            (426, 240): '240p',
            (3840, 2160): '4K UHD',
            (2560, 1440): '2K QHD'
        }
        
        resolution_name = resolution_names.get((width, height), f'{width}x{height}')
        
        # アスペクト比計算
        try:
            from math import gcd
            common_divisor = gcd(width, height)
            aspect_w = width // common_divisor
            aspect_h = height // common_divisor
            aspect_ratio = f'{aspect_w}:{aspect_h}'
        except:
            aspect_ratio = f'{width/height:.2f}:1'
        
        return {
            'width': width,
            'height': height,
            'resolution_name': resolution_name,
            'aspect_ratio': aspect_ratio
        }
        
    except Exception as e:
        return {
            'width': 0,
            'height': 0,
            'resolution_name': 'unknown',
            'aspect_ratio': 'unknown',
            'error': str(e)
        }
