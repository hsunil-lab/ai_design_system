import os
from pathlib import Path
from dotenv import load_dotenv

print("=== DEBUGGING ENV LOADING ===")
print(f"Current working directory: {os.getcwd()}")

# Check if .env exists in current directory
env_file = Path(os.getcwd()) / '.env'
print(f".env file path: {env_file}")
print(f".env file exists: {env_file.exists()}")

if env_file.exists():
    print("\n--- Raw .env content ---")
    with open(env_file, 'r') as f:
        print(f.read())
    
    # Try to load it
    load_dotenv(dotenv_path=env_file)
    
    # Check if loaded
    url = os.getenv("https://skgwjewchckdrwjguqwm.supabase.co")
    key = os.getenv("@supabase_keyeyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNrZ3dqZXdjaGNrZHJ3amd1cXdtIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzY3MzU2MTksImV4cCI6MjA5MjMxMTYxOX0.Ek5RQgeQN8tkwDaw_knW-4nguRIbLljruyg0GFFErMM")
    
    print(f"\n--- After load_dotenv ---")
    print(f"SUPABASE_URL: {url}")
    print(f"SUPABASE_KEY: {key[:20] if key else 'None'}...")
else:
    print("❌ .env file NOT FOUND!")

print("\n=== All environment variables (filtered) ===")
for key in os.environ.keys():
    if 'SUPABASE' in key:
        print(f"{key}: {os.environ[key][:30]}...")