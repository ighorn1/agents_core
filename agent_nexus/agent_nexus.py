"""
Agent Nexus — Orchestrateur central du réseau multi-agents.

Rôle :
  - Router les tâches entrantes (XMPP/MQTT) vers l'agent le plus compétent
  - Agréger les résultats et répondre à l'utilisateur
  - Gérer les broadcasts et les alertes système
  - Tenir à jour le registre des agents en ligne

Utilise agents_core.BaseAgent comme fondation.
"""
import os
from agents_core import BaseAgent, Message, MessageType


class AgentNexus(BaseAgent):
    AGENT_TYPE = "nexus"
    DESCRIPTION = (
        "Orchestrateur central : reçoit les demandes utilisateur, "
        "identifie l'agent compétent et route la tâche. "
        "Agrège et présente les résultats."
    )
    DEFAULT_CONFIG_PATH = os.path.join(
        os.path.dirname(__file__), "config", "config.json"
    )

    # ------------------------------------------------------------------ #
    #  Surcharges de BaseAgent                                             #
    # ------------------------------------------------------------------ #

    def get_skills_dir(self) -> str:
        return os.path.join(os.path.dirname(__file__), "skills")

    def on_start(self):
        """Actions exécutées une fois les connexions établies."""
        self.logger.info("Nexus opérationnel — en attente de tâches.")
        # Annonce aux autres agents que le nexus est prêt
        self.mqtt.broadcast("nexus_online", {"agent_id": self.agent_id})

    def on_xmpp_connected(self):
        """Rejoint la salle MUC dès que XMPP est connecté."""
        self.logger.info("Nexus connecté à XMPP.")

    def on_agent_status_change(self, agent_id: str, status: str):
        """Loggue les changements de statut des agents pairs."""
        emoji = "🟢" if status == "online" else "🔴"
        self.logger.info(f"{emoji} Agent {agent_id!r} est maintenant {status}.")

    def on_broadcast(self, msg: Message):
        """Traite les messages broadcast reçus des autres agents."""
        self.logger.info(
            f"[BROADCAST] de {msg.sender}: {msg.payload}"
        )

    def setup_extra_subscriptions(self):
        """Abonnements MQTT supplémentaires propres au nexus."""
        # Écoute les résultats de tous les agents
        self.mqtt.subscribe("agents/+/result", self._on_agent_result)

    # ------------------------------------------------------------------ #
    #  Gestion des résultats entrants                                      #
    # ------------------------------------------------------------------ #

    def _on_agent_result(self, topic: str, msg: Message):
        """
        Reçoit un résultat d'un agent et le transmet à l'utilisateur
        via XMPP si un JID de réponse est disponible dans la corrélation.
        """
        correlation_id = msg.correlation_id
        result_text = msg.payload.get("result", "")
        sender_agent = msg.sender

        self.logger.info(
            f"Résultat reçu de {sender_agent!r} "
            f"(correlation={correlation_id}): {result_text[:80]}…"
        )

        # Retransmet la réponse à l'utilisateur XMPP si le JID est connu
        reply_jid = msg.payload.get("reply_jid")
        if reply_jid and self.xmpp:
            self.xmpp.send_message(
                reply_jid,
                f"[{sender_agent}] {result_text}",
            )

    # ------------------------------------------------------------------ #
    #  Commandes personnalisées (/nexus_status, /agents, …)               #
    # ------------------------------------------------------------------ #

    def handle_custom_command(self, cmd: str, args: str, msg: Message):
        """Gère les commandes spécifiques au nexus."""
        if cmd == "nexus_status":
            agents = self.registry.list_agents()
            lines = [f"  • {a['agent_id']} ({a['status']})" for a in agents]
            return "Agents connus :\n" + "\n".join(lines) if lines else "Aucun agent enregistré."
        return None  # Délègue au traitement standard


if __name__ == "__main__":
    AgentNexus().run()
