from setuptools import setup, find_packages

setup(
    name="agents_core",
    version="2.0.0",
    packages=find_packages(),
    install_requires=[
        "paho-mqtt>=1.6",
        "slixmpp>=1.8",
        "requests>=2.28",
    ],
    extras_require={
        "omemo": ["slixmpp-omemo>=1.0"],
    },
    python_requires=">=3.10",
)
