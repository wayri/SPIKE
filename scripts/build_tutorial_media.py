# SPDX-License-Identifier: Apache-2.0
"""Record real SPIKE actions, then add tutorial captions and encode MP4/GIF.

Requires a local ffmpeg binary and Pillow. Recording uses a bounded screen
region; inspect all output for unrelated windows before publication.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'build/tutorial-media'
OUT = ROOT / 'docs/tutorial-media'
FFMPEG = WORK / 'tools/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe'


def record(args):
    folder = WORK / 'raw'
    folder.mkdir(parents=True, exist_ok=True)
    meta = {'id': args.id, 'title': args.title, 'subtitle': args.subtitle,
            'started': time.time(), 'source': 'native SPIKE v0.3.5',
            'steps': [{'time': 0, 'text': args.subtitle}]}
    (folder / f'{args.id}.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')
    cmd = [str(FFMPEG), '-hide_banner', '-loglevel', 'warning', '-f', 'gdigrab',
           '-framerate', '12', '-offset_x', '0', '-offset_y', '0',
           '-video_size', '3000x1800', '-i', 'desktop', '-t', '600',
           '-vf', 'scale=1600:-2', '-c:v', 'libx264', '-preset', 'ultrafast',
           '-crf', '18', '-pix_fmt', 'yuv420p', '-y', str(folder / f'{args.id}.mp4')]
    stop = folder / f'{args.id}.stop'
    if stop.exists():
        raise ValueError('Use a fresh recording ID; an existing stop marker is present')
    with (folder / f'{args.id}.log').open('w', encoding='utf-8') as log:
        child = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=log, stderr=log,
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        while child.poll() is None and not stop.exists():
            time.sleep(0.2)
        if child.poll() is None:
            child.stdin.write(b'q\n')
            child.stdin.flush()
        return child.wait(timeout=30)


def mark(args):
    path = WORK / 'raw' / f'{args.id}.json'
    meta = json.loads(path.read_text(encoding='utf-8'))
    elapsed = round(time.time() - meta['started'], 3)
    meta['steps'].append({'time': elapsed, 'text': args.text})
    path.write_text(json.dumps(meta, indent=2), encoding='utf-8')
    print(f'{args.id}: {elapsed:.1f}s - {args.text}')


def render(args):
    from PIL import Image, ImageDraw, ImageFont
    folder = WORK / 'raw'
    meta = json.loads((folder / f'{args.id}.json').read_text(encoding='utf-8'))
    for name in ('gifs', 'videos', 'posters'):
        (OUT / name).mkdir(parents=True, exist_ok=True)
    temp = WORK / 'captions' / args.id
    temp.mkdir(parents=True, exist_ok=True)
    title_font = ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf', 28)
    body_font = ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf', 22)
    # Caption strip is added below the recorded app, never across its controls.
    steps = meta['steps']
    for index, step in enumerate(steps):
        im = Image.new('RGB', (1600, 106), '#102530')
        d = ImageDraw.Draw(im)
        d.rectangle((0, 0, 1600, 3), fill='#40c9c0')
        d.text((26, 12), meta['title'], font=title_font, fill='#f6f8fb')
        d.text((26, 53), step['text'], font=body_font, fill='#c4d9e2')
        d.text((1380, 16), 'SPIKE tutorial', font=body_font, fill='#40c9c0')
        im.save(temp / f'{index:02}.png')
    cmd = [str(FFMPEG), '-hide_banner', '-loglevel', 'error', '-i', str(folder / f'{args.id}.mp4')]
    for index in range(len(steps)):
        cmd += ['-loop', '1', '-i', str(temp / f'{index:02}.png')]
    filters = ['[0:v]pad=iw:ih+106:0:0:color=0x102530[base]']
    previous = 'base'
    for index, step in enumerate(steps):
        end = steps[index + 1]['time'] if index + 1 < len(steps) else 10000
        output = f'c{index}'
        filters.append(f'[{previous}][{index+1}:v]overlay=0:H-106:enable=\'between(t,{step["time"]},{end})\':shortest=1[{output}]')
        previous = output
    # Long operator pauses can be excluded using a deliberate start/end trim.
    if args.start or args.end:
        end = f':end={args.end}' if args.end else ''
        filters.append(f'[{previous}]trim=start={args.start}{end},setpts=PTS-STARTPTS[trimmed]')
        previous = 'trimmed'
    target = OUT / 'videos' / f'{args.id}.mp4'
    cmd += ['-filter_complex', ';'.join(filters), '-map', f'[{previous}]', '-an',
            '-r', '12', '-c:v', 'libx264', '-preset', 'medium', '-crf', '24',
            '-pix_fmt', 'yuv420p', '-movflags', '+faststart', '-y', str(target)]
    subprocess.run(cmd, check=True)
    # Reduced-size README GIF; full-resolution MP4 is the readable tutorial.
    subprocess.run([str(FFMPEG), '-hide_banner', '-loglevel', 'error', '-i', str(target),
                    '-vf', 'fps=6,scale=1000:-2:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128[p];[s1][p]paletteuse=dither=bayer:bayer_scale=3',
                    '-loop', '0', '-y', str(OUT / 'gifs' / f'{args.id}.gif')], check=True)
    subprocess.run([str(FFMPEG), '-hide_banner', '-loglevel', 'error', '-ss', '1', '-i', str(target),
                    '-frames:v', '1', '-y', str(OUT / 'posters' / f'{args.id}.png')], check=True)
    print(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    rec = commands.add_parser('record')
    rec.add_argument('id'); rec.add_argument('title'); rec.add_argument('subtitle')
    marker = commands.add_parser('mark')
    marker.add_argument('id'); marker.add_argument('text')
    stopper = commands.add_parser('stop')
    stopper.add_argument('id')
    enc = commands.add_parser('render')
    enc.add_argument('id'); enc.add_argument('--start', type=float, default=0)
    enc.add_argument('--end', type=float)
    args = parser.parse_args()
    if args.command == 'record': return record(args)
    if args.command == 'mark': return mark(args)
    if args.command == 'stop':
        (WORK / 'raw' / f'{args.id}.stop').touch()
        return 0
    return render(args)


if __name__ == '__main__':
    raise SystemExit(main())
