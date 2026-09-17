/**
 * Archipelago WebSocket protocol layer for the Taskipelago web client.
 *
 * Handles connection across URL candidates and the AP network packets used by
 * play, console, data storage and the DataPackage.
 */
import { hasFeature } from './shared/config.js';

export const ClientStatus = { UNKNOWN: 0, CONNECTED: 5, READY: 10, PLAYING: 20, GOAL: 30 };

export class ArchipelagoClient {
  constructor() {
    this._ws = null;
    this._slotName = '';
    this._password = null;
    this._wsEstablished = false; // true once 'Connected' packet received
    this._advanceOnClose = true; // false after ConnectionRefused
    this._secureOnly = false;

    // Filled on RoomInfo / Connected
    this.roomInfo   = null;
    this.ourSlot    = null;
    this.ourTeam    = null;
    this.playerNames = {};   // slot -> display name
    this.slotInfo   = {};
    this.checkedLocations = new Set();
    this.missingLocations = new Set();
    this.sentLocations    = new Set(); // checks this client sent this session
    this.itemsReceived    = [];  // sparse array indexed by AP item index
    this.ready = false;

    // Callbacks - set these before calling connect()
    this.onRoomInfo     = null; // (roomInfo) => void
    this.onConnected    = null; // (slotData, checkedLocs[]) => void
    this.onDisconnected = null; // (reason) => void
    this.onReceivedItems = null;// (items[], packetIndex) => void
    this.onRoomUpdate   = null; // (newChecked[]) => void
    this.onBounced      = null; // (tags[], data{}) => void
    this.onPrintJSON    = null; // (parts[], msgType, senderSlot) => void
    this.onRetrieved    = null; // (keys{}) => void
    this.onSetReply     = null; // (key, value, msg) => void
    this.onDataPackage  = null; // (games{}) => void
  }

  /**
   * Connect to an Archipelago server.
   * UNIFY 1.3: an explicit scheme is used as-is; ws:// is only attempted when
   * the page may open insecure sockets (local webhost / plain http).
   */
  connect(server, slotName, password) {
    this.disconnect();
    this._slotName = slotName;
    this._password = password || null;
    this._wsEstablished = false;
    this._advanceOnClose = true;
    this.roomInfo = null;
    this.checkedLocations = new Set();
    this.missingLocations = new Set();
    this.sentLocations = new Set();
    this.itemsReceived = [];
    this.ready = false;

    const raw = server.trim();
    const candidates = [];

    this._secureOnly = !hasFeature('insecureWs');
    if (raw.includes('://')) {
      candidates.push(raw);
    } else if (this._secureOnly) {
      candidates.push(`wss://${raw}`);
    } else {
      const isAP = raw.toLowerCase().includes('archipelago.gg');
      if (isAP) candidates.push(`wss://${raw}`);
      candidates.push(`ws://${raw}`);
      if (!isAP) candidates.push(`wss://${raw}`);
    }

    this._tryConnect(candidates, 0);
  }

  _tryConnect(candidates, idx) {
    if (idx >= candidates.length) {
      this.onDisconnected?.(this._secureOnly
        ? 'This server may not support secure connections. Use the Taskipelago Client ' +
          'from the Archipelago launcher to connect to ws:// servers.'
        : 'Could not connect to server.');
      return;
    }

    const url = candidates[idx];
    let ws;
    try {
      ws = new WebSocket(url);
    } catch (e) {
      this._tryConnect(candidates, idx + 1);
      return;
    }

    this._ws = ws;
    let advanced = false;

    const tryNext = () => {
      if (advanced) return;
      advanced = true;
      if (this._ws === ws) this._ws = null;
      this._tryConnect(candidates, idx + 1);
    };

    ws.onmessage = (ev) => {
      let msgs;
      try { msgs = JSON.parse(ev.data); } catch (e) { return; }
      if (!Array.isArray(msgs)) msgs = [msgs];
      for (const msg of msgs) {
        this._handleMsg(msg, tryNext);
      }
    };

    ws.onerror = () => {
      if (!this._wsEstablished) tryNext();
    };

    ws.onclose = () => {
      if (this._wsEstablished) {
        this._wsEstablished = false;
        this.onDisconnected?.('Connection closed.');
      } else if (this._advanceOnClose) {
        tryNext();
      }
    };
  }

  _handleMsg(msg, tryNext) {
    const { cmd } = msg;

    if (cmd === 'RoomInfo') {
      this.roomInfo = msg;
      this.onRoomInfo?.(msg);
      this._sendConnect();

    } else if (cmd === 'Connected') {
      // Stop advancing to next URL on any future close
      this._wsEstablished = true;
      this._advanceOnClose = false;

      this.ourSlot = msg.slot ?? null;
      this.ourTeam = msg.team ?? null;

      this._setPlayers(msg.players);
      this.slotInfo = msg.slot_info || {};

      const checked = msg.checked_locations || [];
      for (const c of checked) this.checkedLocations.add(c);
      this.missingLocations = new Set(msg.missing_locations || []);
      for (const c of checked) this.missingLocations.delete(c);

      const slotData = msg.slot_data || {};
      this.onConnected?.(slotData, checked);

      // Request the full item list twice, 250ms apart (legacy client.py:1460).
      const ws = this._ws;
      this._send([{ cmd: 'Sync' }]);
      setTimeout(() => { if (this._ws === ws) this._send([{ cmd: 'Sync' }]); }, 250);

    } else if (cmd === 'ConnectionRefused') {
      this._advanceOnClose = false;
      const errors = (msg.errors || []).join(', ');
      this.onDisconnected?.(`Connection refused: ${errors || 'unknown reason'}`);

    } else if (cmd === 'ReceivedItems') {
      const packetIndex = msg.index || 0;
      const rawItems    = msg.items || [];
      const items = rawItems.map(it => {
        if (Array.isArray(it)) {
          return { item: it[0], location: it[1], player: it[2], flags: it[3] ?? 0 };
        }
        return {
          item:     it.item     ?? null,
          location: it.location ?? null,
          player:   it.player   ?? null,
          flags:    it.flags    ?? 0,
        };
      });

      // Store into sparse array so callers can index by AP absolute index
      for (let i = 0; i < items.length; i++) {
        this.itemsReceived[packetIndex + i] = items[i];
      }

      this.onReceivedItems?.(items, packetIndex);

    } else if (cmd === 'RoomUpdate') {
      const newChecked = msg.checked_locations || [];
      for (const c of newChecked) {
        this.checkedLocations.add(c);
        this.missingLocations.delete(c);
      }
      if (Array.isArray(msg.players)) this._setPlayers(msg.players);
      this.onRoomUpdate?.(newChecked);

    } else if (cmd === 'Bounced') {
      this.onBounced?.(msg.tags || [], msg.data || {});

    } else if (cmd === 'Retrieved') {
      this.onRetrieved?.(msg.keys || {});

    } else if (cmd === 'SetReply') {
      this.onSetReply?.(msg.key, msg.value, msg);

    } else if (cmd === 'DataPackage') {
      this.onDataPackage?.((msg.data && msg.data.games) || {});

    } else if (cmd === 'PrintJSON') {
      this.onPrintJSON?.(msg.data || [], msg.type || 'text', msg.slot ?? null);
    }
  }

  _setPlayers(players) {
    this.playerNames = {};
    for (const p of (players || [])) {
      this.playerNames[p.slot] = p.alias || p.name || `Player ${p.slot}`;
    }
  }

  _sendConnect() {
    this._send([{
      cmd: 'Connect',
      game: 'Taskipelago',
      name: this._slotName,
      password: this._password,
      version: { major: 0, minor: 5, build: 1, class: 'Version' },
      tags: ['AP', 'TaskipelagoSync'],
      items_handling: 7,
      uuid: (typeof crypto !== 'undefined' && crypto.randomUUID)
        ? crypto.randomUUID()
        : this._makeUUID(),
      slot_data: true,
    }]);
  }

  _makeUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
      const r = Math.random() * 16 | 0;
      return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
    });
  }

  _send(msgs) {
    if (this._ws?.readyState === WebSocket.OPEN) {
      this._ws.send(JSON.stringify(msgs));
    }
  }

  disconnect() {
    if (this._ws) {
      this._advanceOnClose = false;
      try { this._send([{ cmd: 'Disconnect' }]); } catch (_) {}
      try { this._ws.close(); } catch (_) {}
      this._ws = null;
    }
    this._wsEstablished = false;
  }

  /** Resolve a slot number to a display name: playerNames, then slotInfo, then "Player N". */
  resolvePlayerName(slot) {
    if (slot == null) return null;
    if (this.playerNames[slot]) return this.playerNames[slot];
    const info = this.slotInfo[slot];
    if (info && info.name) return info.name;
    return `Player ${slot}`;
  }

  /** Game played by a slot, from slot_info. */
  gameOfSlot(slot) {
    const info = this.slotInfo[slot];
    return (info && info.game) || null;
  }

  // ---- Outgoing helpers ----

  sendLocationChecks(locations) {
    for (const l of locations) this.sentLocations.add(l);
    this._send([{ cmd: 'LocationChecks', locations }]);
  }

  sendSay(text) {
    this._send([{ cmd: 'Say', text }]);
  }

  sendStatusUpdate(status) {
    this._send([{ cmd: 'StatusUpdate', status }]);
  }

  sendLocationScouts(locations, createAsHint) {
    this._send([{ cmd: 'LocationScouts', locations, create_as_hint: createAsHint }]);
  }

  /** Send a Bounce (DeathLink, TaskipelagoSync). */
  sendBounce(tags, data) {
    this._send([{ cmd: 'Bounce', tags, data }]);
  }

  /** Update the tags advertised to the server (used to opt into DeathLink). */
  sendConnectUpdate(tags) {
    this._send([{ cmd: 'ConnectUpdate', tags }]);
  }

  /** Read keys from data storage. Results arrive via onRetrieved. */
  sendGet(keys) {
    this._send([{ cmd: 'Get', keys }]);
  }

  /** Subscribe to data storage changes. Changes arrive via onSetReply. */
  sendSetNotify(keys) {
    this._send([{ cmd: 'SetNotify', keys }]);
  }

  /**
   * Apply data storage operations to a key. Extra fields are echoed back by the
   * server in the SetReply (used to recognize our own writes).
   */
  sendSetOps(key, defaultValue, operations, wantReply = false, extra = {}) {
    this._send([{ ...extra, cmd: 'Set', key, default: defaultValue, want_reply: wantReply, operations }]);
  }

  /** Replace a data storage value. */
  sendSet(key, value, defaultValue = null) {
    this.sendSetOps(key, defaultValue, [{ operation: 'replace', value }], false);
  }

  sendGetDataPackage(games) {
    this._send([{ cmd: 'GetDataPackage', games }]);
  }
}
