from dotenv import load_dotenv
import os

# Try to load .env file
load_dotenv()

# Print current directory
print(f"Current directory: {os.getcwd()}")

# Check if .env file exists
env_path = os.path.join(os.getcwd(), '.env')
print(f".env file exists: {os.path.exists(env_path)}")

# Print environment variables (partial for security)
url = os.getenv("https://skgwjewchckdrwjguqwm.supabase.co")
key = os.getenv("@supabase_keyeyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNrZ3dqZXdjaGNrZHJ3amd1cXdtIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzY3MzU2MTksImV4cCI6MjA5MjMxMTYxOX0.Ek5RQgeQN8tkwDaw_knW-4nguRIbLljruyg0GFFErMMSUPABASE_KEY")

print(f"SUPABASE_URL: {url if url else 'NOT FOUND!'}")
print(f"SUPABASE_KEY: {key[:20] if key else 'NOT FOUND!'}...")

if not url or not key:
    print("\n❌ ERROR: Credentials not found!")
    print("Please create .env file with:")
    print('SUPABASE_URL="https://skgwjewchckdrwjguqwm.supabase.co"')
    print('SUPABASE_KEY="@supabase_keyeyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNrZ3dqZXdjaGNrZHJ3amd1cXdtIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzY3MzU2MTksImV4cCI6MjA5MjMxMTYxOX0.Ek5RQgeQN8tkwDaw_knW-4nguRIbLljruyg0GFFErMM"')
else:
    print("\n✅ Credentials loaded successfully!")