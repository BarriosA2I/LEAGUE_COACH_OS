export type LogLevel = 'debug' | 'info' | 'warn' | 'error';
const LEVELS: Record<LogLevel, number> = { debug: 0, info: 1, warn: 2, error: 3 };
const currentLevel = (process.env.LOG_LEVEL as LogLevel) || 'info';

function log(level: LogLevel, tag: string, msg: string, data?: unknown) {
  if (LEVELS[level] < LEVELS[currentLevel]) return;
  const entry = { ts: new Date().toISOString(), level, tag, msg, ...(data ? { data } : {}) };
  console.log(JSON.stringify(entry));
}

export const logger = {
  debug: (tag: string, msg: string, data?: unknown) => log('debug', tag, msg, data),
  info: (tag: string, msg: string, data?: unknown) => log('info', tag, msg, data),
  warn: (tag: string, msg: string, data?: unknown) => log('warn', tag, msg, data),
  error: (tag: string, msg: string, data?: unknown) => log('error', tag, msg, data),
};
