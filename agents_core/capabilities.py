"""
Gestion des capacités — chaque agent sait ce qu'il peut faire
et connaît les autres agents via les messages MQTT retained.
"""
import json
import logging
import threading
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentCapabilities:
    agent_id: str
    agent_type: str                  # nexus | debian | ansible | deploy | custom
    description: str
    skills: list[dict]               # [{"name": ..., "description": ..., "usage": ...}]
    xmpp_jid: Optional[str] = None
    xmpp_muc: Optional[str] = None
    mqtt_inbox: str = ""
    can_send_xmpp: bool = False
    can_send_mqtt: bool = True
    work_hours: str = "00:00-23:59"
    version: str = "2.0"

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_json(cls, data: str | bytes) -> "AgentCapabilities":
        d = json.loads(data)
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def summary_for_llm(self) -> str:
        """Résumé compact pour injection dans le system prompt."""
        skill_names = [s["name"] for s in self.skills]
        xmpp = f", XMPP: {self.xmpp_jid}" if self.xmpp_jid else ""
        return (
            f"  [{self.agent_id}] ({self.agent_type}) — {self.description}\n"
            f"    Skills: {', '.join(skill_names) or 'aucun'}\n"
            f"    Inbox MQTT: {self.mqtt_inbox}{xmpp}\n"
            f"    Horaires: {self.work_hours}"
        )


class CapabilitiesRegistry:
    """
    Registre local des capacités de tous les agents connus.
    Mis à jour en temps réel via les messages MQTT retained.
    """
    def __init__(self):
        self._agents: dict[str, AgentCapabilities] = {}
        self._lock = threading.Lock()

    def update(self, caps: AgentCapabilities):
        with self._lock:
            self._agents[caps.agent_id] = caps
        logger.debug(f"[Registry] Capacités mises à jour pour {caps.agent_id}")

    def update_from_json(self, data: str | bytes) -> Optional[AgentCapabilities]:
        try:
            caps = AgentCapabilities.from_json(data)
            self.update(caps)
            return caps
        except Exception as e:
            logger.error(f"[Registry] Erreur parsing capacités: {e}")
            return None

    def get(self, agent_id: str) -> Optional[AgentCapabilities]:
        with self._lock:
            return self._agents.get(agent_id)

    def all_agents(self) -> list[AgentCapabilities]:
        with self._lock:
            return list(self._agents.values())

    def online_agents(self, online_ids: set[str]) -> list[AgentCapabilities]:
        with self._lock:
            return [a for a in self._agents.values() if a.agent_id in online_ids]

    def summary_for_llm(self, online_ids: Optional[set[str]] = None) -> str:
        """Génère la section du system prompt listant les agents connus."""
        with self._lock:
            agents = self._agents.values()
        if not agents:
            return "Aucun agent enregistré."
        lines = ["## Agents disponibles\n"]
        for a in agents:
            status = ""
            if online_ids is not None:
                status = " [EN LIGNE]" if a.agent_id in online_ids else " [HORS LIGNE]"
            lines.append(f"{a.summary_for_llm()}{status}")
        return "\n".join(lines)

    def find_capable_agent(self, skill_name: str) -> Optional[AgentCapabilities]:
        """Trouve un agent capable d'exécuter un skill donné."""
        with self._lock:
            for agent in self._agents.values():
                if any(s["name"] == skill_name for s in agent.skills):
                    return agent
        return None
