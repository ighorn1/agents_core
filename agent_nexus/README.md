# Agent Nexus

Orchestrateur central du réseau multi-agents. Basé sur [agents_core](../README.md).

## Rôle

- Reçoit les demandes utilisateur via XMPP ou MQTT
- Identifie l'agent compétent grâce au LLM + registre de capacités
- Route les tâches et agrège les résultats
- Gère les broadcasts et les alertes système

## Structure

```
agent_nexus/
├── agent_nexus.py          # Point d'entrée principal
├── requirements.txt
├── setup.py
├── config/
│   ├── config.json.example # Modèle de configuration
│   └── system_prompt.txt   # Prompt système du LLM
├── data/                   # Base SQLite (créée à l'exécution)
└── skills/
    ├── list_agents.py      # Liste les agents et leur statut
    ├── route_task.py       # Route une tâche vers un agent
    ├── broadcast_message.py# Diffuse un message à tous les agents
    └── agent_stats.py      # Statistiques de la file de tâches
```

## Installation

```bash
# Installer agents_core (dépendance)
pip install -e ../

# Installer agent_nexus
pip install -e .
```

## Configuration

```bash
cp config/config.json.example config/config.json
# Éditer config/config.json avec vos paramètres MQTT, XMPP et LLM
```

## Lancement

```bash
python agent_nexus.py
# ou, après installation :
agent-nexus
```

## Skills disponibles

| Skill | Description |
|-------|-------------|
| `list_agents` | Liste tous les agents enregistrés avec leur statut |
| `route_task` | Route une tâche vers un agent spécifique |
| `broadcast_message` | Diffuse un message à tous les agents |
| `agent_stats` | Statistiques de la file de tâches du nexus |

## Commandes système

| Commande | Effet |
|----------|-------|
| `/nexus_status` | Liste les agents connus |
| `/agents` | Alias intégré dans agents_core |
| `/pause` / `/resume` | Met en pause / reprend la file de tâches |
| `/status` | Affiche le statut courant |
| `/help` | Liste les commandes disponibles |

## Créer un nouvel agent pair

Voir [agents_core/example_agent.py](../example_agent.py) pour un exemple minimal.
Le nexus détecte automatiquement les nouveaux agents via les messages MQTT retained.
