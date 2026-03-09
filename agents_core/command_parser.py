"""
Parseur de commandes — supporte deux modes :
  - Mode commande rapide : @agent message  ou  /commande [args]
  - Mode naturel         : tout le reste → LLM

Syntaxe :
  @agent_name <message>   → message direct à l'agent nommé
  @all <message>          → broadcast à tous les agents
  /pause [agent]          → mettre en pause un agent (ou tous)
  /resume [agent]         → reprendre un agent (ou tous)
  /status [agent]         → statut d'un agent
  /reset [agent]          → effacer l'historique LLM
  /schedule ...           → gérer les tâches planifiées
  /help                   → aide
"""
from dataclasses import dataclass
from typing import Optional


class CommandType:
    NATURAL = "natural"         # Traitement par le LLM
    DIRECT = "direct"           # @agent message
    BROADCAST = "broadcast"     # @all message
    SYSTEM = "system"           # /commande


@dataclass
class ParsedCommand:
    type: str
    target: Optional[str]       # agent_id pour DIRECT, None pour BROADCAST/SYSTEM/NATURAL
    command: Optional[str]      # nom de la commande système
    args: Optional[str]         # arguments
    raw: str                    # texte original


def parse(text: str) -> ParsedCommand:
    """Parse un message entrant et retourne sa nature."""
    text = text.strip()

    # ── Mode commande directe : @agent_name message
    if text.startswith("@"):
        parts = text[1:].split(None, 1)
        target = parts[0].lower()
        message = parts[1] if len(parts) > 1 else ""
        if target == "all":
            return ParsedCommand(
                type=CommandType.BROADCAST,
                target=None,
                command=None,
                args=message,
                raw=text,
            )
        return ParsedCommand(
            type=CommandType.DIRECT,
            target=target,
            command=None,
            args=message,
            raw=text,
        )

    # ── Mode commande système : /commande [args]
    if text.startswith("/"):
        parts = text[1:].split(None, 1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        return ParsedCommand(
            type=CommandType.SYSTEM,
            target=None,
            command=command,
            args=args,
            raw=text,
        )

    # ── Mode naturel — tout le reste
    return ParsedCommand(
        type=CommandType.NATURAL,
        target=None,
        command=None,
        args=text,
        raw=text,
    )


# Commandes système reconnues et leur aide
SYSTEM_COMMANDS_HELP = {
    "pause":    "/pause [agent]        — Mettre en pause un agent ou tous",
    "resume":   "/resume [agent]       — Reprendre un agent ou tous",
    "status":   "/status [agent]       — Voir le statut des agents",
    "reset":    "/reset [agent]        — Effacer l'historique LLM",
    "schedule": "/schedule ...         — Gérer les tâches planifiées",
    "agents":   "/agents               — Lister les agents en ligne",
    "help":     "/help                 — Afficher cette aide",
}


def help_text() -> str:
    lines = [
        "── Aide commandes ──────────────────",
        "Mode direct :",
        "  @<agent> <message>   → Envoyer un message à un agent",
        "  @all <message>       → Broadcast à tous les agents",
        "",
        "Mode système :",
    ]
    lines.extend(f"  {v}" for v in SYSTEM_COMMANDS_HELP.values())
    lines.append("")
    lines.append("Mode naturel : écris simplement ce que tu veux faire.")
    return "\n".join(lines)
