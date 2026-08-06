"""Prompt chunking for distributed processing and rate limit avoidance."""
from __future__ import annotations

import asyncio
from typing import Any


def chunk_messages(messages: list[dict], max_chunks: int = 5) -> list[list[dict]]:
    """Split messages into smaller chunks for parallel processing.
    
    Strategy:
    - System message goes to all chunks
    - User message is split by task complexity
    - Each chunk gets a portion of the work
    """
    if not messages:
        return [[]]
    
    system_msgs = [m for m in messages if m.get("role") == "system"]
    user_msgs = [m for m in messages if m.get("role") == "user"]
    
    if not user_msgs:
        return [messages]
    
    # For simple queries, no chunking needed
    last_user_content = user_msgs[-1].get("content", "")
    if len(last_user_content) < 200:
        return [messages]
    
    # Detect if this is a list generation task
    is_list_task = any(keyword in last_user_content.lower() 
                       for keyword in ["generate", "create", "list", "tags", "keywords"])
    
    if not is_list_task:
        return [messages]
    
    # Extract the number of items requested
    import re
    numbers = re.findall(r'\b(\d+)\b', last_user_content)
    requested_count = int(numbers[0]) if numbers else 10
    
    # Only chunk if requesting many items (> 20)
    # Small requests don't benefit from chunking and waste API calls
    if requested_count <= 20:
        return [messages]
    
    # Calculate chunk size
    items_per_chunk = max(5, requested_count // max_chunks)
    num_chunks = min(max_chunks, (requested_count + items_per_chunk - 1) // items_per_chunk)
    
    chunks = []
    for i in range(num_chunks):
        start = i * items_per_chunk + 1
        end = min((i + 1) * items_per_chunk, requested_count)
        
        # Modify the user message for this chunk
        chunk_content = last_user_content.replace(
            str(requested_count),
            f"{end - start + 1} (items {start}-{end})"
        )
        
        chunk_msgs = system_msgs + [
            {
                "role": "user",
                "content": chunk_content
            }
        ]
        chunks.append(chunk_msgs)
    
    return chunks if len(chunks) > 1 else [messages]


async def process_chunks_parallel(
    env,
    chunks: list[list[dict]],
    model: str,
    temperature: float,
    max_tokens: int,
    user_id: str
) -> list[str]:
    """Process multiple chunks in parallel across different accounts.
    
    Returns list of content strings, one per chunk.
    """
    from . import router
    import time
    
    results = []
    tasks = []
    
    # Create parallel tasks, each using a different account
    for chunk_msgs in chunks:
        task = _process_single_chunk(
            env, chunk_msgs, model, temperature, max_tokens, user_id
        )
        tasks.append(task)
    
    # Wait for all chunks to complete
    chunk_results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Extract content from results
    for result in chunk_results:
        if isinstance(result, Exception):
            results.append("")
        elif isinstance(result, dict):
            results.append(result.get("content", ""))
        else:
            results.append("")
    
    return results


async def _process_single_chunk(
    env,
    messages: list[dict],
    model: str,
    temperature: float,
    max_tokens: int,
    user_id: str
) -> dict:
    """Process a single chunk through the router."""
    from . import router
    import time
    
    # Pick an account for this chunk
    account = await router.pick_account(
        env,
        time.strftime("%Y-%m-%d", time.gmtime()),
        int(time.time())
    )
    
    if not account:
        return {"status": 503, "content": "", "account_id": None, "latency_ms": 0, "cache_hit": False}
    
    # Execute the request
    result = await router.execute_request(
        env,
        user_id=user_id,
        account=account,
        payload={
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
    )
    
    return result


def merge_chunk_results(results: list[str], merge_strategy: str = "concat") -> str:
    """Merge results from multiple chunks into final response.
    
    Strategies:
    - concat: Simply concatenate all results
    - list: Merge as a numbered list
    - json: Merge as JSON array (for structured data)
    """
    if merge_strategy == "list":
        # Merge as numbered list
        merged = []
        item_num = 1
        for result in results:
            if not result:
                continue
            lines = result.strip().split("\n")
            for line in lines:
                line = line.strip()
                if line and not line[0].isdigit():
                    merged.append(f"{item_num}. {line}")
                    item_num += 1
                elif line:
                    merged.append(line)
        return "\n".join(merged)
    
    elif merge_strategy == "json":
        # Try to merge as JSON arrays
        import json
        merged_array = []
        for result in results:
            if not result:
                continue
            try:
                data = json.loads(result)
                if isinstance(data, list):
                    merged_array.extend(data)
                else:
                    merged_array.append(data)
            except (json.JSONDecodeError, ValueError):
                # Not valid JSON, append as string
                merged_array.append(result)
        return json.dumps(merged_array)
    
    else:  # concat
        return "\n".join(r for r in results if r)
