from pytube import YouTube
from retrying import retry
import asyncio

url = ['']


async def download_with_coroutine():
    tasks = []
    for item in url:
        tasks.append(asyncio.create_task(download(item)))
        await asyncio.gather(*tasks)

@retry(stop_max_attempt_number=5)
async def download(item):
    YouTube(item).streams.get_highest_resolution().download()

def main():
    asyncio.run(download_with_coroutine())

if __name__ == '__main__':
    main()
