import { loadConfig } from './shared/config.js';
import { initStorage } from './shared/storage.js';
import { initModal } from './shared/modal.js';
import {
  initConnection, connectTo, startDisconnect, hasServerAddress, getConnectStatus,
} from './play/connection.js';
import { initTasks } from './play/tasks.js';
import { initNotifications } from './play/notifications.js';
import { initConsole } from './console/console.js';
import { renderAll } from './play/render.js';
import { initTooltips } from './shared/tooltip.js';
import { initGenerator } from './generator/generator.js';
import { initBingoGen } from './bingo_gen/bingo_gen.js';

function initTabs() {
  const mainTabs = document.querySelectorAll('#main-tabs .tab-btn');
  mainTabs.forEach(btn => btn.addEventListener('click', () => {
    mainTabs.forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
    document.getElementById(`tab-${btn.dataset.tab}`)?.classList.add('active');
  }));

  const subTabs = document.querySelectorAll('.sub-tabs .tab-btn');
  subTabs.forEach(btn => btn.addEventListener('click', () => {
    subTabs.forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    document.querySelectorAll('.subtab-pane').forEach(p => p.classList.remove('active'));
    document.getElementById(`subtab-${btn.dataset.subtab}`)?.classList.add('active');
  }));
}

async function boot() {
  await loadConfig();
  await initStorage();
  initTabs();
  initModal();
  initConnection();
  initTasks();
  initNotifications();
  initConsole({
    connect: connectTo,
    disconnect: startDisconnect,
    hasAddress: hasServerAddress,
    status: getConnectStatus,
  });
  initTooltips();
  initGenerator();
  initBingoGen();
  renderAll();
}

boot();
