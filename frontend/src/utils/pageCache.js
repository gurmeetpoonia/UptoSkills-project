// Tiny in-memory cache so a page shows its last data instantly when you come back to it,
// then refreshes quietly in the background (stale-while-revalidate). Cleared on full reload.
const store = new Map();

export const pageCache = {
  get: (key) => store.get(key),
  set: (key, value) => {
    store.set(key, value);
    return value;
  },
  clear: (key) => (key ? store.delete(key) : store.clear()),
};
