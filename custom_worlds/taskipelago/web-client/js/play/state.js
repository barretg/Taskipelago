import { ArchipelagoClient } from '../archipelago.js';
import { $ } from '../shared/dom.js';

export const ap = new ArchipelagoClient();

export const state = {
  connState: 'disconnected', // 'disconnected' | 'connecting' | 'connected'

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
  sentItemNames: [],
  sentPlayerNames: [],
  taskRewardPreviews: 0,
  progressiveGroups: [],
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

  // Runtime
  checkedLocations: new Set(), // combined server + optimistic
  pendingLocations: new Set(), // optimistic (not yet confirmed by server)
  taskPurchases: {},           // taskIdx -> {name: amount}
  manualConsumptions: {},      // name -> count of manually consumed units
  hintRequestedIndices: new Set(), // task indices already hinted this session
  notifications: [],           // [{kind, title, body, createdAt}]
  sentGoal: false,
  deathLinkAmnestyLeft: 0,

  // Notify dedup (mirrors legacy _last_item_index logic)
  lastItemIndex: 0,
  notifyIndexLoaded: false,
  pendingNotifyIndex: null,

  // UI toggles
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

  notifList:     $('notif-list'),
  clearNotifsBtn:$('clear-notifs-btn'),
  itemsList:     $('items-list'),
  consumablesList: $('consumables-list'),

  consoleOutput: $('console-output'),
  consoleInput:  $('console-input'),
  consoleSendBtn:$('console-send-btn'),
};
