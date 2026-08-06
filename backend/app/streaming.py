"""Streaming utilities for Server-Sent Events (SSE) responses."""
from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator


class StreamResponse:
    """SSE streaming response builder."""
    
    def __init__(self):
        self.chunks = []
    
    def add_chunk(self, content: str, done: bool = False):
        """Add a content chunk to the stream."""
        self.chunks.append({
            "content": content,
            "done": done
        })
    
    async def generate(self) -> AsyncIterator[str]:
        """Generate SSE formatted chunks."""
        for chunk in self.chunks:
            yield f"data: {json.dumps(chunk)}\n\n"
            await asyncio.sleep(0)  # Allow other tasks to run


async def stream_chunks(chunks: list[str]) -> AsyncIterator[str]:
    """Stream a list of content chunks as SSE."""
    for i, chunk in enumerate(chunks):
        is_last = i == len(chunks) - 1
        data = {
            "content": chunk,
            "done": is_last
        }
        yield f"data: {json.dumps(data)}\n\n"
        await asyncio.sleep(0)


def create_sse_response(generator: AsyncIterator[str]):
    """Create a StreamingResponse with SSE headers."""
    from starlette.responses import StreamingResponse
    
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )
