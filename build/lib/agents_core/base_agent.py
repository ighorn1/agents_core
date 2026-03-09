"""
Classe de base pour tous les agents du système.
Hériter de BaseAgent et implémenter les méthodes abstraites.

Usage minimal :
    class MyAgent(BaseAgent):
        AGENT_TYPE = "debian"
        DESCRIPTION = "Administration système Debian"

        def get_skills_dir(self) -> str:
            return os.path.join(os.path.dirname(__file__), "skills")

    if __name__ == "__main__":
        MyAgent().run()
"""
import json
import logging
import os
import signal
import sys
import threading
import time
from abc import ABC, abstractmethod
from typing import Optional

from .capabilities import AgentCapabilities, CapabilitiesRegistry
from .command_parser import ParsedCommand, parse as parse_command, CommandType, help_text
from .llm_client import LLMClient
from .message_bus import Message, MessageType
from .mqtt_client import MQTTClient
from .skill_loader import SkillLoader
from .task_queue import TaskQueue, Task
from .xmpp_client import XMPPClient

logger = logging.getLogger(__name__)


class AgentContext:
    """Contexte passé aux skills lors de leur exécution."""
    def __init__(self, agent: "BaseAgent", current_task: Optional[Task] = None,
                 current_message: Optional[Message] = None):
        self.agent = agent
        self.task = current_task
        self.message = current_message

    @property
    def mqtt(self) -> MQTTClient:
        return self.agent.mqtt

    @property
    def xmpp(self) -> Optional[XMPPClient]:
        return self.agent.xmpp

    @property
    def llm(self) -> LLMClient:
        return self.agent.llm

    @property
    def registry(self) -> CapabilitiesRegistry:
        return self.agent.registry

    @property
    def config(self) -> dict:
        return self.agent.config

    @property
    def agent_id(self) -> str:
        return self.agent.agent_id


class BaseAgent(ABC):
    """
    Classe mère de tous les agents.
    Fournit : MQTT, XMPP, LLM, TaskQueue, SkillLoader, CapabilitiesRegistry.
    """

    # À surcharger dans chaque agent
    AGENT_TYPE: str = "generic"
    DESCRIPTION: str = "Agent générique"
    DEFAULT_CONFIG_PATH: str = "config/config.json"

    def __init__(self, config_path: Optional[str] = None):
        self.config = self._load_config(config_path or self.DEFAULT_CONFIG_PATH)
        self.agent_id: str = self.config["agent_id"]

        logging.basicConfig(
            level=logging.INFO,
            format=f"%(asctime)s [{self.agent_id}] %(levelname)s %(message)s",
        )

        # Composants principaux
        self.mqtt = self._setup_mqtt()
        self.xmpp: Optional[XMPPClient] = self._setup_xmpp()
        self.llm = self._setup_llm()
        self.skills = SkillLoader()
        self.queue = TaskQueue(self.config.get("queue_db", "queue.db"))
        self.registry = CapabilitiesRegistry()

        # Agents en ligne (mis à jour via MQTT)
        self._online_agents: set[str] = set()
        self._online_lock = threading.Lock()

        self._running = False

    # ──────────────────────────────────────────────
    # Setup
    # ──────────────────────────────────────────────

    def _load_config(self, path: str) -> dict:
        if not os.path.exists(path):
            raise FileNotFoundError(f"Config introuvable : {path}")
        with open(path) as f:
            return json.load(f)

    def _setup_mqtt(self) -> MQTTClient:
        mc = self.config.get("mqtt", {})
        return MQTTClient(
            agent_id=self.config["agent_id"],
            broker_host=mc.get("host", "localhost"),
            broker_port=mc.get("port", 1883),
            username=mc.get("username"),
            password=mc.get("password"),
            tls=mc.get("tls", False),
        )

    def _setup_xmpp(self) -> Optional[XMPPClient]:
        xc = self.config.get("xmpp")
        if not xc:
            return None

        # Supporte admin_jids (list) et admin_jid (str) pour compatibilité
        admin_jids = xc.get("admin_jids") or []
        if not admin_jids and xc.get("admin_jid"):
            admin_jids = [xc["admin_jid"]]

        return XMPPClient(
            jid=xc["jid"],
            password=xc["password"],
            admin_jids=admin_jids,
            muc_room=xc.get("muc_room"),
            muc_nick=self.config["agent_id"],
            use_omemo=xc.get("use_omemo", False),
        )

    def _setup_llm(self) -> LLMClient:
        lc = self.config.get("llm", {})
        return LLMClient(
            base_url=lc.get("base_url", "http://localhost:11434"),
            model=lc.get("model", "mistral"),
            temperature=lc.get("temperature", 0.3),
            system_prompt=self._load_system_prompt(),
        )

    def _load_system_prompt(self) -> str:
        path = self.config.get("system_prompt", "config/system_prompt.txt")
        if os.path.exists(path):
            with open(path) as f:
                return f.read()
        return self._default_system_prompt()

    def _default_system_prompt(self) -> str:
        return (
            f"Tu es {self.agent_id}, un agent IA de type '{self.AGENT_TYPE}'.\n"
            f"Description : {self.DESCRIPTION}\n"
            f"Tu communiques via XMPP et MQTT. "
            f"Tu dois répondre de façon concise et précise.\n"
            f"Pour exécuter un skill, utilise : SKILL:<nom> ARGS:<arguments>\n"
        )

    # ──────────────────────────────────────────────
    # Démarrage
    # ──────────────────────────────────────────────

    def run(self):
        """Point d'entrée principal de l'agent."""
        logger.info(f"Démarrage de {self.agent_id} ({self.AGENT_TYPE})")

        # Chargement des skills
        skills_dir = self.get_skills_dir()
        if skills_dir:
            self.skills.load_directory(skills_dir)

        # Mise à jour du system prompt avec les skills
        if self.skills.list_names():
            extra = self.skills.system_prompt_section()
            self.llm.system_prompt += f"\n\n{extra}"

        # Connexion MQTT
        self.mqtt.connect()
        self._setup_mqtt_subscriptions()

        # Publication des capacités
        self._publish_capabilities()

        # Connexion XMPP
        if self.xmpp:
            self.xmpp.set_message_callback(self._on_xmpp_message)
            self.xmpp.connect_async()

        # Démarrage du worker de tâches
        self.queue.start_worker(self._execute_task)

        # Hook de démarrage custom
        self.on_start()

        # Gestion des signaux
        self._running = True
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

        logger.info(f"{self.agent_id} prêt.")
        try:
            while self._running:
                time.sleep(1)
        except KeyboardInterrupt:
            self._shutdown()

    def _shutdown(self, *args):
        logger.info(f"Arrêt de {self.agent_id}...")
        self._running = False
        self.queue.stop_worker()
        self.mqtt.disconnect()
        if self.xmpp:
            self.xmpp.disconnect()
        sys.exit(0)

    # ──────────────────────────────────────────────
    # MQTT — souscriptions
    # ──────────────────────────────────────────────

    def _setup_mqtt_subscriptions(self):
        self.mqtt.subscribe_inbox(self._on_mqtt_task)
        self.mqtt.subscribe_broadcast(self._on_mqtt_broadcast)
        self.mqtt.subscribe_all_capabilities(self._on_capabilities_update)
        self.mqtt.subscribe_all_status(self._on_status_update)
        # Souscriptions custom de l'agent
        self.setup_extra_subscriptions()

    def _on_mqtt_task(self, msg: Message | str, topic: str):
        """Réception d'une tâche via MQTT inbox."""
        if isinstance(msg, str):
            # Message brut non structuré
            task_id = self.queue.enqueue(
                payload=msg,
                correlation_id="raw",
                sender="unknown",
            )
            return

        if msg.type == MessageType.COMMAND:
            self._handle_system_command(msg.payload, source_msg=msg)
            return

        task_id = self.queue.enqueue(
            payload=msg.payload,
            correlation_id=msg.correlation_id,
            sender=msg.sender,
            reply_to=msg.reply_to,
        )
        logger.info(f"Tâche #{task_id} reçue de {msg.sender}")

    def _on_mqtt_broadcast(self, msg: Message | str, topic: str):
        """Réception d'un broadcast — comportement par défaut : ignorer ou logger."""
        if isinstance(msg, Message):
            logger.info(f"Broadcast reçu de {msg.sender}: {str(msg.payload)[:80]}")
            self.on_broadcast(msg)

    def _on_capabilities_update(self, msg: Message | str, topic: str):
        """Mise à jour du registre de capacités d'un autre agent."""
        try:
            raw = msg if isinstance(msg, (str, bytes)) else msg.payload
            if isinstance(raw, str):
                caps = self.registry.update_from_json(raw)
            elif isinstance(raw, dict):
                from .capabilities import AgentCapabilities
                import json as _json
                caps = self.registry.update_from_json(_json.dumps(raw))
            else:
                caps = None
            if caps and caps.agent_id != self.agent_id:
                logger.debug(f"Capacités reçues : {caps.agent_id}")
                # Mise à jour du context LLM
                self._refresh_llm_context()
        except Exception as e:
            logger.debug(f"Erreur parsing capabilities: {e}")

    def _on_status_update(self, msg: Message | str, topic: str):
        """Mise à jour du statut d'un agent."""
        try:
            raw = msg if isinstance(msg, (str, bytes)) else msg.payload
            if isinstance(raw, str):
                import json as _json
                data = _json.loads(raw)
            elif isinstance(raw, dict):
                data = raw
            else:
                return
            agent_id = data.get("agent_id")
            status = data.get("status")
            if agent_id and status:
                with self._online_lock:
                    if status == "online":
                        self._online_agents.add(agent_id)
                    else:
                        self._online_agents.discard(agent_id)
        except Exception:
            pass

    # ──────────────────────────────────────────────
    # Traitement des tâches
    # ──────────────────────────────────────────────

    def _execute_task(self, task: Task) -> tuple[str, bool]:
        """Exécute une tâche via le LLM + skills. Retourne (résultat, succès)."""
        context = AgentContext(self, current_task=task)

        # Enrichir le LLM avec le contexte actuel
        extra_ctx = self.registry.summary_for_llm(self._online_agents)

        result = self._llm_loop(task.payload, context, extra_ctx)

        # Renvoyer le résultat à l'expéditeur
        if task.sender and task.sender != "unknown":
            import uuid
            dummy_msg = Message(
                msg_type=MessageType.TASK,
                payload=task.payload,
                sender=task.sender,
                correlation_id=task.correlation_id,
                reply_to=task.reply_to,
            )
            dummy_msg.id = task.correlation_id
            self.mqtt.reply(dummy_msg, result)

        return result, True

    def _llm_loop(self, prompt: str, context: AgentContext,
                  extra_ctx: Optional[str] = None, max_steps: int = 10) -> str:
        """Boucle LLM avec exécution de skills."""
        response = self.llm.chat(prompt, extra_context=extra_ctx)

        for _ in range(max_steps):
            skill_call = self.llm.extract_skill_call(response)
            if not skill_call:
                break
            skill_name, args = skill_call
            skill_result = self.skills.run(skill_name, args, context)
            logger.info(f"[{self.agent_id}] Skill {skill_name} → {str(skill_result)[:80]}")
            response = self.llm.chat(
                f"Résultat du skill '{skill_name}':\n{skill_result}\n\nContinue ou donne ta réponse finale."
            )

        return response

    # ──────────────────────────────────────────────
    # XMPP
    # ──────────────────────────────────────────────

    def _on_xmpp_message(self, sender: str, body: str, is_muc: bool = False):
        """Traitement des messages XMPP entrants."""
        cmd = parse_command(body)
        context = AgentContext(self)

        if cmd.type == CommandType.SYSTEM:
            reply = self._handle_system_command(f"/{cmd.command} {cmd.args}", raw_cmd=cmd)
            if reply and self.xmpp:
                self.xmpp.send_message(sender, reply)
            return

        if cmd.type == CommandType.DIRECT:
            # @agent_name message → router via MQTT
            reply = self._route_direct_command(cmd)
            if reply and self.xmpp:
                self.xmpp.send_message(sender, reply)
            return

        if cmd.type == CommandType.BROADCAST:
            msg = self.mqtt.broadcast(cmd.args or "")
            if self.xmpp:
                self.xmpp.send_message(sender, f"Broadcast envoyé à tous les agents.")
            return

        # Mode naturel → LLM
        extra_ctx = self.registry.summary_for_llm(self._online_agents)
        response = self._llm_loop(body, context, extra_ctx)
        if self.xmpp:
            self.xmpp.send_message(sender, response)

    def _route_direct_command(self, cmd: ParsedCommand) -> str:
        """Route un @agent commande vers l'agent cible via MQTT."""
        target = cmd.target
        message = cmd.args or ""

        caps = self.registry.get(target)
        if caps is None:
            return f"Agent '{target}' inconnu. Agents connus : {[a.agent_id for a in self.registry.all_agents()]}"

        self.mqtt.send_to(target, message)
        return f"Message envoyé à {target}."

    # ──────────────────────────────────────────────
    # Commandes système
    # ──────────────────────────────────────────────

    def _handle_system_command(self, text: str, source_msg: Optional[Message] = None,
                                raw_cmd: Optional[ParsedCommand] = None) -> Optional[str]:
        """Gère les commandes /xxx."""
        if raw_cmd is None:
            raw_cmd = parse_command(text)
        cmd = raw_cmd.command
        args = (raw_cmd.args or "").strip()

        if cmd == "help":
            return help_text()

        if cmd == "pause":
            self.queue.pause()
            return f"[{self.agent_id}] En pause."

        if cmd == "resume":
            self.queue.resume()
            return f"[{self.agent_id}] Reprise."

        if cmd == "reset":
            self.llm.reset_history()
            return f"[{self.agent_id}] Historique effacé."

        if cmd == "status":
            stats = self.queue.daily_stats()
            paused = "OUI" if self.queue.is_paused else "NON"
            return (
                f"[{self.agent_id}] Statut\n"
                f"  En pause : {paused}\n"
                f"  Tâches aujourd'hui : {stats['total']} "
                f"(OK:{stats['completed']} ERR:{stats['failed']} ATT:{stats['pending']})\n"
                f"  Durée moyenne : {stats['avg_duration_s']}s"
            )

        if cmd == "agents":
            with self._online_lock:
                online = list(self._online_agents)
            all_agents = [a.agent_id for a in self.registry.all_agents()]
            return f"Agents en ligne : {online}\nAgents connus : {all_agents}"

        # Commandes custom de l'agent
        return self.handle_custom_command(cmd, args, source_msg)

    # ──────────────────────────────────────────────
    # Capacités
    # ──────────────────────────────────────────────

    def _publish_capabilities(self):
        """Publie les capacités de cet agent (retained)."""
        xmpp_cfg = self.config.get("xmpp", {})
        caps = AgentCapabilities(
            agent_id=self.agent_id,
            agent_type=self.AGENT_TYPE,
            description=self.DESCRIPTION,
            skills=self.skills.capabilities_summary(),
            xmpp_jid=xmpp_cfg.get("jid"),
            xmpp_muc=xmpp_cfg.get("muc_room"),
            mqtt_inbox=self.mqtt.topic_inbox(),
            can_send_xmpp=self.xmpp is not None,
            can_send_mqtt=True,
            work_hours=self.config.get("work_hours", "00:00-23:59"),
        )
        self.mqtt.publish_capabilities(caps.to_dict())
        # S'enregistre aussi dans son propre registre
        self.registry.update(caps)
        logger.info(f"Capacités publiées : {len(caps.skills)} skill(s)")

    def _refresh_llm_context(self):
        """Met à jour le context LLM avec les agents connus."""
        # Injecté dynamiquement à chaque appel LLM via extra_context
        pass

    # ──────────────────────────────────────────────
    # Méthodes à implémenter / surcharger
    # ──────────────────────────────────────────────

    @abstractmethod
    def get_skills_dir(self) -> Optional[str]:
        """Retourne le chemin vers le dossier skills de cet agent."""
        ...

    def on_start(self):
        """Hook appelé après le démarrage complet. Surcharger si besoin."""
        pass

    def on_broadcast(self, msg: Message):
        """Hook appelé à la réception d'un broadcast. Surcharger si besoin."""
        pass

    def setup_extra_subscriptions(self):
        """Souscriptions MQTT supplémentaires. Surcharger si besoin."""
        pass

    def handle_custom_command(self, cmd: str, args: str,
                               source_msg: Optional[Message] = None) -> Optional[str]:
        """Commandes /xxx non reconnues par la base. Surcharger si besoin."""
        return f"Commande inconnue : /{cmd}. Tape /help pour l'aide."
