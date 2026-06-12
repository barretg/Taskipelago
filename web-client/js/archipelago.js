/**
 * Archipelago WebSocket protocol layer for Taskipelago Web Client.
 *
 * Handles connection, reconnection across URL candidates, and all
 * standard AP network packets needed by the Connect-and-Play flow.
 */
export class ArchipelagoClient {
  constructor() {
    this._ws = null;
    this._slotName = '';
    this._password = null;
    this._wsEstablished = false; // true once 'Connected' packet received
    this._advanceOnClose = true; // false after ConnectionRefused

    // Filled on Connected
    this.ourSlot    = null;
    this.ourTeam    = null;
    this.playerNames = {};   // slot -> display name
    this.slotInfo   = {};
    this.checkedLocations = new Set();
    this.itemsReceived    = [];  // sparse array indexed by AP item index

    // Callbacks – set these before calling connect()
    this.onConnected    = null; // (slotData, checkedLocs[]) => void
    this.onDisconnected = null; // (reason) => void
    this.onReceivedItems = null;// (items[], packetIndex) => void
    this.onRoomUpdate   = null; // (newChecked[]) => void
    this.onBounced      = null; // (tags[], data{}) => void
    this.onPrintJSON    = null; // (parts[], msgType, senderSlot) => void
  }

  /**
   * Connect to an Archipelago server.
   * Tries wss:// first for archipelago.gg, then ws://, then wss:// for others.
   */
  connect(server, slotName, password) {
    this.disconnect();
    this._slotName = slotName;
    this._password = password || null;
    this._wsEstablished = false;
    this._advanceOnClose = true;
    this.checkedLocations = new Set();
    this.itemsReceived = [];

    const raw = server.trim();
    const candidates = [];

    if (raw.includes('://')) {
      candidates.push(raw);
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
      this.onDisconnected?.(
        'Could not connect to server. ' +
        'If your server is local over ws://, ensure you are accessing this page via HTTP (not HTTPS) ' +
        'to avoid mixed-content restrictions.'
      );
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
      this._sendConnect();

    } else if (cmd === 'Connected') {
      // Stop advancing to next URL on any future close
      this._wsEstablished = true;
      this._advanceOnClose = false;

      this.ourSlot = msg.slot ?? null;
      this.ourTeam = msg.team ?? null;

      this.playerNames = {};
      for (const p of (msg.players || [])) {
        this.playerNames[p.slot] = p.alias || p.name || `Player ${p.slot}`;
      }
      this.slotInfo = msg.slot_info || {};

      const checked = msg.checked_locations || [];
      for (const c of checked) this.checkedLocations.add(c);

      const slotData = msg.slot_data || {};
      this.onConnected?.(slotData, checked);

      // Request full item list
      this._send([{ cmd: 'Sync' }]);

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
      for (const c of newChecked) this.checkedLocations.add(c);
      this.onRoomUpdate?.(newChecked);

    } else if (cmd === 'Bounced') {
      this.onBounced?.(msg.tags || [], msg.data || {});

    } else if (cmd === 'PrintJSON') {
      this.onPrintJSON?.(msg.data || [], msg.type || 'text', msg.slot ?? null);
    }
  }

  _sendConnect() {
    this._send([{
      cmd: 'Connect',
      game: 'Taskipelago',
      name: this._slotName,
      password: this._password,
      version: { major: 0, minor: 5, build: 1, class: 'Version' },
      tags: ['TaskipelagoSync'],
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

  // ---- Outgoing helpers ----

  sendLocationChecks(locations) {
    this._send([{ cmd: 'LocationChecks', locations }]);
  }

  sendSay(text) {
    this._send([{ cmd: 'Say', text }]);
  }

  sendStatusUpdate(status) {
    this._send([{ cmd: 'StatusUpdate', status }]);
  }

  /** Send a DeathLink bounce. */
  sendBounce(tags, data) {
    this._send([{ cmd: 'Bounce', tags, data }]);
  }

  /** Update the tags advertised to the server (used to opt into DeathLink). */
  sendConnectUpdate(tags) {
    this._send([{ cmd: 'ConnectUpdate', tags }]);
  }
}
