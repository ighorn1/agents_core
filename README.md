# agents_core

Bibliothèque partagée pour le système multi-agents. Fournit toutes les briques communes : communication MQTT/XMPP, LLM, gestion des tâches, chargement des skills, et découverte des capacités entre agents.

## Installation

```bash
pip install -e /opt/agents_core
```

## Architecture

```
XMPP (slixmpp)          MQTT (Mosquitto local)
utilisateur  ←→  nexus  ←→  agents/nexus/inbox
                         ←→  agents/+/status      (retained)
                         ←→  agents/+/capabilities (retained)
                         ←→  agents/broadcast
                         ←→  agents/llm/switch     (retained)
```

## Modules

| Fichier | Rôle |
|---------|------|
| `base_agent.py` | Classe abstraite `BaseAgent` — à hériter dans chaque agent |
| `mqtt_client.py` | Client MQTT (paho), reconnexion auto, publish/subscribe/reply |
| `xmpp_client.py` | Client XMPP (slixmpp 1.13), reconnexion auto, MUC, thread-safe |
| `llm_client.py` | Wrapper Ollama — chat, historique, extraction de skill calls |
| `message_bus.py` | Enveloppe `Message` standard (type, payload, sender, reply_to…) |
| `skill_loader.py` | Auto-découverte et exécution des plugins `.py` dans `skills/` |
| `task_queue.py` | Queue SQLite FIFO avec worker thread |
| `capabilities.py` | `AgentCapabilities` + `CapabilitiesRegistry` — annuaire des agents |
| `command_parser.py` | Parse `/cmd`, `@agent msg`, langage naturel |

## Créer un agent

```python
from agents_core import BaseAgent, AgentContext

class MonAgent(BaseAgent):
    AGENT_TYPE = "mon_type"
    DESCRIPTION = "Description courte utilisée pour le routage LLM"
    DEFAULT_CONFIG_PATH = "/opt/mon_agent/config/config.json"

    def get_skills_dir(self) -> str:
        return "/opt/mon_agent/skills"

    def on_start(self):
        self.mqtt.send_to("nexus", f"{self.agent_id} en ligne.")

if __name__ == "__main__":
    MonAgent().run()
```

## Format config.json

```json
{
  "agent_id": "mon_agent",
  "xmpp": {
    "jid": "mon_agent@xmpp.ovh",
    "password": "...",
    "admin_jid": "sylvain@xmpp.ovh",
    "muc_room": "agents@muc.xmpp.ovh"
  },
  "mqtt": {
    "host": "localhost",
    "port": 1883
  },
  "llm": {
    "base_url": "http://192.168.7.119:11434",
    "model": "ministral-3:latest",
    "temperature": 0.3
  },
  "llm_profiles": {
    "local": "ministral-3:latest",
    "cloud": "gpt-oss:120b-cloud"
  },
  "queue_db": "/opt/mon_agent/data/queue.db"
}
```

## Créer un skill

Un skill est un fichier `.py` dans le dossier `skills/` de l'agent :

```python
# skills/mon_skill.py

NAME = "mon_skill"
DESCRIPTION = "Fait quelque chose d'utile. Args: <paramètre>"

def run(args: str, context) -> str:
    # context.agent, context.mqtt, context.xmpp, context.llm
    return f"Résultat pour : {args}"
```

Le LLM appelle le skill avec : `SKILL:mon_skill ARGS:paramètre`

## Hooks disponibles dans BaseAgent

| Méthode | Déclencheur |
|---------|-------------|
| `on_start()` | Au démarrage, après connexion MQTT |
| `on_xmpp_connected()` | Quand la connexion XMPP est établie |
| `on_agent_status_change(agent_id, status)` | Quand un agent passe online/offline |
| `on_broadcast(msg)` | Réception d'un message broadcast MQTT |
| `handle_custom_command(cmd, args, msg)` | Commande `/xxx` non gérée par BaseAgent |
| `setup_extra_subscriptions()` | Pour ajouter des souscriptions MQTT custom |

## Topics MQTT

| Topic | Usage |
|-------|-------|
| `agents/{id}/inbox` | Tâches entrantes |
| `agents/{id}/status` | Statut online/offline (retained + LWT) |
| `agents/{id}/capabilities` | Skills déclarés (retained) |
| `agents/broadcast` | Message à tous les agents |
| `agents/llm/switch` | Changement de modèle LLM global (retained) |

## Dépendances

- Python ≥ 3.10
- paho-mqtt ≥ 1.6
- slixmpp ≥ 1.8
- requests ≥ 2.28
