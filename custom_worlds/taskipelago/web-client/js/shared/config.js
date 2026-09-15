// Feature flags. The committed config.json holds the hosted defaults; the local
// webhost serves a generated config.json with the same shape (UNIFY 1.1).
// Nothing outside this module may check cfg.mode.

const DEFAULTS = {
  mode: 'hosted',
  version: '',
  communityEndpoint: '',
  features: { insecureWs: false, localStorageService: false },
  launch: null,
  token: null,
};

export const cfg = structuredClone(DEFAULTS);

export async function loadConfig() {
  try {
    const res = await fetch('config.json', { cache: 'no-store' });
    if (res.ok) {
      const data = await res.json();
      Object.assign(cfg, DEFAULTS, data);
      cfg.features = { ...DEFAULTS.features, ...(data.features || {}) };
    }
  } catch (_) { /* keep hosted defaults */ }
  // Dev convenience: a plain http server behaves like local for connections.
  if (location.protocol === 'http:') cfg.features.insecureWs = true;
  return cfg;
}

export function hasFeature(name) {
  return !!cfg.features[name];
}
