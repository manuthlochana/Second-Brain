import sys
import os
from datetime import datetime, timedelta

# Import paths
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from backend.memory_manager import memory_manager

def test_memory_scoring():
    print("🧠 Testing Memory Scoring Logic...")
    
    # 1. Test Decay
    t1 = datetime.now() # New
    t2 = datetime.now() - timedelta(days=365) # Old
    
    s1 = memory_manager._calculate_score(0.9, t1)
    s2 = memory_manager._calculate_score(0.9, t2)
    
    print(f"   - Score New (0.9 sim): {s1:.3f}")
    print(f"   - Score Old (0.9 sim): {s2:.3f}")
    
    if s1 > s2:
        print("✅ Temporal Decay is working (Newer > Older)")
    else:
        print("❌ Temporal Decay Failed")

    # 2. Test Summarization (Mock call if needed, or real LLM)
    long_text = "This is a memory. " * 300
    print("   - Testing Compression...")
    if len(long_text) > 2000:
        summary = memory_manager.compress_context(long_text)
        print(f"✅ Compressed: {len(summary)} chars (Original: {len(long_text)})")
    else:
        print("   - Skipping compression test (text too short)")

if __name__ == "__main__":
    test_memory_scoring()
