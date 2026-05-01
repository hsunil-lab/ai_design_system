import os
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client

# Load .env
env_path = Path("C:/ai_design_system/.env")
load_dotenv(dotenv_path=env_path)

# Get credentials
url = os.getenv("https://skgwjewchckdrwjguqwm.supabase.co")
key = os.getenv("@supabase_keyeyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNrZ3dqZXdjaGNrZHJ3amd1cXdtIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzY3MzU2MTksImV4cCI6MjA5MjMxMTYxOX0.Ek5RQgeQN8tkwDaw_knW-4nguRIbLljruyg0GFFErMMASE_KEY")

print(f"URL: {url}")
print(f"Key starts with: {key[:30] if key else 'None'}...")

# Remove quotes if present
url = url.strip('"')
key = key.strip('"')

# Test connection
try:
    supabase = create_client(url, key)
    print("✅ Supabase connection successful!")
    
    # Try a simple query
    response = supabase.table("profiles").select("*").limit(1).execute()
    print("✅ Database query successful!")
    
except Exception as e:
    print(f"❌ Error: {e}")