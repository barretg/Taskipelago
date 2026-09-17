import { renderTasks, renderRegionProgress } from './tasks.js';
import { renderNotifications } from './notifications.js';
import { renderItems } from './items.js';
import { renderConsumables } from './consumables.js';

export function renderAll() {
  renderTasks();
  renderRegionProgress();
  renderNotifications();
  renderItems();
  renderConsumables();
}
