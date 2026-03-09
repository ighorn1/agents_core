from setuptools import setup, find_packages

setup(
    name="agent_nexus",
    version="1.0.0",
    description="Agent Nexus — Orchestrateur central du réseau multi-agents",
    py_modules=["agent_nexus"],
    install_requires=[
        "agents_core>=2.0.0",
    ],
    python_requires=">=3.10",
    entry_points={
        "console_scripts": [
            "agent-nexus=agent_nexus:main",
        ],
    },
)
