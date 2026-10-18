import os
import sys
import time
from datetime import datetime
import soundfile as sf
import numpy as np

# Import existing helper functions from the project
from helper import load_text_to_speech, load_voice_style

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def print_header(step_name):
    print("=" * 60)
    print(f"  SUPERTONIC CONTENT CREATOR - {step_name}")
    print("=" * 60)

def main():
    # --- Initialization ---
    onnx_dir = "../assets/onnx"
    save_dir = "results"
    
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    # Pre-load TTS Engine to ensure everything is ready
    print("Initializing Supertonic TTS Engine...")
    try:
        text_to_speech = load_text_to_speech(onnx_dir, use_gpu=False)
    except Exception as e:
        print(f"Error loading models: {e}")
        return

    # --- Step 1: Raw Text Input ---
    clear_screen()
    print_header("STEP 1: TEXT INPUT")
    print("Enter the script you want to convert to audio.")
    print("(Press Enter twice or Ctrl+Z then Enter to finish typing)")
    
    input_lines = []
    while True:
        try:
            line = input("> ")
            if line == "" and (len(input_lines) > 0 and input_lines[-1] == ""):
                break
            input_lines.append(line)
            if len(input_lines) > 1 and input_lines[-1] == "" and input_lines[-2] == "":
                break
        except EOFError:
            break
    
    raw_text = " ".join(input_lines).strip()
    if not raw_text:
        print("Error: No text provided. Exiting.")
        return

    # --- Step 2: Voice Selection ---
    clear_screen()
    print_header("STEP 2: VOICE SELECTION")
    voices = [
        ("Male Style 1 (Default Professional)", "M1"),
        ("Male Style 2 (Deep/Energetic)", "M2"),
        ("Male Style 3 (Casual Narrator)", "M3"),
        ("Male Style 4 (Smooth/Warm)", "M4"),
        ("Male Style 5 (Alternative)", "M5"),
        ("Female Style 1 (Clear Professional)", "F1"),
        ("Female Style 2 (Casual/Friendly)", "F2"),
        ("Female Style 3 (Soft Narrator)", "F3"),
        ("Female Style 4 (Bright/Upbeat)", "F4"),
        ("Female Style 5 (Alternative)", "F5"),
    ]

    for i, (desc, _) in enumerate(voices, 1):
        print(f"{i:2}. {desc}")

    voice_choice = 0
    while voice_choice < 1 or voice_choice > 10:
        try:
            voice_choice = int(input("\nSelect a voice (1-10): "))
        except ValueError:
            pass

    selected_voice_code = voices[voice_choice - 1][1]
    voice_path = f"../assets/voice_styles/{selected_voice_code}.json"

    # --- Step 3: Vibe Selection ---
    clear_screen()
    print_header("STEP 3: CHARACTERISTICS & VIBE")
    vibes = [
        ("Professional / Corporate", 1.05, ""),
        ("Funny / Comedic", 1.3, "<laugh> "),
        ("Dramatic / Storytelling", 0.9, "<breath> "),
        ("Sarcastic / Low Energy", 0.95, "", " <sigh>"),
        ("Standard / Flat", 1.05, ""),
    ]

    for i, (name, speed, _, *extra) in enumerate(vibes, 1):
        suffix = extra[0] if extra else ""
        print(f"{i}. {name}")

    vibe_choice = 0
    while vibe_choice < 1 or vibe_choice > 5:
        try:
            vibe_choice = int(input("\nSelect a vibe (1-5): "))
        except ValueError:
            pass

    vibe_name, speed, prefix, *suffix_list = vibes[vibe_choice - 1]
    suffix = suffix_list[0] if suffix_list else ""
    
    # Process text based on vibe
    final_text = f"{prefix}{raw_text}{suffix}"

    # --- Step 4: Inference and Saving ---
    clear_screen()
    print_header("STEP 4: GENERATING AUDIO")
    print(f"Text: \"{final_text[:50]}...\"")
    print(f"Voice: {selected_voice_code}")
    print(f"Vibe: {vibe_name}")
    print(f"Speed: {speed}")
    print("\nProcessing... Please wait.")

    try:
        # Load style
        style = load_voice_style([voice_path])

        # Synthesize
        start_time = time.time()
        wav, duration = text_to_speech(final_text, "en", style, total_step=8, speed=speed)
        end_time = time.time()

        # Save file with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_name = f"generation_{timestamp}.wav"
        file_path = os.path.join(save_dir, file_name)

        # Process wav for saving
        # text_to_speech returns [Batch, Samples]
        w = wav[0, : int(text_to_speech.sample_rate * duration[0].item())]
        sf.write(file_path, w, text_to_speech.sample_rate)

        print("\n" + "=" * 60)
        print("SUCCESSFULLY GENERATED!")
        print(f"File Saved: {file_path}")
        print(f"Audio Length: {duration[0]:.2f}s")
        print(f"Inference Time: {end_time - start_time:.2f}s")
        print("=" * 60)

    except Exception as e:
        print(f"\nAn error occurred during generation: {e}")

if __name__ == "__main__":
    main()
