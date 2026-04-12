// @ts-check

/**
 * @typedef {Object} PlayerState
 * @property {string} id - Entity ID (e.g. "player_1")
 * @property {number} dbId - DB primary key
 * @property {string} name
 * @property {number} x
 * @property {number} y
 */

/**
 * @typedef {Object} Entity
 * @property {string} id
 * @property {string} name
 * @property {number} x
 * @property {number} y
 */

/**
 * @typedef {Object} NpcData
 * @property {string} id
 * @property {string} npc_key
 * @property {string} name
 * @property {number} x
 * @property {number} y
 * @property {boolean} is_alive
 */

/**
 * @typedef {Object} RoomObject
 * @property {string} id
 * @property {string} type
 * @property {number} x
 * @property {number} y
 * @property {string} category
 * @property {boolean} [blocking]
 * @property {string} [state_scope]
 * @property {Object} [config]
 */

/**
 * @typedef {Object} RoomState
 * @property {string} room_key
 * @property {string} name
 * @property {number} width
 * @property {number} height
 * @property {number[][]} tiles
 * @property {Entity[]} entities
 * @property {NpcData[]} npcs
 * @property {Object[]} exits
 * @property {RoomObject[]} objects
 */

/**
 * @typedef {Object} CardDef
 * @property {string} card_key
 * @property {string} name
 * @property {number} cost
 * @property {Object[]} effects
 * @property {string} description
 */

/**
 * @typedef {Object} CombatState
 * @property {string} instance_id
 * @property {string} current_turn
 * @property {Object[]} participants
 * @property {Object} mob
 * @property {Object.<string, CardDef[]>} hands
 */

/**
 * @typedef {Object} InventoryItem
 * @property {string} item_key
 * @property {string} name
 * @property {string} category
 * @property {number} quantity
 * @property {number} charges
 * @property {string} description
 */

/**
 * @typedef {Object} GameState
 * @property {WebSocket|null} ws
 * @property {PlayerState|null} player
 * @property {RoomState|null} room
 * @property {CombatState|null} combat
 * @property {InventoryItem[]} inventory
 * @property {'auth'|'explore'|'combat'} mode
 * @property {{username:string, password:string}|null} credentials
 * @property {'register'|'login'|null} pendingAction
 * @property {boolean} movePending
 */

/** @type {GameState} */
const gameState = {
  ws: null,
  player: null,
  room: null,
  combat: null,
  inventory: [],
  mode: 'auth',
  credentials: null,
  pendingAction: null,
  movePending: false,
  /** @type {Object|null} */
  pendingLevelUp: null,
  /** @type {string[]} */
  levelUpSelections: [],
  /** @type {number|undefined} */
  _lastXp: undefined,
};

let reconnectAttempts = 0;
const MAX_RECONNECT = 5;
/** @type {number|null} */
let reconnectTimer = null;
let serverShuttingDown = false;
/** @type {string|null} */
let sessionToken = null;
/** @type {number|null} */
let moveErrorTimer = null;
const LOG_MAX = 200;

// =========================================================================
// DOM References
// =========================================================================
const $authScreen = /** @type {HTMLElement} */ (document.getElementById('auth-screen'));
const $gameScreen = /** @type {HTMLElement} */ (document.getElementById('game-screen'));
const $combatOverlay = /** @type {HTMLElement} */ (document.getElementById('combat-overlay'));
const $statusDot = /** @type {HTMLElement} */ (document.getElementById('status-dot'));
const $statusText = /** @type {HTMLElement} */ (document.getElementById('status-text'));
const $authError = /** @type {HTMLElement} */ (document.getElementById('auth-error'));
const $authMessage = /** @type {HTMLElement} */ (document.getElementById('auth-message'));
const $tileGrid = /** @type {HTMLElement} */ (document.getElementById('tile-grid'));
const $chatLog = /** @type {HTMLElement} */ (document.getElementById('chat-log'));
const $chatInput = /** @type {HTMLInputElement} */ (document.getElementById('chat-input'));
const $whisperTarget = /** @type {HTMLSelectElement} */ (document.getElementById('whisper-target'));
const $messageLog = /** @type {HTMLElement} */ (document.getElementById('message-log'));
const $moveError = /** @type {HTMLElement} */ (document.getElementById('move-error'));

// =========================================================================
// Slash Command Registry & Parser
// =========================================================================

/** @type {Object<string, {handler: function(string[]): void, description: string, usage: string}>} */
const COMMANDS = {
  help: {
    handler: () => {
      appendChat('Available commands:', 'system');
      for (const [, cmd] of Object.entries(COMMANDS)) {
        appendChat(`  ${cmd.usage} \u2014 ${cmd.description}`, 'system');
      }
    },
    description: 'Show available commands',
    usage: '/help',
  },
  logout: {
    handler: () => sendAction('logout', {}),
    description: 'Log out and return to login screen',
    usage: '/logout',
  },
  whisper: {
    handler: (args) => {
      if (args.length < 2) {
        appendChat('Usage: /whisper <name> <message>', 'system');
        return;
      }
      const targetName = args[0].replace(/^@/, '');
      const message = args.slice(1).join(' ');
      const target = gameState.room?.entities?.find(
        (e) => e.name.toLowerCase() === targetName.toLowerCase()
      );
      if (!target) {
        appendChat(`Player "${targetName}" not found in this room.`, 'system');
        return;
      }
      sendAction('chat', { message, whisper_to: target.id });
    },
    description: 'Send a private message',
    usage: '/whisper <name> <message>',
  },
  inventory: {
    handler: () => sendAction('inventory'),
    description: 'Show your inventory',
    usage: '/inventory',
  },
  use: {
    handler: (args) => {
      if (!args.length) {
        appendChat('Usage: /use <item_name>', 'system');
        return;
      }
      const input = args.join(' ');
      // Match by item_key first, then by display name (case-insensitive)
      const match = gameState.inventory.find(
        (i) => i.item_key === input || i.name.toLowerCase() === input.toLowerCase()
      );
      sendAction('use_item', { item_key: match ? match.item_key : input });
    },
    description: 'Use an item',
    usage: '/use <item_name>',
  },
  flee: {
    handler: () => sendAction('flee'),
    description: 'Flee from combat',
    usage: '/flee',
  },
  pass: {
    handler: () => sendAction('pass_turn'),
    description: 'Pass your turn in combat',
    usage: '/pass',
  },
  interact: {
    handler: (args) => {
      if (!args.length) {
        appendChat('Usage: /interact <direction>', 'system');
        return;
      }
      sendAction('interact', { direction: args[0] });
    },
    description: 'Interact with adjacent object',
    usage: '/interact <direction>',
  },
  look: {
    handler: () => sendAction('look'),
    description: 'Look at nearby surroundings',
    usage: '/look',
  },
  who: {
    handler: () => sendAction('who'),
    description: 'List players in room',
    usage: '/who',
  },
  stats: {
    handler: () => {
      sendAction('stats');
      toggleStatsPanel(true);
    },
    description: 'Show your stats',
    usage: '/stats',
  },
  levelup: {
    handler: () => {
      if (gameState.pendingLevelUp) {
        showLevelUpModal(gameState.pendingLevelUp);
      } else {
        appendChat('No level-up available.', 'system');
      }
    },
    description: 'Open level-up stat selection',
    usage: '/levelup',
  },
  map: {
    handler: () => sendAction('map'),
    description: 'Show world map',
    usage: '/map',
  },
  trade: {
    handler: (args) => sendAction('trade', { args: args.join(' ') }),
    description: 'Trade items with another player',
    usage: '/trade @player | accept | reject | offer <item> [qty] | remove <item> | ready | cancel',
  },
  party: {
    handler: (args) => sendAction('party', { args: args.join(' ') }),
    description: 'Party commands',
    usage: '/party <message> | invite @player | accept | reject | leave | kick @player | disband',
  },
};

/**
 * Parse and dispatch slash commands. Returns true if input was a command.
 * @param {string} input
 * @returns {boolean}
 */
function parseCommand(input) {
  if (!input.startsWith('/')) return false;
  const trimmed = input.slice(1).trim();
  if (!trimmed) {
    appendChat('Type /help for available commands.', 'system');
    return true;
  }
  const parts = trimmed.split(/\s+/);
  const cmdName = parts[0].toLowerCase();
  const args = parts.slice(1);
  const cmd = COMMANDS[cmdName];
  if (!cmd) {
    appendChat(`Unknown command: /${cmdName}. Type /help for available commands.`, 'system');
    return true;
  }
  cmd.handler(args);
  return true;
}

// =========================================================================
// WebSocket Connection
// =========================================================================

function connectWebSocket() {
  // Guard against duplicate connections
  if (gameState.ws && (gameState.ws.readyState === WebSocket.CONNECTING || gameState.ws.readyState === WebSocket.OPEN)) {
    return;
  }

  const wsProto = location.protocol === 'https:' ? 'wss' : 'ws';
  const wsUrl = `${wsProto}://${location.host}/ws/game`;
  const ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    gameState.ws = ws;
    reconnectAttempts = 0;
    setConnectionStatus('connected');

    // Try token-based reconnect first, fall back to credentials
    if (sessionToken && gameState.player) {
      sendAction('reconnect', { session_token: sessionToken });
    } else if (gameState.credentials && gameState.pendingAction) {
      sendAction(gameState.pendingAction, gameState.credentials);
    } else if (gameState.credentials) {
      gameState.pendingAction = 'login';
      sendAction('login', gameState.credentials);
    }
  };

  ws.onclose = () => {
    gameState.ws = null;
    setConnectionStatus('disconnected');

    // Don't reconnect if server is shutting down
    if (serverShuttingDown) return;

    if (gameState.player && reconnectAttempts < MAX_RECONNECT) {
      setConnectionStatus('reconnecting');
      const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 15000);
      reconnectAttempts++;
      reconnectTimer = window.setTimeout(connectWebSocket, delay);
    } else if (gameState.player) {
      // All reconnect attempts exhausted
      resetToLogin('Connection lost. Please log in again.');
    }
  };

  ws.onerror = () => {
    // onclose will fire after this
  };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      logMessage('recv', data);
      dispatchMessage(data);
    } catch {
      logMessage('recv', { raw: event.data, error: 'parse failed' });
    }
  };
}

/**
 * @param {'connected'|'reconnecting'|'disconnected'} status
 */
function setConnectionStatus(status) {
  $statusDot.className = `dot dot-${status}`;
  $statusText.textContent = status === 'connected' ? 'Connected'
    : status === 'reconnecting' ? 'Reconnecting...'
    : 'Disconnected';
}

/**
 * Reset client to login screen after permanent disconnect.
 * Clears all game state but preserves credentials for convenience.
 * @param {string} statusMessage - Message to show on the auth screen
 */
function resetToLogin(statusMessage) {
  // Close active WebSocket if still open
  if (gameState.ws) {
    try { gameState.ws.close(); } catch { /* ignore */ }
    gameState.ws = null;
  }

  // Clear reconnect state
  reconnectAttempts = 0;
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }

  // Clear move error timer
  if (moveErrorTimer) {
    clearTimeout(moveErrorTimer);
    moveErrorTimer = null;
  }

  // Clear game state (preserve credentials, clear token)
  sessionToken = null;
  gameState.player = null;
  gameState.room = null;
  gameState.combat = null;
  gameState.inventory = [];
  gameState.pendingAction = null;
  gameState.movePending = false;
  gameState.pendingLevelUp = null;
  gameState.levelUpSelections = [];
  gameState._lastXp = undefined;

  // Clear UI
  $tileGrid.innerHTML = '';
  $chatLog.innerHTML = '';
  $combatOverlay.classList.add('hidden');
  const $levelupOverlay = document.getElementById('levelup-overlay');
  if ($levelupOverlay) $levelupOverlay.classList.add('hidden');

  // Switch to auth screen
  setMode('auth');

  // Show status message
  $authError.textContent = '';
  $authMessage.textContent = statusMessage;

  // Pre-fill login form from stored credentials
  if (gameState.credentials) {
    const $loginUser = /** @type {HTMLInputElement} */ (document.getElementById('login-username'));
    if ($loginUser) $loginUser.value = gameState.credentials.username;
  }
}

/**
 * @param {string} action
 * @param {Object} [data]
 */
function sendAction(action, data = {}) {
  if (!gameState.ws || gameState.ws.readyState !== WebSocket.OPEN) return;
  const msg = { action, ...data };
  gameState.ws.send(JSON.stringify(msg));
  logMessage('sent', msg);
}

// =========================================================================
// Message Dispatch
// =========================================================================

/** @param {Object} data */
function dispatchMessage(data) {
  const handlers = {
    login_success: handleLoginSuccess,
    room_state: handleRoomState,
    entity_moved: handleEntityMoved,
    entity_entered: handleEntityEntered,
    entity_left: handleEntityLeft,
    combat_start: handleCombatStart,
    combat_turn: handleCombatTurn,
    combat_end: handleCombatEnd,
    combat_fled: handleCombatFled,
    combat_update: handleCombatUpdate,
    chat: handleChat,
    inventory: handleInventory,
    item_used: handleItemUsed,
    interact_result: handleInteractResult,
    tile_changed: handleTileChanged,
    announcement: handleAnnouncement,
    nearby_objects: handleNearbyObjects,
    look_result: handleLookResult,
    who_result: handleWhoResult,
    stats_result: handleStatsResult,
    help_result: handleHelpResult,
    map_data: handleMapData,
    xp_gained: handleXpGained,
    level_up_available: handleLevelUpAvailable,
    level_up_complete: handleLevelUpComplete,
    logged_out: handleLoggedOut,
    server_shutdown: handleServerShutdown,
    kicked: handleKicked,
    respawn: handleRespawn,
    trade_request: handleTradeRequest,
    trade_update: handleTradeUpdate,
    trade_result: handleTradeResult,
    party_invite: handlePartyInvite,
    party_update: handlePartyUpdate,
    party_status: handlePartyStatus,
    party_invite_response: handlePartyInviteResponse,
    party_chat: handlePartyChat,
    ping: () => sendAction('pong'),
    error: handleError,
  };

  const handler = handlers[data.type];
  if (handler) {
    handler(data);
  } else {
    logMessage('unknown', data);
  }
}

// =========================================================================
// UI Mode
// =========================================================================

/** @param {'auth'|'explore'|'combat'} mode */
function setMode(mode) {
  gameState.mode = mode;
  $authScreen.classList.toggle('hidden', mode !== 'auth');
  $gameScreen.classList.toggle('hidden', mode === 'auth');
  $combatOverlay.classList.toggle('hidden', mode !== 'combat');
}

// =========================================================================
// Auth Handlers
// =========================================================================

/** @param {Object} data */
function handleLoginSuccess(data) {
  if (gameState.pendingAction === 'register') {
    // Registration succeeded — auto-login
    $authMessage.textContent = 'Account created! Logging in...';
    gameState.pendingAction = 'login';
    sendAction('login', gameState.credentials);
    return;
  }

  // Login flow
  const entityId = data.entity_id || `player_${data.player_id}`;
  gameState.player = {
    id: entityId,
    dbId: data.player_id,
    name: data.username,
    x: 0,
    y: 0,
    stats: data.stats || {},
  };
  // Store session token for reconnection (if present)
  if (data.session_token) {
    sessionToken = data.session_token;
  }
}

/** @param {Object} data */
function handleTradeRequest(data) {
  appendChat(`[Trade] ${data.from_player} wants to trade with you. /trade accept or /trade reject`, 'system');
}

function handleTradeUpdate(data) {
  const formatOffers = (offers) => {
    const entries = Object.entries(offers);
    if (entries.length === 0) return '(nothing)';
    return entries.map(([k, q]) => `${k} x${q}`).join(', ');
  };
  appendChat(`[Trade] ${data.player_a}: ${formatOffers(data.offers_a)} ${data.ready_a ? '✓' : ''}`, 'system');
  appendChat(`[Trade] ${data.player_b}: ${formatOffers(data.offers_b)} ${data.ready_b ? '✓' : ''}`, 'system');
}

function handleTradeResult(data) {
  appendChat(`[Trade] ${data.reason}`, 'system');
}

function handlePartyInvite(data) {
  appendChat(`[Party] ${data.from_player} invited you to a party. /party accept or /party reject`, 'system');
}

function handlePartyUpdate(data) {
  const action = data.action;
  const who = data.entity_id || 'someone';
  if (action === 'member_joined') {
    appendChat(`[Party] ${who} joined the party.`, 'system');
  } else if (action === 'member_left') {
    appendChat(`[Party] ${who} left the party.`, 'system');
    if (data.new_leader) {
      appendChat(`[Party] ${data.new_leader} is now the party leader.`, 'system');
    }
  } else if (action === 'member_kicked') {
    appendChat(`[Party] ${who} was kicked from the party.`, 'system');
  } else if (action === 'disbanded') {
    appendChat(`[Party] The party has been disbanded.`, 'system');
  }
}

function handlePartyStatus(data) {
  if (data.pending_invite) {
    appendChat(`[Party] You have a pending invite from ${data.from_player}. /party accept or /party reject`, 'system');
    return;
  }
  appendChat('[Party] Members:', 'system');
  for (const m of data.members || []) {
    const leader = m.is_leader ? ' (Leader)' : '';
    const room = m.room || 'offline';
    appendChat(`  ${m.name}${leader} — ${room}`, 'system');
  }
}

function handlePartyInviteResponse(data) {
  if (data.status === 'sent') {
    appendChat(`[Party] Invite sent to ${data.target}.`, 'system');
  } else if (data.status === 'rejected') {
    appendChat('[Party] Invite was rejected.', 'system');
  } else if (data.status === 'expired') {
    appendChat('[Party] Invite expired.', 'system');
  }
}

function handlePartyChat(data) {
  appendChat(`[Party] ${data.from}: ${data.message}`, 'party', data.format);
}

function handleError(data) {
  // Token reconnect failed — fall back to credential login
  if (data.detail === 'Invalid or expired token' && gameState.credentials) {
    sessionToken = null;
    sendAction('login', gameState.credentials);
    return;
  }
  if (gameState.mode === 'auth') {
    $authError.textContent = data.detail || 'Unknown error';
  } else if (gameState.mode === 'combat') {
    const $status = document.getElementById('combat-status');
    if ($status) $status.textContent = data.detail || '';
  } else {
    // Show as move error or log
    showMoveError(data.detail || 'Error');
  }
  // Reset movePending on error
  gameState.movePending = false;
}

/** @param {Object} data */
function handleServerShutdown(data) {
  serverShuttingDown = true;
  const reason = data.reason || 'Server is shutting down.';
  resetToLogin(`Server is shutting down. ${reason}`);
}

/** @param {Object} _data */
function handleLoggedOut(_data) {
  // Clear credentials and token to prevent auto-login (unlike kicked which preserves them)
  sessionToken = null;
  gameState.credentials = null;
  gameState.player = null;
  gameState.room = null;
  gameState.combat = null;
  gameState.inventory = [];
  gameState.pendingLevelUp = null;
  gameState.levelUpSelections = [];
  gameState._lastXp = undefined;
  // Clear UI
  const $grid = document.getElementById('tile-grid');
  if ($grid) $grid.innerHTML = '';
  const $chatLog = document.getElementById('chat-log');
  if ($chatLog) $chatLog.innerHTML = '';
  // Switch to auth mode (also dismisses combat overlay)
  setMode('auth');
  const $authMsg = document.getElementById('auth-message');
  if ($authMsg) {
    $authMsg.textContent = 'You have been logged out.';
  }
}

/** @param {Object} data */
function handleKicked(data) {
  resetToLogin(data.reason || 'Disconnected from server.');
}

/** @param {Object} data */
function handleRespawn(data) {
  if (gameState.player) {
    gameState.player.x = data.x;
    gameState.player.y = data.y;
    if (gameState.player.stats) {
      gameState.player.stats.hp = data.hp;
    }
  }
  gameState.combat = null;
  setMode('explore');
  renderRoom();
  updateStatsPanel();
  appendChat('You have been respawned.', 'system');
}

// =========================================================================
// Room Rendering
// =========================================================================

/** @param {Object} data */
function handleRoomState(data) {
  gameState.room = /** @type {RoomState} */ (data);
  gameState.movePending = false;

  // Extract player position from entities
  if (gameState.player) {
    const self = data.entities.find((/** @type {Entity} */ e) => e.id === gameState.player?.id);
    if (self) {
      gameState.player.x = self.x;
      gameState.player.y = self.y;
    }
  }

  renderRoom();
  updateStatsPanel();
  updateWhisperDropdown();
  setMode('explore');

  // Request inventory
  sendAction('inventory', {});
}

function renderRoom() {
  if (!gameState.room || !gameState.player) return;
  const { width, height, tiles } = gameState.room;

  $tileGrid.style.gridTemplateColumns = `repeat(${width}, 20px)`;
  $tileGrid.style.gridTemplateRows = `repeat(${height}, 20px)`;
  $tileGrid.innerHTML = '';

  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const div = document.createElement('div');
      div.className = `tile ${tileClass(tiles[y][x])}`;
      div.dataset.x = String(x);
      div.dataset.y = String(y);

      // Overlay entity/npc/object
      const overlay = getOverlayAt(x, y);
      if (overlay) {
        const span = document.createElement('span');
        span.className = `entity ${overlay.cls}`;
        span.textContent = overlay.icon;
        if (overlay.clickAction) {
          span.style.pointerEvents = 'auto';
          span.style.cursor = 'pointer';
          span.addEventListener('click', overlay.clickAction);
        }
        div.appendChild(span);
      }

      $tileGrid.appendChild(div);
    }
  }

  updateViewport();
}

/** @param {number} type */
function tileClass(type) {
  switch (type) {
    case 0: return 'tile-floor';
    case 1: return 'tile-wall';
    case 2: return 'tile-exit';
    case 3: return 'tile-spawn';
    case 4: return 'tile-water';
    case 5: return 'tile-stairs-up';
    case 6: return 'tile-stairs-down';
    default: return 'tile-floor';
  }
}

const OBJECT_ICONS = {
  tree: { icon: '\u2663', cls: 'entity-object-static' },
  rock: { icon: '\u25CF', cls: 'entity-object-rock' },
  chest: { icon: '\u25A0', cls: 'entity-object-interactive' },
  lever: { icon: '\u2195', cls: 'entity-object-lever' },
  flower: { icon: '\u273F', cls: 'entity-object-flower' },
  fountain: { icon: '\u224B', cls: 'entity-object-fountain' },
  stalagmite: { icon: '\u25B2', cls: 'entity-object-rock' },
};

/**
 * Get the highest-priority overlay icon for a tile position.
 * @param {number} x
 * @param {number} y
 * @returns {{icon: string, cls: string, clickAction?: Function}|null}
 */
function getOverlayAt(x, y) {
  if (!gameState.room || !gameState.player) return null;

  // Priority 1: Self
  if (gameState.player.x === x && gameState.player.y === y) {
    return { icon: '@', cls: 'entity-self' };
  }

  // Priority 2: Other players
  const otherPlayer = gameState.room.entities.find(
    (e) => e.x === x && e.y === y && e.id !== gameState.player?.id
  );
  if (otherPlayer) return { icon: '@', cls: 'entity-player' };

  // Priority 3: NPCs
  const npc = gameState.room.npcs.find((n) => n.x === x && n.y === y);
  if (npc) {
    return npc.is_alive
      ? { icon: '!', cls: 'entity-npc-hostile' }
      : { icon: 'x', cls: 'entity-npc-dead' };
  }

  // Priority 4-5: Objects
  const obj = gameState.room.objects.find((o) => o.x === x && o.y === y);
  if (obj) {
    const info = OBJECT_ICONS[obj.type] || { icon: '?', cls: 'entity-object-static' };
    const result = { icon: info.icon, cls: info.cls };
    if (obj.category === 'interactive') {
      const objId = obj.id;
      result.clickAction = () => sendAction('interact', { target_id: objId });
    }
    return result;
  }

  return null;
}

function updateViewport() {
  if (!gameState.player || !gameState.room) return;
  const { x, y } = gameState.player;
  const { width, height } = gameState.room;

  const gridW = width * 20;
  const gridH = height * 20;

  let tx = 240 - x * 20;
  let ty = 240 - y * 20;

  tx = Math.max(-(gridW - 500), Math.min(240, tx));
  ty = Math.max(-(gridH - 500), Math.min(240, ty));

  $tileGrid.style.transform = `translate(${tx}px, ${ty}px)`;
}

/**
 * Update only specific tiles instead of full re-render.
 * @param {Array<{x: number, y: number}>} positions
 */
function updateTiles(positions) {
  if (!gameState.room) return;
  for (const { x, y } of positions) {
    const idx = y * gameState.room.width + x;
    const div = $tileGrid.children[idx];
    if (!div) continue;

    // Remove existing entity overlay
    const existing = div.querySelector('.entity');
    if (existing) existing.remove();

    // Re-add overlay if needed
    const overlay = getOverlayAt(x, y);
    if (overlay) {
      const span = document.createElement('span');
      span.className = `entity ${overlay.cls}`;
      span.textContent = overlay.icon;
      if (overlay.clickAction) {
        span.style.pointerEvents = 'auto';
        span.style.cursor = 'pointer';
        span.addEventListener('click', overlay.clickAction);
      }
      div.appendChild(span);
    }
  }
}

// =========================================================================
// Entity Movement
// =========================================================================

/** @param {Object} data */
function handleEntityMoved(data) {
  if (!gameState.room) return;

  const entity = gameState.room.entities.find((e) => e.id === data.entity_id);
  if (!entity) return;

  const oldPos = { x: entity.x, y: entity.y };
  entity.x = data.x;
  entity.y = data.y;

  if (data.entity_id === gameState.player?.id) {
    gameState.player.x = data.x;
    gameState.player.y = data.y;
    gameState.movePending = false;
    updateViewport();
    updateStatsPanel();
  }

  if (gameState.mode !== 'combat') {
    updateTiles([oldPos, { x: data.x, y: data.y }]);
  }
}

/** @param {Object} data */
function handleEntityEntered(data) {
  if (!gameState.room) return;
  gameState.room.entities.push(data.entity);

  if (gameState.mode !== 'combat') {
    updateTiles([{ x: data.entity.x, y: data.entity.y }]);
  }
  updateWhisperDropdown();
  appendChat(`${data.entity.name} entered the room.`, 'system');
}

/** @param {Object} data */
function handleEntityLeft(data) {
  if (!gameState.room) return;
  const idx = gameState.room.entities.findIndex((e) => e.id === data.entity_id);
  if (idx >= 0) {
    const entity = gameState.room.entities[idx];
    gameState.room.entities.splice(idx, 1);
    if (gameState.mode !== 'combat') {
      updateTiles([{ x: entity.x, y: entity.y }]);
    }
  }
  updateWhisperDropdown();
  appendChat(`A player left the room.`, 'system');
}

// =========================================================================
// Keyboard Movement
// =========================================================================

/** @type {Object.<string, string>} */
const KEY_MAP = {
  ArrowUp: 'up', ArrowDown: 'down', ArrowLeft: 'left', ArrowRight: 'right',
  w: 'up', W: 'up', s: 'down', S: 'down', a: 'left', A: 'left', d: 'right', D: 'right',
};

/** @param {KeyboardEvent} e */
function handleKeyDown(e) {
  if (gameState.mode !== 'explore') return;
  if (document.activeElement === $chatInput) return;
  if (gameState.movePending) return;

  const direction = KEY_MAP[e.key];
  if (!direction) return;

  e.preventDefault();
  gameState.movePending = true;
  sendAction('move', { direction });
}

document.addEventListener('keydown', handleKeyDown);

// =========================================================================
// Chat
// =========================================================================

/** @param {Object} data */
function handleChat(data) {
  const cls = data.whisper ? 'chat-whisper' : '';
  const prefix = data.whisper ? '[whisper] ' : '';
  appendChat(`${prefix}${data.sender}: ${data.message}`, cls || 'chat', data.format);
}

/** @param {Object} data */
function handleAnnouncement(data) {
  appendChat(`\u2605 ${data.message}`, 'announcement', data.format);
}

/** @param {{type: string, objects: Array<{id: string, type: string, direction: string}>}} data */
function handleNearbyObjects(data) {
  if (data.objects && data.objects.length > 0) {
    for (const obj of data.objects) {
      appendChat(`You see a ${obj.type} to the ${obj.direction}`, 'system');
    }
  }
}

/** @param {{type: string, objects: Array, npcs: Array, players: Array}} data */
function handleLookResult(data) {
  const dirLabel = (d) => d === 'here' ? '(here)' : `to the ${d}`;
  if (data.objects?.length) {
    appendChat('Objects: ' + data.objects.map(o => `${o.type} ${dirLabel(o.direction)}`).join(', '), 'system');
  }
  if (data.npcs?.length) {
    appendChat('NPCs: ' + data.npcs.map(n => `${n.name} (${n.alive ? 'alive' : 'dead'}) ${dirLabel(n.direction)}`).join(', '), 'system');
  }
  if (data.players?.length) {
    appendChat('Players: ' + data.players.map(p => `${p.name} ${dirLabel(p.direction)}`).join(', '), 'system');
  }
  if (!data.objects?.length && !data.npcs?.length && !data.players?.length) {
    appendChat('Nothing nearby.', 'system');
  }
}

/** @param {{type: string, room: string, players: Array}} data */
function handleWhoResult(data) {
  appendChat(`Players in ${data.room}:`, 'system');
  if (data.players?.length) {
    for (const p of data.players) {
      appendChat(`  ${p.name} at (${p.x}, ${p.y})`, 'system');
    }
  }
}

/** @param {{type: string, stats: Object}} data */
function handleStatsResult(data) {
  const s = data.stats;
  if (!s) return;
  if (gameState.player) {
    gameState.player.stats = { ...s };
    updateStatsPanel();
  }
  toggleStatsPanel(true);
  appendChat(`HP: ${s.hp}/${s.max_hp} | LVL: ${s.level ?? 1} | XP: ${s.xp} | STR: ${s.strength ?? 1} DEX: ${s.dexterity ?? 1} CON: ${s.constitution ?? 1} INT: ${s.intelligence ?? 1} WIS: ${s.wisdom ?? 1} CHA: ${s.charisma ?? 1}`, 'system');
}

/** @param {{type: string, categories?: Object, actions?: Array}} data */
function handleHelpResult(data) {
  if (data.categories) {
    appendChat('Server actions:', 'system');
    for (const [category, actions] of Object.entries(data.categories)) {
      appendChat(`  ${category}: ${actions.join(', ')}`, 'system');
    }
  } else if (data.actions?.length) {
    appendChat('Server actions:', 'system');
    appendChat('  ' + data.actions.join(', '), 'system');
  }
}

/** @param {{type: string, rooms: Array, connections: Array}} data */
function handleMapData(data) {
  appendChat('=== World Map ===', 'system');
  if (!data.rooms?.length) {
    appendChat('  No rooms discovered yet.', 'system');
    return;
  }
  const nameMap = {};
  for (const room of data.rooms) {
    nameMap[room.room_key] = room.name;
  }
  appendChat('Rooms:', 'system');
  for (const room of data.rooms) {
    appendChat(`  \u2022 ${room.name}`, 'system');
  }
  if (data.connections?.length) {
    appendChat('Connections:', 'system');
    for (const conn of data.connections) {
      const fromName = nameMap[conn.from_room] || conn.from_room;
      appendChat(`  ${fromName} \u2192 ${conn.to_room} (${conn.direction})`, 'system');
    }
  }
}

/**
 * @param {string} text
 * @param {string} [type]
 */
/**
 * Render safe markdown subset: bold, italic, code, strikethrough.
 * HTML-escapes FIRST (XSS prevention), then applies markdown regex.
 * Code spans processed first to prevent formatting inside code.
 * NO links, NO images (eliminates javascript: URI XSS vectors).
 */
function renderSafeMarkdown(text) {
  // 1. HTML-escape
  let s = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
  // 2. Extract code spans first (prevent formatting inside code)
  const codeSpans = [];
  s = s.replace(/`([^`]+)`/g, (_, code) => {
    codeSpans.push(`<code>${code}</code>`);
    return `\x00CODE${codeSpans.length - 1}\x00`;
  });
  // 3. Apply formatting (order matters: bold before italic)
  s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/\*(.+?)\*/g, '<em>$1</em>');
  s = s.replace(/~~(.+?)~~/g, '<del>$1</del>');
  // 4. Reinsert code spans
  s = s.replace(/\x00CODE(\d+)\x00/g, (_, i) => codeSpans[parseInt(i)]);
  return s;
}

function appendChat(text, type = 'chat', format = null) {
  const div = document.createElement('div');
  div.className = `chat-msg chat-${type}`;
  if (format === 'markdown') {
    div.innerHTML = renderSafeMarkdown(text);
  } else {
    div.textContent = text;
  }
  $chatLog.appendChild(div);
  $chatLog.scrollTop = $chatLog.scrollHeight;
}

function sendChat() {
  const msg = $chatInput.value.trim();
  if (!msg) return;

  if (parseCommand(msg)) {
    $chatInput.value = '';
    return;
  }

  const target = $whisperTarget.value;
  if (target) {
    sendAction('chat', { message: msg, whisper_to: target });
  } else {
    sendAction('chat', { message: msg });
  }
  $chatInput.value = '';
}

document.getElementById('chat-send')?.addEventListener('click', sendChat);
$chatInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') sendChat();
});

function updateWhisperDropdown() {
  if (!gameState.room || !gameState.player) return;
  const current = $whisperTarget.value;
  $whisperTarget.innerHTML = '<option value="">Room (all)</option>';
  for (const e of gameState.room.entities) {
    if (e.id === gameState.player.id) continue;
    const opt = document.createElement('option');
    opt.value = e.id;
    opt.textContent = e.name;
    $whisperTarget.appendChild(opt);
  }
  // Restore selection if still valid
  if (current && [...$whisperTarget.options].some((o) => o.value === current)) {
    $whisperTarget.value = current;
  }
}

// =========================================================================
// Combat
// =========================================================================

/** @param {Object} data */
function handleCombatStart(data) {
  gameState.combat = /** @type {CombatState} */ (data);
  gameState.movePending = false;
  setMode('combat');
  renderCombatOverlay();
}

/** @param {Object} data */
function handleCombatTurn(data) {
  // Update combat state
  gameState.combat = {
    instance_id: data.instance_id,
    current_turn: data.current_turn,
    participants: data.participants,
    mob: data.mob,
    hands: data.hands,
  };

  // Sync combat HP back to player stats
  syncCombatStatsToPlayer();

  // Show action result
  const result = data.result;
  let resultText = '';

  if (result) {
    if (result.action === 'play_card') {
      resultText = `${result.entity_id} played a card.`;
    } else if (result.action === 'pass_turn') {
      resultText = `${result.entity_id} passed their turn.`;
    } else if (result.action === 'use_item') {
      resultText = `${result.entity_id} used an item.`;
    }

    // Mob attack (always present for pass_turn, conditional for others)
    if (result.mob_attack) {
      const ma = result.mob_attack;
      resultText += ` Mob attacked ${ma.target} for ${ma.damage} damage`;
      if (ma.shield_absorbed) resultText += ` (${ma.shield_absorbed} absorbed)`;
      resultText += '.';
    }

    // Cycle mob attack (only on pass_turn)
    if (result.cycle_mob_attack) {
      const ca = result.cycle_mob_attack;
      resultText += ` Cycle attack: ${ca.target} took ${ca.damage} damage`;
      if (ca.shield_absorbed) resultText += ` (${ca.shield_absorbed} absorbed)`;
      resultText += '.';
    }

    // DoT tick results
    if (result.dot_ticks && result.dot_ticks.length > 0) {
      for (const tick of result.dot_ticks) {
        const sub = tick.subtype.charAt(0).toUpperCase() + tick.subtype.slice(1);
        resultText += ` ${sub} dealt ${tick.value} damage to ${tick.target}`;
        if (tick.shield_absorbed) resultText += ` (${tick.shield_absorbed} absorbed)`;
        if (tick.remaining > 0) {
          resultText += ` (${tick.remaining} turn${tick.remaining !== 1 ? 's' : ''} remaining)`;
        } else {
          resultText += ' (expired)';
        }
        resultText += '.';
      }
    }
  }

  const $result = document.getElementById('combat-result');
  if ($result) $result.textContent = resultText;

  renderCombatOverlay();

  // Trigger damage animation on player HP bar
  if (result?.mob_attack || result?.cycle_mob_attack) {
    const $hpBar = document.getElementById('combat-hp-bar');
    if ($hpBar) {
      $hpBar.classList.remove('damage-anim');
      void $hpBar.offsetWidth; // reflow
      $hpBar.classList.add('damage-anim');
    }
  }
}

/** @param {Object} data */
function handleCombatEnd(data) {
  const isVictory = data.victory;
  let msg;

  if (isVictory) {
    msg = `Victory! Gained ${data.rewards?.xp || 0} XP`;
    if (data.loot?.length) {
      const lootStr = data.loot.map((l) => `${l.item_key} x${l.quantity}`).join(', ');
      msg += ` | Loot: ${lootStr}`;
    }
    // Mark mob NPC as dead in room state
    if (gameState.room && data.defeated_npc_id) {
      const npc = gameState.room.npcs.find((n) => n.id === data.defeated_npc_id);
      if (npc) npc.is_alive = false;
    }
  } else {
    msg = 'Defeated!';
  }

  // Sync final combat stats to player stats
  syncCombatStatsToPlayer();
  // Note: XP increment is handled by xp_gained handler — do not add here to avoid double-count

  const $result = document.getElementById('combat-result');
  if ($result) $result.textContent = msg;
  appendChat(msg, 'system');

  setTimeout(() => {
    gameState.combat = null;
    setMode('explore');
    renderRoom();
    updateStatsPanel();
  }, 2000);
}

/** @param {Object} _data */
function handleCombatFled(_data) {
  syncCombatStatsToPlayer();
  gameState.combat = null;
  setMode('explore');
  appendChat('You fled from combat.', 'system');
  renderRoom();
  updateStatsPanel();
}

/** @param {Object} data */
function handleCombatUpdate(data) {
  gameState.combat = {
    instance_id: data.instance_id,
    current_turn: data.current_turn,
    participants: data.participants,
    mob: data.mob,
    hands: data.hands,
  };
  syncCombatStatsToPlayer();
  renderCombatOverlay();
}

function renderCombatOverlay() {
  if (!gameState.combat || !gameState.player) return;
  const { mob, participants, hands, current_turn } = gameState.combat;
  const isMyTurn = current_turn === gameState.player.id;

  // Mob info
  const $mobName = document.getElementById('mob-name');
  const $mobHpBar = /** @type {HTMLElement} */ (document.getElementById('mob-hp-bar'));
  const $mobHpText = document.getElementById('mob-hp-text');
  if ($mobName) $mobName.textContent = mob.name;
  if ($mobHpBar && mob.max_hp > 0) {
    const pct = (mob.hp / mob.max_hp) * 100;
    $mobHpBar.style.width = `${pct}%`;
    setHpBarColor($mobHpBar, pct);
  }
  if ($mobHpText) $mobHpText.textContent = `${mob.hp} / ${mob.max_hp}`;

  // Player combat info
  const me = participants.find((/** @type {Object} */ p) => p.entity_id === gameState.player?.id);
  const $cpName = document.getElementById('combat-player-name');
  const $cpHpBar = /** @type {HTMLElement} */ (document.getElementById('combat-hp-bar'));
  const $cpHpText = document.getElementById('combat-hp-text');
  const $cpShield = document.getElementById('combat-shield-text');

  if ($cpName) $cpName.textContent = gameState.player.name;
  if (me) {
    const pct = me.max_hp > 0 ? (me.hp / me.max_hp) * 100 : 0;
    if ($cpHpBar) {
      $cpHpBar.style.width = `${pct}%`;
      setHpBarColor($cpHpBar, pct);
    }
    if ($cpHpText) $cpHpText.textContent = `${me.hp} / ${me.max_hp}`;
    if ($cpShield) $cpShield.textContent = me.shield ? `Shield: ${me.shield}` : '';
  }

  // Status
  const $status = document.getElementById('combat-status');
  if ($status) $status.textContent = isMyTurn ? 'Your turn!' : 'Waiting for turn...';

  // Card hand
  const $cardHand = document.getElementById('card-hand');
  if ($cardHand) {
    $cardHand.innerHTML = '';
    const myCards = hands?.[gameState.player.id] || [];
    for (const card of myCards) {
      const cardEl = createCardElement(card, isMyTurn);
      $cardHand.appendChild(cardEl);
    }
  }

  // Action buttons
  const $passBtn = /** @type {HTMLElement} */ (document.getElementById('btn-pass-turn'));
  const $fleeBtn = /** @type {HTMLElement} */ (document.getElementById('btn-flee'));
  if ($passBtn) $passBtn.classList.toggle('disabled', !isMyTurn);
  if ($fleeBtn) $fleeBtn.classList.toggle('disabled', !isMyTurn);

  // Combat inventory
  renderCombatInventory(isMyTurn);
}

/**
 * @param {CardDef} card
 * @param {boolean} enabled
 * @returns {HTMLElement}
 */
function createCardElement(card, enabled) {
  const div = document.createElement('div');
  div.className = `card${enabled ? '' : ' disabled'}`;

  const header = document.createElement('div');
  header.className = 'card-header';
  const nameEl = document.createElement('span');
  nameEl.className = 'card-name';
  nameEl.textContent = card.name;
  const costEl = document.createElement('span');
  costEl.className = 'card-cost';
  costEl.textContent = String(card.cost);
  header.appendChild(nameEl);
  header.appendChild(costEl);
  div.appendChild(header);

  if (card.effects && card.effects.length > 0) {
    const effectsEl = document.createElement('div');
    effectsEl.className = 'card-effects';
    for (const eff of card.effects) {
      const effLine = document.createElement('div');
      effLine.textContent = formatEffect(eff);
      effectsEl.appendChild(effLine);
    }
    div.appendChild(effectsEl);
  }

  if (card.description) {
    const descEl = document.createElement('div');
    descEl.className = 'card-desc';
    descEl.textContent = card.description;
    div.appendChild(descEl);
  }

  if (enabled) {
    div.addEventListener('click', () => sendAction('play_card', { card_key: card.card_key }));
  }

  return div;
}

/** @param {Object} eff */
function formatEffect(eff) {
  switch (eff.type) {
    case 'damage': return `damage ${eff.subtype || ''} ${eff.value}`.trim();
    case 'heal': return `heal ${eff.value}`;
    case 'shield': return `shield ${eff.value}`;
    case 'dot': return `dot ${eff.subtype} ${eff.value} for ${eff.duration} turns`;
    case 'draw': return `draw ${eff.value} card(s)`;
    default: return `${eff.type} ${eff.value || ''}`.trim();
  }
}

/**
 * @param {HTMLElement} el
 * @param {number} pct
 */
function setHpBarColor(el, pct) {
  el.classList.remove('hp-medium', 'hp-low');
  if (pct <= 25) el.classList.add('hp-low');
  else if (pct <= 50) el.classList.add('hp-medium');
}

/** @param {boolean} enabled */
function renderCombatInventory(enabled) {
  const $list = document.getElementById('combat-inventory-list');
  if (!$list) return;
  $list.innerHTML = '';

  const consumables = gameState.inventory.filter((i) => i.category === 'consumable');
  for (const item of consumables) {
    const btn = document.createElement('button');
    btn.className = `btn-use${enabled ? '' : ' disabled'}`;
    btn.textContent = `${item.name} (${item.quantity})`;
    if (enabled) {
      btn.addEventListener('click', () => sendAction('use_item_combat', { item_key: item.item_key }));
    }
    $list.appendChild(btn);
  }
}

document.getElementById('btn-pass-turn')?.addEventListener('click', () => {
  if (gameState.combat?.current_turn === gameState.player?.id) {
    sendAction('pass_turn', {});
  }
});

document.getElementById('btn-logout')?.addEventListener('click', () => {
  sendAction('logout', {});
});

document.getElementById('btn-flee')?.addEventListener('click', () => {
  if (gameState.combat?.current_turn === gameState.player?.id) {
    sendAction('flee', {});
  }
});

// =========================================================================
// Inventory
// =========================================================================

/** @param {Object} data */
function handleInventory(data) {
  gameState.inventory = data.items || [];
  renderInventory();
  // Show inventory in chat
  if (gameState.inventory.length === 0) {
    appendChat('Inventory is empty.', 'system');
  } else {
    const lines = gameState.inventory.map(
      (i) => `  ${i.name} (${i.item_key}) x${i.quantity}`
    );
    appendChat('Inventory:\n' + lines.join('\n'), 'system');
  }
}

function renderInventory() {
  const $list = document.getElementById('inventory-list');
  if (!$list) return;
  $list.innerHTML = '';

  if (gameState.inventory.length === 0) {
    $list.innerHTML = '<div style="color:#555;font-size:12px;font-style:italic">Empty</div>';
    return;
  }

  for (const item of gameState.inventory) {
    const div = document.createElement('div');
    div.className = 'inventory-item';

    const nameSpan = document.createElement('span');
    nameSpan.className = 'inventory-item-name';
    nameSpan.textContent = item.name;
    nameSpan.title = `/use ${item.item_key}`;
    div.appendChild(nameSpan);

    const qtySpan = document.createElement('span');
    qtySpan.className = 'inventory-item-qty';
    qtySpan.textContent = `x${item.quantity}`;
    div.appendChild(qtySpan);

    if (item.category === 'consumable') {
      const btn = document.createElement('button');
      btn.className = 'btn-use';
      btn.textContent = 'Use';
      btn.addEventListener('click', () => sendAction('use_item', { item_key: item.item_key }));
      div.appendChild(btn);
    }

    $list.appendChild(div);
  }
}

/** @param {Object} data */
function handleItemUsed(data) {
  let text = `Used ${data.item_name}: `;
  const parts = [];
  for (const r of (data.effect_results || [])) {
    switch (r.type) {
      case 'heal': parts.push(`Healed ${r.value} HP (HP: ${r.target_hp})`); break;
      case 'damage': parts.push(`Dealt ${r.value} damage`); break;
      case 'shield': parts.push(`Gained ${r.value} shield (total: ${r.total_shield})`); break;
      case 'dot': parts.push(`Applied ${r.subtype} for ${r.value} over ${r.duration} turns`); break;
      case 'draw': parts.push(`Drew ${r.value} card(s)`); break;
      default: parts.push(`${r.type}: ${r.value || ''}`);
    }
  }
  text += parts.join(', ');
  appendChat(text, 'system');

  // Sync HP from heal effect results to player stats HUD
  if (gameState.player?.stats) {
    for (const r of (data.effect_results || [])) {
      if (r.type === 'heal' && r.target_hp != null) {
        gameState.player.stats.hp = r.target_hp;
      }
    }
    updateStatsPanel();
  }

  sendAction('inventory', {});
}

// =========================================================================
// Interaction
// =========================================================================

/** @param {Object} data */
function handleInteractResult(data) {
  const r = data.result;
  if (!r) return;

  if (r.status === 'looted') {
    const items = (r.items || []).map((/** @type {Object} */ i) => i.item_key).join(', ');
    appendChat(`Opened chest \u2014 received: ${items || 'nothing'}`, 'system');
    sendAction('inventory', {});
  } else if (r.status === 'already_looted') {
    appendChat(r.message || 'Already looted.', 'system');
  } else if (r.status === 'toggled') {
    appendChat(`Pulled lever \u2014 ${r.active ? 'activated' : 'deactivated'}`, 'system');
  } else if (r.status === 'error') {
    appendChat(r.message || 'Interaction failed.', 'system');
  } else {
    appendChat(`Interact: ${JSON.stringify(r)}`, 'system');
  }
}

/** @param {Object} data */
function handleTileChanged(data) {
  if (!gameState.room) return;
  gameState.room.tiles[data.y][data.x] = data.tile_type;

  // Update the tile div
  const idx = data.y * gameState.room.width + data.x;
  const div = $tileGrid.children[idx];
  if (div) {
    div.className = `tile ${tileClass(data.tile_type)}`;
    // Re-add overlay if any
    const existing = div.querySelector('.entity');
    if (existing) existing.remove();
    const overlay = getOverlayAt(data.x, data.y);
    if (overlay) {
      const span = document.createElement('span');
      span.className = `entity ${overlay.cls}`;
      span.textContent = overlay.icon;
      div.appendChild(span);
    }
  }
}

// =========================================================================
// Stats Panel
// =========================================================================

/** Sync HP/max_hp from combat participant data back to player stats. */
function syncCombatStatsToPlayer() {
  if (!gameState.player?.stats || !gameState.combat) return;
  const me = gameState.combat.participants.find(
    (/** @type {Object} */ p) => p.entity_id === gameState.player?.id
  );
  if (me) {
    gameState.player.stats.hp = me.hp;
    gameState.player.stats.max_hp = me.max_hp;
  }
}

function updateStatsPanel() {
  if (!gameState.player) return;

  const $name = document.getElementById('player-name');
  const $pos = document.getElementById('player-position');
  const $roomName = document.getElementById('room-name');

  if ($name) $name.textContent = gameState.player.name;
  if ($pos) $pos.textContent = `Position: (${gameState.player.x}, ${gameState.player.y})`;
  if ($roomName && gameState.room) $roomName.textContent = gameState.room.name;

  const stats = gameState.player.stats;
  if (!stats) return;

  // Find combat participant once (used for HP and shield)
  const me = gameState.combat
    ? gameState.combat.participants.find(
        (/** @type {Object} */ p) => p.entity_id === gameState.player?.id
      )
    : null;

  // HP: prefer combat participant data during combat, else use player stats
  const hp = me ? me.hp : stats.hp;
  const maxHp = me ? me.max_hp : stats.max_hp;

  // Update HP bar (always visible)
  const $hpBar = /** @type {HTMLElement} */ (document.getElementById('hp-bar'));
  const $hpText = document.getElementById('hp-text');
  const pct = maxHp > 0 ? (hp / maxHp) * 100 : 0;
  if ($hpBar) {
    $hpBar.style.width = `${pct}%`;
    setHpBarColor($hpBar, pct);
  }
  if ($hpText) $hpText.textContent = `${hp} / ${maxHp}`;

  // Shield (combat only)
  const $shieldSection = document.getElementById('shield-section');
  if (me && me.shield > 0) {
    $shieldSection?.classList.remove('hidden');
    const $shieldText = document.getElementById('shield-text');
    if ($shieldText) $shieldText.textContent = `${me.shield}`;
  } else {
    $shieldSection?.classList.add('hidden');
  }

  // Level display
  const $levelText = document.getElementById('level-text');
  if ($levelText) $levelText.textContent = `${stats.level || 1}`;

  // XP progress bar
  const level = stats.level || 1;
  const xpNext = stats.xp_for_next_level ?? 0;
  const xpPrev = stats.xp_for_current_level ?? 0;
  const currentXp = stats.xp || 0;
  const xpInLevel = currentXp - xpPrev;
  const xpNeeded = xpNext - xpPrev;
  const xpPct = Math.min(100, Math.max(0, (xpInLevel / xpNeeded) * 100));

  const $xpBar = /** @type {HTMLElement} */ (document.getElementById('xp-bar'));
  const $xpText = document.getElementById('xp-text');
  const oldXp = gameState._lastXp;
  if ($xpBar) {
    $xpBar.style.width = `${xpPct}%`;
    // Flash animation on XP change
    if (oldXp !== undefined && oldXp !== currentXp) {
      const $track = $xpBar.parentElement;
      if ($track) {
        $track.classList.remove('xp-flash-anim');
        void $track.offsetWidth;
        $track.classList.add('xp-flash-anim');
      }
    }
  }
  if ($xpText) $xpText.textContent = `${currentXp}/${xpNext}`;
  gameState._lastXp = currentXp;

  // Stats detail panel
  updateStatsDetailPanel(stats);
}

/** @param {Object} stats */
function updateStatsDetailPanel(stats) {
  const descriptions = {
    str: { label: 'STR', key: 'strength', desc: 'physical dmg bonus' },
    dex: { label: 'DEX', key: 'dexterity', desc: 'incoming dmg reduction' },
    con: { label: 'CON', key: 'constitution', desc: 'max HP bonus' },
    int: { label: 'INT', key: 'intelligence', desc: 'magic dmg bonus' },
    wis: { label: 'WIS', key: 'wisdom', desc: 'healing bonus' },
    cha: { label: 'CHA', key: 'charisma', desc: 'XP bonus' },
  };
  for (const [id, info] of Object.entries(descriptions)) {
    const $row = document.getElementById(`stat-${id}`);
    if ($row) {
      const val = stats[info.key] ?? 1;
      $row.textContent = `${info.label}: ${val} (${info.desc})`;
    }
  }
}

/** @param {boolean} [forceOpen] */
function toggleStatsPanel(forceOpen) {
  const $panel = document.getElementById('stats-detail-panel');
  if (!$panel) return;
  if (forceOpen) {
    $panel.classList.remove('hidden');
  } else {
    $panel.classList.toggle('hidden');
  }
}

// =========================================================================
// XP & Level-Up Handlers
// =========================================================================

/** @param {Object} data */
function handleXpGained(data) {
  if (!gameState.player?.stats) return;
  gameState.player.stats.xp = data.new_total_xp ?? ((gameState.player.stats.xp || 0) + (data.amount || 0));
  updateStatsPanel();
  if (data.source !== 'combat') {
    appendChat(`+${data.amount} XP (${data.source}: ${data.detail})`, 'system');
  }
}

/** @param {Object} data */
function handleLevelUpAvailable(data) {
  gameState.pendingLevelUp = data;
  // Show badge
  const $badge = document.getElementById('levelup-badge');
  if ($badge) $badge.classList.remove('hidden');
  showLevelUpModal(data);
}

/** @param {Object} data */
function handleLevelUpComplete(data) {
  if (!gameState.player?.stats) return;
  const stats = gameState.player.stats;
  stats.level = data.level;
  stats.max_hp = data.new_max_hp;
  stats.hp = data.new_hp || data.new_max_hp;
  if (data.stat_changes) {
    for (const [key, val] of Object.entries(data.stat_changes)) {
      stats[key] = val;
    }
  }
  updateStatsPanel();

  // Celebration chat message
  const changes = data.stat_changes
    ? Object.entries(data.stat_changes)
        .map(([k, _v]) => `${k.substring(0, 3).toUpperCase()}+1`)
        .join(', ')
    : '';
  appendChat(`You reached Level ${data.level}! ${changes}`, 'system');

  // Clear pending
  gameState.pendingLevelUp = null;
  gameState.levelUpSelections = [];
  const $badge = document.getElementById('levelup-badge');
  if ($badge) $badge.classList.add('hidden');
  // Hide modal if open
  const $overlay = document.getElementById('levelup-overlay');
  if ($overlay) $overlay.classList.add('hidden');
  // Note: if another level-up is queued, server sends a new level_up_available immediately
}

/** @param {Object} data */
function showLevelUpModal(data) {
  const $overlay = document.getElementById('levelup-overlay');
  const $grid = document.getElementById('levelup-stats-grid');
  const $feedback = document.getElementById('levelup-feedback');
  const $confirm = /** @type {HTMLButtonElement} */ (document.getElementById('levelup-confirm-btn'));
  if (!$overlay || !$grid || !$feedback || !$confirm) return;

  gameState.levelUpSelections = [];
  $feedback.textContent = '';
  $confirm.disabled = true;
  $grid.innerHTML = '';

  const serverEffects = data.stat_effects || {};
  const statInfo = {
    strength: { label: 'STR', effect: serverEffects.strength || 'physical dmg per point' },
    dexterity: { label: 'DEX', effect: serverEffects.dexterity || 'incoming dmg reduction per point' },
    constitution: { label: 'CON', effect: serverEffects.constitution || 'max HP per point' },
    intelligence: { label: 'INT', effect: serverEffects.intelligence || 'magic dmg per point' },
    wisdom: { label: 'WIS', effect: serverEffects.wisdom || 'healing per point' },
    charisma: { label: 'CHA', effect: serverEffects.charisma || 'XP per point' },
  };

  const currentStats = data.current_stats || {};
  const cap = data.stat_cap || 10;

  for (const [key, info] of Object.entries(statInfo)) {
    const val = currentStats[key] ?? 1;
    const atCap = val >= cap;

    const btn = document.createElement('div');
    btn.className = `levelup-stat-btn${atCap ? ' disabled' : ''}`;
    btn.dataset.stat = key;

    const nameEl = document.createElement('div');
    nameEl.className = 'levelup-stat-name';
    nameEl.textContent = info.label;
    btn.appendChild(nameEl);

    const changeEl = document.createElement('div');
    changeEl.className = 'levelup-stat-change';
    changeEl.textContent = atCap ? `${val} (MAX)` : `${val} \u2192 ${val + 1}`;
    btn.appendChild(changeEl);

    const effectEl = document.createElement('div');
    effectEl.className = 'levelup-stat-effect';
    effectEl.textContent = `+1 ${info.effect}`;
    btn.appendChild(effectEl);

    if (!atCap) {
      btn.addEventListener('click', () => {
        toggleLevelUpStat(key, btn, $feedback, $confirm);
      });
    }

    $grid.appendChild(btn);
  }

  $overlay.classList.remove('hidden');
}

/**
 * @param {string} stat
 * @param {HTMLElement} btn
 * @param {HTMLElement} $feedback
 * @param {HTMLButtonElement} $confirm
 */
function toggleLevelUpStat(stat, btn, $feedback, $confirm) {
  const idx = gameState.levelUpSelections.indexOf(stat);
  if (idx >= 0) {
    gameState.levelUpSelections.splice(idx, 1);
    btn.classList.remove('selected');
  } else if (gameState.levelUpSelections.length >= (gameState.pendingLevelUp?.choose_stats ?? 3)) {
    $feedback.textContent = `Max ${gameState.pendingLevelUp?.choose_stats ?? 3} selected`;
    return;
  } else {
    gameState.levelUpSelections.push(stat);
    btn.classList.add('selected');
  }
  $feedback.textContent = '';
  $confirm.disabled = gameState.levelUpSelections.length === 0;
}

// =========================================================================
// Move Error
// =========================================================================

/** @param {string} text */
function showMoveError(text) {
  $moveError.textContent = text;
  $moveError.classList.remove('hidden');
  if (moveErrorTimer) clearTimeout(moveErrorTimer);
  moveErrorTimer = window.setTimeout(() => {
    $moveError.classList.add('hidden');
  }, 2000);
}

// =========================================================================
// Message Log
// =========================================================================

/**
 * @param {'sent'|'recv'|'unknown'} direction
 * @param {Object} data
 */
function logMessage(direction, data) {
  const time = new Date().toLocaleTimeString();
  const div = document.createElement('div');
  div.className = 'log-entry';

  let cls = 'log-system';
  if (direction === 'sent') cls = 'log-sent';
  else if (data.type === 'error') cls = 'log-error';
  else if (data.type?.startsWith('combat')) cls = 'log-combat';
  else if (data.type === 'chat') cls = 'log-chat';
  else if (direction === 'unknown') cls = 'log-unknown';

  const prefix = direction === 'sent' ? 'SENT: ' : direction === 'unknown' ? 'UNKNOWN: ' : '';
  div.innerHTML = `<span class="log-time">${time}</span> <span class="${cls}">${prefix}${JSON.stringify(data)}</span>`;
  $messageLog.appendChild(div);

  // Trim old entries
  while ($messageLog.children.length > LOG_MAX) {
    $messageLog.removeChild($messageLog.firstChild);
  }

  $messageLog.scrollTop = $messageLog.scrollHeight;
}

// Toggle message log
document.getElementById('msglog-toggle')?.addEventListener('click', () => {
  $messageLog.classList.toggle('collapsed');
  const icon = document.querySelector('.toggle-icon');
  icon?.classList.toggle('open');
});

// =========================================================================
// Auth Form Wiring
// =========================================================================

document.getElementById('register-form')?.addEventListener('submit', (e) => {
  e.preventDefault();
  const username = /** @type {HTMLInputElement} */ (document.getElementById('reg-username')).value.trim();
  const password = /** @type {HTMLInputElement} */ (document.getElementById('reg-password')).value;
  $authError.textContent = '';
  $authMessage.textContent = '';
  serverShuttingDown = false;
  gameState.credentials = { username, password };
  gameState.pendingAction = 'register';

  if (!gameState.ws || gameState.ws.readyState !== WebSocket.OPEN) {
    connectWebSocket();
  } else {
    sendAction('register', { username, password });
  }
});

document.getElementById('login-form')?.addEventListener('submit', (e) => {
  e.preventDefault();
  const username = /** @type {HTMLInputElement} */ (document.getElementById('login-username')).value.trim();
  const password = /** @type {HTMLInputElement} */ (document.getElementById('login-password')).value;
  $authError.textContent = '';
  $authMessage.textContent = '';
  serverShuttingDown = false;
  gameState.credentials = { username, password };
  gameState.pendingAction = 'login';

  // Establish new WebSocket if needed (e.g., after permanent disconnect)
  if (!gameState.ws || gameState.ws.readyState !== WebSocket.OPEN) {
    connectWebSocket();
  } else {
    sendAction('login', { username, password });
  }
});

// =========================================================================
// Level-Up Modal Wiring
// =========================================================================

document.getElementById('levelup-confirm-btn')?.addEventListener('click', () => {
  if (gameState.levelUpSelections.length > 0) {
    sendAction('level_up', { stats: gameState.levelUpSelections });
    const $overlay = document.getElementById('levelup-overlay');
    if ($overlay) $overlay.classList.add('hidden');
  }
});

document.getElementById('levelup-close-btn')?.addEventListener('click', () => {
  const $overlay = document.getElementById('levelup-overlay');
  if ($overlay) $overlay.classList.add('hidden');
});

document.getElementById('levelup-badge')?.addEventListener('click', () => {
  if (gameState.pendingLevelUp) {
    showLevelUpModal(gameState.pendingLevelUp);
  }
});

document.getElementById('stats-toggle-btn')?.addEventListener('click', () => {
  toggleStatsPanel();
});

// =========================================================================
// Init
// =========================================================================

connectWebSocket();
