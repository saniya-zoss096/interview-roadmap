# test_env.py
from dotenv import load_dotenv
import os

print("\n" + "="*50)
print("ENVIRONMENT VARIABLE CHECK")
print("="*50)

load_dotenv()

# Check each variable
checks = [
    ('SECRET_KEY', os.environ.get('SECRET_KEY')),
    ('SERPAPI_KEY', os.environ.get('SERPAPI_KEY')),
    ('GITHUB_TOKEN', os.environ.get('GITHUB_TOKEN')),
]

all_ok = True
for name, value in checks:
    if value:
        print(f"✅ {name}: Present (length: {len(value)})")
    else:
        print(f"❌ {name}: MISSING - Add to .env file!")
        all_ok = False

print("="*50)
if all_ok:
    print("✅ All good! Run: python app.py")
else:
    print("❌ Fix missing variables in .env file")
print("="*50 + "\n")