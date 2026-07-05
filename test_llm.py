import os
import asyncio
from dotenv import load_dotenv

load_dotenv()

async def test_llm():
    import litellm
    print("Testing LiteLLM with Gemini...")
    try:
        response = await litellm.acompletion(
            model=os.environ.get("PLANNER_MODEL", "gemini/gemini-3.1-flash-lite"),
            messages=[{"role": "user", "content": "Hello! Reply with 'LiteLLM works' if you can read this."}]
        )
        print("Response:", response.choices[0].message.content)
    except Exception as e:
        print("Error:", str(e))

if __name__ == "__main__":
    asyncio.run(test_llm())
