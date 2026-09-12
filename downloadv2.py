import asyncio
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from mutagen.id3 import APIC, ID3
from mutagen.mp3 import MP3
from pytubefix import Playlist
from retrying import retry
from ytmusicapi import YTMusic

WATCH_URL = 'https://www.youtube.com/watch?v={}'
COVER_SIZE = 1200

ALBUM_URLS = [
    "https://music.youtube.com/playlist?list=OLAK5uy_nhl4_yK3nHsUTBKScSVV36ExzCGxt6rKk",
    "https://music.youtube.com/playlist?list=OLAK5uy_kTgeLyC9VzFDmmtaW1xunJFV4xLHMUCxk",
    "https://music.youtube.com/playlist?list=OLAK5uy_lfa8yhzk313tsyAo4D9hM4GSvfL6ZCpGI",
    "https://music.youtube.com/playlist?list=OLAK5uy_kZZ5YDZTiKs-Rh6FiOIGU-cgzkdVqsJqk",
    "https://music.youtube.com/playlist?list=OLAK5uy_lsTDMdd7Ct2PbVNrY-SkVWktDBNLQDKSE",
    "https://music.youtube.com/playlist?list=OLAK5uy_kJUBIVR54Z3drIK-exqLKGdAIB71rVV84",
    "https://music.youtube.com/playlist?list=OLAK5uy_nWqxGYrVHOwOzlQNq1YJLWdknrmKyWqxk",
    "https://music.youtube.com/playlist?list=OLAK5uy_npEu1QiW3TMtGtzKH_sjvPhCEoOFlHwH0",
    "https://music.youtube.com/playlist?list=OLAK5uy_m0TFnAZY3SsRd4ibNl2FT0N7uN2kzsJ-g",
    "https://music.youtube.com/playlist?list=OLAK5uy_nWHmQ-qT0t6_tPKQ5ulbYzsl1fLdEyqdQ",
    "https://music.youtube.com/playlist?list=OLAK5uy_khf5lK1bJwvANC_wkdybZyN1FSuT_vTQ8",
    "https://music.youtube.com/playlist?list=OLAK5uy_nesu7nFCfeNrOB7m3XEt-yE7zBtuTdyyg",
    "https://music.youtube.com/playlist?list=OLAK5uy_nl3bvmGxJSYS22r9FOEoottNULhljTfn8",
    "https://music.youtube.com/playlist?list=OLAK5uy_mRvEVcedcrOs3O2t2PpWpq_cLy2pV-DBU",
    "https://music.youtube.com/playlist?list=OLAK5uy_lGRQmmODmg_WuvlSBKORULtbgqhQECxuM",
    "https://music.youtube.com/playlist?list=OLAK5uy_nET_TrdyRsRRrWDa5RaLGFplP3TJU2FDk",
    "https://music.youtube.com/playlist?list=OLAK5uy_kZlus5525yv4pDYR5l7OERqXCFrBVV8TI",
    "https://music.youtube.com/playlist?list=OLAK5uy_nsG0vyTKAGvdY8vRH5pQwbz2flxh-EHeg",
    "https://music.youtube.com/playlist?list=OLAK5uy_m-MbuPvYM4BFPsPXDGsUnezJ9fxkSsGQ0",
    "https://music.youtube.com/playlist?list=OLAK5uy_nOX2mMux6lVVPDZSt7uJsnV6Iujsp4LoI",
    "https://music.youtube.com/playlist?list=OLAK5uy_n9zNQxISYbMKoF5i1Nkc3_Iuu8YK8ZP2A",
    "https://music.youtube.com/playlist?list=OLAK5uy_kFV0jYYEptxqZFb3PFUE2LFRq_N2-4xLM",
    "https://music.youtube.com/playlist?list=OLAK5uy_nIUuvKqXQcx3CR_3Ad8Nz_rtxjb09_xi0",
    "https://music.youtube.com/playlist?list=OLAK5uy_ka9Glv8EU02NIN4bQbAP9Z8_iox_EC4e4",
    "https://music.youtube.com/playlist?list=OLAK5uy_m85bg9SPNGTZxFJh6X0XOiof126Tjzd-Y",
    "https://music.youtube.com/playlist?list=OLAK5uy_mx2KnrcN2AQJlRuXBLNi4PtzseKSOf6AA",
    "https://music.youtube.com/playlist?list=OLAK5uy_l0wswgL0drBpxw127TrnyfsTkGxjI5LVM",
    "https://music.youtube.com/playlist?list=OLAK5uy_lhRsNtgO9SmUb1qaCHSYlZSPg4bMd7h90",
]

BASE_DIR = Path('downloads')
MP3_BITRATE = '320k'
TRACK_CONCURRENCY = 6

ytmusic = YTMusic()


def sanitize(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', name).strip()
    return name or 'untitled'


def _album_name(album: dict) -> str:
    artist = album['artists'][0]['name'] if album.get('artists') else 'Various'
    return f"{artist} - {album['title']}"


def _album_tracks(album: dict) -> list[tuple[str, str]]:
    tracks = []
    for track in album.get('tracks', []):
        video_id = track.get('videoId')
        if video_id and track.get('isAvailable', True):
            tracks.append((track.get('title'), WATCH_URL.format(video_id)))
    return tracks


def _album_cover_url(album: dict) -> str | None:
    thumbs = album.get('thumbnails') or []
    if not thumbs:
        return None
    url = thumbs[-1]['url']
    return re.sub(r'=w\d+-h\d+', f'=w{COVER_SIZE}-h{COVER_SIZE}', url)


def resolve_to_tracks(url: str) -> tuple[str, str | None, list[tuple[str | None, str]]]:
    parsed = urlparse(url)
    path = parsed.path or ''

    if 'playlist' in path:
        playlist_id = parse_qs(parsed.query).get('list', [''])[0]
        try:
            browse_id = ytmusic.get_album_browse_id(playlist_id)
            album = ytmusic.get_album(browse_id)
            return _album_name(album), _album_cover_url(album), _album_tracks(album)
        except Exception:
            pl = Playlist(url)
            return pl.title, None, [(None, u) for u in pl.video_urls]

    if '/browse/' in path:
        browse_id = path.split('/browse/')[-1]
        album = ytmusic.get_album(browse_id)
    elif '/search' in path:
        query = parse_qs(parsed.query).get('q', [''])[0]
        results = ytmusic.search(query, filter='albums')
        if not results:
            raise RuntimeError(f'nenhum álbum encontrado para: {query}')
        album = ytmusic.get_album(results[0]['browseId'])
    else:
        raise ValueError(f'URL não suportada: {url}')

    return _album_name(album), _album_cover_url(album), _album_tracks(album)


def fetch_cover(cover_url: str, album_dir: Path) -> bytes | None:
    req = urllib.request.Request(cover_url, headers={'User-Agent': 'Mozilla/5.0'})
    for attempt in range(3):
        try:
            data = urllib.request.urlopen(req, timeout=30).read()
            (album_dir / 'cover.jpg').write_bytes(data)
            return data
        except Exception as e:
            if attempt == 2:
                print(f'  [aviso] capa não baixada: {e}')
                return None
            time.sleep(1.5)
    return None


def embed_cover(mp3_path: Path, cover: bytes, force: bool = False) -> bool:
    try:
        audio = MP3(mp3_path, ID3=ID3)
        if audio.tags is None:
            audio.add_tags()
        if audio.tags.getall('APIC') and not force:
            return False
        audio.tags.delall('APIC')
        audio.tags.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=cover))
        audio.save(v2_version=3)
        return True
    except Exception as e:
        print(f'  [aviso] capa não embutida em {mp3_path.name}: {e}')
        return False


def _tokens(text: str) -> set[str]:
    return set(re.findall(r'\w+', text.lower()))


MATCH_THRESHOLD = 0.7


def _best_album_match(query: str, want_title: set[str]) -> tuple[dict | None, float]:
    if not want_title:
        return None, 0.0
    results = []
    for attempt in range(3):
        try:
            results = ytmusic.search(query, filter='albums', limit=5)
            break
        except Exception as e:
            if attempt == 2:
                print(f'  [aviso] busca falhou p/ "{query}": {e}')
                return None, 0.0
            time.sleep(1.5)
    best, best_score = None, 0.0
    for r in results:
        score = len(want_title & _tokens(r.get('title', ''))) / len(want_title)
        if score > best_score:
            best, best_score = r, score
    return best, best_score


def _mp3_has_cover(mp3_path: Path) -> bool:
    try:
        audio = MP3(mp3_path, ID3=ID3)
        return bool(audio.tags and audio.tags.getall('APIC'))
    except Exception:
        return False


def _extract_embedded_cover(mp3_path: Path) -> bytes | None:
    try:
        audio = MP3(mp3_path, ID3=ID3)
        pics = audio.tags.getall('APIC') if audio.tags else []
        return pics[0].data if pics else None
    except Exception:
        return None


def find_cover_for_folder(album_dir: Path) -> bytes | None:
    """Descobre a capa de uma pasta 'Artista - Álbum': cover.jpg > capa já
    embutida numa faixa > busca no YouTube Music. Sempre salva cover.jpg."""
    existing = album_dir / 'cover.jpg'
    if existing.exists():
        return existing.read_bytes()

    # reaproveita capa já embutida em alguma faixa (evita rede)
    for m in sorted(album_dir.glob('*.mp3')):
        data = _extract_embedded_cover(m)
        if data:
            existing.write_bytes(data)
            return data

    folder_name = album_dir.name
    title_part = folder_name.split(' - ', 1)[1] if ' - ' in folder_name else folder_name
    want_title = _tokens(title_part)

    # busca pelo nome completo e só pelo título; escolhe o melhor score dos dois
    best, best_score = None, 0.0
    for query in dict.fromkeys([folder_name, title_part]):
        cand, score = _best_album_match(query, want_title)
        if score > best_score:
            best, best_score = cand, score

    if best and best_score >= MATCH_THRESHOLD:
        cover_url = _album_cover_url(best)
        if cover_url:
            return fetch_cover(cover_url, album_dir)  # fetch_cover salva cover.jpg
    return None


def repair_covers() -> None:
    """Garante que toda pasta tenha cover.jpg e que toda faixa tenha capa embutida."""
    if not BASE_DIR.exists():
        return
    folders = sorted(p for p in BASE_DIR.iterdir()
                     if p.is_dir() and not p.name.startswith('__') and any(p.glob('*.mp3')))

    print(f'\n=== reparo de capas: {len(folders)} pasta(s) ===')
    sem_capa = []
    for album_dir in folders:
        mp3s = sorted(album_dir.glob('*.mp3'))
        missing = [m for m in mp3s if not _mp3_has_cover(m)]
        has_cover_jpg = (album_dir / 'cover.jpg').exists()
        if not missing and has_cover_jpg:
            continue

        cover = find_cover_for_folder(album_dir)
        if not cover:
            sem_capa.append(album_dir.name)
            print(f'  [SEM CAPA] {album_dir.name} ({len(missing)} faixas sem capa)')
            continue
        added = sum(embed_cover(m, cover) for m in missing)
        print(f'  [ok] {album_dir.name}: +{added} faixa(s), cover.jpg garantido')

    if sem_capa:
        print(f'\n⚠ {len(sem_capa)} pasta(s) sem capa encontrada (resolver manual):')
        for n in sem_capa:
            print(f'   - {n}')


@retry(stop_max_attempt_number=5, wait_fixed=2000)
def download_track(video_url: str, album_dir: Path, title: str | None = None,
                   cover: bytes | None = None) -> None:
    safe = sanitize(title) if title else None
    target = album_dir / f'{safe}.mp3' if safe else None

    if target and target.exists():
        if cover:
            embed_cover(target, cover)
        print(f'  [skip] {safe}')
        return

    outtmpl = f'{safe}.%(ext)s' if safe else '%(title)s.%(ext)s'
    print(f'  [get] {title or video_url}')
    result = subprocess.run(
        [
            sys.executable, '-m', 'yt_dlp',
            '--no-playlist',
            '--quiet', '--no-warnings',
            '--extract-audio',
            '--audio-format', 'mp3',
            '--audio-quality', MP3_BITRATE,
            '--embed-metadata',
            '--no-overwrites',
            '-o', str(album_dir / outtmpl),
            video_url,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f'yt-dlp falhou ({result.returncode})')

    if cover and target and target.exists():
        embed_cover(target, cover)


async def download_album(url: str) -> None:
    try:
        album_name, cover_url, tracks = resolve_to_tracks(url)
    except Exception as e:
        print(f'\n[ERRO resolução] {url}: {e}')
        return

    album_dir = BASE_DIR / sanitize(album_name)
    album_dir.mkdir(parents=True, exist_ok=True)

    print(f'\n=== {album_name} ({len(tracks)} faixas) -> {album_dir} ===')

    cover = fetch_cover(cover_url, album_dir) if cover_url else None

    loop = asyncio.get_running_loop()
    sem = asyncio.Semaphore(TRACK_CONCURRENCY)

    async def bounded(title: str | None, vurl: str) -> None:
        async with sem:
            try:
                await loop.run_in_executor(None, download_track, vurl, album_dir, title, cover)
            except Exception as e:
                print(f'  [ERRO] {vurl}: {e}')

    await asyncio.gather(*[bounded(t, v) for t, v in tracks])


async def main_async() -> None:
    BASE_DIR.mkdir(exist_ok=True)
    print(f'{len(ALBUM_URLS)} álbuns na fila')
    for i, url in enumerate(ALBUM_URLS, 1):
        print(f'\n[{i}/{len(ALBUM_URLS)}]', end=' ')
        await download_album(url)
    print('\n✓ downloads concluídos')

    repair_covers()
    print('\n✓ concluído')


def main() -> None:
    asyncio.run(main_async())


if __name__ == '__main__':
    main()
