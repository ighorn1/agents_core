"""
agents_core — Librairie commune pour tous les agents du système.
"""
from .base_agent import BaseAgent, AgentContext
from .message_bus import Message, MessageType
from .mqtt_client import MQTTClient
from .xmpp_client import XMPPClient
from .llm_client import LLMClient
from .task_queue import TaskQueue, Task, TaskStatus
from .skill_loader import SkillLoader, Skill
from .capabilities import AgentCapabilities, CapabilitiesRegistry
from .command_parser import parse as parse_command, ParsedCommand, CommandType

__version__ = "2.0.0"
__all__ = [
    "BaseAgent", "AgentContext",
    "Message", "MessageType",
    "MQTTClient",
    "XMPPClient",
    "LLMClient",
    "TaskQueue", "Task", "TaskStatus",
    "SkillLoader", "Skill",
    "AgentCapabilities", "CapabilitiesRegistry",
    "parse_command", "ParsedCommand", "CommandType",
]
