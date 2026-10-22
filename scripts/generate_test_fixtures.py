import gzip
from pathlib import Path


def main() -> None:
    output = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
    output.mkdir(parents=True, exist_ok=True)
    grayscale_row = b"".join(bytes([(level << 4) | level]) * 40 for level in range(15, -1, -1))
    checkerboard_rows = (
        (b"\xff" * 4 + b"\x00" * 4) * 80,
        (b"\x00" * 4 + b"\xff" * 4) * 80,
    )
    patterns = {
        "grayscale": grayscale_row * 720,
        "checkerboard": b"".join(checkerboard_rows[(y // 8) % 2] for y in range(720)),
    }
    for name, pattern in patterns.items():
        frame = bytearray(pattern)
        frame[0], frame[639], frame[-640], frame[-1] = 0xEF, 0x01, 0xDF, 0x02
        (output / f"{name}.frame.gz").write_bytes(gzip.compress(bytes(frame), mtime=0))


if __name__ == "__main__":
    main()
