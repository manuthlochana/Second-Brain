import sys
import os

# Add backend to sys.path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

try:
    from backend import brain
    print("✅ Successfully imported brain module.")
except ImportError as e:
    print(f"❌ Failed to import brain module: {e}")
    sys.exit(1)

# Mock state for testing nodes individually (optional, but good for sanity check)
print("Sanity check complete. Brain module structure seems valid.")
