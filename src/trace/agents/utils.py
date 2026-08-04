import os
from litellm import acompletion

async def safe_acompletion(model: str, messages: list, **kwargs):
    """
    Wrapper around litellm.acompletion to handle model-specific deprecations
    and quirks (e.g. Gemini 3.1+ temperature deprecation).
    """
    
    # Check if this is a Gemini 3.1+ model
    if model.startswith("gemini/gemini-3.1") or model.startswith("gemini-3.1"):
        # For Gemini 3.1+, sampling parameters are deprecated. 
        # Move guidance to system instructions.
        system_directive = ""
        
        if "temperature" in kwargs:
            temp = kwargs.pop("temperature")
            if temp < 0.3:
                system_directive = "[SYSTEM DIRECTIVE: Output must be highly deterministic and analytical. Avoid creative sampling.]"
            elif temp > 0.7:
                system_directive = "[SYSTEM DIRECTIVE: Output must be highly creative, divergent, and exploratory.]"
                
        if "top_p" in kwargs:
            kwargs.pop("top_p")
        if "top_k" in kwargs:
            kwargs.pop("top_k")
            
        if system_directive:
            # Ensure there is a system message to append to, or create one
            has_system = False
            for msg in messages:
                if msg["role"] == "system":
                    msg["content"] = f"{msg['content']}\n\n{system_directive}"
                    has_system = True
                    break
            
            if not has_system:
                messages.insert(0, {"role": "system", "content": system_directive})

    import asyncio
    import litellm.exceptions
    
    try:
        return await acompletion(model=model, messages=messages, **kwargs)
    except litellm.exceptions.RateLimitError as e:
        delay = 5.0
        if hasattr(e, "response") and e.response is not None:
            retry_after = e.response.headers.get("Retry-After")
            if retry_after:
                try:
                    delay = float(retry_after)
                except ValueError:
                    pass
        print(f"Rate limited on {model}, sleeping for {delay} seconds...")
        await asyncio.sleep(delay)
        raise e
