import streamlit as st
import os
from pydub import AudioSegment
from pydub.exceptions import CouldntDecodeError
import time
import concurrent.futures
import os
import tempfile
from pydub import AudioSegment
import asyncio
import psutil
import logging
from concurrent.futures import ThreadPoolExecutor
import subprocess
import mutagen
from mutagen.mp3 import MP3
from mutagen.wave import WAVE
from mutagen.m4a import M4A
import requests
import io

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
# 배경음악 목록 (실제 경로로 교체해야 함)
# 현재 스크립트의 디렉토리 경로

current_dir = os.path.dirname(os.path.abspath(__file__))

BACKGROUND_MUSIC = {
    "dream": "https://nadio-studio-open-fonts-metadata.s3.ap-northeast-2.amazonaws.com/audio/dream.mp3",
    "frost": "https://nadio-studio-open-fonts-metadata.s3.ap-northeast-2.amazonaws.com/audio/frost.mp3",
    "attunda": "https://nadio-studio-open-fonts-metadata.s3.ap-northeast-2.amazonaws.com/audio/attunda.mp3",
    "fyrsta": "https://nadio-studio-open-fonts-metadata.s3.ap-northeast-2.amazonaws.com/audio/fyrsta.mp3",
    "paris": "https://nadio-studio-open-fonts-metadata.s3.ap-northeast-2.amazonaws.com/audio/paris.mp3",
    "periwig": "https://nadio-studio-open-fonts-metadata.s3.ap-northeast-2.amazonaws.com/audio/periwig.mp3",
    "picnic": "https://nadio-studio-open-fonts-metadata.s3.ap-northeast-2.amazonaws.com/audio/picnic.mp3",
    "sitcom": "https://nadio-studio-open-fonts-metadata.s3.ap-northeast-2.amazonaws.com/audio/sitcom.mp3",
    "sky": "https://nadio-studio-open-fonts-metadata.s3.ap-northeast-2.amazonaws.com/audio/sky.mp3",
    "teatime": "https://nadio-studio-open-fonts-metadata.s3.ap-northeast-2.amazonaws.com/audio/teatime.mp3",
    "ukulele": "https://nadio-studio-open-fonts-metadata.s3.ap-northeast-2.amazonaws.com/audio/ukulele.mp3",
    "post": "https://nadio-studio-open-fonts-metadata.s3.ap-northeast-2.amazonaws.com/audio/post.mp3"

    # ... 나머지 음악 파일들도 같은 방식으로 추가 ...
}

# 배경음악 목록 생성
# BACKGROUND_MUSIC = {
#     file.split('.')[0]: os.path.join(bg_music_dir, file)
#     for file in os.listdir(bg_music_dir)
#     if file.endswith('.mp3')
# }
def check_audio_file(file_path):
    try:
        probe_command = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            file_path
        ]
        result = subprocess.run(probe_command, capture_output=True, text=True)
        return result.returncode == 0
    except Exception as e:
        logger.error(f"Error checking audio file: {str(e)}")
        return False

def get_audio_info(file_path):
    try:
        probe_command = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            file_path
        ]
        result = subprocess.run(probe_command, capture_output=True, text=True)
        if result.returncode == 0:
            import json
            data = json.loads(result.stdout)
            audio_stream = next((stream for stream in data['streams'] if stream['codec_type'] == 'audio'), None)
            if audio_stream:
                return {
                    "format": data['format']['format_name'],
                    "duration": float(data['format']['duration']),
                    "bit_rate": int(data['format']['bit_rate']) // 1000,
                    "sample_rate": int(audio_stream['sample_rate']),
                    "channels": audio_stream['channels']
                }
    except Exception as e:
        logger.error(f"Error getting audio info: {str(e)}")
    return None

def convert_to_mp3(input_file, output_file):
    try:
        command = [
            "ffmpeg",
            "-i", input_file,
            "-acodec", "libmp3lame",
            "-b:a", "192k",
            "-y",
            output_file
        ]
        subprocess.run(command, check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Error converting to MP3: {e.stderr}")
        return False

@st.cache_data()
def load_audio(url):
    try:
        response = requests.get(url)
        if response.status_code == 200:
            audio = AudioSegment.from_mp3(io.BytesIO(response.content))
            return audio
        else:
            st.error(f"Failed to download audio file. Status code: {response.status_code}")
            return None
    except Exception as e:
        st.error(f"Error loading audio: {str(e)}")
        return None


async def apply_background_music(main_audio, background_audio, fade_duration=10000):
    # 배경음악 준비
    bg_duration = len(background_audio)
    main_duration = len(main_audio)
    
    # 메인 오디오보다 배경음악이 짧으면 반복
    if bg_duration < main_duration:
        repetitions = -(-main_duration // bg_duration)  # 올림 나눗셈
        background_audio = background_audio * repetitions
    
    # 메인 오디오 길이에 맞게 배경음악 자르기
    background_audio = background_audio[:main_duration]
    
    # 전체 배경음악의 볼륨을 크게 낮춤 (예: 25% 볼륨)
    background_audio = background_audio - 12  # -12dB는 대략 25% 볼륨
    
    # 앞뒤 10초 부분의 볼륨을 원래 볼륨으로 설정 (확연한 차이를 위해)
    fade_in = background_audio[:fade_duration].fade_in(duration=fade_duration)
    fade_out = background_audio[-fade_duration:].fade_out(duration=fade_duration)
    
    # 페이드 인/아웃 효과를 적용한 배경음악 생성
    background_audio = (fade_in + 12) + background_audio[fade_duration:-fade_duration] + (fade_out + 12)
    
    # 배경음악과 메인 오디오 합치기
    result = background_audio.overlay(main_audio)
    
    return result

async def process_audio(input_file, background_url, progress_bar):
    try:
        main_audio = AudioSegment.from_file(input_file)
        if main_audio is None:
            st.error("Failed to load the main audio file. Please try a different file.")
            return None

        progress_bar.progress(20)

        background_audio = load_audio(background_url)
        if background_audio is None:
            st.error("Failed to load the background music. Please try a different file.")
            return None

        progress_bar.progress(40)

        result = await apply_background_music(main_audio, background_audio)

        progress_bar.progress(80)

        return result
    except Exception as e:
        logger.error(f"Error processing audio: {str(e)}")
        st.error(f"An error occurred while processing the audio: {str(e)}")
        return None

def main():
    st.title("Audio Processing with Background Music")

    uploaded_file = st.file_uploader("Choose an audio file", type=["mp3", "wav", "m4a", "ogg", "flac"])

    if uploaded_file is not None:
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(uploaded_file.name)[1]) as tmp_file:
            tmp_file.write(uploaded_file.getvalue())
            tmp_file_path = tmp_file.name

        if check_audio_file(tmp_file_path):
            # st.audio(tmp_file_path)
            with open(tmp_file_path, "rb") as f:
                audio_bytes = f.read()
                st.audio(audio_bytes, format="audio/mp3")

            audio_info = get_audio_info(tmp_file_path)
            if audio_info:
                st.write("File Information:")
                for key, value in audio_info.items():
                    st.write(f"- {key.capitalize()}: {value}")

            if audio_info and audio_info["format"] != "mp3":
                st.warning(f"The uploaded file is a {audio_info['format']} file. It will be converted to MP3 for processing.")
                mp3_file = tempfile.mktemp(suffix=".mp3")
                if convert_to_mp3(tmp_file_path, mp3_file):
                    st.success("File converted to MP3 successfully.")
                    tmp_file_path = mp3_file
                else:
                    st.error("Failed to convert the file to MP3. Please upload an MP3 file.")
                    return

            background_choice = st.selectbox("Choose background music", list(BACKGROUND_MUSIC.keys()))

            if st.button("Apply Background Music"):
                progress_bar = st.progress(0)
                with st.spinner("Applying background music..."):
                    background_url = BACKGROUND_MUSIC[background_choice]
        
                    async def process_audio_async():
                        return await process_audio(tmp_file_path, background_url, progress_bar)
                    
                    processed_audio = asyncio.run(process_audio_async())
    
                if processed_audio is not None:
                    output_path = tempfile.mktemp(suffix=".mp3")
                    processed_audio.export(output_path, format="mp3")
                    
                    with open(output_path, "rb") as file:
                        btn = st.download_button(
                            label="Download Processed Audio",
                            data=file,
                            file_name="processed_audio.mp3",
                            mime="audio/mp3"
                        )
        
                    os.unlink(output_path)
                    st.success("Background music applied successfully!")
                else:
                    st.error("Failed to process the audio. Please try a different file or settings.")

if __name__ == "__main__":
    main()