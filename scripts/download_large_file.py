from __future__ import annotations

import argparse
import asyncio
import shutil
from pathlib import Path

import httpx


async def download_part(
    client: httpx.AsyncClient,
    url: str,
    path: Path,
    start: int,
    end: int,
    retries: int,
) -> None:
    expected = end - start + 1
    for attempt in range(retries + 1):
        existing = path.stat().st_size if path.exists() else 0
        if existing == expected:
            return
        if existing > expected:
            raise RuntimeError(f"oversized partial file: {path}")

        range_start = start + existing
        headers = {"Range": f"bytes={range_start}-{end}"}
        try:
            async with client.stream("GET", url, headers=headers) as response:
                if response.status_code != 206:
                    raise RuntimeError(f"range request failed with HTTP {response.status_code}")
                content_range = response.headers.get("content-range", "")
                if not content_range.startswith(f"bytes {range_start}-{end}/"):
                    raise RuntimeError(f"unexpected Content-Range: {content_range}")
                with path.open("ab") as handle:
                    async for chunk in response.aiter_bytes(1024 * 1024):
                        handle.write(chunk)
        except httpx.TransportError:
            if attempt == retries:
                raise
            await asyncio.sleep(min(2 ** min(attempt, 5), 30))
            continue

    current = path.stat().st_size if path.exists() else 0
    raise RuntimeError(f"incomplete range {start}-{end}: {current}/{expected}")


async def download(
    url: str,
    output: Path,
    expected_size: int,
    connections: int,
    retries: int,
) -> None:
    part_dir = output.parent / f".{output.name}.parts"
    part_dir.mkdir(parents=True, exist_ok=True)
    part_size = (expected_size + connections - 1) // connections
    ranges = [
        (index, index * part_size, min(((index + 1) * part_size) - 1, expected_size - 1))
        for index in range(connections)
        if index * part_size < expected_size
    ]

    first_part = part_dir / "part-000"
    if output.exists() and not first_part.exists():
        first_expected = ranges[0][2] - ranges[0][1] + 1
        if output.stat().st_size <= first_expected:
            output.replace(first_part)

    timeout = httpx.Timeout(connect=60, read=120, write=60, pool=60)
    limits = httpx.Limits(max_connections=connections, max_keepalive_connections=connections)
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=timeout,
        limits=limits,
    ) as client:
        await asyncio.gather(
            *(
                download_part(
                    client,
                    url,
                    part_dir / f"part-{index:03d}",
                    start,
                    end,
                    retries,
                )
                for index, start, end in ranges
            )
        )

    assembled = output.with_suffix(output.suffix + ".complete")
    with assembled.open("wb") as destination:
        for index, _, _ in ranges:
            with (part_dir / f"part-{index:03d}").open("rb") as source:
                shutil.copyfileobj(source, destination, length=8 * 1024 * 1024)
    if assembled.stat().st_size != expected_size:
        raise RuntimeError(f"assembled size mismatch: {assembled.stat().st_size}/{expected_size}")
    assembled.replace(output)
    shutil.rmtree(part_dir)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("output", type=Path)
    parser.add_argument("--size", type=int, required=True)
    parser.add_argument("--connections", type=int, default=8)
    parser.add_argument("--retries", type=int, default=20)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    asyncio.run(download(args.url, args.output, args.size, args.connections, args.retries))
    print(f"downloaded {args.output} ({args.output.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
