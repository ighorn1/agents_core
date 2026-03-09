"""
Wrapper Anthropic Claude — interface unifiée pour le LLM cloud.
"""
import json
import logging
from typing import Optional

import anthropic

logger = logging.getLogger(__name__)

MAX_HISTORY = 20  # messages conservés dans le contexte


class LLMClient:
    def __init__(self, api_key: Optional[str] = None, model: str = "claude-opus-4-6",
                 temperature: float = 0.3, system_prompt: str = ""):
        self.model = model
        self.temperature = temperature
        self.system_prompt = system_prompt
        self._history: list[dict] = []
        self._client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    def chat(self, user_message: str, extra_context: Optional[str] = None) -> str:
        """Envoie un message et retourne la réponse du LLM."""
        # System prompt enrichi avec contexte dynamique si fourni
        system = self.system_prompt
        if extra_context:
            system = f"{system}\n\n[CONTEXTE ACTUEL]\n{extra_context}"

        # Historique tronqué (format Anthropic : system est un paramètre séparé)
        messages = list(self._history[-MAX_HISTORY:])
        messages.append({"role": "user", "content": user_message})

        create_kwargs = dict(
            model=self.model,
            max_tokens=4096,
            messages=messages,
            thinking={"type": "adaptive"},
        )
        if system:
            create_kwargs["system"] = system

        try:
            with self._client.messages.stream(**create_kwargs) as stream:
                response = stream.get_final_message()

            # Extraire le texte de la réponse (on ignore les blocs thinking)
            assistant_msg = next(
                (block.text for block in response.content if block.type == "text"),
                "",
            )

            # Mise à jour de l'historique
            self._history.append({"role": "user", "content": user_message})
            self._history.append({"role": "assistant", "content": assistant_msg})

            return assistant_msg

        except anthropic.APIStatusError as e:
            logger.error(f"Erreur API Anthropic ({e.status_code}): {e.message}")
            return f"Erreur LLM: {e.message}"
        except anthropic.APIConnectionError as e:
            logger.error(f"Erreur connexion Anthropic: {e}")
            return "Erreur : impossible de joindre l'API Anthropic."
        except Exception as e:
            logger.error(f"Erreur LLM: {e}")
            return f"Erreur LLM: {e}"

    def reset_history(self):
        """Efface l'historique de conversation."""
        self._history.clear()
        logger.info("Historique LLM effacé")

    def extract_skill_call(self, llm_response: str) -> Optional[tuple[str, str]]:
        """
        Extrait un appel de skill depuis la réponse du LLM.
        Format attendu : SKILL:nom_skill ARGS:arguments
        Retourne (skill_name, args) ou None.
        """
        for line in llm_response.splitlines():
            line = line.strip()
            if line.startswith("SKILL:"):
                parts = line.split(" ARGS:", 1)
                skill_name = parts[0].replace("SKILL:", "").strip()
                args = parts[1].strip() if len(parts) > 1 else ""
                return skill_name, args
        return None

    def extract_json_block(self, text: str) -> Optional[dict]:
        """Extrait un bloc JSON depuis la réponse du LLM."""
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
        return None
