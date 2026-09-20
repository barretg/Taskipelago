import { ArchipelagoClient } from '../archipelago.js';
import { $ } from '../shared/dom.js';

export const ap = new ArchipelagoClient();

export const state = {
  connState: 'disconnected', // 'disconnected' | 'connecting' | 'connected'

  // Captured at connect; every storage key uses these, not the live inputs
  serverAddr: '',
  slotName: '',
  seedName: '',

  // Slot data
  tasks: [],
  items: [],
  taskPrereqs: [],
  itemPrereqs: [],
  lockPrereqs: false,
  hideUnreachable: true,
  goalExpression: '',
  goalRegionReqs: [],
  baseRewardId: null,
  baseCompleteId: null,
  baseItemId: null,
  baseTokenId: null,
  deathLinkPool: [],
  deathLinkWeights: [],
  deathLinkAmnesty: 0,
  deathLinkEnabled: false,
  deathLinkLockTasks: false,   // v1.1 F3 (slot_data death_link_lock_tasks)
  sentItemNames: [],
  sentPlayerNames: [],
  taskRewardPreviews: 0,
  progressiveGroups: [],
  progressiveGroupColors: [],  // v1.1 F6, parallel to progressiveGroups
  groupTypes: [],              // parallel to progressiveGroups; missing = progressive
  itemFillers: null,           // v1.1 F7, expanded item_fillers; null for older seeds
  rewardProgressiveGroup: [],
  taskProgressiveReqs: [],
  taskCostAmounts: [],
  itemConsumable: [],
  regions: [],
  regionColors: [],
  taskRegion: [],
  taskRegionReqs: [],
  taskDescriptions: [],
  bingoMode: false,
  bingoDimX: 5,
  bingoDimY: 5,
  bingoal: 3,

  // Tasclickpelago (clicker mode). Absent slot_data keys leave clickerMode off,
  // so an older seed behaves exactly as before.
  clickerMode: false,
  taskActivations: [],         // ints, parallel to tasks
  taskManual: [],              // bools, parallel to tasks: a normal task row, never clickable
  // Every grant kind carries a target, so each entry is a list of resolved
  // specs. A pre-targeting seed sends one bare value per item, which
  // connection.js normalizes to a single '*' spec.
  itemProduction: [],          // parallel to items: resolved target specs
  itemClickPower: [],          // parallel to items: resolved target specs
  itemProductionMult: [],      // parallel to items: resolved target specs
  itemClickMult: [],           // parallel to items: resolved target specs
  itemOfflineMult: [],         // parallel to items: resolved target specs
  regionDistributed: {},       // region name -> bool
  clickerDistributeGlobal: false,
  clickerOffline: true,
  clickerOfflineRate: 1,       // number | AST
  regionOfflineRate: {},       // region name -> number | AST
  clickerOfflineCapHours: 8,

  // Runtime
  checkedLocations: new Set(), // combined server + optimistic
  pendingLocations: new Set(), // optimistic (not yet confirmed by server)
  taskPurchases: {},           // taskIdx -> {name: amount}
  clickerProgress: {},         // taskIdx -> float activations accrued
  clickerLastTick: 0,          // ms epoch of the last accrual write
  manualConsumptions: {},      // name -> count of manually consumed units
  hintRequestedIndices: new Set(), // task indices already hinted this session
  notifications: [],           // [{kind, title, body, createdAt}]
  sentGoal: false,
  deathLinkAmnestyLeft: 0,
  deathLinkQueue: {},          // v1.1 F3: {id: {id, task, source, cause, time}}

  // Notify dedup (mirrors legacy _last_item_index logic)
  lastItemIndex: 0,
  notifyIndexLoaded: false,
  notifyReady: false,          // server notify key retrieved (or fallback timer fired)
  notifyQueue: [],             // ReceivedItems packets held until notifyReady
  serverNotifyIndex: null,     // taskipelago_notify value from the server

  // UI toggles (enforce locally and hide completed persist in taskipelago_ui)
  localEnforce: false,
  showLocked: false,
  hideCompleted: false,
};

export const CLIENT_ID = crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2);

export const MAX_NOTIFICATIONS = 200;

export const els = {
  serverInput:   $('server-input'),
  slotInput:     $('slot-input'),
  passInput:     $('pass-input'),
  connectBtn:    $('connect-btn'),
  deathLinkBtn:  $('deathlink-send-btn'),
  connectStatus: $('connect-status'),

  enforceHeader: $('enforce-header'),
  enforceCb:     $('enforce-cb'),
  showLockedHeader: $('show-locked-header'),
  showLockedWrapper: $('show-locked-wrapper'),
  showLockedCb:  $('show-locked-cb'),
  hideCompletedCb: $('hide-completed-cb'),

  tasksList:     $('tasks-list'),
  bingoSection:  $('bingo-section'),
  bingoCounter:  $('bingo-counter'),
  bingoGrid:     $('bingo-grid'),

  clickerSection: $('clicker-section'),
  clickerHeader:  $('clicker-header'),
  clickerGrid:    $('clicker-grid'),
  clickerManual:     $('clicker-manual'),
  clickerManualList: $('clicker-manual-list'),

  notifList:     $('notif-list'),
  clearNotifsBtn:$('clear-notifs-btn'),
  itemsList:     $('items-list'),
  itemsFilterBtn: $('items-filter-btn'),
  dlSoundCb:     $('dl-sound-cb'),
  deathLinkCards: $('deathlink-cards'),
  consumablesList: $('consumables-list'),

  consoleOutput: $('console-output'),
  consoleInput:  $('console-input'),
  consoleSendBtn:$('console-send-btn'),
};
