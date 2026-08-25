# CHANGELOG

```txt
Summary
  1. document grouping follow 'SemVer2.0' protocol
  2. use 'PATCH' as a minimum granularity
  3. use concise descriptions
  4. type: feat \ fix \ update \ perf \ remove \ docs \ chore
  5. version timestamp follow the yyyy.MM.dd format
```

## 1.1.3 [2026.08.24]

- fix: save refreshed Firebase tokens back to IndexedDB (prevents session loss from refresh-token rotation)
- feat: silent re-login via Chrome OAuth grant when Firebase session is unrecoverable
- feat: friendly "session expired — please log in again" message on auth failures
- fix: UI now reflects logged-out state immediately when session dies
- fix: pinned extension ID for stable local/dev builds

## 0.0.0 [2026.08.04]

- feat: initial
- feat: generator by ![create-chrome-ext](https://github.com/guocaoyi/create-chrome-ext)
