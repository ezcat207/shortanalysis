import re
import json
import os

def parse_srt(filepath):
    """Parse SRT file into list of (start_sec, end_sec, text) tuples"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    blocks = re.split(r'\n\n+', content.strip())
    subtitles = []
    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) < 3:
            continue
        # Find timestamp line
        ts_line = None
        ts_idx = 0
        for i, line in enumerate(lines):
            if '-->' in line:
                ts_line = line
                ts_idx = i
                break
        if not ts_line:
            continue
        
        m = re.match(r'(\d+):(\d+):(\d+),(\d+)\s*-->\s*(\d+):(\d+):(\d+),(\d+)', ts_line)
        if not m:
            continue
        
        start_sec = int(m.group(1))*3600 + int(m.group(2))*60 + int(m.group(3)) + int(m.group(4))/1000
        end_sec = int(m.group(5))*3600 + int(m.group(6))*60 + int(m.group(7)) + int(m.group(8))/1000
        
        text_lines = [l for l in lines[ts_idx+1:] if l.strip()]
        text = ' '.join(text_lines)
        if text:
            subtitles.append((start_sec, end_sec, text))
    
    return subtitles

def split_into_episodes(subtitles, episode_duration=480):
    """Split subtitles into episodes of ~episode_duration seconds (8 min default)"""
    if not subtitles:
        return []
    
    total_duration = subtitles[-1][1]
    num_episodes = max(1, round(total_duration / episode_duration))
    actual_duration = total_duration / num_episodes
    
    episodes = []
    for ep_idx in range(num_episodes):
        ep_start = ep_idx * actual_duration
        ep_end = (ep_idx + 1) * actual_duration
        
        ep_subs = [(s, e, t) for s, e, t in subtitles if s >= ep_start and s < ep_end]
        
        if ep_subs:
            text = ' '.join(t for _, _, t in ep_subs)
            episodes.append({
                "episode": ep_idx + 1,
                "start_time": ep_start,
                "end_time": ep_end,
                "start_fmt": f"{int(ep_start//3600):02d}:{int((ep_start%3600)//60):02d}:{int(ep_start%60):02d}",
                "end_fmt": f"{int(ep_end//3600):02d}:{int((ep_end%3600)//60):02d}:{int(ep_end%60):02d}",
                "subtitle_count": len(ep_subs),
                "text": text
            })
    
    return episodes

# Process both videos
base_dir = "/Volumes/Lexar/oneweekoneproject/shortanalysis/video_downloads"
output_dir = "/Volumes/Lexar/oneweekoneproject/shortanalysis/episodes"
os.makedirs(output_dir, exist_ok=True)

videos = {
    "video1_zh": {
        "file": f"{base_dir}/Sgnlchs9LGU/【FULL】女孩被迫嫁給30歲高冷總裁，一紙契約開始的婚姻，他的貼心卻一點點瓦解她的防線，彼此的心越靠越近...《深情誘引》姊妹篇《盛夏芬德拉》熱播來襲💕💌.zh-Hant.srt",
        "title": "深情誘引（中文）"
    },
    "video1_en": {
        "file": f"{base_dir}/Sgnlchs9LGU/【FULL】女孩被迫嫁給30歲高冷總裁，一紙契約開始的婚姻，他的貼心卻一點點瓦解她的防線，彼此的心越靠越近...《深情誘引》姊妹篇《盛夏芬德拉》熱播來襲💕💌.en.srt",
        "title": "深情誘引（英文）"
    },
    "video2_en": {
        "file": f"{base_dir}/Pt9I5R25L54/【全集FULL】《冒姓琅琊之南朝贵公子》｜ ENG SUB ｜ 金泽&李汐微#薄荷听书 #cdrama #latest #热门短剧 #都市 #重生 #逆袭 #现代 #甜宠.en.srt",
        "title": "冒姓琅琊之南朝贵公子（英文）"
    }
}

for key, info in videos.items():
    print(f"\nProcessing {key}: {info['title']}")
    subs = parse_srt(info['file'])
    episodes = split_into_episodes(subs, episode_duration=480)
    
    print(f"  Total subtitles: {len(subs)}")
    print(f"  Total duration: {subs[-1][1]/3600:.2f}h")
    print(f"  Split into {len(episodes)} episodes")
    
    # Save episodes JSON
    out_path = f"{output_dir}/{key}_episodes.json"
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump({
            "title": info["title"],
            "total_episodes": len(episodes),
            "episodes": episodes
        }, f, ensure_ascii=False, indent=2)
    
    # Also save individual episode text files for NotebookLM
    ep_dir = f"{output_dir}/{key}"
    os.makedirs(ep_dir, exist_ok=True)
    for ep in episodes:
        ep_file = f"{ep_dir}/ep{ep['episode']:03d}_{ep['start_fmt'].replace(':','-')}.txt"
        with open(ep_file, 'w', encoding='utf-8') as f:
            f.write(f"剧名: {info['title']}\n")
            f.write(f"第{ep['episode']}集 ({ep['start_fmt']} - {ep['end_fmt']})\n")
            f.write(f"字幕数: {ep['subtitle_count']}\n\n")
            f.write(ep['text'])
    
    print(f"  Saved to {out_path}")

print("\nPreprocessing complete!")
