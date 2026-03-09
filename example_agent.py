"""
Exemple minimal d'un agent utilisant agents_core.
Remplace les 227 lignes actuelles de agent2_debian13.py.
"""
import os
from agents_core import BaseAgent


class AgentDebian(BaseAgent):
    AGENT_TYPE = "debian"
    DESCRIPTION = "Administration système Debian : apt, systemd, réseau, conteneurs, logs"

    def get_skills_dir(self) -> str:
        return os.path.join(os.path.dirname(__file__), "skills")

    def on_start(self):
        """Actions au démarrage."""
        self.mqtt.send_to("nexus", "Agent Debian en ligne et prêt.")


if __name__ == "__main__":
    AgentDebian().run()
