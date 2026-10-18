# 🎬 REEL SCRIPT GENERATOR

Complete local system for generating short-form video scripts using llama.cpp and GGUF models.

---

## 📋 Current Status

| Component | Status | Notes |
|-----------|--------|-------|
| `main.py` | ✅ **Ready** | Full menu system with 4 options for topic, type, duration & audience |
| `llama-cli` | ✅ **Available** | Located in llama.cpp folder |
| `model.gguf` | ⏳ **Needed** | Download required (~2.3 - 4.3 GB) |

---

## 🚀 Quick Start

### Step 1: Download Model

**SIMPLEST METHOD** (Download in browser):

1. Visit: https://huggingface.co/QuantFactory/Phi-3-5-mini-instruct-GGUF
2. Click on one of these files (pick one):
   - `Phi-3.5-mini-instruct.IQ3_M.gguf` **(2.3 GB - Fast - RECOMMENDED)**
   - `Phi-3.5-mini-instruct.Q4_K_M.gguf` (3.3 GB - Balanced)
3. Click download button
4. Move downloaded file to this folder
5. Rename to: `model.gguf`

**File should be at:** `c:\Users\papan\Downloads\script\model.gguf`

### Step 2: Run Generator

```powershell
cd c:\Users\papan\Downloads\script
python main.py
```

### Step 3: Follow Interactive Menu

```
Enter topic: What is Machine Learning

📋 SELECT CONTENT TYPE:
  1. technology
  2. funny
  3. professional
  4. educational
Enter choice (1-4): 1

Enter duration (seconds): 15

👥 SELECT TARGET AUDIENCE:
  1. engineers - Professional, exam-focused, technical
  2. common - Simple, clear, everyday language
  3. kids - Very simple, friendly, easy words
Enter choice (1-3): 2
```

### Step 4: Get Result

Output saved to: `outputs/final.txt`

---

## 📁 Project Structure

```
c:\Users\papan\Downloads\script\
├── main.py              ✅ Generator script (ready to run)
├── llama.cpp/           ✅ Contains llama-cli executable
├── model.gguf           ⏳ Download & place here
├── outputs/
│   └── final.txt        📝 Generated script (created on first run)
├── SETUP.md             📚 Complete setup guide
└── README.md            📖 This file
```

---

## ⚙️ How It Works

### Input
- **Topic**: What to generate about (e.g., "Artificial Intelligence")
- **Content Type**: 
  1. Technology - Technical explanation with examples
  2. Funny - Humorous and exaggerated
  3. Professional - Clean, confident, focused
  4. Educational - Simple, clear, easy to revise
- **Duration**: Seconds (calculates tokens: ~2.2 words/sec)
- **Target Audience**:
  1. Engineers - Professional, exam-focused, practical
  2. Common people - Simple, clear, no jargon
  3. Kids - Slow, very simple, friendly tone

### Processing
1. Builds dynamic prompt with audience guidance
2. Calls `llama-cli` locally with:
   - `--temp 0.8` (creativity)
   - `--top-p 0.9` (diversity)
   - `--repeat-penalty 1.1` (avoid repetition)
   - `-n` tokens (based on duration)
3. Cleans output (removes noise, fixes spacing)
4. Saves to `outputs/final.txt`

### Output
Clean, ready-to-use voiceover text for:
- Text-to-Speech (TTS) conversion
- Subtitles
- Short-form video (TikTok, Instagram Reels, YouTube Shorts)

---

## 📦 Model Download Links

### Recommended (Fastest)
- **Phi-3.5 IQ3_M** (2.3 GB)
  https://huggingface.co/QuantFactory/Phi-3-5-mini-instruct-GGUF/blob/main/Phi-3.5-mini-instruct.IQ3_M.gguf

### Balanced
- **Phi-3.5 Q4_K_M** (3.3 GB)
  https://huggingface.co/QuantFactory/Phi-3-5-mini-instruct-GGUF/blob/main/Phi-3.5-mini-instruct.Q4_K_M.gguf

### Best Quality
- **Phi-3.5 Q5_K_M** (4.3 GB)
  https://huggingface.co/QuantFactory/Phi-3-5-mini-instruct-GGUF/blob/main/Phi-3.5-mini-instruct.Q5_K_M.gguf

### Alternative Models
- **Qwen 7B**: https://huggingface.co/QuantFactory/Qwen2-7B-Instruct-GGUF
- **Mistral 7B**: https://huggingface.co/QuantFactory/Mistral-7B-Instruct-v0.3-GGUF

---

## 🎯 Example Usage

### Input:
```
Topic: What is Photosynthesis
Type: educational
Duration: 20 seconds
Audience: kids
```

### Sample Output:
```
Hey there! Have you ever wondered how plants make their own food? 
It's like magic, but it's actually science! Plants are like little 
factories. They take sunlight, water, and something in the air called 
carbon dioxide. Then, boom! They mix it all together and create their 
own food and oxygen for us to breathe. Pretty amazing, right? That's 
photosynthesis!
```

---

## 🔧 Requirements

- Python 3.8+
- llama.cpp executable (already in folder)
- GGUF model file (~2-4 GB)
- ~500MB free RAM during generation
- Internet connection (first download only)

---

## ❓ Troubleshooting

### "Error: model.gguf not found"
- Download model from links above
- Save as `model.gguf` in script folder
- Verify file exists: `ls model.gguf`

### Generation hangs or is slow
- Model size: Smaller models are faster (IQ3_M vs Q5_K_M)
- RAM: Ensure 6GB+ free
- Duration: Reduce duration input for faster generation

### Output quality is poor
- Try a larger model (Q5_K_M instead of IQ3_M)
- Adjust temperature (0.7-0.9 for different styles)
- Add more specific details to topic

---

## 📝 Features

✅ Full interactive CLI menu  
✅ Dynamic prompt adjustment per audience  
✅ Automatic token calculation  
✅ Output cleaning & formatting  
✅ Auto-create outputs folder  
✅ No API calls - 100% offline  
✅ Single file executable  

---

## 🎬 Next Steps After Generation

Once you have generated scripts, you can:

1. **Text-to-Speech**: Use Windows TTS or services like:
   - ElevenLabs (Free tier available)
   - Google Cloud TTS
   - Azure Speech
   - Free: pyttsx3 (Windows built-in)

2. **Video**: Combine with:
   - Canva (free templates)
   - DaVinci Resolve (free video editor)
   - ElevenLabs video creator

3. **Subtitles**: Use:
   - Automatic subtitle generators
   - CapCut (mobile app)
   - Adobe Premiere

---

## 📄 License

This project uses llama.cpp (MIT License) and GGUF models.

---

**Ready to generate viral reels? Download the model and run `python main.py`! 🚀**
