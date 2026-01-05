import os
import json
import sys

# Add backend to sys.path to allow imports
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from backend.processor import InputProcessor

def test_semantic_router():
    print("🚀 Initializing InputProcessor...")
    try:
        processor = InputProcessor()
    except Exception as e:
        print(f"❌ Failed to initialize processor: {e}")
        return

    test_cases = [
        {
            "input": "Remind me to call functionality at 5pm",
            "expected_intent": "CREATE_TASK"
        },
        {
            "input": "Save my HNB bank account details: 123456789",
            "expected_intent": "STORE_NOTE" # Or GET_CREDENTIALS depending on nuance, security usually implies STORE if saving.
        },
        {
            "input": "Who is Manuth?",
            "expected_intent": "SEARCH_MEMORY"
        },
        {
            "input": "shabalabadingdong",
            "expected_intent": "UNKNOWN"
        }
    ]

    print("\n--- Running Tests ---")
    for case in test_cases:
        text = case["input"]
        print(f"\n🔹 Input: '{text}'")
        
        try:
            result = processor.process(text)
            intent = result.get("intent")
            print(f"   Intent: {intent}")
            print(f"   Reasoning: {result.get('reasoning')}")
            
            if intent == "UNKNOWN":
                 print(f"   Clarification: {result.get('response_if_unknown')}")

            # Basic Validation
            if intent == case["expected_intent"] or (case["expected_intent"] == "STORE_NOTE" and intent in ["STORE_NOTE", "GET_CREDENTIALS"]):
                 print("   ✅ Intent Match")
            else:
                 print(f"   ⚠️ Intent Mismatch (Expected: {case['expected_intent']})")
                 
        except Exception as e:
            print(f"   ❌ Error processing: {e}")

if __name__ == "__main__":
    test_semantic_router()
