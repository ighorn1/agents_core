"""
Skill : broadcast_message
Envoie un message à tous les agents connectés.
"""

NAME = "broadcast_message"
DESCRIPTION = "Diffuse un message à tous les agents du réseau. Args: <message>"
USAGE = "SKILL:broadcast_message ARGS:<message>"


def run(args: str, context) -> str:
    message = args.strip()
    if not message:
        return "Message vide. Utilise : SKILL:broadcast_message ARGS:<ton message>"

    context.mqtt.broadcast("nexus_broadcast", {"message": message})
    agents = context.registry.list_agents()
    online_count = sum(1 for a in agents if a.get("status") == "online")
    return f"Message diffusé à {online_count} agent(s) en ligne : « {message} »"
