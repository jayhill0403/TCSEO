#!/usr/bin/env python3
"""
growth_agent.py
───────────────
Zero-budget SEO growth engine for TagCraft.
Runs on GitHub Actions every 4 hours to auto-publish keyword cheat sheets.

Stack:
  • Groq API (free tier) — LLM generation
  • GitHub Pages — free hosting
  • history.json — lightweight local state, committed back to the repo
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

# ─── Config ───────────────────────────────────────────────────────────────────

GROQ_API_KEY   = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL     = "llama3-70b-8192"          # free on Groq's tier
OUTPUT_DIR     = Path("docs/seo")           # GitHub Pages serves /docs
HISTORY_FILE   = Path("history.json")
INDEX_FILE     = Path("docs/index.html")
TAGCRAFT_URL   = "https://tagcraft.app"     # ← your real URL
TAGCRAFT_CTA   = "Generate 50 Viral Tags in 10 Seconds — Free with TagCraft"
TAGCRAFT_BADGE = "🚀 TagCraft Pro — Unlimited AI Tags + Trend Alerts"

MAX_PAGES_PER_RUN = 3   # stay inside Groq free-tier rate limits

# ─── Trend Seeds ──────────────────────────────────────────────────────────────
# Expanded pool; new niches drop in automatically as the list grows.

TREND_NICHES = [
    # Etsy digital
    {"slug": "digital-planners-2025",         "title": "Digital Planners 2025",         "platform": "Etsy", "type": "digital"},
    {"slug": "ai-wall-art-printables",        "title": "AI Wall Art Printables",        "platform": "Etsy", "type": "digital"},
    {"slug": "wedding-invitation-templates",  "title": "Wedding Invitation Templates",  "platform": "Etsy", "type": "digital"},
    {"slug": "notion-dashboard-templates",    "title": "Notion Dashboard Templates",    "platform": "Etsy", "type": "digital"},
    {"slug": "kids-activity-sheets",          "title": "Kids Activity Sheets",          "platform": "Etsy", "type": "digital"},
    {"slug": "resume-templates-canva",        "title": "Canva Resume Templates",        "platform": "Etsy", "type": "digital"},
    {"slug": "svg-cut-files-cricut",          "title": "SVG Cut Files for Cricut",      "platform": "Etsy", "type": "digital"},
    {"slug": "budget-spreadsheet-templates",  "title": "Budget Spreadsheet Templates",  "platform": "Etsy", "type": "digital"},
    # Etsy physical
    {"slug": "custom-tote-bags-etsy",         "title": "Custom Tote Bags",              "platform": "Etsy", "type": "physical"},
    {"slug": "personalized-jewelry-etsy",     "title": "Personalized Jewelry",          "platform": "Etsy", "type": "physical"},
    {"slug": "aesthetic-candles-etsy",        "title": "Aesthetic Candles",             "platform": "Etsy", "type": "physical"},
    {"slug": "handmade-ceramic-mugs",         "title": "Handmade Ceramic Mugs",         "platform": "Etsy", "type": "physical"},
    {"slug": "wildflower-seed-packets",       "title": "Wildflower Seed Packet Favors", "platform": "Etsy", "type": "physical"},
    # TikTok Shop
    {"slug": "tiktok-shop-stanley-dupes",     "title": "Stanley Cup Dupes",             "platform": "TikTok Shop", "type": "physical"},
    {"slug": "tiktok-shop-skincare-tools",    "title": "Viral Skincare Tools",          "platform": "TikTok Shop", "type": "physical"},
    {"slug": "tiktok-shop-bookmarks",         "title": "Aesthetic Bookmarks",           "platform": "TikTok Shop", "type": "physical"},
    {"slug": "tiktok-shop-led-strip-lights",  "title": "LED Strip Lights Room Decor",   "platform": "TikTok Shop", "type": "physical"},
    {"slug": "tiktok-shop-digital-products",  "title": "TikTok Shop Digital Products",  "platform": "TikTok Shop", "type": "digital"},
    {"slug": "tiktok-shop-pet-accessories",   "title": "Viral Pet Accessories",         "platform": "TikTok Shop", "type": "physical"},
    # Cross-platform
    {"slug": "cottagecore-home-decor",        "title": "Cottagecore Home Décor",        "platform": "Etsy + TikTok", "type": "physical"},
    {"slug": "dark-academia-aesthetic",       "title": "Dark Academia Aesthetic",       "platform": "Etsy + TikTok", "type": "physical"},
    {"slug": "coquette-aesthetic-products",   "title": "Coquette Aesthetic Products",   "platform": "TikTok Shop", "type": "physical"},
    {"slug": "indie-sleaze-fashion",          "title": "Indie Sleaze Fashion",          "platform": "TikTok Shop", "type": "physical"},
]

# ─── Helpers ──────────────────────────────────────────────────────────────────

def load_history() -> dict:
    if HISTORY_FILE.exists():
        return json.loads(HISTORY_FILE.read_text())
    return {"generated": {}, "index": []}


def save_history(h: dict):
    HISTORY_FILE.write_text(json.dumps(h, indent=2))


def niche_hash(niche: dict) -> str:
    return hashlib.md5(niche["slug"].encode()).hexdigest()[:8]


def pick_niches(history: dict, n: int) -> list:
    """Return `n` niches not yet generated this week (oldest-first)."""
    generated = history.get("generated", {})
    week_ago  = (datetime.datetime.utcnow() - datetime.timedelta(days=7)).isoformat()

    fresh = [
        niche for niche in TREND_NICHES
        if generated.get(niche["slug"], {}).get("last_run", "") < week_ago
    ]
    # Shuffle so different runs don't always pick the same order
    random.shuffle(fresh)
    return fresh[:n]


# ─── Groq API ─────────────────────────────────────────────────────────────────

def groq_complete(prompt: str, max_tokens: int = 2800) -> str:
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not set.")

    payload = json.dumps({
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.7,
    }).encode()

    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {GROQ_API_KEY}",
        },
    )

    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
                return data["choices"][0]["message"]["content"].strip()
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 20 * (attempt + 1)
                print(f"  Rate-limited. Waiting {wait}s …")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("Groq API failed after 3 attempts.")


# ─── Prompt ───────────────────────────────────────────────────────────────────

def build_prompt(niche: dict) -> str:
    return f"""
You are an elite e-commerce SEO strategist. Write a 100% complete, highly detailed
SEO Keyword Cheat Sheet in Markdown for sellers targeting the niche:

  Niche:    {niche['title']}
  Platform: {niche['platform']}
  Type:     {niche['type']} product

The cheat sheet MUST include every section below, fully populated — no placeholders:

## 1. Niche Overview
- One-paragraph summary of the opportunity, buyer intent, and seasonality.

## 2. Buyer Personas (3 personas)
For each: name, age range, pain point, buying trigger, and average spend.

## 3. Seed Keywords (20 keywords)
A table with columns: Keyword | Estimated Monthly Searches | Competition | Intent
All rows must be filled with realistic data.

## 4. Long-Tail Keyword Clusters (5 clusters, 5 phrases each)
Group them by topic. Format: **Cluster Name** → bullet list.

## 5. Etsy / TikTok Tag Formulas (10 ready-to-copy tags)
Formatted exactly as sellers paste them into listing tools — comma-separated, max 20 chars each.

## 6. Title & Description Templates (3 templates each)
Ready-to-use listing titles and descriptions with [BRACKET] placeholders.

## 7. Trending Hashtags (15 hashtags)
Ranked by platform relevance. Label each: #hashtag (Etsy | TikTok | Both).

## 8. Competitor Gap Keywords
5 under-served keyword opportunities most competitors are missing.

## 9. Seasonal Calendar
A month-by-month table (Jan–Dec) showing demand spikes and recommended push dates.

## 10. Quick-Win Action Plan (5-step checklist)
Numbered steps a seller can take THIS WEEK to start ranking.

Write in a direct, expert tone. Be specific with numbers and examples.
Do NOT add any intro or outro outside the 10 sections above.
""".strip()


# ─── HTML Generation ──────────────────────────────────────────────────────────

def markdown_to_html_body(md: str) -> str:
    """
    Minimal Markdown → HTML converter (no deps needed).
    Handles: ## headings, ### headings, **bold**, `code`, tables, bullet lists, numbered lists.
    """
    lines   = md.split("\n")
    html    = []
    in_list = False
    in_ol   = False
    in_table = False

    def close_lists():
        nonlocal in_list, in_ol, in_table
        if in_list:   html.append("</ul>"); in_list = False
        if in_ol:     html.append("</ol>"); in_ol = False
        if in_table:  html.append("</tbody></table>"); in_table = False

    def inline(text):
        # Bold
        text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
        # Italic
        text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
        # Code
        text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
        # Links
        text = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>', text)
        return text

    for line in lines:
        stripped = line.strip()

        # Blank line
        if not stripped:
            close_lists()
            continue

        # H2
        if stripped.startswith("## "):
            close_lists()
            html.append(f'<h2>{inline(stripped[3:])}</h2>')
            continue

        # H3
        if stripped.startswith("### "):
            close_lists()
            html.append(f'<h3>{inline(stripped[4:])}</h3>')
            continue

        # HR
        if re.match(r"^[-*]{3,}$", stripped):
            close_lists()
            html.append("<hr>")
            continue

        # Table row
        if stripped.startswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            # Header separator row
            if all(re.match(r"^[-:]+$", c) for c in cells):
                continue
            if not in_table:
                close_lists()
                html.append('<table><tbody>')
                in_table = True
            row_html = "".join(f"<td>{inline(c)}</td>" for c in cells)
            html.append(f"<tr>{row_html}</tr>")
            continue

        # Unordered list
        if stripped.startswith(("- ", "* ", "• ")):
            if in_table: close_lists()
            if in_ol:    html.append("</ol>"); in_ol = False
            if not in_list: html.append("<ul>"); in_list = True
            html.append(f"<li>{inline(stripped[2:])}</li>")
            continue

        # Ordered list
        ol_match = re.match(r"^\d+\.\s(.+)", stripped)
        if ol_match:
            if in_table: close_lists()
            if in_list:  html.append("</ul>"); in_list = False
            if not in_ol: html.append("<ol>"); in_ol = True
            html.append(f"<li>{inline(ol_match.group(1))}</li>")
            continue

        # Regular paragraph
        close_lists()
        html.append(f"<p>{inline(stripped)}</p>")

    close_lists()
    return "\n".join(html)


def tagcraft_banner() -> str:
    return f"""
<div class="tc-banner">
  <div class="tc-banner-inner">
    <div class="tc-badge">{TAGCRAFT_BADGE}</div>
    <p class="tc-pitch">
      Stop guessing keywords. TagCraft's AI reads live Etsy &amp; TikTok trends
      and writes your tags, titles, and descriptions in seconds —
      so you rank faster and sell more.
    </p>
    <a class="tc-cta" href="{TAGCRAFT_URL}?utm_source=seo-cheatsheet&utm_medium=banner&utm_campaign=growth-agent"
       target="_blank" rel="noopener">
      {TAGCRAFT_CTA} →
    </a>
  </div>
</div>
""".strip()


def build_html_page(niche: dict, markdown_content: str, generated_at: str) -> str:
    body_html = markdown_to_html_body(markdown_content)
    banner    = tagcraft_banner()
    title     = f"{niche['title']} SEO Keyword Cheat Sheet — {niche['platform']}"
    canonical_slug = niche['slug']

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} | TagCraft SEO Hub</title>
  <meta name="description" content="Free {niche['title']} SEO keyword cheat sheet for {niche['platform']} sellers. 20+ seed keywords, long-tail clusters, hashtags, tag formulas, and a 5-step quick-win plan.">
  <meta name="robots" content="index, follow">
  <link rel="canonical" href="https://YOUR-USERNAME.github.io/YOUR-REPO/seo/{canonical_slug}.html">

  <!-- Open Graph -->
  <meta property="og:title" content="{title}">
  <meta property="og:description" content="The only SEO cheat sheet you need for {niche['title']} on {niche['platform']}.">
  <meta property="og:type" content="article">

  <!-- Schema -->
  <script type="application/ld+json">
  {{
    "@context": "https://schema.org",
    "@type": "Article",
    "headline": "{title}",
    "datePublished": "{generated_at[:10]}",
    "dateModified": "{generated_at[:10]}",
    "publisher": {{
      "@type": "Organization",
      "name": "TagCraft SEO Hub"
    }}
  }}
  </script>

  <style>
    /* ── Reset & base ── */
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    :root {{
      --bg:       #0d0f14;
      --surface:  #161922;
      --border:   #252a35;
      --accent:   #6c63ff;
      --accent2:  #ff6584;
      --text:     #e2e8f0;
      --muted:    #8896b3;
      --code-bg:  #1e2230;
      --radius:   10px;
      --max-w:    820px;
    }}

    html {{ scroll-behavior: smooth; }}

    body {{
      background: var(--bg);
      color: var(--text);
      font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
      font-size: 16px;
      line-height: 1.75;
    }}

    /* ── Layout ── */
    .wrapper {{ max-width: var(--max-w); margin: 0 auto; padding: 0 1.25rem 4rem; }}

    /* ── Top bar ── */
    .topbar {{
      background: var(--surface);
      border-bottom: 1px solid var(--border);
      padding: .65rem 1.25rem;
      display: flex;
      align-items: center;
      gap: .75rem;
      font-size: .8rem;
      color: var(--muted);
    }}
    .topbar a {{ color: var(--accent); text-decoration: none; font-weight: 600; }}
    .topbar-logo {{ font-size: 1rem; font-weight: 700; color: var(--text); }}

    /* ── Hero ── */
    .hero {{
      padding: 3.5rem 0 2rem;
      border-bottom: 1px solid var(--border);
      margin-bottom: 2.5rem;
    }}
    .hero-eyebrow {{
      font-size: .75rem;
      font-weight: 700;
      letter-spacing: .12em;
      text-transform: uppercase;
      color: var(--accent);
      margin-bottom: .6rem;
    }}
    .hero h1 {{
      font-size: clamp(1.6rem, 4vw, 2.4rem);
      font-weight: 800;
      line-height: 1.2;
      margin-bottom: 1rem;
    }}
    .hero h1 span {{ color: var(--accent2); }}
    .hero-meta {{
      display: flex;
      flex-wrap: wrap;
      gap: .5rem;
      font-size: .8rem;
      color: var(--muted);
    }}
    .chip {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 20px;
      padding: .2rem .7rem;
    }}

    /* ── TagCraft Banner ── */
    .tc-banner {{
      background: linear-gradient(135deg, #1a1535 0%, #0f1620 100%);
      border: 1px solid var(--accent);
      border-radius: var(--radius);
      padding: 1.75rem 1.5rem;
      margin: 2.5rem 0;
      position: relative;
      overflow: hidden;
    }}
    .tc-banner::before {{
      content: '';
      position: absolute;
      inset: 0;
      background: radial-gradient(ellipse at top left, rgba(108,99,255,.18) 0%, transparent 65%);
      pointer-events: none;
    }}
    .tc-badge {{
      font-size: .7rem;
      font-weight: 800;
      letter-spacing: .12em;
      text-transform: uppercase;
      color: var(--accent);
      margin-bottom: .6rem;
    }}
    .tc-pitch {{
      font-size: .95rem;
      color: #c3cfe2;
      margin-bottom: 1.1rem;
      max-width: 560px;
    }}
    .tc-cta {{
      display: inline-block;
      background: var(--accent);
      color: #fff;
      font-weight: 700;
      font-size: .9rem;
      padding: .7rem 1.5rem;
      border-radius: 6px;
      text-decoration: none;
      transition: background .2s, transform .15s;
    }}
    .tc-cta:hover {{ background: #574fd6; transform: translateY(-1px); }}

    /* ── Article body ── */
    .content h2 {{
      font-size: 1.35rem;
      font-weight: 700;
      color: var(--accent);
      margin: 2.5rem 0 .75rem;
      padding-bottom: .4rem;
      border-bottom: 1px solid var(--border);
    }}
    .content h3 {{
      font-size: 1.05rem;
      font-weight: 600;
      color: #a5b4fc;
      margin: 1.5rem 0 .5rem;
    }}
    .content p {{ margin-bottom: 1rem; color: #cbd5e1; }}
    .content strong {{ color: var(--text); }}
    .content em {{ color: var(--muted); font-style: italic; }}
    .content code {{
      background: var(--code-bg);
      color: #f9a8d4;
      font-size: .85em;
      padding: .15em .4em;
      border-radius: 4px;
      font-family: 'Fira Code', 'Cascadia Code', monospace;
    }}

    .content ul, .content ol {{
      margin: .5rem 0 1rem 1.25rem;
    }}
    .content li {{ margin-bottom: .35rem; color: #cbd5e1; }}

    /* ── Tables ── */
    .content table {{
      width: 100%;
      border-collapse: collapse;
      margin: 1.25rem 0;
      font-size: .9rem;
      overflow-x: auto;
      display: block;
    }}
    .content td {{
      padding: .55rem .75rem;
      border: 1px solid var(--border);
      color: #cbd5e1;
      vertical-align: top;
    }}
    .content tr:first-child td {{
      background: var(--surface);
      font-weight: 700;
      color: var(--text);
    }}
    .content tr:nth-child(even) td {{ background: rgba(255,255,255,.025); }}

    /* ── Footer ── */
    .footer {{
      border-top: 1px solid var(--border);
      padding-top: 1.5rem;
      margin-top: 3rem;
      font-size: .8rem;
      color: var(--muted);
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      gap: .5rem;
    }}
    .footer a {{ color: var(--accent); text-decoration: none; }}

    @media (max-width: 600px) {{
      .hero h1 {{ font-size: 1.4rem; }}
      .tc-cta {{ font-size: .82rem; padding: .6rem 1rem; }}
    }}
  </style>
</head>
<body>

<nav class="topbar">
  <span class="topbar-logo">TagCraft SEO Hub</span>
  <span>›</span>
  <a href="{TAGCRAFT_URL}?utm_source=seo-cheatsheet&utm_medium=nav&utm_campaign=growth-agent">Get Free Tags</a>
</nav>

<div class="wrapper">

  <!-- Hero -->
  <header class="hero">
    <div class="hero-eyebrow">Free SEO Keyword Cheat Sheet</div>
    <h1>{niche['title']}<br><span>for {niche['platform']} Sellers</span></h1>
    <div class="hero-meta">
      <span class="chip">📦 {niche['type'].capitalize()} product</span>
      <span class="chip">🛒 {niche['platform']}</span>
      <span class="chip">📅 Updated {generated_at[:10]}</span>
      <span class="chip">⏱️ 5-min read</span>
    </div>
  </header>

  <!-- Top Banner -->
  {banner}

  <!-- Main content -->
  <article class="content">
    {body_html}
  </article>

  <!-- Bottom Banner -->
  {banner}

  <!-- Footer -->
  <footer class="footer">
    <span>© {generated_at[:4]} TagCraft SEO Hub — AI-generated keyword research, updated automatically.</span>
    <span><a href="{TAGCRAFT_URL}">tagcraft.app</a> · Free Etsy &amp; TikTok tag generator</span>
  </footer>

</div>
</body>
</html>"""


# ─── Index Page ───────────────────────────────────────────────────────────────

def rebuild_index(history: dict):
    pages = list(history.get("generated", {}).values())
    pages.sort(key=lambda p: p.get("last_run", ""), reverse=True)

    cards = ""
    for p in pages:
        cards += f"""
        <a class="card" href="seo/{p['slug']}.html">
          <div class="card-platform">{p['platform']}</div>
          <div class="card-title">{p['title']}</div>
          <div class="card-date">{p['last_run'][:10]}</div>
        </a>"""

    INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    INDEX_FILE.write_text(f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>TagCraft SEO Hub — Free Etsy &amp; TikTok Keyword Cheat Sheets</title>
  <meta name="description" content="Free SEO keyword cheat sheets for Etsy and TikTok Shop sellers. Auto-updated every 4 hours with trending niches, long-tail keywords, and tag formulas.">
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    :root {{
      --bg:#0d0f14; --surface:#161922; --border:#252a35;
      --accent:#6c63ff; --accent2:#ff6584; --text:#e2e8f0; --muted:#8896b3;
    }}
    body {{ background:var(--bg); color:var(--text); font-family:system-ui,sans-serif;
            line-height:1.65; }}
    .wrap {{ max-width:900px; margin:0 auto; padding:0 1.25rem 4rem; }}
    header {{ padding:3rem 0 2rem; text-align:center; border-bottom:1px solid var(--border); margin-bottom:2.5rem; }}
    header h1 {{ font-size:clamp(1.6rem,4vw,2.6rem); font-weight:800; margin-bottom:.6rem; }}
    header h1 span {{ color:var(--accent2); }}
    header p {{ color:var(--muted); max-width:520px; margin:0 auto 1.5rem; }}
    .hero-cta {{
      display:inline-block; background:var(--accent); color:#fff;
      font-weight:700; padding:.75rem 1.75rem; border-radius:7px;
      text-decoration:none; font-size:.95rem;
    }}
    .hero-cta:hover {{ background:#574fd6; }}
    .grid {{
      display:grid;
      grid-template-columns:repeat(auto-fill, minmax(240px,1fr));
      gap:1rem;
    }}
    .card {{
      display:block; text-decoration:none;
      background:var(--surface); border:1px solid var(--border);
      border-radius:10px; padding:1.1rem 1.2rem;
      transition:border-color .2s, transform .15s;
    }}
    .card:hover {{ border-color:var(--accent); transform:translateY(-2px); }}
    .card-platform {{ font-size:.7rem; font-weight:700; letter-spacing:.1em;
                      text-transform:uppercase; color:var(--accent); margin-bottom:.4rem; }}
    .card-title {{ font-weight:700; color:var(--text); margin-bottom:.5rem; }}
    .card-date {{ font-size:.75rem; color:var(--muted); }}
    footer {{ border-top:1px solid var(--border); padding-top:1.25rem; margin-top:3rem;
              text-align:center; font-size:.8rem; color:var(--muted); }}
    footer a {{ color:var(--accent); text-decoration:none; }}
  </style>
</head>
<body>
<div class="wrap">
  <header>
    <div style="font-size:.75rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;
                color:var(--accent);margin-bottom:.6rem;">TagCraft SEO Hub</div>
    <h1>Free Etsy &amp; TikTok<br><span>Keyword Cheat Sheets</span></h1>
    <p>Auto-generated every 4 hours. Each guide includes 20+ keywords, tag formulas,
       hashtags, listing templates, and a quick-win action plan.</p>
    <a class="hero-cta" href="{TAGCRAFT_URL}?utm_source=seo-hub-index&utm_medium=hero&utm_campaign=growth-agent">
      🚀 Generate Your Tags Free on TagCraft →
    </a>
  </header>
  <div class="grid">{cards}</div>
  <footer>
    <p>Powered by <a href="{TAGCRAFT_URL}">TagCraft</a> · AI tag generator for Etsy &amp; TikTok Shop</p>
  </footer>
</div>
</body>
</html>""")
    print(f"  ✅  Index rebuilt → {INDEX_FILE}")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("TagCraft Growth Agent")
    print(f"Run at: {datetime.datetime.utcnow().isoformat()} UTC")
    print("=" * 60)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    history = load_history()
    targets = pick_niches(history, MAX_PAGES_PER_RUN)

    if not targets:
        print("✓ All niches are fresh. Nothing to generate this run.")
        rebuild_index(history)
        save_history(history)
        return

    print(f"\nGenerating {len(targets)} page(s) this run:\n")

    for niche in targets:
        print(f"  → {niche['title']} ({niche['platform']})")
        try:
            prompt   = build_prompt(niche)
            md_body  = groq_complete(prompt)
            now      = datetime.datetime.utcnow().isoformat()
            html     = build_html_page(niche, md_body, now)

            out_path = OUTPUT_DIR / f"{niche['slug']}.html"
            out_path.write_text(html, encoding="utf-8")
            print(f"     ✅  Written → {out_path}")

            # Update history
            history.setdefault("generated", {})[niche["slug"]] = {
                "slug":     niche["slug"],
                "title":    niche["title"],
                "platform": niche["platform"],
                "last_run": now,
            }
            save_history(history)

            # Be polite to the API between pages
            if niche != targets[-1]:
                print("     ⏳  Sleeping 8s between requests …")
                time.sleep(8)

        except Exception as exc:
            print(f"     ❌  FAILED: {exc}", file=sys.stderr)
            continue

    rebuild_index(history)
    save_history(history)

    print("\n✓ Run complete.")


if __name__ == "__main__":
    main()
