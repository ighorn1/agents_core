"""
Message envelope standard pour tout le système.
Tous les messages MQTT et XMPP utilisent ce format.
"""
import uuid
import json
from datetime import datetime, timezone
from typing import Optional, Any


class MessageType:
    TASK = "task"                  # Tâche à exécuter
    RESULT = "result"              # Résultat d'une tâche
    STATUS = "status"              # Statut d'un agent
    BROADCAST = "broadcast"        # Message à tous les agents
    DIRECT = "direct_message"      # Message direct agent→agent
    CAPABILITIES = "capabilities"  # Déclaration des capacités
    ALERT = "alert"                # Alerte proactive d'un agent
    COMMAND = "command"            # Commande système (/pause, /resume...)


class Message:
    def __init__(
        self,
        msg_type: str,
        payload: Any,
        sender: str,
        recipient: Optional[str] = None,
        correlation_id: Optional[str] = None,
        reply_to: Optional[str] = None,
        metadata: Optional[dict] = None,
    ):
        self.id = str(uuid.uuid4())
        self.type = msg_type
        self.payload = payload
        self.sender = sender
        self.recipient = recipient
        self.correlation_id = correlation_id or self.id
        self.reply_to = reply_to
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.metadata = metadata or {}

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "payload": self.payload,
            "sender": self.sender,
            "recipient": self.recipient,
            "correlation_id": self.correlation_id,
            "reply_to": self.reply_to,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_json(cls, data: str | bytes) -> "Message":
        d = json.loads(data)
        msg = cls.__new__(cls)
        msg.id = d.get("id", str(uuid.uuid4()))
        msg.type = d.get("type", MessageType.TASK)
        msg.payload = d.get("payload", "")
        msg.sender = d.get("sender", "unknown")
        msg.recipient = d.get("recipient")
        msg.correlation_id = d.get("correlation_id", msg.id)
        msg.reply_to = d.get("reply_to")
        msg.timestamp = d.get("timestamp", datetime.now(timezone.utc).isoformat())
        msg.metadata = d.get("metadata", {})
        return msg

    def make_reply(self, sender: str, result: Any, msg_type: str = MessageType.RESULT) -> "Message":
        """Crée un message de réponse lié à ce message."""
        return Message(
            msg_type=msg_type,
            payload=result,
            sender=sender,
            recipient=self.sender,
            correlation_id=self.correlation_id,
            reply_to=self.reply_to,
        )

    def __repr__(self):
        return f"<Message type={self.type} from={self.sender} to={self.recipient}>"
