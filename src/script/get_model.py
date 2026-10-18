#!/usr/bin/env python3

import subprocess
import os
import sys

def download_with_aria2(url, filename):
    """Download using aria2c (fastest method)"""
    try:
        cmd = [
            "aria2c",
            "-x", "16",  # 16 connections
            "-k", "1M",  # 1MB chunk size
            "-o", filename,
            url
        ]
        print("📥 Downloading with aria2c (fastest)...")
        subprocess.run(cmd, check=True)
        return True
    except:
        return False

def download_with_curl(url, filename):
    """Download using curl"""
    try:
        cmd = ["curl", "-L", "-o", filename, url]
        print("📥 Downloading with curl...")
        subprocess.run(cmd, check=True)
        return True
    except:
        return False

def download_with_wget(url, filename):
    """Download using wget"""
    try:
        cmd = ["wget", "-O", filename, url]
        print("📥 Downloading with wget...")
        subprocess.run(cmd, check=True)
        return True
    except:
        return False

def download_with_powershell(url, filename):
    """Download using PowerShell"""
    try:
        ps_cmd = f"""
$url = '{url}'
$outfile = '{filename}'
$ProgressPreference = 'Continue'
try {{
    (New-Object System.Net.WebClient).DownloadFile($url, $outfile)
    Write-Host "Download complete"
}} catch {{
    Write-Host "Error: $($_.Exception.Message)"
    exit 1
}}
"""
        print("📥 Downloading with PowerShell...")
        subprocess.run(["powershell", "-Command", ps_cmd], check=True)
        return True
    except:
        return False

def main():
    print("=" * 70)
    print("🎬 HERMES 3 LLAMA MODEL DOWNLOADER (Q5_K_M)")
    print("=" * 70)
    print()
    
    if os.path.exists("model.gguf"):
        size = os.path.getsize("model.gguf") / (1024**3)
        if size > 1.0:
            print(f"✓ Model already exists: model.gguf ({size:.2f} GB)")
            return
        else:
            print(f"⚠ Found incomplete model.gguf ({size:.2f} GB). Removing it and restarting download...")
            os.remove("model.gguf")
        
    url = "https://huggingface.co/mradermacher/Hermes-3-Llama-3.1-8B-lorablated-GGUF/resolve/main/Hermes-3-Llama-3.1-8B-lorablated.Q5_K_M.gguf"
    print(f"\nInitiating download of Hermes-3-Llama-3.1-8B-lorablated.Q5_K_M...")
    print("URL: " + url)
    print("This will take 10-60 minutes depending on your connection.\n")
    
    # Try in order: aria2c > curl > wget > powershell
    success = False
    if download_with_aria2(url, "model.gguf"):
        success = True
    elif download_with_curl(url, "model.gguf"):
        success = True
    elif download_with_wget(url, "model.gguf"):
        success = True
    elif download_with_powershell(url, "model.gguf"):
        success = True
        
    if not success:
        print("\n✗ All automatic download methods failed")
        print("\n📌 MANUAL DOWNLOAD OPTION:")
        print(f"URL: {url}")
        print("Save it as: model.gguf in the src/script folder")
        sys.exit(1)
        
    if os.path.exists("model.gguf"):
        size = os.path.getsize("model.gguf") / (1024**3)
        if size > 1:  # Verify it's a real file
            print("\n" + "=" * 70)
            print("✓ DOWNLOAD COMPLETE!")
            print("=" * 70)
            print(f"\n✓ Model saved: model.gguf ({size:.2f} GB)")
            print("\nNow run: python main.py")
            return
            
    print("\n✗ Download failed or incomplete")

if __name__ == "__main__":
    main()
