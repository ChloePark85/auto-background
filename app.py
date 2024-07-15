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
from concurrent.futures import ThreadPoolExecutor
import subprocess
import mutagen
from mutagen.mp3 import MP3
from mutagen.wave import WAVE
from mutagen.m4a import M4A

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
# 배경음악 목록 (실제 경로로 교체해야 함)
# 현재 스크립트의 디렉토리 경로
current_dir = os.path.dirname(os.path.abspath(__file__))

# 배경음악 폴더 경로
bg_music_dir = os.path.join(current_dir, "background_music")

# 배경음악 목록 생성
BACKGROUND_MUSIC = {
    file.split('.')[0]: os.path.join(bg_music_dir, file)
    for file in os.listdir(bg_music_dir)
    if file.endswith('.mp3')
}
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

@st.cache_data
def load_audio(file_path):
    try:
        return AudioSegment.from_file(file_path)
    except Exception as e:
        logger.error(f"Error loading audio: {str(e)}")
        return None

async def apply_background_music(main_audio, background_audio, fade_duration=10000):
    # 배경음악 준비
    bg_intro = background_audio[:fade_duration].fade_out(duration=fade_duration)
    bg_outro = background_audio[:fade_duration].fade_in(duration=fade_duration)

    # 메인 오디오 준비
    main_duration = len(main_audio)
    result = AudioSegment.silent(duration=main_duration + 2*fade_duration)

    # 배경음악 인트로 적용
    result = result.overlay(bg_intro, position=0)

    # 메인 오디오 적용
    result = result.overlay(main_audio, position=fade_duration)

    # 배경음악 아웃트로 적용
    result = result.overlay(bg_outro, position=main_duration + fade_duration)

    return result

async def process_audio(input_file, background_file, progress_bar):
    try:
        main_audio = load_audio(input_file)
        if main_audio is None:
            st.error("Failed to load the main audio file. Please try a different file.")
            return None

        progress_bar.progress(20)

        background_audio = None
        if background_file:
            background_audio = load_audio(background_file)
            if background_audio is None:
                st.error("Failed to load the background music. Please try a different file.")
                return None

        progress_bar.progress(40)

        if background_audio:
            result = await apply_background_music(main_audio, background_audio)
        else:
            result = main_audio

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
            st.audio(tmp_file_path)

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
                    background_file = BACKGROUND_MUSIC[background_choice]

                    async def process_audio_async():
                        return await process_audio(tmp_file_path, background_file, progress_bar)

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
        else:
            st.error("The uploaded file is not a valid audio file. Please upload a different file.")

        os.unlink(tmp_file_path)

if __name__ == "__main__":
    main()