"""Retired vendor diagnostic; current product calls use DeepSeek only."""

import asyncio


async def main() -> int:
    print("This legacy diagnostic is disabled. Use python -m app.scripts.check_deepseek instead.")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
