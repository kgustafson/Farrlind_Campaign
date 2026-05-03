import argparse
import os
import subprocess
import tempfile
from faster_whisper import WhisperModel


#DEFAULT_CHUNK_SECONDS = 30
DEFAULT_CHUNK_SECONDS = 180
#DEFAULT_MODEL_SIZE = "medium"
DEFAULT_MODEL_SIZE = "large-v3"


def get_duration_seconds(audio_path: str) -> float:
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        audio_path,
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=True,
    )

    return float(result.stdout.strip())


def extract_chunk(audio_path: str, start: float, duration: float, out_wav: str):
    cmd = [
        "ffmpeg",
        "-y",
        "-ss", str(start),
        "-t", str(duration),
        "-i", audio_path,
        "-ar", "16000",
        "-ac", "1",
        "-c:a", "pcm_s16le",
        out_wav,
    ]

    try:
        subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        print("\nFFmpeg failed.")
        print("Command was:")
        print(" ".join(cmd))
        print("\nFFmpeg error output:")
        print(e.stderr)
        raise


def fmt_time(seconds: float) -> str:
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Transcribe an audio file in chunks using faster-whisper."
    )

    parser.add_argument(
        "audio_file",
        help="Input audio file, such as session20.wav",
    )

    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output transcript file. Defaults to <audio filename>_transcript.txt",
    )

    parser.add_argument(
        "--chunk-seconds",
        type=int,
        default=DEFAULT_CHUNK_SECONDS,
        help=f"Chunk size in seconds. Default: {DEFAULT_CHUNK_SECONDS}",
    )

    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL_SIZE,
        help=f"Whisper model size. Default: {DEFAULT_MODEL_SIZE}",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    audio_file = args.audio_file

    audio_stem = os.path.splitext(os.path.basename(audio_file))[0]

    output_file = args.output or (
        f"/Volumes/T7_WORK/AI_RAG/knowledge/Faban/raw/{audio_stem}_transcript.txt"
    )
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    chunk_seconds = args.chunk_seconds
    model_size = args.model

    if not os.path.exists(audio_file):
        raise FileNotFoundError(f"Audio file not found: {audio_file}")

    print("Loading Whisper model...")
    print(f"Model: {model_size}")
    print(f"Input: {audio_file}")
    print(f"Output: {output_file}")
    print(f"Chunk size: {chunk_seconds} seconds")

    model = WhisperModel(
        model_size,
        device="cpu",
        compute_type="int8",
    )

    total_duration = get_duration_seconds(audio_file)
    print(f"Audio duration: {fmt_time(total_duration)}")

    with open(output_file, "w", encoding="utf-8") as out:
        chunk_start = 0

        while chunk_start < total_duration:
            chunk_len = min(chunk_seconds, total_duration - chunk_start)

            print(
                f"\nProcessing {fmt_time(chunk_start)} "
                f"to {fmt_time(chunk_start + chunk_len)}..."
            )

            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp_path = tmp.name
            tmp.close()

            try:
                extract_chunk(audio_file, chunk_start, chunk_len, tmp_path)

                segments, info = model.transcribe(
                    tmp_path,
                    task="transcribe",
                    beam_size=5,
                    temperature=0.0,
                    vad_filter=True,
                )

                out.write(f"\n\n=== {fmt_time(chunk_start)} ===\n\n")
                out.flush()

                for segment in segments:
                    absolute_start = chunk_start + segment.start
                    absolute_end = chunk_start + segment.end

                    text = segment.text.strip()
                    if not text:
                        continue

                    line = (
                        f"[{fmt_time(absolute_start)} - "
                        f"{fmt_time(absolute_end)}] "
                        f"{text}\n"
                    )

                    print(line, end="")
                    out.write(line)
                    out.flush()

            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)

            chunk_start += chunk_seconds

    print(f"\nDone. Transcript saved to {output_file}")


if __name__ == "__main__":
    main()
