======================================================================
🎬 MANUAL DEEPSEEK MODEL DOWNLOAD GUIDE
======================================================================

Due to Hugging Face authentication, automatic download currently encounters issues.
Use this simple 3-step manual process instead:

======================================================================
STEP 1: OPEN DOWNLOAD LINK
======================================================================

Click this link (or copy to your browser):

🔗 https://huggingface.co/bartowski/deepseek-r1-distill-qwen-7b-gguf

The page will show several model files.

======================================================================
STEP 2: SELECT & DOWNLOAD MODEL FILE
======================================================================

Choose ONE of these (we recommend Q4):

📦 OPTION A - FASTEST (Recommended) ⭐
   File: deepseek-r1-distill-qwen-7b-Q4_K_M.gguf
   Size: ~4.7 GB
   Speed: ⚡⚡⚡
   Quality: ⭐⭐⭐⭐

📦 OPTION B - BEST QUALITY
   File: deepseek-r1-distill-qwen-7b-Q5_K_M.gguf
   Size: ~6.2 GB
   Speed: ⚡⚡
   Quality: ⭐⭐⭐⭐⭐

📦 OPTION C - SMALLEST/FASTEST
   File: deepseek-r1-distill-qwen-7b-Q3_K_M.gguf
   Size: ~3.3 GB
   Speed: ⚡⚡⚡⚡
   Quality: ⭐⭐⭐

HOW TO DOWNLOAD:
1. Scroll down to find the file you want
2. Click the file name
3. Click the Download button (down arrow icon)
4. Wait for download to complete

======================================================================
STEP 3: MOVE TO SCRIPT FOLDER
======================================================================

After download completes:

A) Locate the downloaded file (usually in Downloads folder)

B) Rename it to:
   model.gguf

C) Move it to:
   c:\Users\papan\Downloads\script\

You can do this by:
1. Open File Explorer
2. Navigate to Downloads
3. Find the .gguf file
4. Right-click → Rename → Type "model.gguf"
5. Right-click → Cut
6. Navigate to c:\Users\papan\Downloads\script\
7. Right-click → Paste

======================================================================
VERIFY & RUN
======================================================================

After file is in place, verify:

   python -c "import os; print('✓ Model found!' if os.path.exists('model.gguf') else '✗ Not found')"

Then run:

   python main.py

======================================================================
DIRECT DOWNLOAD LINKS (Copy to Browser)
======================================================================

Q4 (Recommended):
https://huggingface.co/bartowski/deepseek-r1-distill-qwen-7b-gguf/resolve/main/deepseek-r1-distill-qwen-7b-Q4_K_M.gguf

Q5 (Best Quality):
https://huggingface.co/bartowski/deepseek-r1-distill-qwen-7b-gguf/resolve/main/deepseek-r1-distill-qwen-7b-Q5_K_M.gguf

Q3 (Smallest):
https://huggingface.co/bartowski/deepseek-r1-distill-qwen-7b-gguf/resolve/main/deepseek-r1-distill-qwen-7b-Q3_K_M.gguf

======================================================================
⏱️ EXPECTED TIME
======================================================================

Download time depends on your internet speed:

Speed          Q3 (3.3GB)    Q4 (4.7GB)    Q5 (6.2GB)
─────────────────────────────────────────────────────
100 Mbps       ~5 min        ~7.5 min      ~10 min
50 Mbps        ~10 min       ~15 min       ~20 min
25 Mbps        ~20 min       ~30 min       ~40 min
10 Mbps        ~50 min       ~75 min       ~100 min

======================================================================
❓ TROUBLESHOOTING
======================================================================

Q: Download button not working?
A: Try copying the direct link above and pasting in browser address bar

Q: File size looks wrong after download?
A: Check file properties (right-click > Properties)
   Q4 should be: 4.7 GB
   Q5 should be: 6.2 GB

Q: Can't find Downloads folder?
A: Press Windows key + R, type: %USERPROFILE%\Downloads

Q: Still having issues?
A: System requirements needed:
   - 8GB RAM minimum
   - 10GB free disk space
   - Stable internet connection

======================================================================

Ready? Start by clicking/copying the link above! 🚀
