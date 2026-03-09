"""
Système de chargement de skills (plugins).
Chaque skill est un module Python avec une fonction run(args, context) → str.
"""
import importlib.util
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


class Skill:
    def __init__(self, name: str, description: str, usage: str, module):
        self.name = name
        self.description = description
        self.usage = usage
        self._module = module

    def run(self, args: str, context: "AgentContext") -> str:
        try:
            return self._module.run(args, context)
        except Exception as e:
            logger.error(f"[Skill:{self.name}] Erreur: {e}", exc_info=True)
            return f"Erreur dans le skill '{self.name}': {e}"


class SkillLoader:
    def __init__(self):
        self._skills: dict[str, Skill] = {}

    def load_directory(self, skills_dir: str):
        """Charge tous les skills d'un dossier."""
        if not os.path.isdir(skills_dir):
            logger.warning(f"Dossier skills introuvable : {skills_dir}")
            return

        for filename in sorted(os.listdir(skills_dir)):
            if filename.startswith("_") or not filename.endswith(".py"):
                continue
            skill_name = filename[:-3]
            skill_path = os.path.join(skills_dir, filename)
            self._load_skill(skill_name, skill_path)

        logger.info(f"[SkillLoader] {len(self._skills)} skill(s) chargé(s) : {list(self._skills.keys())}")

    def _load_skill(self, name: str, path: str):
        try:
            spec = importlib.util.spec_from_file_location(name, path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Vérifie les attributs requis
            if not hasattr(module, "run"):
                logger.warning(f"[SkillLoader] {name} ignoré : pas de fonction run()")
                return

            description = getattr(module, "DESCRIPTION", "Pas de description")
            usage = getattr(module, "USAGE", f"SKILL:{name} ARGS:<arguments>")

            self._skills[name] = Skill(name, description, usage, module)
            logger.debug(f"[SkillLoader] Skill chargé : {name}")

        except Exception as e:
            logger.error(f"[SkillLoader] Erreur chargement skill {name}: {e}")

    def get(self, name: str) -> Optional[Skill]:
        return self._skills.get(name)

    def run(self, name: str, args: str, context) -> str:
        skill = self.get(name)
        if skill is None:
            return f"Skill inconnu : '{name}'. Skills disponibles : {self.list_names()}"
        return skill.run(args, context)

    def list_names(self) -> list[str]:
        return list(self._skills.keys())

    def capabilities_summary(self) -> list[dict]:
        """Retourne la liste des skills pour la déclaration de capacités."""
        return [
            {"name": s.name, "description": s.description, "usage": s.usage}
            for s in self._skills.values()
        ]

    def system_prompt_section(self) -> str:
        """Génère la section du system prompt décrivant les skills disponibles."""
        if not self._skills:
            return ""
        lines = ["## Skills disponibles\n"]
        for s in self._skills.values():
            lines.append(f"- **{s.name}** : {s.description}")
            lines.append(f"  Usage : `{s.usage}`")
        lines.append(
            "\nPour utiliser un skill, réponds avec une ligne au format :\n"
            "`SKILL:<nom> ARGS:<arguments>`\n"
            "Tu peux enchaîner plusieurs skills. Explique brièvement ce que tu fais."
        )
        return "\n".join(lines)
