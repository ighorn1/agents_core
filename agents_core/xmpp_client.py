"""
Client XMPP avec support OMEMO, MUC (groupe), messages directs, et multi-utilisateurs.
"""
import logging
import threading
from typing import Callable, Optional

from slixmpp import ClientXMPP

logger = logging.getLogger(__name__)


class XMPPClient:
    """
    Client XMPP simplifié avec :
      - Messages directs (1-to-1)
      - Groupes MUC (Multi-User Chat)
      - OMEMO (si slixmpp-omemo installé)
      - Multi-utilisateurs : liste de JIDs autorisés à envoyer des commandes
      - Callback unique pour les messages entrants
    """

    def __init__(
        self,
        jid: str,
        password: str,
        admin_jids: Optional[list[str]] = None,
        muc_room: Optional[str] = None,
        muc_nick: Optional[str] = None,
        use_omemo: bool = False,
    ):
        self.jid       = jid
        self.password  = password
        self.muc_room  = muc_room
        self.muc_nick  = muc_nick or jid.split("@")[0]
        self.use_omemo = use_omemo

        # Normalise : accepte str ou list, stocke toujours un set de bare JIDs
        if admin_jids is None:
            self.admin_jids: set[str] = set()
        elif isinstance(admin_jids, str):
            self.admin_jids = {admin_jids.lower().split("/")[0]} if admin_jids else set()
        else:
            self.admin_jids = {j.lower().split("/")[0] for j in admin_jids if j}

        # Rétro-compat : admin_jid pointe vers le premier JID
        self.admin_jid: Optional[str] = next(iter(self.admin_jids), None)

        self._message_callback: Optional[Callable] = None
        self._client: Optional[_SlixClient] = None
        self._thread: Optional[threading.Thread] = None
        self._connected = threading.Event()

    # ──────────────────────────────────────────────
    # API publique
    # ──────────────────────────────────────────────

    def set_message_callback(self, callback: Callable[[str, str, bool], None]):
        """
        Définit le callback pour les messages reçus.
        callback(sender_jid, body, is_muc)
        Seuls les messages de admin_jids sont transmis (+ MUC).
        """
        self._message_callback = callback

    def is_authorized(self, jid: str) -> bool:
        """Vérifie si un JID est autorisé à envoyer des commandes."""
        if not self.admin_jids:
            return True  # Aucun filtre configuré → tout le monde
        bare = jid.lower().split("/")[0]
        return bare in self.admin_jids

    def connect_async(self, on_ready: Optional[Callable] = None):
        """Connexion XMPP dans un thread dédié avec reconnexion automatique."""
        self._on_ready_cb = on_ready
        self._stop_reconnect = False
        threading.Thread(target=self._reconnect_loop, daemon=True, name="xmpp-reconnect").start()

    def _reconnect_loop(self):
        """Boucle de connexion/reconnexion XMPP."""
        import time as _time
        delay = 5
        first = True
        while not self._stop_reconnect:
            self._connected.clear()
            try:
                self._client = _SlixClient(
                    jid=self.jid,
                    password=self.password,
                    muc_room=self.muc_room,
                    muc_nick=self.muc_nick,
                    use_omemo=self.use_omemo,
                    on_message=self._on_message,
                    on_connected=self._connected.set,
                )
                # Lance la connexion dans ce thread (bloquant)
                t = threading.Thread(target=self._client.start, daemon=True, name="xmpp-client")
                t.start()

                if self._connected.wait(timeout=30):
                    logger.info(f"[XMPP] Connecté : {self.jid}")
                    if self.muc_room:
                        logger.info(f"[XMPP] Groupe rejoint : {self.muc_room}")
                    if self.admin_jids:
                        logger.info(f"[XMPP] Admins autorisés : {', '.join(sorted(self.admin_jids))}")
                    if first and self._on_ready_cb:
                        first = False
                        try:
                            self._on_ready_cb()
                        except Exception as e:
                            logger.error(f"[XMPP] Erreur on_ready callback : {e}")
                    delay = 5  # Reset du délai après succès
                    t.join()   # Attend la fin de la session (déconnexion)
                    if not self._stop_reconnect:
                        logger.warning("[XMPP] Connexion perdue. Reconnexion dans 5s...")
                else:
                    logger.warning("[XMPP] Timeout connexion. Nouvelle tentative dans 10s...")
                    delay = 10
            except Exception as e:
                logger.error(f"[XMPP] Erreur connexion : {e}. Retry dans {delay}s...")

            if not self._stop_reconnect:
                _time.sleep(delay)
                delay = min(delay * 2, 60)  # Backoff exponentiel jusqu'à 60s

    def _on_message(self, sender: str, body: str, is_muc: bool):
        """Filtre les messages : seuls les admins sont traités (sauf MUC)."""
        if not is_muc and not self.is_authorized(sender):
            logger.debug(f"[XMPP] Message ignoré (non autorisé) : {sender}")
            return
        if self._message_callback:
            try:
                self._message_callback(sender, body, is_muc)
            except Exception as e:
                logger.error(f"[XMPP] Erreur callback : {e}")

    def send_message(self, to: str, body: str, is_muc: bool = False):
        """Envoie un message XMPP (direct ou MUC)."""
        if self._client is None:
            logger.warning("[XMPP] Client non initialisé")
            return
        self._client.send_xmpp_message(to, body, is_muc)

    def send_to_all_admins(self, body: str):
        """Envoie un message à tous les admins."""
        for jid in self.admin_jids:
            self.send_message(jid, body)

    def send_to_admin(self, body: str):
        """Envoie au premier admin (rétro-compat)."""
        if self.admin_jid:
            self.send_message(self.admin_jid, body)

    def send_to_group(self, body: str):
        """Envoie dans le groupe MUC."""
        if self.muc_room:
            self.send_message(self.muc_room, body, is_muc=True)

    def add_admin(self, jid: str):
        """Ajoute un JID autorisé à la volée."""
        bare = jid.lower().split("/")[0]
        self.admin_jids.add(bare)
        if not self.admin_jid:
            self.admin_jid = bare
        logger.info(f"[XMPP] Admin ajouté : {bare}")

    def remove_admin(self, jid: str):
        """Retire un JID autorisé."""
        bare = jid.lower().split("/")[0]
        self.admin_jids.discard(bare)
        if self.admin_jid == bare:
            self.admin_jid = next(iter(self.admin_jids), None)
        logger.info(f"[XMPP] Admin retiré : {bare}")

    def disconnect(self):
        self._stop_reconnect = True
        if self._client:
            try:
                self._client.disconnect()
            except Exception:
                pass


class _SlixClient(ClientXMPP):
    """Implémentation interne slixmpp."""

    def __init__(self, jid, password, muc_room, muc_nick,
                 use_omemo, on_message, on_connected):
        super().__init__(jid, password)
        self._muc_room        = muc_room
        self._muc_nick        = muc_nick
        self._on_message_cb   = on_message
        self._on_connected_cb = on_connected

        self.register_plugin("xep_0030")  # Service Discovery
        self.register_plugin("xep_0045")  # MUC
        self.register_plugin("xep_0085")  # Chat state
        self.register_plugin("xep_0199")  # Ping keepalive

        if use_omemo:
            self._setup_omemo()

        self.add_event_handler("session_start",    self._on_session_start)
        self.add_event_handler("message",          self._on_message)
        self.add_event_handler("groupchat_message", self._on_muc_message)

    def _setup_omemo(self):
        try:
            self.register_plugin("xep_0384")
            logger.info("[XMPP] OMEMO activé")
        except Exception as e:
            logger.warning(f"[XMPP] OMEMO non disponible : {e}")

    def start(self):
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.loop = loop
        self.connect()
        loop.run_forever()

    async def _on_session_start(self, event):
        self.send_presence()
        await self.get_roster()
        if self._muc_room:
            self.plugin["xep_0045"].join_muc(
                room=self._muc_room,
                nick=self._muc_nick,
            )
        if self._on_connected_cb:
            self._on_connected_cb()

    def _on_message(self, msg):
        if msg["type"] in ("chat", "normal") and msg["body"]:
            body = msg["body"].strip()
            if body:
                self._on_message_cb(str(msg["from"]), body, is_muc=False)

    def _on_muc_message(self, msg):
        if msg["mucnick"] == self._muc_nick:
            return
        if msg["body"]:
            body = msg["body"].strip()
            if body:
                self._on_message_cb(str(msg["from"]), body, is_muc=True)

    def send_xmpp_message(self, to: str, body: str, is_muc: bool = False):
        import functools
        msg_type = "groupchat" if is_muc else "chat"
        fn = functools.partial(self.send_message, mto=to, mbody=body, mtype=msg_type)
        if hasattr(self, 'loop') and self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(fn)
        else:
            fn()
