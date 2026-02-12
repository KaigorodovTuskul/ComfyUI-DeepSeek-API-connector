import json
from typing import Dict
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"


SYSTEM_PROMPT_PRESETS: Dict[str, str] = {
    "Improve prompt (default)": (
        "You are an expert prompt engineer for image generation. "
        "Rewrite and improve the user's prompt to be clearer, richer in visual details, "
        "composition, lighting, style, quality tags, and camera/lens hints when relevant. "
        "Return only the final improved prompt text."
    ),
    "Create prompt from idea": (
        "You are an expert prompt engineer for image generation. "
        "If user provides an idea, produce one strong, production-ready image prompt. "
        "If input is empty, invent a compelling prompt yourself. "
        "Return only the final prompt text."
    ),
    "Photorealistic refinement": (
        "You improve prompts for photorealistic image generation. "
        "Add scene detail, lens/camera cues, realistic lighting, textures, and composition. "
        "Avoid fantasy terms unless user asks. Return only the final prompt text."
    ),
    "Cinematic style": (
        "You improve prompts in cinematic style. "
        "Enhance storytelling, framing, mood, color grading, lighting direction, and shot type. "
        "Return only the final prompt text."
    ),
    "Anime style": (
        "You improve prompts for anime-style image generation. "
        "Enhance character design, line style, palette, mood, and composition. "
        "Return only the final prompt text."
    ),
    "Custom": "",
}

TARGET_MODEL_HINTS: Dict[str, str] = {
    "z-image turbo": (
        "Prioritize concise but high-signal wording with strong visual anchors and minimal redundancy."
    ),
    "nano banana pro": (
        "Use practical, concrete descriptors and stable composition instructions."
    ),
    "seedream 4.5": (
        "Emphasize imaginative atmosphere, cinematic lighting, and rich scene storytelling."
    ),
    "flux 2 klein 9b": (
        "Use clear structure with subject, environment, lighting, and style in predictable order."
    ),
    "qwen image 2512": (
        "Provide balanced detail and explicit visual constraints for reliable output."
    ),
    "qwen edit image 2511": (
        "Write edit-oriented instructions, preserving base content while specifying precise changes."
    ),
    "sdxl": (
        "Use SDXL-friendly descriptive style with clear subject, style, composition, and quality cues."
    ),
}

PROMPT_STYLE_HINTS: Dict[str, str] = {
    "Short": "Keep the output short and compact.",
    "Detailed": "Provide a detailed, information-rich prompt.",
    "Artistic": "Use expressive artistic language and mood-driven descriptors.",
    "Cinematic": "Use cinematic framing, shot language, and color-grading cues.",
    "Technical": "Use technical, precise wording focused on controllable visual attributes.",
}

LANGUAGE_HINTS: Dict[str, str] = {
    "english": "Return the final prompt in English only.",
    "chinese": "Return the final prompt in Simplified Chinese only.",
}


class DeepSeekPromptConnector:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "api_key": ("STRING", {"multiline": False, "default": ""}),
                "model": (["deepseek-chat", "deepseek-reasoner"], {"default": "deepseek-chat"}),
                "temperature": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.05}),
                "max_tokens": ("INT", {"default": 512, "min": 1, "max": 8192, "step": 1}),
                "output_language": (["english", "chinese"], {"default": "english"}),
                "target_model": (
                    [
                        "z-image turbo",
                        "nano banana pro",
                        "seedream 4.5",
                        "flux 2 klein 9b",
                        "qwen image 2512",
                        "qwen edit image 2511",
                        "sdxl",
                    ],
                    {"default": "sdxl"},
                ),
                "prompt_style": (
                    ["Short", "Detailed", "Artistic", "Cinematic", "Technical"],
                    {"default": "Detailed"},
                ),
                "system_prompt_mode": (list(SYSTEM_PROMPT_PRESETS.keys()), {"default": "Improve prompt (default)"}),
                "custom_system_prompt": ("STRING", {"multiline": True, "default": ""}),
            },
            "optional": {
                "text": ("STRING", {"multiline": True, "default": ""}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("prompt", "preview")
    FUNCTION = "generate_prompt"
    CATEGORY = "text/deepseek"

    def _resolve_system_prompt(self, system_prompt_mode: str, custom_system_prompt: str) -> str:
        if system_prompt_mode == "Custom":
            custom_value = (custom_system_prompt or "").strip()
            if not custom_value:
                raise ValueError("system_prompt_mode is Custom, but custom_system_prompt is empty.")
            return custom_value
        return SYSTEM_PROMPT_PRESETS.get(system_prompt_mode, SYSTEM_PROMPT_PRESETS["Improve prompt (default)"])

    def _build_user_message(self, text: str, output_language: str, target_model: str, prompt_style: str) -> str:
        clean_text = (text or "").strip()
        language_hint = LANGUAGE_HINTS.get(output_language, LANGUAGE_HINTS["english"])
        target_model_hint = TARGET_MODEL_HINTS.get(target_model, TARGET_MODEL_HINTS["sdxl"])
        style_hint = PROMPT_STYLE_HINTS.get(prompt_style, PROMPT_STYLE_HINTS["Detailed"])

        control_block = (
            "Generation requirements:\n"
            f"- Target image model: {target_model}\n"
            f"- Model adaptation note: {target_model_hint}\n"
            f"- Prompt style: {prompt_style}. {style_hint}\n"
            f"- Output language: {output_language}. {language_hint}\n"
            "- Return only the final prompt text with no explanation."
        )

        if clean_text:
            return (
                "Improve this prompt for image generation. "
                "Keep intent, but increase quality and specificity:\n\n"
                f"{clean_text}\n\n"
                f"{control_block}"
            )
        return (
            "No input prompt was provided. "
            "Generate a complete high-quality image-generation prompt from scratch.\n\n"
            f"{control_block}"
        )

    def _call_deepseek(
        self,
        api_key: str,
        model: str,
        temperature: float,
        max_tokens: int,
        system_prompt: str,
        user_message: str,
    ) -> str:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        req = Request(
            DEEPSEEK_API_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )

        try:
            with urlopen(req, timeout=90) as resp:
                raw = resp.read().decode("utf-8")
        except HTTPError as e:
            body = e.read().decode("utf-8", errors="replace") if e.fp else ""
            raise RuntimeError(f"DeepSeek API HTTP {e.code}: {body}") from e
        except URLError as e:
            raise RuntimeError(f"DeepSeek API connection error: {e.reason}") from e
        except Exception as e:
            raise RuntimeError(f"Unexpected DeepSeek API error: {e}") from e

        try:
            data = json.loads(raw)
            content = data["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError("Empty response content.")
            return content.strip()
        except Exception as e:
            raise RuntimeError(f"Failed to parse DeepSeek response: {raw}") from e

    def generate_prompt(
        self,
        api_key,
        model,
        temperature,
        max_tokens,
        output_language,
        target_model,
        prompt_style,
        system_prompt_mode,
        custom_system_prompt,
        text="",
    ):
        api_key = (api_key or "").strip()
        if not api_key:
            raise ValueError("api_key is required.")

        system_prompt = self._resolve_system_prompt(system_prompt_mode, custom_system_prompt)
        user_message = self._build_user_message(
            text=text,
            output_language=output_language,
            target_model=target_model,
            prompt_style=prompt_style,
        )
        prompt = self._call_deepseek(
            api_key=api_key,
            model=model,
            temperature=float(temperature),
            max_tokens=int(max_tokens),
            system_prompt=system_prompt,
            user_message=user_message,
        )
        preview = (
            f"[model: {target_model}] [style: {prompt_style}] [lang: {output_language}]\n\n{prompt}"
        )
        return {"ui": {"text": [preview]}, "result": (prompt, preview)}


NODE_CLASS_MAPPINGS = {
    "DeepSeekPromptConnector": DeepSeekPromptConnector,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "DeepSeekPromptConnector": "DeepSeek Prompt Connector",
}
