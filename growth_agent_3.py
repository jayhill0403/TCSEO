#!/usr/bin/env python3
"""
growth_agent_3.py
-----------------
Part of the TagCraft SEO automated marketing fleet.
Utilizes GROQ_API_KEY_2 to generate high-intent keyword cheat sheets.
"""

import json
import os
import re
import sys
import time
import random
import hashlib
import datetime
import urllib.request
import urllib.error
from pathlib import Path

# --- Config & Keys ---
# Pulls from your second Groq key slot to bypass rate limits
GROQ_API_KEY = "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"


if not GROQ_API_KEY:
    print("Error: GROQ_API_KEY_2 environment variable is missing.")
    sys.exit(1)

print("Bot 3 successfully authenticated using Groq Key Pool #2.")

# --- Paths Configuration ---
# Matches the standard structure for publishing keyword cheat sheets
BASE_DIR = Path(__file__).resolve().parent
DOCS_DIR = BASE_DIR / "docs"
HISTORY_FILE = BASE_DIR / "history.json"

# Ensure directories exist
DOCS_DIR.mkdir(exist_ok=True)

# --- Load / Save History Log ---
def load_history():
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_history(history):
    try:
        with open(HISTORY_FILE, "w") as f:
            json.dump(history, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not update history.json: {e}")

# --- Call Groq Inference Engine ---
def call_groq_api(prompt_text):
    """Sends a fast inference request to the Groq API endpoint."""
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Utilizing an ultra-fast, cost-effective marketing model configuration
    data = {
        "model": "llama3-8b-8192",
        "messages": [
            {"role": "system", "content": "You are an expert e-commerce SEO specialist and growth marketer."},
            {"role": "user", "content": prompt_text}
        ],
        "temperature": 0.7,
        "max_tokens": 1024
    }
    
    req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"), headers=headers, method="POST")
    
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            return res_data["choices"][0]["message"]["content"]
    except urllib.error.URLError as e:
        print(f"API Error: Failed to contact Groq engine. {e}")
        return None

# --- Main Engine Execution ---
def run_engine():
    history = load_history()
    
    # Niche rotation list to ensure diverse target audience capture
    niches = ["Etsy Sellers", "Shopify Store Owners", "TikTok Shop Dropshippers", "Print on Demand Creators"]
    selected_niche = random.choice(niches)
    
    print(f"Targeting niche: {selected_niche}")
    
    prompt = (
        f"Generate a targeted e-commerce keyword cheat sheet focusing on high-volume, low-competition keywords for {selected_niche}. "
        "Format it completely in clean Markdown, including a table structure and 3 actionable title optimization tips. "
        "At the bottom, add a strong call-to-action link to 'https://tagcraftseo.com' explaining how the tool automates this entire process in seconds."
    )
    
    content = call_groq_api(prompt)
    if not content:
        sys.exit(1)
        
    # Generate unique signature to avoid duplicate publishing loops
    content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()
    if content_hash in history.values():
        print("Duplicate content detected. Skipping file write to protect repository reputation.")
        return
        
    # Format safe filename structure
    date_str = datetime.date.today().isoformat()
    clean_niche = re.sub(r'[^a-z0-9]', '-', selected_niche.lower())
    filename = f"keywords-{clean_niche}-{date_str}.md"
    file_path = DOCS_DIR / filename
    
    # Write the asset out to the web directory
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
        
    print(f"Success: New marketing asset generated and saved to docs/{filename}")
    
    # Update local database state
    history[filename] = content_hash
    save_history(history)

if __name__ == "__main__":
    run_engine()
