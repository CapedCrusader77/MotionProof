"""Convert rendered PNG frames (f_NNNN.png, every 8th film frame) to frontend/public/home/seq/sNNN.webp."""
import sys
from pathlib import Path

from PIL import Image

src, dst = Path(sys.argv[1]), Path(sys.argv[2]); dst.mkdir(parents=True, exist_ok=True)
for p in sorted(src.glob("f_*.png")):
    i = (int(p.stem[2:]) - 1) // 8
    o = dst / f"s{i:03d}.webp"
    if not o.exists(): Image.open(p).convert("RGB").save(o, quality=80)
print(len(list(dst.glob("*.webp"))))
