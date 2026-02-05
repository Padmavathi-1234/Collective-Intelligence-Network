import requests
import json

def test_perplexica():
    hosts = ["localhost", "127.0.0.1"]
    ports = [3001, 3000, 8080, 8000]
    
    for host in hosts:
        for port in ports:
            url = f"http://{host}:{port}/api/search"
            print(f"Trying {url}...")
            try:
                response = requests.post(url, json={
                    "query": "test",
                    "mode": "normal",
                    "focus": "internet"
                }, headers={'Content-Type': 'application/json'}, timeout=2)
                
                if response.status_code == 200:
                    print(f"SUCCESS! Found Perplexica at {url}")
                    print("Response Keys:", list(response.json().keys()))
                    return
                else:
                    print(f"Failed with status {response.status_code}")
            except Exception as e:
                # print(f"Failed: {e}")
                pass
    
    print("Could not find Perplexica on any common port.")

if __name__ == "__main__":
    test_perplexica()
