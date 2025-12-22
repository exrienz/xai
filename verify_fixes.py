import asyncio
import httpx
from main import app, is_censored
import os

# Mock environment for testing
os.environ["CODE_X_KEY"] = "test-secret-key"
# Ensure we have a secret key for sessions
os.environ["CSRF_SECRET_KEY"] = "test-csrf-secret"

async def test_security_headers():
    print("Testing Security Headers...")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/")
        if response.headers.get("x-frame-options") == "DENY":
            print("✅ X-Frame-Options: DENY found")
        else:
            print(f"❌ X-Frame-Options missing or invalid: {response.headers.get('x-frame-options')}")

async def test_auth_bypass():
    print("\nTesting Auth Enforcement...")
    # 1. No Header
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/ask", json={"question": "ping"})
        if response.status_code in [401, 403, 422, 500]:
            print(f"✅ Auth blocked request without key (Status: {response.status_code})")
        else:
            print(f"❌ Request without key allowed (Status: {response.status_code})")

    # 2. Wrong Header
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/ask", json={"question": "ping"}, headers={"code-x-key": "wrong"})
        if response.status_code in [401, 403]:
            print(f"✅ Auth blocked request with wrong key (Status: {response.status_code})")
        else:
            print(f"❌ Request with wrong key allowed (Status: {response.status_code})")

async def test_censorship_detection():
    print("\nTesting Censorship Detection...")
    long_text = "A" * 500 + " I cannot fulfill this request."
    if is_censored(long_text):
        print("✅ Detected censorship at end of long text")
    else:
        print("❌ Failed to detect censorship at end of long text")

async def test_csrf_protection():
    print("\nTesting CSRF Protection...")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # 1. Get initial page to set cookie and get token (we'll scrape it lightly or assume logic)
        # Since we can't easily scrape HTML here without BS4, we might need a workaround.
        # However, for testing, we can inspect the session since we are in-process? 
        # Actually, with ASGITransport, cookies are handled by the client if we reuse it.
        
        # But we need to extract the token from the response HTML.
        resp = await client.get("/")
        cookies = resp.cookies
        
        # Extract token from HTML (hacky search)
        # Searching for value="..." inside the hidden input
        html = resp.text
        import re
        match = re.search(r'name="csrf_token" value="([^"]+)"', html)
        if not match:
            print("❌ Could not find CSRF token in index page")
            return
            
        token = match.group(1)
        print(f"   Token found: {token[:10]}...")
        
        # 2. Valid Request (Token + Cookie)
        resp_valid = await client.post("/web-ask", data={"question": "hi", "csrf_token": token}, cookies=cookies)
        # Expecting 200 or 500 (if orchestration fails), but NOT 403
        if resp_valid.status_code == 403:
             print(f"❌ Valid CSRF request rejected (Status: {resp_valid.status_code})")
        else:
             print(f"✅ Valid CSRF request accepted (Status: {resp_valid.status_code})")

        # 3. Invalid Token
        resp_invalid = await client.post("/web-ask", data={"question": "hi", "csrf_token": "wrong"}, cookies=cookies)
        if resp_invalid.status_code == 403:
             print(f"✅ Invalid CSRF token rejected (Status: {resp_invalid.status_code})")
        else:
             print(f"❌ Invalid CSRF token allowed (Status: {resp_invalid.status_code})")
             
        # 4. Missing Cookie (Simulate CSRF attack from another site)
        # Create new client to clear cookies
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client2:
             # Try to use the VALID token we got earlier, but without the session cookie
             resp_attack = await client2.post("/web-ask", data={"question": "hi", "csrf_token": token})
             if resp_attack.status_code == 403:
                 print(f"✅ CSRF Attack (valid token, no cookie) rejected (Status: {resp_attack.status_code})")
             else:
                 print(f"❌ CSRF Attack allowed (Status: {resp_attack.status_code})")

async def main():
    await test_security_headers()
    await test_auth_bypass()
    await test_censorship_detection()
    await test_csrf_protection()

if __name__ == "__main__":
    asyncio.run(main())
