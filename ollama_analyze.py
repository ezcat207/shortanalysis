import json
import re
import requests
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen3:1.7b"
OUTPUT_DIR = "/Volumes/Lexar/oneweekoneproject/shortanalysis/analysis_results"
os.makedirs(OUTPUT_DIR, exist_ok=True)

SYSTEM_PROMPT = """You are a professional short drama content analyst specializing in emotion rhythm and engagement structure analysis.

Analyze the given episode subtitles and identify emotion point types and their time proportion.

## Emotion Point Definitions

**Laugh Points (笑点)**: Content that makes viewers laugh:
- Contrast: unexpected gap in character behavior/identity/language
- Self-mockery & Sarcasm: character self-deprecation or mocking others
- Exaggeration: overly exaggerated emotions/actions/expressions
- Unexpected & Out-of-control: sudden situations breaking expectations
- Misunderstanding & Info Gap: errors from characters having different information
- Comic Relief Character: side character that gets embarrassed/tricked
- Wordplay: puns, homophones
- Physical Comedy: body actions creating humor
- Group Chaos: multi-person chaotic scene

**Sweet Points (甜点)**: Content making viewers feel warm/touched:
- Romantic interactions between leads
- Family/friendship warmth moments

**Hype Points (爽点)**: Content making viewers feel excited/triumphant:
- Protagonist fighting back/confronting villain/face-slapping
- Career/status reversal, gaining recognition
- Victory in battle, showing strength

**Conflict Points (冲突点)**: Tension without resolution:
- Villain threats, coercion
- Protagonist in crisis

**Cry Points (泪点)**: Content triggering sadness/sympathy:
- Suffering, death, separation
- Character's grievance, despair

## Output Format
- Output JSON only, no other text
- All percentages sum to ≤100 (remainder = neutral transitions)
- laugh_types: only actual types in this episode, max 4
- All notes within 15 words"""

def build_user_prompt(ep_num, title, text, start_fmt, end_fmt):
    # Limit text to ~3000 chars to keep context manageable
    text_truncated = text[:3000] if len(text) > 3000 else text
    
    return f"""Analyze episode {ep_num} of "{title}" ({start_fmt} - {end_fmt}).

Subtitle text:
{text_truncated}

Output strictly in this JSON format, no other text:
{{
  "episode": {ep_num},
  "title": "{title}",
  "time_range": "{start_fmt}-{end_fmt}",
  "emotion_count": <integer, total main emotion points>,
  "laugh_pct": <integer 0-100>,
  "laugh_types": ["type1", "type2"],
  "laugh_notes": "<key laugh scene, max 15 words>",
  "sweet_pct": <integer 0-100>,
  "sweet_notes": "<sweet scene, max 15 words, null if none>",
  "hype_pct": <integer 0-100>,
  "hype_notes": "<hype scene, max 15 words, null if none>",
  "conflict_pct": <integer 0-100>,
  "conflict_notes": "<conflict scene, max 15 words, null if none>",
  "cry_pct": <integer 0-100>,
  "cry_notes": "<cry scene, max 15 words, null if none>",
  "episode_summary": "<one sentence summary, max 20 words>"
}}"""

def parse_json_output(raw):
    # Try to extract JSON from output
    # Remove <think>...</think> blocks if present
    raw = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except:
            pass
    return None

def validate_and_fix(data):
    """Ensure percentages are valid integers"""
    pct_fields = ['laugh_pct', 'sweet_pct', 'hype_pct', 'conflict_pct', 'cry_pct']
    total = 0
    for f in pct_fields:
        v = data.get(f, 0)
        try:
            data[f] = max(0, min(100, int(v)))
        except:
            data[f] = 0
        total += data[f]
    # Scale down if over 100
    if total > 100:
        scale = 100 / total
        for f in pct_fields:
            data[f] = round(data[f] * scale)
    data['emotion_count'] = max(1, data.get('emotion_count', 3))
    return data

def analyze_episode(ep, video_key, title):
    ep_num = ep['episode']
    cache_file = f"{OUTPUT_DIR}/{video_key}_ep{ep_num:03d}.json"
    
    if os.path.exists(cache_file):
        with open(cache_file) as f:
            return json.load(f)
    
    prompt = build_user_prompt(ep_num, title, ep['text'], ep['start_fmt'], ep['end_fmt'])
    
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "system": SYSTEM_PROMPT,
        "think": False,
        "stream": False,
        "options": {"temperature": 0.2, "num_predict": 500}
    }
    
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=120)
        raw = resp.json().get('response', '')
        result = parse_json_output(raw)
        if result:
            result = validate_and_fix(result)
            result['episode'] = ep_num
            result['video'] = video_key
            result['raw_response'] = raw[:500]
            with open(cache_file, 'w') as f:
                json.dump(result, f, ensure_ascii=False)
            return result
        else:
            print(f"  WARN: Could not parse JSON for {video_key} ep{ep_num}, raw: {raw[:200]}")
            return None
    except Exception as e:
        print(f"  ERROR: {video_key} ep{ep_num}: {e}")
        return None

def process_video(video_key, episodes_file, title):
    with open(episodes_file) as f:
        data = json.load(f)
    
    episodes = data['episodes']
    print(f"\n{'='*50}")
    print(f"Processing {video_key}: {title}")
    print(f"Total episodes: {len(episodes)}")
    
    results = []
    # Process sequentially (Ollama is single-threaded)
    with ThreadPoolExecutor(max_workers=1) as executor:
        futures = {executor.submit(analyze_episode, ep, video_key, title): ep['episode'] 
                   for ep in episodes}
        for future in as_completed(futures):
            ep_num = futures[future]
            result = future.result()
            if result:
                results.append(result)
                print(f"  ✓ {video_key} ep{ep_num:03d}: laugh={result.get('laugh_pct')}% sweet={result.get('sweet_pct')}% hype={result.get('hype_pct')}% conflict={result.get('conflict_pct')}% cry={result.get('cry_pct')}%")
            else:
                print(f"  ✗ {video_key} ep{ep_num:03d}: FAILED")
    
    results.sort(key=lambda x: x['episode'])
    
    # Save combined results
    out_file = f"{OUTPUT_DIR}/{video_key}_results.json"
    with open(out_file, 'w') as f:
        json.dump({"video_key": video_key, "title": title, "results": results}, f, ensure_ascii=False, indent=2)
    
    print(f"Saved {len(results)}/{len(episodes)} episodes to {out_file}")
    return results

if __name__ == "__main__":
    episodes_dir = "/Volumes/Lexar/oneweekoneproject/shortanalysis/episodes"
    
    all_results = {}
    
    # Video 1: 深情誘引 (use en subtitles since both zh/en are same)
    all_results['video1'] = process_video(
        "video1",
        f"{episodes_dir}/video1_en_episodes.json",
        "深情誘引 (Forced Marriage Contract)"
    )
    
    # Video 2: 冒姓琅琊
    all_results['video2'] = process_video(
        "video2", 
        f"{episodes_dir}/video2_en_episodes.json",
        "冒姓琅琊之南朝贵公子 (Impersonating the Lanling Noble)"
    )
    
    # Save all combined
    with open(f"{OUTPUT_DIR}/all_results.json", 'w') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    
    print("\n✅ All analysis complete!")
