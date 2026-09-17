const DRIVE_FOLDER_ID = '1-zjxfR_OHQD4OgOISBVcO6GXEZtm3-B7gUGFvkkLVSokfjBb7xtKvgoQrSk-sBrE1ycFzLgA';
const MAX_FILE_BYTES = 262144;
const NAME_PATTERN = /^[A-Za-z0-9-]+$/;
const VERSION_PATTERN = /^\d+\.\d+\.\d+$/;

// GET routes (UNIFY 5.6). The web client cannot scrape the Drive folder view
// (no CORS), so it reads the community list through this web app instead:
//   ?action=list          JSON [{file_id, filename, slot, author, version}]
//   ?action=file&id=ID    JSON {file_id, filename, text}; ids outside the folder are rejected
//   (no action)           the submission page
// Errors come back as JSON {error: "..."} (ContentService cannot set a status code).
function doGet(e) {
  const params = (e && e.parameter) || {};
  if (params.action === 'list') {
    return respond_(function () { return listCommunityYamls_(); });
  }
  if (params.action === 'file') {
    return respond_(function () { return readCommunityYaml_(params.id); });
  }
  return HtmlService.createHtmlOutputFromFile('Index')
    .setTitle('Taskipelago Community YAML Submission')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

function respond_(fn) {
  let body;
  try {
    body = fn();
  } catch (err) {
    body = { error: String((err && err.message) || err) };
  }
  return ContentService.createTextOutput(JSON.stringify(body)).setMimeType(ContentService.MimeType.JSON);
}

// Port of the legacy client's _parse_community_yaml_filename:
// SLOTNAME_AUTHORNAME_VERSION-WITH-DASHES.yaml -> {slot, author, version} or null.
function parseCommunityYamlFilename_(filename) {
  const lower = filename.toLowerCase();
  let base;
  if (lower.slice(-5) === '.yaml') base = filename.slice(0, -5);
  else if (lower.slice(-4) === '.yml') base = filename.slice(0, -4);
  else return null;
  const parts = base.split('_');
  if (parts.length !== 3) return null;
  const slot = parts[0].trim();
  const author = parts[1].trim();
  const versionDashed = parts[2].trim();
  if (!slot || !author || !versionDashed) return null;
  return { slot: slot, author: author, version: versionDashed.replace(/-/g, '.') };
}

function listCommunityYamls_() {
  const files = DriveApp.getFolderById(DRIVE_FOLDER_ID).getFiles();
  const entries = [];
  while (files.hasNext()) {
    const file = files.next();
    if (file.isTrashed()) continue;
    const filename = file.getName();
    const parsed = parseCommunityYamlFilename_(filename);
    if (!parsed) continue;
    entries.push({
      file_id: file.getId(), filename: filename,
      slot: parsed.slot, author: parsed.author, version: parsed.version,
    });
  }
  entries.sort(function (a, b) {
    const ka = [a.slot.toLowerCase(), a.author.toLowerCase()];
    const kb = [b.slot.toLowerCase(), b.author.toLowerCase()];
    if (ka[0] !== kb[0]) return ka[0] < kb[0] ? -1 : 1;
    if (ka[1] !== kb[1]) return ka[1] < kb[1] ? -1 : 1;
    return 0;
  });
  return entries;
}

function readCommunityYaml_(fileId) {
  if (!fileId || !/^[-\w]{10,}$/.test(fileId)) throw new Error('Unknown community YAML.');
  let file;
  try {
    file = DriveApp.getFileById(fileId);
  } catch (err) {
    throw new Error('Unknown community YAML.');
  }
  let inFolder = false;
  const parents = file.getParents();
  while (parents.hasNext()) {
    if (parents.next().getId() === DRIVE_FOLDER_ID) inFolder = true;
  }
  if (!inFolder || file.isTrashed() || !parseCommunityYamlFilename_(file.getName())) {
    throw new Error('Unknown community YAML.');
  }
  if (file.getSize() > MAX_FILE_BYTES) throw new Error('Community YAML is too large.');
  return { file_id: fileId, filename: file.getName(), text: file.getBlob().getDataAsString('UTF-8') };
}

function submitYaml(slotName, authorName, version, base64Data, originalFileName) {
  slotName = (slotName || '').trim();
  authorName = (authorName || '').trim();
  version = (version || '').trim();

  if (!NAME_PATTERN.test(slotName)) {
    throw new Error('Slot name may only contain letters, numbers, and hyphens (no spaces or underscores).');
  }
  if (!NAME_PATTERN.test(authorName)) {
    throw new Error('Author name may only contain letters, numbers, and hyphens (no spaces or underscores).');
  }
  if (!VERSION_PATTERN.test(version)) {
    throw new Error('Version must look like 1.0.0');
  }
  if (!/\.ya?ml$/i.test(originalFileName || '')) {
    throw new Error('File must be a .yaml or .yml file.');
  }

  const bytes = Utilities.base64Decode(base64Data);
  if (bytes.length === 0) {
    throw new Error('Uploaded file is empty.');
  }
  if (bytes.length > MAX_FILE_BYTES) {
    throw new Error('File is too large (limit ' + Math.floor(MAX_FILE_BYTES / 1024) + ' KB).');
  }

  const text = Utilities.newBlob(bytes).getDataAsString('UTF-8');
  if (text.indexOf(':') === -1) {
    throw new Error('File does not look like valid YAML.');
  }

  const fileName = slotName + '_' + authorName + '_' + version.replace(/\./g, '-') + '.yaml';
  const folder = DriveApp.getFolderById(DRIVE_FOLDER_ID);

  const existing = folder.getFilesByName(fileName);
  while (existing.hasNext()) {
    existing.next().setTrashed(true);
  }

  const blob = Utilities.newBlob(bytes, 'application/x-yaml', fileName);
  folder.createFile(blob);

  return fileName;
}
