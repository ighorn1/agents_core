"""
Skill : list_agents
Retourne la liste des agents enregistrés et leur statut.
"""

NAME = "list_agents"
DESCRIPTION = "Liste tous les agents connus avec leur statut (online/offline) et leurs capacités."
USAGE = "SKILL:list_agents ARGS:"


def run(args: str, context) -> str:
    agents = context.registry.list_agents()
    if not agents:
        return "Aucun agent enregistré pour l'instant."

    lines = []
    for a in agents:
        status_icon = "🟢" if a.get("status") == "online" else "🔴"
        skills = ", ".join(a.get("skills", [])) or "—"
        lines.append(
            f"{status_icon} {a['agent_id']} [{a.get('agent_type', '?')}] — skills : {skills}"
        )
    return "Agents du réseau :\n" + "\n".join(lines)
