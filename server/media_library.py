"""Bounded, normalized image uploads; opaque IDs never become arbitrary paths."""
import io
import json
import os
from pathlib import Path
import re
import threading
import uuid
from PIL import Image, ImageOps

MAX_UPLOAD = 12 * 1024 * 1024


class MediaLibrary:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.lock = threading.RLock()

    def path(self, ident):
        if not isinstance(ident, str) or not re.fullmatch('[a-f0-9]{32}', ident):
            raise ValueError('Unknown picture.')
        return self.directory / (ident + '.png')

    def list(self):
        with self.lock:
            result = []
            for path in sorted(self.directory.glob('*.json')):
                try:
                    item = json.loads(path.read_text())
                    if self.path(item['id']).exists():
                        result.append(item)
                except (OSError, ValueError, KeyError):
                    continue
            return sorted(result, key=lambda item: (item['added_at'], item['id']))

    def add(self, body, name):
        if not body or len(body) > MAX_UPLOAD:
            raise ValueError('Choose an image smaller than 12 MB.')
        try:
            with Image.open(io.BytesIO(body)) as source:
                if source.format not in ('JPEG', 'PNG', 'WEBP') or source.width * source.height > 24000000:
                    raise ValueError('Use JPEG, PNG or WebP, up to 24 megapixels.')
                source.load()
                picture = ImageOps.exif_transpose(source).convert('RGBA')
                picture.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
                background = Image.new('RGBA', picture.size, 'white')
                background.alpha_composite(picture)
                picture = background.convert('RGB')
        except (OSError, Image.DecompressionBombError) as exc:
            raise ValueError('This picture could not be read.') from exc
        with self.lock:
            if len(self.list()) >= 100:
                raise ValueError('The library holds up to 100 pictures. Delete one first.')
            self.directory.mkdir(parents=True, exist_ok=True)
            ident = uuid.uuid4().hex
            path = self.path(ident)
            picture.save(path, format='PNG')
            import time
            item = {'id': ident, 'name': str(name).strip()[:100] or 'Untitled picture',
                    'width': picture.width, 'height': picture.height, 'added_at': time.time()}
            try:
                path.with_suffix('.json').write_text(json.dumps(item))
            except OSError:
                path.unlink(missing_ok=True)
                raise
            return item

    def delete(self, ident):
        with self.lock:
            path = self.path(ident)
            if not path.exists():
                raise ValueError('Picture was already deleted.')
            path.unlink()
            path.with_suffix('.json').unlink(missing_ok=True)

    def image(self, ident):
        with self.lock:
            with Image.open(self.path(ident)) as source:
                return source.copy()
