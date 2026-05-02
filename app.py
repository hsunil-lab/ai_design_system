import os
import shutil
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import bcrypt
import httpx
import uvicorn
from fastapi import FastAPI, File, UploadFile, Form, Header
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jose import JWTError, jwt

# ---------- Load environment variables ----------
from dotenv import load_dotenv
load_dotenv()

# ---------- Supabase REST API ----------
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise Exception("Missing SUPABASE_URL or SUPABASE_KEY environment variables")

SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

def supabase_select(table: str, match: dict = None, order: str = None):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    params = match or {}
    if order:
        params["order"] = order
    response = httpx.get(url, headers=SUPABASE_HEADERS, params=params)
    return response.json()

def supabase_insert(table: str, data: dict):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    response = httpx.post(url, headers=SUPABASE_HEADERS, json=data)
    return response.json()

def supabase_update(table: str, match: dict, data: dict):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    params = match or {}
    response = httpx.patch(url, headers=SUPABASE_HEADERS, params=params, json=data)
    return response

def supabase_delete(table: str, match: dict):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    params = match or {}
    response = httpx.delete(url, headers=SUPABASE_HEADERS, params=params)
    return response

# ---------- FastAPI app ----------
app = FastAPI(title="AI Interior & Exterior Design System")

# ---------- Directories (uploads/generated images go to /tmp on Vercel) ----------
BASE_DIR = Path(__file__).resolve().parent
IS_VERCEL = os.getenv("VERCEL") == "1"

UPLOAD_DIR = Path("/tmp/uploads") if IS_VERCEL else BASE_DIR / "uploads"
GENERATED_DIR = Path("/tmp/generated") if IS_VERCEL else BASE_DIR / "generated"
STATIC_DIR = BASE_DIR / "static"

for dir_path in [UPLOAD_DIR, GENERATED_DIR, STATIC_DIR]:
    dir_path.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory="static"), name="static")

# ---------- JWT Configuration ----------
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-this")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(token: str):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None

# ---------- Database helpers ----------
async def get_user_by_email(email: str):
    result = supabase_select("users", {"email": f"eq.{email}"})
    return result[0] if result else None

async def get_user_by_id(user_id: str):
    result = supabase_select("users", {"id": f"eq.{user_id}"})
    return result[0] if result else None

async def create_user(email: str, username: str, hashed_password: str, full_name: str = ""):
    user_id = str(uuid.uuid4())
    data = {
        "id": user_id,
        "email": email,
        "username": username,
        "password": hashed_password,
        "full_name": full_name,
        "role": "user",
        "created_at": datetime.now().isoformat(),
        "reset_token": None,
        "reset_token_expiry": None
    }
    supabase_insert("users", data)
    return data

async def update_user(user_id: str, updates: dict):
    supabase_update("users", {"id": f"eq.{user_id}"}, updates)

async def save_design(design_data: dict):
    print(f"📝 Saving design: {design_data}")
    result = supabase_insert("designs", design_data)
    print(f"✅ Save result: {result}")
    return design_data

async def get_user_designs(user_id: str):
    result = supabase_select("designs", {"user_id": f"eq.{user_id}"}, order="created_at.desc")
    return result

async def get_all_designs():
    result = supabase_select("designs", order="created_at.desc")
    return result

async def delete_design(design_id: str, user_id: str):
    supabase_delete("designs", {"id": f"eq.{design_id}", "user_id": f"eq.{user_id}"})

async def get_all_users():
    result = supabase_select("users")
    return result

async def delete_user(user_id: str):
    supabase_delete("users", {"id": f"eq.{user_id}"})

# ---------- AI image generation ----------
async def generate_ai_image(prompt: str, design_type: str, style: str, color_palette: dict = None, budget: int = None, location: str = None):
    full_prompt = prompt
    if location:
        full_prompt += f", suitable for {location} area"
    if budget:
        full_prompt += f", designed within ${budget} budget using cost-effective materials"
    if color_palette:
        full_prompt += f", color scheme: {color_palette.get('primary')}, {color_palette.get('secondary')}, {color_palette.get('accent')}"
    full_prompt += f", {style} style, {design_type}, high quality, detailed, professional"
    
    import urllib.parse
    encoded_prompt = urllib.parse.quote(full_prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}"
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(url)
            if response.status_code == 200:
                filename = f"ai_{design_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.jpg"
                output_path = GENERATED_DIR / filename
                with open(output_path, "wb") as f:
                    f.write(response.content)
                return f"/generated/{filename}"
    except Exception as e:
        print(f"Error: {e}")
    return None

# ========== HTML TEMPLATES (served directly, no file writing) ==========
INDEX_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>AI Design System</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 1000px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            overflow: hidden;
        }
        header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px;
            text-align: center;
        }
        header h1 { font-size: 2em; margin-bottom: 10px; }
        .cards {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 30px;
            padding: 40px;
        }
        .card {
            text-align: center;
            padding: 30px;
            background: #f8f9fa;
            border-radius: 15px;
            transition: transform 0.3s;
        }
        .card:hover { transform: translateY(-5px); }
        .card-icon { font-size: 4em; margin-bottom: 20px; }
        .card h2 { margin-bottom: 15px; color: #333; }
        .card p { color: #666; margin-bottom: 20px; }
        .btn {
            display: inline-block;
            padding: 12px 30px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            text-decoration: none;
            border-radius: 8px;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🎨 AI Interior & Exterior Design System</h1>
            <p>Transform your spaces with artificial intelligence</p>
        </header>
        <div class="cards">
            <div class="card">
                <div class="card-icon">🏠</div>
                <h2>Interior Design</h2>
                <p>Design beautiful interiors for any room</p>
                <a href="/interior" class="btn">Start Designing →</a>
            </div>
            <div class="card">
                <div class="card-icon">🏢</div>
                <h2>Exterior Design</h2>
                <p>Create stunning building exteriors</p>
                <a href="/exterior" class="btn">Start Designing →</a>
            </div>
        </div>
    </div>
</body>
</html>
'''

LOGIN_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>Login - AI Design System</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        .container {
            background: white;
            padding: 40px;
            border-radius: 20px;
            width: 400px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }
        h1 { margin-bottom: 30px; color: #333; text-align: center; }
        input {
            width: 100%;
            padding: 12px;
            margin: 10px 0;
            border: 2px solid #ddd;
            border-radius: 8px;
            font-size: 16px;
        }
        button {
            width: 100%;
            padding: 12px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            margin-top: 20px;
            font-size: 16px;
        }
        .links { text-align: center; margin-top: 20px; }
        .links a { color: #667eea; text-decoration: none; margin: 0 10px; }
        .error { color: red; margin-top: 10px; text-align: center; display: none; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Login</h1>
        <form id="loginForm">
            <input type="email" id="email" name="email" placeholder="Email" required>
            <input type="password" id="password" name="password" placeholder="Password" required>
            <div class="error" id="errorMsg"></div>
            <button type="submit">Login</button>
        </form>
        <div class="links">
            <a href="/register">Register</a>
            <a href="/forgot-password">Forgot Password?</a>
        </div>
    </div>
    <script>
        document.getElementById('loginForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const email = document.getElementById('email').value;
            const password = document.getElementById('password').value;
            const errorMsg = document.getElementById('errorMsg');
            errorMsg.style.display = 'none';
            try {
                const formData = new FormData();
                formData.append('email', email);
                formData.append('password', password);
                const response = await fetch('/api/login', { method: 'POST', body: formData });
                const data = await response.json();
                if (data.success) {
                    localStorage.setItem('token', data.token);
                    localStorage.setItem('user', JSON.stringify(data.user));
                    window.location.href = '/dashboard';
                } else {
                    errorMsg.style.display = 'block';
                    errorMsg.textContent = data.error || 'Login failed';
                }
            } catch (error) {
                errorMsg.style.display = 'block';
                errorMsg.textContent = 'Error: ' + error.message;
            }
        });
    </script>
</body>
</html>
'''

REGISTER_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>Register - AI Design System</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        .container {
            background: white;
            padding: 40px;
            border-radius: 20px;
            width: 400px;
        }
        h1 { margin-bottom: 30px; color: #333; text-align: center; }
        input {
            width: 100%;
            padding: 12px;
            margin: 10px 0;
            border: 2px solid #ddd;
            border-radius: 8px;
        }
        button {
            width: 100%;
            padding: 12px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            margin-top: 20px;
        }
        .links { text-align: center; margin-top: 20px; }
        .links a { color: #667eea; text-decoration: none; }
        .error { color: red; margin-top: 10px; text-align: center; display: none; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Register</h1>
        <form id="registerForm">
            <input type="email" id="email" name="email" placeholder="Email" required>
            <input type="text" id="username" name="username" placeholder="Username" required>
            <input type="text" id="full_name" name="full_name" placeholder="Full Name">
            <input type="password" id="password" name="password" placeholder="Password" required>
            <div class="error" id="errorMsg"></div>
            <button type="submit">Register</button>
        </form>
        <div class="links">
            <a href="/login">Already have an account? Login</a>
        </div>
    </div>
    <script>
        document.getElementById('registerForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const email = document.getElementById('email').value;
            const username = document.getElementById('username').value;
            const full_name = document.getElementById('full_name').value;
            const password = document.getElementById('password').value;
            const errorMsg = document.getElementById('errorMsg');
            errorMsg.style.display = 'none';
            try {
                const formData = new FormData();
                formData.append('email', email);
                formData.append('username', username);
                formData.append('full_name', full_name);
                formData.append('password', password);
                const response = await fetch('/api/register', { method: 'POST', body: formData });
                const data = await response.json();
                if (data.success) {
                    localStorage.setItem('token', data.token);
                    localStorage.setItem('user', JSON.stringify(data.user));
                    window.location.href = '/dashboard';
                } else {
                    errorMsg.style.display = 'block';
                    errorMsg.textContent = data.error || 'Registration failed';
                }
            } catch (error) {
                errorMsg.style.display = 'block';
                errorMsg.textContent = 'Error: ' + error.message;
            }
        });
    </script>
</body>
</html>
'''

FORGOT_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>Forgot Password - AI Design System</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        .container {
            background: white;
            padding: 40px;
            border-radius: 20px;
            width: 400px;
        }
        h1 { margin-bottom: 30px; color: #333; text-align: center; }
        input {
            width: 100%;
            padding: 12px;
            margin: 10px 0;
            border: 2px solid #ddd;
            border-radius: 8px;
        }
        button {
            width: 100%;
            padding: 12px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            margin-top: 20px;
        }
        .links { text-align: center; margin-top: 20px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Forgot Password</h1>
        <form id="forgotForm">
            <input type="email" name="email" placeholder="Email" required>
            <button type="submit">Send Reset Link</button>
        </form>
        <div class="links">
            <a href="/login">Back to Login</a>
        </div>
    </div>
    <script>
        document.getElementById('forgotForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            const response = await fetch('/api/forgot-password', { method: 'POST', body: formData });
            const data = await response.json();
            if (data.success) {
                alert('Reset token: ' + data.reset_token + '\\nUse this token to reset your password');
                window.location.href = '/reset-password?token=' + data.reset_token;
            } else {
                alert('Error: ' + data.error);
            }
        });
    </script>
</body>
</html>
'''

RESET_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>Reset Password - AI Design System</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        .container {
            background: white;
            padding: 40px;
            border-radius: 20px;
            width: 400px;
        }
        h1 { margin-bottom: 30px; color: #333; text-align: center; }
        input {
            width: 100%;
            padding: 12px;
            margin: 10px 0;
            border: 2px solid #ddd;
            border-radius: 8px;
        }
        button {
            width: 100%;
            padding: 12px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            margin-top: 20px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Reset Password</h1>
        <form id="resetForm">
            <input type="hidden" name="token" value="">
            <input type="password" name="new_password" placeholder="New Password" required>
            <button type="submit">Reset Password</button>
        </form>
    </div>
    <script>
        const urlParams = new URLSearchParams(window.location.search);
        const token = urlParams.get('token');
        document.querySelector('input[name="token"]').value = token;
        
        document.getElementById('resetForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            const response = await fetch('/api/reset-password', { method: 'POST', body: formData });
            const data = await response.json();
            if (data.success) {
                alert('Password reset successfully! Please login.');
                window.location.href = '/login';
            } else {
                alert('Error: ' + data.error);
            }
        });
    </script>
</body>
</html>
'''

DASHBOARD_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>Dashboard - AI Design System</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            overflow: hidden;
        }
        header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .nav { display: flex; gap: 20px; align-items: center; }
        .nav a { color: white; text-decoration: none; }
        .content { padding: 30px; }
        .filter-bar {
            margin: 20px 0;
            display: flex;
            gap: 15px;
            align-items: center;
            flex-wrap: wrap;
            background: #f8f9fa;
            padding: 15px;
            border-radius: 10px;
        }
        .filter-bar input {
            padding: 8px;
            border: 1px solid #ddd;
            border-radius: 5px;
            width: 120px;
        }
        .btn {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 8px 16px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
        }
        .btn-secondary { background: #6c757d; }
        .designs-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }
        .design-card {
            background: #f8f9fa;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }
        .design-card img {
            width: 100%;
            height: 200px;
            object-fit: cover;
        }
        .design-info { padding: 15px; }
        .btn-danger { background: #dc3545; }
        .admin-link {
            background: #ffc107;
            color: #333;
            padding: 8px 15px;
            border-radius: 8px;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🎨 My Dashboard</h1>
            <div class="nav">
                <a href="/interior">New Interior</a>
                <a href="/exterior">New Exterior</a>
                <a href="#" id="adminLink" style="display:none" class="admin-link">Admin Panel</a>
                <a href="/logout">Logout</a>
            </div>
        </header>
        <div class="content">
            <h2>My Designs</h2>
            
            <div class="filter-bar">
                <label>💰 Budget Range:</label>
                <input type="number" id="budgetMin" placeholder="Min $" value="">
                <span>-</span>
                <input type="number" id="budgetMax" placeholder="Max $" value="">
                <button id="filterBtn" class="btn">Apply Filter</button>
                <button id="resetFilterBtn" class="btn btn-secondary">Reset</button>
            </div>
            
            <div id="designsGrid" class="designs-grid">
                <p>Loading designs...</p>
            </div>
        </div>
    </div>
    
    <script>
        const token = localStorage.getItem('token');
        if (!token) { window.location.href = '/login'; }
        
        const user = JSON.parse(localStorage.getItem('user') || '{}');
        if (user.role === 'admin') {
            document.getElementById('adminLink').style.display = 'inline-block';
            document.getElementById('adminLink').href = '/admin';
        }
        
        let allDesigns = [];
        
        function createDesignCard(design) {
            const card = document.createElement('div');
            card.className = 'design-card';
            card.innerHTML = `
                <img src="${design.generated_image_url}" alt="Design">
                <div class="design-info">
                    <h3>${design.type} - ${design.style || 'Modern'}</h3>
                    <p>💰 Budget: $${design.budget || 'N/A'}</p>
                    <p>📍 Location: ${design.location || 'Any'}</p>
                    <p>${design.prompt || 'No description'}</p>
                    <button onclick="editDesign('${design.id}')" class="btn">Edit Colors</button>
                    <button onclick="deleteDesign('${design.id}')" class="btn btn-danger">Delete</button>
                </div>
            `;
            return card;
        }
        
        function filterDesigns() {
            const min = parseInt(document.getElementById('budgetMin').value);
            const max = parseInt(document.getElementById('budgetMax').value);
            const grid = document.getElementById('designsGrid');
            
            let filtered = allDesigns;
            if (!isNaN(min)) { filtered = filtered.filter(d => (d.budget || 0) >= min); }
            if (!isNaN(max)) { filtered = filtered.filter(d => (d.budget || 0) <= max); }
            
            if (filtered.length > 0) {
                grid.innerHTML = '';
                filtered.forEach(design => { grid.appendChild(createDesignCard(design)); });
            } else {
                grid.innerHTML = '<p>No designs in this budget range.</p>';
            }
        }
        
        async function loadDesigns() {
            try {
                const response = await fetch('/api/my-designs', {
                    headers: { 'Authorization': 'Bearer ' + token }
                });
                
                if (response.status === 401) {
                    localStorage.removeItem('token');
                    localStorage.removeItem('user');
                    window.location.href = '/login';
                    return;
                }
                
                const data = await response.json();
                const grid = document.getElementById('designsGrid');
                
                if (data.success && data.designs && data.designs.length > 0) {
                    allDesigns = data.designs;
                    grid.innerHTML = '';
                    allDesigns.forEach(design => { grid.appendChild(createDesignCard(design)); });
                } else {
                    allDesigns = [];
                    grid.innerHTML = '<p>No designs yet. Create your first design!</p>';
                }
            } catch (error) {
                console.error('Error:', error);
                document.getElementById('designsGrid').innerHTML = '<p>Error loading designs. Please refresh.</p>';
            }
        }
        
        function editDesign(id) { window.location.href = `/design-editor/${id}`; }
        
        async function deleteDesign(id) {
            if (confirm('Delete this design?')) {
                const response = await fetch(`/api/delete-design/${id}`, {
                    method: 'DELETE',
                    headers: { 'Authorization': 'Bearer ' + token }
                });
                if (response.ok) { loadDesigns(); }
                else { alert('Failed to delete design'); }
            }
        }
        
        document.getElementById('filterBtn').addEventListener('click', filterDesigns);
        document.getElementById('resetFilterBtn').addEventListener('click', () => {
            document.getElementById('budgetMin').value = '';
            document.getElementById('budgetMax').value = '';
            if (allDesigns.length) {
                const grid = document.getElementById('designsGrid');
                grid.innerHTML = '';
                allDesigns.forEach(design => grid.appendChild(createDesignCard(design)));
            }
        });
        
        loadDesigns();
    </script>
</body>
</html>
'''

INTERIOR_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>Interior Design</title>
    <style>
        body { font-family: Arial; background: linear-gradient(135deg, #667eea, #764ba2); padding: 20px; }
        .container { max-width: 500px; margin: 0 auto; background: white; padding: 30px; border-radius: 20px; }
        input, select, textarea { width: 100%; padding: 10px; margin: 10px 0; border: 1px solid #ddd; border-radius: 5px; }
        button { background: #667eea; color: white; padding: 12px; border: none; border-radius: 5px; cursor: pointer; width: 100%; }
        img { max-width: 100%; margin-top: 20px; border-radius: 10px; }
        .loading { color: #667eea; text-align: center; display: none; }
        .hidden { display: none; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Interior Design</h1>
        <a href="/dashboard">← Dashboard</a>
        
        <form id="designForm">
            <select name="room_type" required>
                <option value="living room">Living Room</option>
                <option value="bedroom">Bedroom</option>
                <option value="kitchen">Kitchen</option>
            </select>
            
            <select name="style" required>
                <option value="modern">Modern</option>
                <option value="minimalist">Minimalist</option>
                <option value="industrial">Industrial</option>
            </select>
            
            <input type="number" name="budget" value="5000" placeholder="Budget">
            <input type="text" name="location" value="New York" placeholder="Location">
            
            <input type="color" name="color_primary" value="#667eea">
            <input type="color" name="color_secondary" value="#764ba2">
            <input type="color" name="color_accent" value="#f5f5f5">
            
            <textarea name="prompt" rows="3" placeholder="Describe your design..."></textarea>
            
            <button type="submit">Generate</button>
        </form>
        
        <div class="loading" id="loading">Generating...</div>
        <div id="result"></div>
    </div>
    
    <script>
        const token = localStorage.getItem('token');
        if (!token) {
            alert('Login required');
            window.location.href = '/login';
        }
        
        const form = document.getElementById('designForm');
        const loading = document.getElementById('loading');
        const resultDiv = document.getElementById('result');
        
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            loading.style.display = 'block';
            resultDiv.innerHTML = '';
            
            const formData = new FormData(form);
            
            try {
                const res = await fetch('/api/generate-interior', {
                    method: 'POST',
                    headers: { 'Authorization': 'Bearer ' + token },
                    body: formData
                });
                
                const data = await res.json();
                console.log('Response:', data);
                
                if (data.success) {
                    resultDiv.innerHTML = '<img src="' + data.design_url + '"><br><button onclick="window.location.href=\'/dashboard\'">Go to Dashboard</button>';
                } else {
                    resultDiv.innerHTML = '<p style="color:red">Error: ' + data.error + '</p>';
                }
            } catch (err) {
                resultDiv.innerHTML = '<p style="color:red">Error: ' + err.message + '</p>';
            } finally {
                loading.style.display = 'none';
            }
        });
    </script>
</body>
</html>
'''

EXTERIOR_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>Exterior Design - AI Design System</title>
    <meta charset="UTF-8">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 700px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            padding: 30px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }
        h1 { margin-bottom: 20px; color: #333; text-align: center; }
        .form-group { margin-bottom: 20px; }
        label { display: block; margin-bottom: 8px; font-weight: bold; color: #333; }
        select, input, textarea {
            width: 100%;
            padding: 12px;
            border: 2px solid #ddd;
            border-radius: 8px;
            font-size: 16px;
        }
        .color-row {
            display: flex;
            gap: 15px;
            margin-top: 10px;
        }
        .color-input { flex: 1; text-align: center; }
        .color-input input { width: 60px; height: 40px; cursor: pointer; margin: 0 auto; }
        button {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 14px;
            border-radius: 8px;
            cursor: pointer;
            width: 100%;
            font-size: 16px;
            font-weight: bold;
            margin-top: 20px;
        }
        button:hover { opacity: 0.9; }
        .loading { text-align: center; padding: 20px; display: none; color: #667eea; font-weight: bold; }
        .result { margin-top: 30px; text-align: center; display: none; }
        .result img { max-width: 100%; border-radius: 10px; margin-top: 15px; box-shadow: 0 5px 15px rgba(0,0,0,0.2); }
        .back-link { display: inline-block; margin-bottom: 20px; color: #667eea; text-decoration: none; }
        .success { color: green; margin-top: 10px; }
        .error { color: red; margin-top: 10px; }
    </style>
</head>
<body>
    <div class="container">
        <a href="/dashboard" class="back-link">← Back to Dashboard</a>
        <h1>🏠 AI Exterior Design Generator</h1>
        
        <form id="designForm">
            <div class="form-group">
                <label>Room Type</label>
                <select name="room_type" required>
                    <option value="living room">Living Room</option>
                    <option value="bedroom">Bedroom</option>
                    <option value="kitchen">Kitchen</option>
                    <option value="bathroom">Bathroom</option>
                    <option value="office">Home Office</option>
                </select>
            </div>
            
            <div class="form-group">
                <label>Design Style</label>
                <select name="style" required>
                    <option value="modern">Modern</option>
                    <option value="minimalist">Minimalist</option>
                    <option value="industrial">Industrial</option>
                    <option value="scandinavian">Scandinavian</option>
                    <option value="bohemian">Bohemian</option>
                </select>
            </div>
            
            <div class="form-group">
                <label>💰 Budget (USD)</label>
                <input type="number" name="budget" value="5000" step="1000">
                <small>AI will design within your budget</small>
            </div>
            
            <div class="form-group">
                <label>📍 Location</label>
                <input type="text" name="location" placeholder="e.g., New York, Beach, Mountains" value="Modern City">
                <small>AI adapts design to this location</small>
            </div>
            
            <div class="form-group">
                <label>🎨 Color Palette (Optional)</label>
                <div class="color-row">
                    <div class="color-input">
                        <input type="color" name="color_primary" value="#667eea">
                        <div>Primary</div>
                    </div>
                    <div class="color-input">
                        <input type="color" name="color_secondary" value="#764ba2">
                        <div>Secondary</div>
                    </div>
                    <div class="color-input">
                        <input type="color" name="color_accent" value="#f5f5f5">
                        <div>Accent</div>
                    </div>
                </div>
            </div>
            
            <div class="form-group">
                <label>📝 Describe Your Dream Design</label>
                <textarea name="prompt" rows="4" placeholder="Example: Add large windows, wooden floors, green plants, and warm lighting..."></textarea>
            </div>
            
            <button type="submit">🎨 Generate Design</button>
        </form>
        
        <div class="loading" id="loading">
            ⏳ AI is creating your design... (10-20 seconds)
        </div>
        
        <div class="result" id="result">
            <h3>✨ Your AI-Generated Design</h3>
            <img id="resultImage" alt="Generated design">
            <p class="success" id="successMsg"></p>
            <p class="error" id="errorMsg"></p>
            <button onclick="saveAndContinue()" style="margin-top: 15px;">💾 Save & Go to Dashboard</button>
        </div>
    </div>
    
    <script>
        // Get token from localStorage
        const token = localStorage.getItem('token');
        if (!token) {
            alert('Please login first');
            window.location.href = '/login';
        }
        
        const form = document.getElementById('designForm');
        const loading = document.getElementById('loading');
        const resultDiv = document.getElementById('result');
        const resultImage = document.getElementById('resultImage');
        const errorMsg = document.getElementById('errorMsg');
        const successMsg = document.getElementById('successMsg');
        
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            // Show loading, hide result
            loading.style.display = 'block';
            resultDiv.style.display = 'none';
            errorMsg.textContent = '';
            successMsg.textContent = '';
            
            const formData = new FormData(form);
            
            try {
                const response = await fetch('/api/generate-interior', {
                    method: 'POST',
                    headers: { 'Authorization': 'Bearer ' + token },
                    body: formData
                });
                
                const data = await response.json();
                
                if (data.success) {
                    resultImage.src = data.design_url;
                    successMsg.textContent = '✅ Design generated successfully!';
                    resultDiv.style.display = 'block';
                } else {
                    errorMsg.textContent = '❌ Error: ' + data.error;
                    resultDiv.style.display = 'block';
                }
            } catch (err) {
                errorMsg.textContent = '❌ Network Error: ' + err.message;
                resultDiv.style.display = 'block';
            } finally {
                loading.style.display = 'none';
            }
        });
        
        function saveAndContinue() {
            window.location.href = '/dashboard';
        }
    </script>
</body>
</html>
'''

EDITOR_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>Edit Design - AI Design System</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 1000px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            padding: 30px;
        }
        h1 { margin-bottom: 20px; color: #333; }
        .editor-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 30px;
        }
        .design-preview img { width: 100%; border-radius: 10px; }
        .color-controls { padding: 20px; background: #f8f9fa; border-radius: 10px; }
        .color-group { margin-bottom: 20px; }
        .color-group label { display: block; margin-bottom: 10px; font-weight: bold; }
        .color-group input[type="color"] { width: 100%; height: 50px; cursor: pointer; border: 2px solid #ddd; border-radius: 8px; background: white; }
        button {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 8px;
            cursor: pointer;
            width: 100%;
            margin-top: 20px;
            font-size: 16px;
        }
        .loading {
            text-align: center;
            padding: 20px;
            display: none;
        }
        .spinner {
            border: 4px solid #f3f3f3;
            border-top: 4px solid #667eea;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            animation: spin 1s linear infinite;
            margin: 0 auto;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        .back-link { display: inline-block; margin-bottom: 20px; color: #667eea; text-decoration: none; }
        .error-msg { color: red; margin-top: 10px; text-align: center; display: none; }
    </style>
</head>
<body>
    <div class="container">
        <a href="/dashboard" class="back-link">← Back to Dashboard</a>
        <h1>🎨 Edit Design Colors</h1>
        
        <div class="editor-grid">
            <div class="design-preview">
                <h3>Current Design</h3>
                <img id="designImage" alt="Design">
            </div>
            
            <div class="color-controls">
                <h3>Color Palette Editor</h3>
                <div class="color-group">
                    <label>🎨 Primary Color</label>
                    <input type="color" id="primaryColor" value="#667eea">
                </div>
                <div class="color-group">
                    <label>🎨 Secondary Color</label>
                    <input type="color" id="secondaryColor" value="#764ba2">
                </div>
                <div class="color-group">
                    <label>🎨 Accent Color</label>
                    <input type="color" id="accentColor" value="#f5f5f5">
                </div>
                <button id="applyBtn">Apply New Colors & Regenerate</button>
                <div class="error-msg" id="errorMsg"></div>
            </div>
        </div>
        
        <div class="loading" id="loading">
            <div class="spinner"></div>
            <p>Regenerating design with new colors...</p>
        </div>
    </div>
    
    <script>
        const token = localStorage.getItem('token');
        if (!token) { window.location.href = '/login'; }
        
        const designId = window.location.pathname.split('/').pop();
        
        async function loadDesign() {
            try {
                const response = await fetch('/api/my-designs', {
                    headers: { 'Authorization': 'Bearer ' + token }
                });
                const data = await response.json();
                if (data.success) {
                    const design = data.designs.find(d => d.id === designId);
                    if (design) {
                        document.getElementById('designImage').src = design.generated_image_url;
                        if (design.color_palette) {
                            document.getElementById('primaryColor').value = design.color_palette.primary || '#667eea';
                            document.getElementById('secondaryColor').value = design.color_palette.secondary || '#764ba2';
                            document.getElementById('accentColor').value = design.color_palette.accent || '#f5f5f5';
                        }
                    } else {
                        alert('Design not found');
                        window.location.href = '/dashboard';
                    }
                } else {
                    alert('Failed to load design');
                }
            } catch (error) {
                console.error(error);
                alert('Error loading design');
            }
        }
        
        async function applyNewColors() {
            const loading = document.getElementById('loading');
            const errorMsg = document.getElementById('errorMsg');
            loading.style.display = 'block';
            errorMsg.style.display = 'none';
            
            const formData = new FormData();
            formData.append('color_primary', document.getElementById('primaryColor').value);
            formData.append('color_secondary', document.getElementById('secondaryColor').value);
            formData.append('color_accent', document.getElementById('accentColor').value);
            
            try {
                const response = await fetch(`/api/update-design/${designId}`, {
                    method: 'POST',
                    headers: { 'Authorization': 'Bearer ' + token },
                    body: formData
                });
                const data = await response.json();
                if (data.success) {
                    document.getElementById('designImage').src = data.design_url + '?t=' + Date.now();
                    alert('Design updated with new colors!');
                } else {
                    errorMsg.style.display = 'block';
                    errorMsg.textContent = data.error || 'Update failed';
                }
            } catch (error) {
                errorMsg.style.display = 'block';
                errorMsg.textContent = 'Network error: ' + error.message;
            } finally {
                loading.style.display = 'none';
            }
        }
        
        document.getElementById('applyBtn').addEventListener('click', applyNewColors);
        loadDesign();
    </script>
</body>
</html>
'''

ADMIN_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>Admin Panel - AI Design System</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            overflow: hidden;
        }
        header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .nav a { color: white; text-decoration: none; margin-left: 20px; }
        .content { padding: 30px; }
        .stats {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 10px;
            text-align: center;
        }
        .stat-number { font-size: 2em; font-weight: bold; color: #667eea; }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        th { background: #f8f9fa; }
        .btn {
            background: #dc3545;
            color: white;
            border: none;
            padding: 5px 10px;
            border-radius: 5px;
            cursor: pointer;
        }
        .tab {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
        }
        .tab button {
            padding: 10px 20px;
            background: #f8f9fa;
            border: none;
            cursor: pointer;
        }
        .tab button.active {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Admin Panel</h1>
            <div class="nav">
                <a href="/dashboard">Dashboard</a>
                <a href="/logout">Logout</a>
            </div>
        </header>
        <div class="content">
            <div class="stats">
                <div class="stat-card">
                    <div class="stat-number" id="userCount">0</div>
                    <div>Total Users</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" id="designCount">0</div>
                    <div>Total Designs</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" id="todayCount">0</div>
                    <div>Today's Designs</div>
                </div>
            </div>

            <div class="tab">
                <button class="active" onclick="showTab('users')">Users</button>
                <button onclick="showTab('designs')">All Designs</button>
            </div>

            <div id="usersTab" class="tab-content active">
                <table id="usersTable">
                    <thead>
                        <tr><th>ID</th><th>Email</th><th>Username</th><th>Role</th><th>Created</th><th>Action</th></tr>
                    </thead>
                    <tbody></tbody>
                </table>
            </div>

            <div id="designsTab" class="tab-content">
                <table id="designsTable">
                    <thead>
                        <tr><th>ID</th><th>User ID</th><th>Type</th><th>Style</th><th>Budget</th><th>Location</th><th>Created</th><th>Preview</th></tr>
                    </thead>
                    <tbody></tbody>
                </table>
            </div>
        </div>
    </div>

    <script>
        const token = localStorage.getItem('token');
        if (!token) window.location.href = '/login';

        function showTab(tab) {
            document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
            document.getElementById(tab + 'Tab').classList.add('active');
            event.target.classList.add('active');
        }

        async function loadAdminData() {
            const usersRes = await fetch('/api/admin/users', {
                headers: { 'Authorization': 'Bearer ' + token }
            });
            const usersData = await usersRes.json();
            if (usersData.success) {
                document.getElementById('userCount').innerText = usersData.users.length;
                const tbody = document.querySelector('#usersTable tbody');
                tbody.innerHTML = '';
                usersData.users.forEach(user => {
                    const row = tbody.insertRow();
                    row.insertCell(0).innerText = user.id;
                    row.insertCell(1).innerText = user.email;
                    row.insertCell(2).innerText = user.username;
                    row.insertCell(3).innerText = user.role;
                    row.insertCell(4).innerText = new Date(user.created_at).toLocaleDateString();
                    row.insertCell(5).innerHTML = user.role !== 'admin' ? `<button class="btn" onclick="deleteUser('${user.id}')">Delete</button>` : '-';
                });
            }

            const designsRes = await fetch('/api/admin/designs', {
                headers: { 'Authorization': 'Bearer ' + token }
            });
            const designsData = await designsRes.json();
            if (designsData.success) {
                document.getElementById('designCount').innerText = designsData.designs.length;
                const today = new Date().toDateString();
                const todayDesigns = designsData.designs.filter(d => new Date(d.created_at).toDateString() === today);
                document.getElementById('todayCount').innerText = todayDesigns.length;

                const tbody = document.querySelector('#designsTable tbody');
                tbody.innerHTML = '';
                designsData.designs.forEach(design => {
                    const row = tbody.insertRow();
                    row.insertCell(0).innerText = design.id;
                    row.insertCell(1).innerText = design.user_id;
                    row.insertCell(2).innerText = design.type;
                    row.insertCell(3).innerText = design.style;
                    row.insertCell(4).innerText = design.budget || 'N/A';
                    row.insertCell(5).innerText = design.location || 'Any';
                    row.insertCell(6).innerText = new Date(design.created_at).toLocaleDateString();
                    row.insertCell(7).innerHTML = `<a href="${design.generated_image_url}" target="_blank">View</a>`;
                });
            }
        }

        async function deleteUser(userId) {
            if (confirm('Delete this user? All their designs will also be deleted.')) {
                const response = await fetch(`/api/admin/delete-user/${userId}`, {
                    method: 'POST',
                    headers: { 'Authorization': 'Bearer ' + token }
                });
                if (response.ok) {
                    loadAdminData();
                } else {
                    alert('Failed to delete user');
                }
            }
        }

        loadAdminData();
    </script>
</body>
</html>
'''

# ========== ROUTES (serve HTML directly – NO FILE WRITING) ==========
@app.get("/", response_class=HTMLResponse)
async def home():
    return HTMLResponse(content=INDEX_HTML)

@app.get("/login", response_class=HTMLResponse)
async def login_page():
    return HTMLResponse(content=LOGIN_HTML)

@app.get("/register", response_class=HTMLResponse)
async def register_page():
    return HTMLResponse(content=REGISTER_HTML)

@app.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page():
    return HTMLResponse(content=FORGOT_HTML)

@app.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page():
    return HTMLResponse(content=RESET_HTML)

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page():
    return HTMLResponse(content=DASHBOARD_HTML)

@app.get("/interior", response_class=HTMLResponse)
async def interior_page():
    return HTMLResponse(content=INTERIOR_HTML)

@app.get("/exterior", response_class=HTMLResponse)
async def exterior_page():
    return HTMLResponse(content=EXTERIOR_HTML)

@app.get("/design-editor/{design_id}", response_class=HTMLResponse)
async def design_editor_page(design_id: str):
    return HTMLResponse(content=EDITOR_HTML)

@app.get("/admin", response_class=HTMLResponse)
async def admin_page():
    return HTMLResponse(content=ADMIN_HTML)

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login")
    response.delete_cookie("token")
    return response

# ========== API ENDPOINTS ==========
@app.post("/api/register")
async def register(
    email: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    full_name: str = Form("")
):
    existing = await get_user_by_email(email)
    if existing:
        return JSONResponse({"success": False, "error": "Email already registered"}, status_code=400)
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    new_user = await create_user(email, username, hashed, full_name)
    token = create_access_token({"sub": new_user["id"], "email": new_user["email"], "role": new_user["role"]})
    user_copy = {k: v for k, v in new_user.items() if k != "password"}
    return JSONResponse({"success": True, "token": token, "user": user_copy})

@app.post("/api/login")
async def login(email: str = Form(...), password: str = Form(...)):
    user = await get_user_by_email(email)
    if not user:
        return JSONResponse({"success": False, "error": "Invalid credentials"}, status_code=401)
    if not bcrypt.checkpw(password.encode('utf-8'), user["password"].encode('utf-8')):
        return JSONResponse({"success": False, "error": "Invalid credentials"}, status_code=401)
    token = create_access_token({"sub": user["id"], "email": user["email"], "role": user["role"]})
    user_copy = {k: v for k, v in user.items() if k != "password"}
    return JSONResponse({"success": True, "token": token, "user": user_copy})

@app.post("/api/forgot-password")
async def forgot_password(email: str = Form(...)):
    user = await get_user_by_email(email)
    if not user:
        return JSONResponse({"success": False, "error": "Email not found"}, status_code=404)
    reset_token = str(uuid.uuid4())
    expiry = (datetime.now() + timedelta(hours=1)).isoformat()
    await update_user(user["id"], {"reset_token": reset_token, "reset_token_expiry": expiry})
    return JSONResponse({"success": True, "reset_token": reset_token})

@app.post("/api/reset-password")
async def reset_password(token: str = Form(...), new_password: str = Form(...)):
    result = supabase_select("users", {"reset_token": f"eq.{token}"})
    if not result:
        return JSONResponse({"success": False, "error": "Invalid token"}, status_code=400)
    user = result[0]
    if datetime.fromisoformat(user["reset_token_expiry"]) < datetime.now():
        return JSONResponse({"success": False, "error": "Token expired"}, status_code=400)
    hashed = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    await update_user(user["id"], {"password": hashed, "reset_token": None, "reset_token_expiry": None})
    return JSONResponse({"success": True})

@app.get("/api/user")
async def get_current_user(authorization: str = None):
    if not authorization or not authorization.startswith("Bearer "):
        return JSONResponse({"success": False}, status_code=401)
    token = authorization.replace("Bearer ", "")
    payload = verify_token(token)
    if not payload:
        return JSONResponse({"success": False}, status_code=401)
    user = await get_user_by_id(payload.get("sub"))
    if not user:
        return JSONResponse({"success": False}, status_code=401)
    user_copy = {k: v for k, v in user.items() if k != "password"}
    return JSONResponse({"success": True, "user": user_copy})

@app.post("/api/generate-interior")
async def generate_interior(
    image: UploadFile = File(None),
    room_type: str = Form(...),
    style: str = Form(...),
    prompt: str = Form(""),
    color_primary: str = Form(""),
    color_secondary: str = Form(""),
    color_accent: str = Form(""),
    budget: int = Form(5000),
    location: str = Form(""),
    authorization: Optional[str] = Header(None)
):
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "")
    payload = verify_token(token) if token else None
    if not payload:
        return JSONResponse({"success": False, "error": "Unauthorized"}, status_code=401)
    
    print(f"🔍 Token payload: {payload}")
    print(f"🔍 User ID from token: {payload.get('sub')}")


    color_palette = None
    if color_primary:
        color_palette = {"primary": color_primary, "secondary": color_secondary, "accent": color_accent}
    
    full_prompt = f"{room_type}, {prompt if prompt else 'beautiful interior design'}, {style} style"
    image_url = await generate_ai_image(full_prompt, "interior", style, color_palette, budget, location)
    if not image_url:
        return JSONResponse({"success": False, "error": "AI generation failed"}, status_code=500)
    
    original_url = None
    if image and image.filename:
        upload_filename = f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{image.filename}"
        upload_path = UPLOAD_DIR / upload_filename
        with open(upload_path, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)
        original_url = f"/uploads/{upload_filename}"
    
    design_data = {
        "id": str(uuid.uuid4()),
        "user_id": payload.get("sub"),
        "type": "interior",
        "room_type": room_type,
        "style": style,
        "prompt": prompt,
        "budget": budget,
        "location": location,
        "color_palette": color_palette,
        "generated_image_url": image_url,
        "original_image_url": original_url,
        "created_at": datetime.now().isoformat()
    }

    print(f"📝 Saving design for user: {payload.get('sub')}")
    print(f"📝 Design data: {design_data}")

    await save_design(design_data)
    return JSONResponse({"success": True, "design_url": image_url, "design_id": design_data["id"]})

@app.post("/api/generate-exterior")
async def generate_exterior(
    image: UploadFile = File(None),
    building_type: str = Form(...),
    style: str = Form(...),
    prompt: str = Form(""),
    color_primary: str = Form(""),
    color_secondary: str = Form(""),
    color_accent: str = Form(""),
    budget: int = Form(5000),
    location: str = Form(""),
    authorization: Optional[str] = Header(None)
):
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "")
    payload = verify_token(token) if token else None
    if not payload:
        return JSONResponse({"success": False, "error": "Unauthorized"}, status_code=401)
    
    color_palette = None
    if color_primary:
        color_palette = {"primary": color_primary, "secondary": color_secondary, "accent": color_accent}
    
    full_prompt = f"{building_type}, {prompt if prompt else 'beautiful exterior design'}, {style} style"
    image_url = await generate_ai_image(full_prompt, "exterior", style, color_palette, budget, location)
    if not image_url:
        return JSONResponse({"success": False, "error": "AI generation failed"}, status_code=500)
    
    original_url = None
    if image and image.filename:
        upload_filename = f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{image.filename}"
        upload_path = UPLOAD_DIR / upload_filename
        with open(upload_path, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)
        original_url = f"/uploads/{upload_filename}"
    
    design_data = {
        "id": str(uuid.uuid4()),
        "user_id": payload.get("sub"),
        "type": "exterior",
        "building_type": building_type,
        "style": style,
        "prompt": prompt,
        "budget": budget,
        "location": location,
        "color_palette": color_palette,
        "generated_image_url": image_url,
        "original_image_url": original_url,
        "created_at": datetime.now().isoformat()
    }
    await save_design(design_data)
    return JSONResponse({"success": True, "design_url": image_url, "design_id": design_data["id"]})

@app.post("/api/update-design/{design_id}")
async def update_design(
    design_id: str,
    color_primary: str = Form(...),
    color_secondary: str = Form(...),
    color_accent: str = Form(...),
    authorization: Optional[str] = Header(None)
):
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "")
    payload = verify_token(token) if token else None
    if not payload:
        return JSONResponse({"success": False, "error": "Unauthorized"}, status_code=401)
    
    result = supabase_select("designs", {"id": f"eq.{design_id}", "user_id": f"eq.{payload.get('sub')}"})
    if not result:
        return JSONResponse({"success": False, "error": "Design not found"}, status_code=404)
    design = result[0]
    
    color_palette = {"primary": color_primary, "secondary": color_secondary, "accent": color_accent}
    prompt = design.get("prompt", "")
    style = design.get("style", "modern")
    design_type = design.get("type", "interior")
    budget = design.get("budget", 5000)
    location = design.get("location", "")
    
    full_prompt = f"{prompt}, {style} style, dominant colors: primary {color_primary}, secondary {color_secondary}, accent {color_accent}"
    new_image_url = await generate_ai_image(full_prompt, design_type, style, color_palette, budget, location)
    if not new_image_url:
        return JSONResponse({"success": False, "error": "AI generation failed"}, status_code=500)
    
    updates = {
        "color_palette": color_palette,
        "generated_image_url": new_image_url,
        "updated_at": datetime.now().isoformat()
    }
    supabase_update("designs", {"id": f"eq.{design_id}"}, updates)
    return JSONResponse({"success": True, "design_url": new_image_url})

@app.get("/api/my-designs")
async def get_my_designs(authorization: Optional[str] = Header(None)):
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "")
    payload = verify_token(token) if token else None
    if not payload:
        return JSONResponse({"success": False, "error": "Unauthorized"}, status_code=401)
    designs = await get_user_designs(payload.get("sub"))
    return JSONResponse({"success": True, "designs": designs})

@app.delete("/api/delete-design/{design_id}")
async def delete_design(design_id: str, authorization: Optional[str] = Header(None)):
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "")
    payload = verify_token(token) if token else None
    if not payload:
        return JSONResponse({"success": False, "error": "Unauthorized"}, status_code=401)
    await delete_design(design_id, payload.get("sub"))
    return JSONResponse({"success": True})

@app.get("/api/admin/users")
async def admin_get_users(authorization: Optional[str] = Header(None)):
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "")
    payload = verify_token(token) if token else None
    if not payload or payload.get("role") != "admin":
        return JSONResponse({"success": False, "error": "Admin access required"}, status_code=403)
    users = await get_all_users()
    users_clean = [{k: v for k, v in u.items() if k != "password"} for u in users]
    return JSONResponse({"success": True, "users": users_clean})

@app.get("/api/admin/designs")
async def admin_get_designs(authorization: Optional[str] = Header(None)):
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "")
    payload = verify_token(token) if token else None
    if not payload or payload.get("role") != "admin":
        return JSONResponse({"success": False, "error": "Admin access required"}, status_code=403)
    designs = await get_all_designs()
    return JSONResponse({"success": True, "designs": designs})

@app.post("/api/admin/delete-user/{user_id}")
async def admin_delete_user(user_id: str, authorization: Optional[str] = Header(None)):
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "")
    payload = verify_token(token) if token else None
    if not payload or payload.get("role") != "admin":
        return JSONResponse({"success": False, "error": "Admin access required"}, status_code=403)
    if user_id == payload.get("sub"):
        return JSONResponse({"success": False, "error": "Cannot delete yourself"}, status_code=400)
    await delete_user(user_id)
    return JSONResponse({"success": True})

@app.get("/uploads/{filename}")
async def get_uploaded_image(filename: str):
    file_path = UPLOAD_DIR / filename
    if file_path.exists():
        return FileResponse(file_path)
    return JSONResponse({"error": "Not found"}, status_code=404)

@app.get("/generated/{filename}")
async def get_generated_image(filename: str):
    file_path = GENERATED_DIR / filename
    if file_path.exists():
        return FileResponse(file_path)
    return JSONResponse({"error": "Not found"}, status_code=404)

@app.post("/api/test-save")
async def test_save():
    test_data = {
        "id": "test-123",
        "user_id": "test-user-1",
        "type": "interior",
        "style": "modern",
        "prompt": "test",
        "budget": 5000,
        "location": "test",
        "generated_image_url": "https://example.com/test.jpg",
        "created_at": datetime.now().isoformat()
    }
    result = supabase_insert("designs", test_data)
    return JSONResponse({"success": True, "result": result})

# ---------- Run ----------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port)