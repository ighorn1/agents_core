"""
Wrapper Ollama — interface unifiée pour le LLM local.
"""
import json
import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 120
MAX_HISTORY = 20  # messages conservés dans le contexte


class LLMClient:
    def __init__(self, base_url: str, model: str, temperature: float = 0.3,
                 system_prompt: str = ""):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.system_prompt = system_prompt
        self._history: list[dict] = []

    def chat(self, user_message: str, extra_context: Optional[str] = None) -> str:
        """Envoie un message et retourne la réponse du LLM."""
        messages = []

        # System prompt enrichi avec contexte dynamique si fourni
        system = self.system_prompt
        if extra_context:
            system = f"{system}\n\n[CONTEXTE ACTUEL]\n{extra_context}"
        if system:
            messages.append({"role": "system", "content": system})

        # Historique tronqué
        messages.extend(self._history[-MAX_HISTORY:])
        messages.append({"role": "user", "content": user_message})

        try:
            resp = requests.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "options": {"temperature": self.temperature},
                },
                timeout=DEFAULT_TIMEOUT,
            )
            resp.raise_for_status()
            assistant_msg = resp.json()["message"]["content"]

            # Mise à jour de l'historique
            self._history.append({"role": "user", "content": user_message})
            self._history.append({"role": "assistant", "content": assistant_msg})

            return assistant_msg

        except requests.exceptions.Timeout:
            logger.error("LLM timeout")
            return "Erreur : le LLM n'a pas répondu dans les temps."
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
