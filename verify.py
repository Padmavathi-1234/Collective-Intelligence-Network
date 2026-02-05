"""
Simple verification script to check if the Flask app is running
"""
import requests
import time

def check_server():
    try:
        response = requests.get('http://localhost:5000', timeout=5)
        print(f"✓ Server is running!")
        print(f"  Status Code: {response.status_code}")
        print(f"  Content Length: {len(response.text)} bytes")
        
        # Check for key elements in the HTML
        content = response.text.lower()
        
        checks = {
            "Hero headline": "observe intelligence" in content,
            "Neural canvas": "neural-canvas" in content,
            "CTA button": "enter the network" in content,
            "Workflow section": "how it works" in content,
            "Domains section": "explore domains" in content,
            "Footer tagline": "built for observation" in content,
            "Custom CSS": "style.css" in content,
            "Custom JS": "main.js" in content,
        }
        
        print("\n  Content Checks:")
        for check, result in checks.items():
            status = "✓" if result else "✗"
            print(f"    {status} {check}")
        
        # Check login page
        print("\n✓ Checking login page...")
        login_response = requests.get('http://localhost:5000/login', timeout=5)
        print(f"  Status Code: {login_response.status_code}")
        login_content = login_response.text.lower()
        
        login_checks = {
            "Login title": "access network" in login_content,
            "Email field": 'type="email"' in login_content,
            "Password field": 'type="password"' in login_content,
            "Back link": "back to landing page" in login_content,
        }
        
        print("  Login Page Checks:")
        for check, result in login_checks.items():
            status = "✓" if result else "✗"
            print(f"    {status} {check}")
        
        return True
        
    except requests.exceptions.ConnectionError:
        print("✗ Server is not running or not accessible")
        return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

if __name__ == "__main__":
    print("Checking Flask server at http://localhost:5000...\n")
    time.sleep(2)  # Give server time to start
    check_server()
