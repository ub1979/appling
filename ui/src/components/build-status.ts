export const STATUS_INTERVAL = 5 * 60 * 1000;

// A page-local check, not a background job or a chat notification schedule.
export function watchStatus<T>(read: () => Promise<T>, update: (value: T) => void, failed: () => void) {
  let disposed = false;
  let pending = false;
  const check = async () => {
    if (pending) return;
    pending = true;
    try { const value = await read(); if (!disposed) update(value); }
    catch { if (!disposed) failed(); }
    finally { pending = false; }
  };
  void check();
  const timer = setInterval(() => void check(), STATUS_INTERVAL);
  return () => { disposed = true; clearInterval(timer); };
}
