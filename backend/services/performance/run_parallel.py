import asyncio

async def run_parallel(tasks):
    return await asyncio.gather(*tasks)
