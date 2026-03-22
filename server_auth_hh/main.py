import asyncio
import uuid
import base64
import httpx
import os
import json
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from playwright.async_api import async_playwright
from urllib.parse import urlsplit, parse_qs

app = FastAPI()

# HH Android App Keys
ANDROID_CLIENT_ID = "HIOMIAS39CA9DICTA7JIO64LQKQJF5AGIK74G9ITJKLNEDAOH5FHS5G1JI7FOEGD"
ANDROID_CLIENT_SECRET = "V9M870DE342BGHFRUJ5FTCGCUA1482AN0DI8C5TFI9ULMA89H10N60NOP8I4JMVS"
HH_ANDROID_SCHEME = "hhandroid"

# Selectors
SEL_LOGIN_INPUT = 'input[data-qa="login-input-username"]'
SEL_PIN_CODE_INPUT = 'input[data-qa="magritte-pincode-input-field"]'
SEL_CAPTCHA_IMAGE = 'img[data-qa="account-captcha-picture"]'
SEL_CAPTCHA_INPUT = 'input[data-qa="account-captcha-input"]'
SEL_PASSWORD_INPUT = 'input[data-qa="login-input-password"]'
SEL_EXPAND_PASSWORD = 'button[data-qa="expand-login-by_password"]'

sessions = {}

class LoginPhoneRequest(BaseModel):
    phone: str

class LoginCodeRequest(BaseModel):
    session_id: str
    code: str

class LoginPasswordRequest(BaseModel):
    session_id: str
    password: str

class LoginFullRequest(BaseModel):
    phone: str
    password: str

class LoginCaptchaRequest(BaseModel):
    session_id: str
    captcha_text: str

async def save_debug_screenshot(page, name="debug_last_error"):
    try:
        await page.screenshot(path=f"{name}.png")
        print(f"Debug screenshot saved to {name}.png")
    except: pass

async def check_for_captcha(session_id: str):
    session = sessions[session_id]
    page = session["page"]
    try:
        captcha_element = await page.wait_for_selector(SEL_CAPTCHA_IMAGE, timeout=3000, state="visible")
        if captcha_element:
            img_bytes = await captcha_element.screenshot()
            session["captcha_image"] = base64.b64encode(img_bytes).decode('utf-8')
            session["status"] = "waiting_captcha"
            return True
    except: pass
    return False

async def start_session(session_id: str):
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=True)
    device = playwright.devices["Galaxy A55"]
    context = await browser.new_context(**device)
    page = await context.new_page()
    code_future = asyncio.get_event_loop().create_future()

    async def handle_request(request):
        url = request.url
        if url.startswith(f"{HH_ANDROID_SCHEME}://"):
            if not code_future.done():
                sp = urlsplit(url)
                code = parse_qs(sp.query).get("code", [None])[0]
                code_future.set_result(code)
    page.on("request", handle_request)

    sessions[session_id] = {
        "playwright": playwright, "browser": browser, "context": context, "page": page,
        "code_future": code_future, "status": "initializing", "captcha_image": None
    }
    return sessions[session_id]

@app.get("/status/{session_id}")
async def get_status(session_id: str):
    if session_id not in sessions: raise HTTPException(status_code=404, detail="Session not found")
    return {"status": sessions[session_id]["status"], "captcha_image": sessions[session_id].get("captcha_image")}

@app.post("/login/phone")
async def login_phone(req: LoginPhoneRequest):
    session_id = str(uuid.uuid4())
    session = await start_session(session_id)
    page = session["page"]
    try:
        auth_url = f"https://hh.ru/oauth/authorize?client_id={ANDROID_CLIENT_ID}&response_type=code"
        await page.goto(auth_url, wait_until="load")
        await page.wait_for_selector(SEL_LOGIN_INPUT, timeout=15000)
        await page.fill(SEL_LOGIN_INPUT, req.phone)
        await page.keyboard.press("Enter")
        if await check_for_captcha(session_id): return {"session_id": session_id, "status": "waiting_captcha", "captcha_image": session["captcha_image"]}
        try:
            await asyncio.wait([
                page.wait_for_selector(SEL_PIN_CODE_INPUT, state="visible"),
                page.wait_for_selector(SEL_PASSWORD_INPUT, state="visible"),
                page.wait_for_selector(SEL_EXPAND_PASSWORD, state="visible")
            ], return_when=asyncio.FIRST_COMPLETED, timeout=10000)
        except: pass
        if await check_for_captcha(session_id): return {"session_id": session_id, "status": "waiting_captcha", "captcha_image": session["captcha_image"]}
        if await page.query_selector(SEL_PIN_CODE_INPUT): session["status"] = "waiting_otp"
        elif await page.query_selector(SEL_PASSWORD_INPUT): session["status"] = "waiting_password"
        elif await page.query_selector(SEL_EXPAND_PASSWORD): session["status"] = "waiting_otp_with_password_option"
        return {"session_id": session_id, "status": session["status"]}
    except Exception as e:
        await save_debug_screenshot(page, f"err_phone_{session_id}")
        await session["browser"].close(); await session["playwright"].stop()
        if session_id in sessions: del sessions[session_id]
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/login/full")
async def login_full(req: LoginFullRequest):
    session_id = str(uuid.uuid4())
    session = await start_session(session_id)
    page = session["page"]
    try:
        auth_url = f"https://hh.ru/oauth/authorize?client_id={ANDROID_CLIENT_ID}&response_type=code"
        await page.goto(auth_url, wait_until="load")
        await page.wait_for_selector(SEL_LOGIN_INPUT, timeout=15000)
        await page.fill(SEL_LOGIN_INPUT, req.phone)
        await page.keyboard.press("Enter")
        if await check_for_captcha(session_id): return {"session_id": session_id, "status": "waiting_captcha", "captcha_image": session["captcha_image"]}
        try:
            await asyncio.wait([
                page.wait_for_selector(SEL_PIN_CODE_INPUT, state="visible"),
                page.wait_for_selector(SEL_PASSWORD_INPUT, state="visible"),
                page.wait_for_selector(SEL_EXPAND_PASSWORD, state="visible")
            ], return_when=asyncio.FIRST_COMPLETED, timeout=10000)
        except: pass
        if await check_for_captcha(session_id): return {"session_id": session_id, "status": "waiting_captcha", "captcha_image": session["captcha_image"]}
        
        # Switch to password
        expand_btn = await page.query_selector(SEL_EXPAND_PASSWORD)
        if expand_btn and await expand_btn.is_visible():
            await expand_btn.click(force=True)
            await page.wait_for_selector(SEL_PASSWORD_INPUT, timeout=5000)
        
        await page.fill(SEL_PASSWORD_INPUT, req.password)
        await page.keyboard.press("Enter")
        auth_code = await asyncio.wait_for(session["code_future"], timeout=30.0)
        async with httpx.AsyncClient() as client:
            resp = await client.post("https://hh.ru/oauth/token", data={
                "client_id": ANDROID_CLIENT_ID, "client_secret": ANDROID_CLIENT_SECRET,
                "code": auth_code, "grant_type": "authorization_code"
            })
            tokens = resp.json()
        cookies = await session["context"].cookies()
        await session["browser"].close(); await session["playwright"].stop(); del sessions[session_id]
        return {"tokens": tokens, "cookies": cookies, "success": True}
    except Exception as e:
        await save_debug_screenshot(page, f"err_full_{session_id}")
        await session["browser"].close(); await session["playwright"].stop()
        if session_id in sessions: del sessions[session_id]
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/login/captcha")
async def login_captcha(req: LoginCaptchaRequest):
    if req.session_id not in sessions: raise HTTPException(status_code=404, detail="Session not found")
    session = sessions[req.session_id]
    page = session["page"]
    try:
        await page.fill(SEL_CAPTCHA_INPUT, req.captcha_text)
        await page.keyboard.press("Enter")
        session["captcha_image"] = None
        await asyncio.sleep(4)
        if await check_for_captcha(req.session_id): return {"status": "waiting_captcha", "captcha_image": session["captcha_image"]}
        if await page.query_selector(SEL_PIN_CODE_INPUT): session["status"] = "waiting_otp"
        elif await page.query_selector(SEL_PASSWORD_INPUT): session["status"] = "waiting_password"
        elif await page.query_selector(SEL_EXPAND_PASSWORD): session["status"] = "waiting_otp_with_password_option"
        return {"status": session["status"]}
    except Exception as e:
        await save_debug_screenshot(page, f"err_captcha_{req.session_id}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/login/password")
async def login_password(req: LoginPasswordRequest):
    if req.session_id not in sessions: raise HTTPException(status_code=404, detail="Session not found")
    session = sessions[req.session_id]
    page = session["page"]
    try:
        # Пытаемся кликнуть через JS если обычный клик блокируется
        expand_btn = await page.query_selector(SEL_EXPAND_PASSWORD)
        if expand_btn and await expand_btn.is_visible():
            print(f"[{req.session_id}] Clicking expand password via JS...")
            await page.evaluate("el => el.click()", expand_btn)
            await page.wait_for_selector(SEL_PASSWORD_INPUT, timeout=5000)
        
        await page.fill(SEL_PASSWORD_INPUT, req.password)
        await page.keyboard.press("Enter")
        
        try:
            auth_code = await asyncio.wait_for(session["code_future"], timeout=30.0)
        except asyncio.TimeoutError:
            if await check_for_captcha(req.session_id):
                 return {"status": "waiting_captcha", "captcha_image": session["captcha_image"]}
            await save_debug_screenshot(page, f"err_pass_timeout_{req.session_id}")
            raise Exception("Timeout waiting for tokens. Check credentials.")

        async with httpx.AsyncClient() as client:
            resp = await client.post("https://hh.ru/oauth/token", data={
                "client_id": ANDROID_CLIENT_ID, "client_secret": ANDROID_CLIENT_SECRET,
                "code": auth_code, "grant_type": "authorization_code"
            })
            tokens = resp.json()
        cookies = await session["context"].cookies()
        await session["browser"].close(); await session["playwright"].stop(); del sessions[req.session_id]
        return {"tokens": tokens, "cookies": cookies, "success": True}
    except Exception as e:
        await save_debug_screenshot(page, f"err_pass_{req.session_id}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/login/code")
async def login_code(req: LoginCodeRequest):
    if req.session_id not in sessions: raise HTTPException(status_code=404, detail="Session not found")
    session = sessions[req.session_id]
    page = session["page"]
    try:
        await page.fill(SEL_PIN_CODE_INPUT, req.code)
        await page.keyboard.press("Enter")
        auth_code = await asyncio.wait_for(session["code_future"], timeout=30.0)
        async with httpx.AsyncClient() as client:
            resp = await client.post("https://hh.ru/oauth/token", data={
                "client_id": ANDROID_CLIENT_ID, "client_secret": ANDROID_CLIENT_SECRET,
                "code": auth_code, "grant_type": "authorization_code"
            })
            tokens = resp.json()
        cookies = await session["context"].cookies()
        await session["browser"].close(); await session["playwright"].stop(); del sessions[req.session_id]
        return {"tokens": tokens, "cookies": cookies, "success": True}
    except Exception as e:
        await save_debug_screenshot(page, f"err_code_{req.session_id}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
