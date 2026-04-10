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
};

let reconnectAttempts = 0;
const MAX_RECONNECT = 5;
/** @type {number|null} */
let reconnectTimer = null;
let serverShuttingDown = false;
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

    // Auto re-send pending action on reconnect (login or register)
    if (gameState.credentials && gameState.pendingAction) {
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

  // Clear game state (preserve credentials)
  gameState.player = null;
  gameState.room = null;
  gameState.combat = null;
  gameState.inventory = [];
  gameState.pendingAction = null;
  gameState.movePending = false;

  // Clear UI
  $tileGrid.innerHTML = '';
  $chatLog.innerHTML = '';
  $combatOverlay.classList.add('hidden');

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
    logged_out: handleLoggedOut,
    server_shutdown: handleServerShutdown,
    kicked: handleKicked,
    respawn: handleRespawn,
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
  const entityId = `player_${data.player_id}`;
  gameState.player = {
    id: entityId,
    dbId: data.player_id,
    name: data.username,
    x: 0,
    y: 0,
  };
}

/** @param {Object} data */
function handleError(data) {
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
  // Clear credentials to prevent auto-login (unlike kicked which preserves them)
  gameState.credentials = null;
  gameState.player = null;
  gameState.room = null;
  gameState.combat = null;
  gameState.inventory = [];
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
  appendChat(`${prefix}${data.sender}: ${data.message}`, cls || 'chat');
}

/** @param {Object} data */
function handleAnnouncement(data) {
  appendChat(`\u2605 ${data.message}`, 'announcement');
}

/**
 * @param {string} text
 * @param {string} [type]
 */
function appendChat(text, type = 'chat') {
  const div = document.createElement('div');
  div.className = `chat-msg chat-${type}`;
  div.textContent = text;
  $chatLog.appendChild(div);
  $chatLog.scrollTop = $chatLog.scrollHeight;
}

function sendChat() {
  const msg = $chatInput.value.trim();
  if (!msg) return;
  // Intercept /logout command
  if (msg.toLowerCase() === '/logout') {
    sendAction('logout', {});
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
    // Mark mob NPC as dead in room state
    if (gameState.room && gameState.combat && gameState.player) {
      const mobName = gameState.combat.mob?.name;
      if (mobName) {
        const npc = gameState.room.npcs.find(
          (n) => n.name === mobName && n.is_alive &&
            Math.abs(n.x - gameState.player.x) <= 1 &&
            Math.abs(n.y - gameState.player.y) <= 1
        );
        if (npc) npc.is_alive = false;
      }
    }
  } else {
    msg = 'Defeated!';
  }

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
  gameState.combat = null;
  setMode('explore');
  appendChat('You fled from combat.', 'system');
  renderRoom();
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

function updateStatsPanel() {
  if (!gameState.player) return;

  const $name = document.getElementById('player-name');
  const $pos = document.getElementById('player-position');
  const $roomName = document.getElementById('room-name');

  if ($name) $name.textContent = gameState.player.name;
  if ($pos) $pos.textContent = `Position: (${gameState.player.x}, ${gameState.player.y})`;
  if ($roomName && gameState.room) $roomName.textContent = gameState.room.name;

  // HP/Shield from combat
  const $hpSection = document.getElementById('hp-section');
  const $shieldSection = document.getElementById('shield-section');
  const $noStats = document.getElementById('no-stats-text');

  if (gameState.combat && gameState.player) {
    const me = gameState.combat.participants.find(
      (/** @type {Object} */ p) => p.entity_id === gameState.player?.id
    );
    if (me) {
      $hpSection?.classList.remove('hidden');
      const $hpBar = /** @type {HTMLElement} */ (document.getElementById('hp-bar'));
      const $hpText = document.getElementById('hp-text');
      const pct = me.max_hp > 0 ? (me.hp / me.max_hp) * 100 : 0;
      if ($hpBar) {
        $hpBar.style.width = `${pct}%`;
        setHpBarColor($hpBar, pct);
      }
      if ($hpText) $hpText.textContent = `${me.hp} / ${me.max_hp}`;

      if (me.shield > 0) {
        $shieldSection?.classList.remove('hidden');
        const $shieldText = document.getElementById('shield-text');
        if ($shieldText) $shieldText.textContent = `${me.shield}`;
      } else {
        $shieldSection?.classList.add('hidden');
      }
      $noStats?.classList.add('hidden');
      return;
    }
  }

  $hpSection?.classList.add('hidden');
  $shieldSection?.classList.add('hidden');
  $noStats?.classList.remove('hidden');
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
// Init
// =========================================================================

connectWebSocket();
