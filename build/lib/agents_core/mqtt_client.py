"""
Wrapper MQTT enrichi — API simple pour publish/subscribe/reply.
Gère la reconnexion automatique, le LWT, et les enveloppes de messages.
"""
import json
import logging
import threading
import time
from typing import Callable, Optional

import paho.mqtt.client as mqtt

from .message_bus import Message, MessageType

logger = logging.getLogger(__name__)


class MQTTClient:
    """
    Client MQTT avec API simplifiée.

    Topics schema:
      agents/{id}/inbox        → tâches entrantes
      agents/{id}/status       → online/offline (retained + LWT)
      agents/{id}/capabilities → skills déclarés (retained)
      agents/broadcast         → message à tous les agents
      agents/results/{corr_id} → résultats routés
    """

    def __init__(self, agent_id: str, broker_host: str, broker_port: int = 1883,
                 username: Optional[str] = None, password: Optional[str] = None,
                 tls: bool = False):
        self.agent_id = agent_id
        self.broker_host = broker_host
        self.broker_port = broker_port
        self._subscriptions: dict[str, Callable] = {}
        self._connected = threading.Event()
        self._lock = threading.Lock()

        self.client = mqtt.Client(
            client_id=agent_id,
            clean_session=False,
            protocol=mqtt.MQTTv311,
        )

        if username:
            self.client.username_pw_set(username, password)

        if tls:
            self.client.tls_set()

        # LWT — marque l'agent offline si la connexion est perdue
        lwt_payload = json.dumps({"agent_id": agent_id, "status": "offline"})
        self.client.will_set(
            topic=self.topic_status(),
            payload=lwt_payload,
            qos=1,
            retain=True,
        )

        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

    # ──────────────────────────────────────────────
    # Topics helpers
    # ──────────────────────────────────────────────

    def topic_inbox(self, agent_id: Optional[str] = None) -> str:
        return f"agents/{agent_id or self.agent_id}/inbox"

    def topic_status(self, agent_id: Optional[str] = None) -> str:
        return f"agents/{agent_id or self.agent_id}/status"

    def topic_capabilities(self, agent_id: Optional[str] = None) -> str:
        return f"agents/{agent_id or self.agent_id}/capabilities"

    def topic_broadcast(self) -> str:
        return "agents/broadcast"

    def topic_results(self, correlation_id: str) -> str:
        return f"agents/results/{correlation_id}"

    # ──────────────────────────────────────────────
    # Connexion
    # ──────────────────────────────────────────────

    def connect(self):
        """Connexion au broker avec reconnexion automatique."""
        self.client.connect_async(self.broker_host, self.broker_port, keepalive=60)
        self.client.loop_start()
        if not self._connected.wait(timeout=10):
            raise ConnectionError(f"Impossible de se connecter au broker MQTT {self.broker_host}:{self.broker_port}")
        logger.info(f"[{self.agent_id}] Connecté au broker MQTT {self.broker_host}")

    def disconnect(self):
        self.publish_status("offline")
        self.client.loop_stop()
        self.client.disconnect()

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self._connected.set()
            self.publish_status("online")
            # Réabonnement automatique après reconnexion
            with self._lock:
                for topic in self._subscriptions:
                    client.subscribe(topic, qos=1)
            logger.info(f"[{self.agent_id}] Reconnecté et réabonné à {len(self._subscriptions)} topics")
        else:
            logger.error(f"[{self.agent_id}] Échec connexion MQTT, code={rc}")

    def _on_disconnect(self, client, userdata, rc):
        self._connected.clear()
        if rc != 0:
            logger.warning(f"[{self.agent_id}] Déconnecté du broker MQTT (rc={rc}), reconnexion automatique...")

    def _on_message(self, client, userdata, mqtt_msg):
        topic = mqtt_msg.topic
        with self._lock:
            # Cherche le callback exact ou wildcard
            callback = self._subscriptions.get(topic)
            if callback is None:
                for pattern, cb in self._subscriptions.items():
                    if self._topic_matches(pattern, topic):
                        callback = cb
                        break

        if callback is None:
            logger.debug(f"[{self.agent_id}] Message reçu sur {topic} sans callback")
            return

        try:
            msg = Message.from_json(mqtt_msg.payload)
            callback(msg, topic)
        except Exception as e:
            # Payload non-JSON (ex: commande shell brute)
            logger.debug(f"[{self.agent_id}] Payload non-JSON sur {topic}: {e}")
            try:
                callback(mqtt_msg.payload.decode(), topic)
            except Exception as e2:
                logger.error(f"[{self.agent_id}] Erreur callback sur {topic}: {e2}")

    @staticmethod
    def _topic_matches(pattern: str, topic: str) -> bool:
        """Vérifie si un topic correspond à un pattern MQTT avec wildcards."""
        p_parts = pattern.split("/")
        t_parts = topic.split("/")
        if "#" in p_parts:
            idx = p_parts.index("#")
            return p_parts[:idx] == t_parts[:idx]
        if len(p_parts) != len(t_parts):
            return False
        return all(pp == tp or pp == "+" for pp, tp in zip(p_parts, t_parts))

    # ──────────────────────────────────────────────
    # API publique — Subscribe
    # ──────────────────────────────────────────────

    def subscribe(self, topic: str, callback: Callable):
        """S'abonner à un topic avec un callback(message, topic)."""
        with self._lock:
            self._subscriptions[topic] = callback
        self.client.subscribe(topic, qos=1)
        logger.debug(f"[{self.agent_id}] Abonné à {topic}")

    def subscribe_inbox(self, callback: Callable):
        """S'abonner à sa propre inbox."""
        self.subscribe(self.topic_inbox(), callback)

    def subscribe_broadcast(self, callback: Callable):
        """S'abonner aux messages broadcast."""
        self.subscribe(self.topic_broadcast(), callback)

    def subscribe_all_capabilities(self, callback: Callable):
        """S'abonner aux déclarations de capacités de tous les agents."""
        self.subscribe("agents/+/capabilities", callback)

    def subscribe_all_status(self, callback: Callable):
        """S'abonner aux statuts de tous les agents."""
        self.subscribe("agents/+/status", callback)

    # ──────────────────────────────────────────────
    # API publique — Publish
    # ──────────────────────────────────────────────

    def publish_raw(self, topic: str, payload: str | bytes | dict, retain: bool = False, qos: int = 1):
        """Publication brute sur un topic."""
        if isinstance(payload, dict):
            payload = json.dumps(payload, ensure_ascii=False)
        self.client.publish(topic, payload, qos=qos, retain=retain)

    def send_to(self, recipient_id: str, payload: str, msg_type: str = MessageType.TASK,
                correlation_id: Optional[str] = None, reply_to: Optional[str] = None) -> Message:
        """Envoyer un message à un agent spécifique via son inbox."""
        msg = Message(
            msg_type=msg_type,
            payload=payload,
            sender=self.agent_id,
            recipient=recipient_id,
            correlation_id=correlation_id,
            reply_to=reply_to or self.topic_inbox(),
        )
        self.publish_raw(self.topic_inbox(recipient_id), msg.to_json())
        logger.info(f"[{self.agent_id}] → {recipient_id}: {str(payload)[:80]}")
        return msg

    def reply(self, original: Message, result: str, msg_type: str = MessageType.RESULT):
        """Répondre à un message reçu (utilise reply_to ou inbox du sender)."""
        reply_msg = original.make_reply(self.agent_id, result, msg_type)
        target_topic = original.reply_to or self.topic_inbox(original.sender)
        self.publish_raw(target_topic, reply_msg.to_json())
        logger.info(f"[{self.agent_id}] ↩ {original.sender}: {str(result)[:80]}")
        return reply_msg

    def broadcast(self, payload: str, msg_type: str = MessageType.BROADCAST) -> Message:
        """Envoyer un message à tous les agents."""
        msg = Message(
            msg_type=msg_type,
            payload=payload,
            sender=self.agent_id,
        )
        self.publish_raw(self.topic_broadcast(), msg.to_json())
        return msg

    def alert(self, message: str, severity: str = "warning"):
        """Envoyer une alerte proactive à l'orchestrateur."""
        # Cherche le nexus dans les agents connus ou utilise un topic dédié
        msg = Message(
            msg_type=MessageType.ALERT,
            payload=message,
            sender=self.agent_id,
            metadata={"severity": severity},
        )
        # On publie sur l'inbox de l'orchestrateur (nom configurable)
        self.publish_raw("agents/nexus/inbox", msg.to_json())

    def publish_status(self, status: str, extra: Optional[dict] = None):
        """Publier le statut de l'agent (retained)."""
        payload = {"agent_id": self.agent_id, "status": status}
        if extra:
            payload.update(extra)
        self.publish_raw(self.topic_status(), payload, retain=True)

    def publish_capabilities(self, capabilities: dict):
        """Publier les capacités de l'agent (retained)."""
        self.publish_raw(self.topic_capabilities(), capabilities, retain=True)
