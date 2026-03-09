"""
Skill : agent_stats
Affiche les statistiques de la file de tâches du nexus.
"""

NAME = "agent_stats"
DESCRIPTION = "Affiche les statistiques de traitement de tâches du nexus (complétées, échouées, en attente)."
USAGE = "SKILL:agent_stats ARGS:"


def run(args: str, context) -> str:
    stats = context.agent.task_queue.get_stats()
    return (
        f"Statistiques du nexus (aujourd'hui) :\n"
        f"  • Complétées : {stats.get('completed', 0)}\n"
        f"  • Échouées   : {stats.get('failed', 0)}\n"
        f"  • En attente : {stats.get('pending', 0)}\n"
        f"  • Durée moy. : {stats.get('avg_duration_ms', 0):.0f} ms"
    )
