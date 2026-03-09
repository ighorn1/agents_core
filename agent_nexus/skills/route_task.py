"""
Skill : route_task
Route une tâche vers l'agent le plus approprié selon ses capacités.
"""

NAME = "route_task"
DESCRIPTION = (
    "Route une tâche vers l'agent compétent. "
    "Args: <agent_id>:<message>  — ex: SKILL:route_task ARGS:debian:redémarre nginx"
)
USAGE = "SKILL:route_task ARGS:<agent_id>:<message>"


def run(args: str, context) -> str:
    if ":" not in args:
        return (
            "Format invalide. Utilise : SKILL:route_task ARGS:<agent_id>:<message>\n"
            "Exemple : SKILL:route_task ARGS:debian:redémarre le service nginx"
        )

    agent_id, _, message = args.partition(":")
    agent_id = agent_id.strip()
    message = message.strip()

    if not agent_id or not message:
        return "agent_id ou message vide. Format : <agent_id>:<message>"

    # Vérifie que l'agent est connu et en ligne
    agent_info = context.registry.get_agent(agent_id)
    if not agent_info:
        available = [a["agent_id"] for a in context.registry.list_agents()]
        return (
            f"Agent '{agent_id}' inconnu. "
            f"Agents disponibles : {', '.join(available) or 'aucun'}"
        )

    if agent_info.get("status") != "online":
        return f"Agent '{agent_id}' est hors ligne. La tâche ne peut pas être routée."

    # Envoie la tâche via MQTT
    context.mqtt.send_to(agent_id, message)
    return f"Tâche envoyée à '{agent_id}' : {message}"
