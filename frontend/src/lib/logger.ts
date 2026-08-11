/**
 * Development logger.
 *
 * The only sanctioned place in the app that touches `console`. Silenced in
 * production builds so shipped code never leaks debug output.
 */
const enabled = import.meta.env.DEV;

type LogArg = string | number | boolean | null | undefined | Error | object;

export const logger = {
  debug(message: string, ...args: LogArg[]) {
    if (enabled) console.debug(`[sensei] ${message}`, ...args);
  },
  info(message: string, ...args: LogArg[]) {
    if (enabled) console.info(`[sensei] ${message}`, ...args);
  },
  warn(message: string, ...args: LogArg[]) {
    if (enabled) console.warn(`[sensei] ${message}`, ...args);
  },
  error(message: string, ...args: LogArg[]) {
    if (enabled) console.error(`[sensei] ${message}`, ...args);
  },
};
