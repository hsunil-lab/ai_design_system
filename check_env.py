import os
from pathlib import Path

# Check current directory
print(f"Current directory: {os.getcwd()}")

# Check if .env exists
env_file = Path("C:/ai_design_system/.env")
print(f".env file exists: {env_file.exists()}")

# Try to read .env directly
if env_file.exists():
    with open(env_file, 'r') as f:
        content = f.read()
        print(f".env content:\n{content}")
else:
    print("Creating .env file now...")
    with open(env_file, 'w') as f:
        f.write("SUPABASE_URL=https://skgwjewchckdrwjguqwm.supabase.co\n")
        f.write("SUPABASE_KEY=@supabase_keyeyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNrZ3dqZXdjaGNrZHJ3amd1cXdtIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzY3MzU2MTksImV4cCI6MjA5MjMxMTYxOX0.Ek5RQgeQN8tkwDaw_knW-4nguRIbLljruyg0GFFErMM\n")
    print(".env file created! Please edit it with your actual credentials.")