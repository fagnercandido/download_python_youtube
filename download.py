from pytube import YouTube
from retrying import retry

url = ['myVideos']


def main():
    for item in url:
        download(item)

@retry(stop_max_attempt_number=5)
def download(item):
    YouTube(item).streams.get_highest_resolution().download()

if __name__ == '__main__':
    main()
