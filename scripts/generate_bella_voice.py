import os
import urllib.request
import numpy as np

# Monkeypatch np.load to allow pickle for Kokoro voices.bin in NumPy 2.x
_orig_load = np.load
np.load = lambda *args, **kwargs: _orig_load(*args, **{**kwargs, "allow_pickle": True})

import soundfile as sf
from kokoro_onnx import Kokoro
import subprocess

CACHE_DIR = os.path.join(os.path.expanduser("~"), ".cache", "kokoro")
os.makedirs(CACHE_DIR, exist_ok=True)

MODEL_PATH = os.path.join(CACHE_DIR, "kokoro-v0_19.onnx")
VOICES_PATH = os.path.join(CACHE_DIR, "voices.bin")

MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/kokoro-v0_19.onnx"
VOICES_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/voices.bin"

def download_file(url, target_path):
    if os.path.exists(target_path) and os.path.getsize(target_path) > 1000:
        print(f"[✓] Already downloaded: {target_path}")
        return
    print(f"[*] Downloading {url} to {target_path}...")
    urllib.request.urlretrieve(url, target_path)
    print(f"[✓] Downloaded {target_path}")

def generate_voice():
    download_file(MODEL_URL, MODEL_PATH)
    download_file(VOICES_URL, VOICES_PATH)

    print("[*] Initializing Kokoro TTS engine with voice 'af_bella'...")
    kokoro = Kokoro(MODEL_PATH, VOICES_PATH)

    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    static_audio_dir = os.path.join(root_dir, "static", "audio")
    public_audio_dir = os.path.join(root_dir, "original_repo", "public", "audio")

    os.makedirs(static_audio_dir, exist_ok=True)
    os.makedirs(public_audio_dir, exist_ok=True)

    prompts = [
        ("Take a break.", "break_bella"),
        ("Time to focus.", "focus_bella")
    ]

    for text, filename in prompts:
        print(f"[*] Generating speech for '{text}' with Bella...")
        samples, sample_rate = kokoro.create(text, voice="af_bella", speed=1.0, lang="en-us")
        
        # Save to static/audio
        wav_path = os.path.join(static_audio_dir, f"{filename}.wav")
        mp3_path = os.path.join(static_audio_dir, f"{filename}.mp3")
        sf.write(wav_path, samples, sample_rate)
        print(f"[✓] Saved WAV: {wav_path}")

        # Convert to lightweight MP3 using ffmpeg
        subprocess.run(["ffmpeg", "-y", "-i", wav_path, "-codec:a", "libmp3lame", "-b:a", "192k", mp3_path], check=True, capture_output=True)
        print(f"[✓] Converted to MP3: {mp3_path}")

        # Also copy to original_repo/public/audio for frontend Vite builds
        pub_wav = os.path.join(public_audio_dir, f"{filename}.wav")
        pub_mp3 = os.path.join(public_audio_dir, f"{filename}.mp3")
        sf.write(pub_wav, samples, sample_rate)
        subprocess.run(["ffmpeg", "-y", "-i", pub_wav, "-codec:a", "libmp3lame", "-b:a", "192k", pub_mp3], check=True, capture_output=True)

    print("\n=======================================================")
    print("[✓] Bella TTS Voice clips generated successfully!")
    print(f"    - Break: 'Take a break.' -> {os.path.join(static_audio_dir, 'break_bella.mp3')}")
    print(f"    - Focus: 'Time to focus.' -> {os.path.join(static_audio_dir, 'focus_bella.mp3')}")
    print("=======================================================")

if __name__ == "__main__":
    generate_voice()
