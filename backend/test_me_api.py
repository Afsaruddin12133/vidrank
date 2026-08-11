import urllib.request
import json

def check_me():
    url = "https://vidrank-backend.fahad288ali.workers.dev/v1/me"
    print(f"Fetching live API endpoint with Browser User-Agent: {url}")
    
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            print("Status:", resp.status)
            print("Body:", resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"HTTP Status Code: {e.code}")
        print("Response Body:", e.read().decode())

if __name__ == "__main__":
    check_me()
